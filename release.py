from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

PROJECT_NAME = "bikeshed"
TEST_PYPI_URL = "https://test.pypi.org/legacy/"
SEMVER_FILE = Path("bikeshed/semver.txt")
VERSION_INFO_FILE = Path("bikeshed/spec-data/readonly/bikeshed-version.txt")
SECRETS_FILE = Path("secrets.json")
BUILD_DIRS = ("build", "dist")


class ReleaseError(Exception):
    """Expected, user-facing failure during release preflight or execution."""


def parseArgs(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Releases a new Bikeshed version to pypi.org.")
    parser.add_argument(
        "bump",
        nargs="?",
        choices=["break", "feature", "bugfix"],
        help="Which type of release is this? (Optional when --version is specified.)",
    )
    parser.add_argument(
        "--test",
        dest="test",
        action="store_true",
        help="Upload to test.pypi.org instead (rolls back version files and skips git commit/tag/push).",
    )
    parser.add_argument(
        "--version",
        dest="version",
        nargs=3,
        type=int,
        metavar=("MAJOR", "MINOR", "PATCH"),
        help="Explicitly set the new version instead of bumping bikeshed/semver.txt.",
    )
    parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Run checks and build/validate artifacts without uploading or pushing to git.",
    )
    parser.add_argument(
        "--skip-lint",
        dest="skip_lint",
        action="store_true",
        help="Skip running ./lint before building (still runs check-manifest).",
    )
    parser.add_argument(
        "--no-tag",
        dest="no_tag",
        action="store_true",
        help="Skip creating and pushing the v<version> git tag.",
    )
    options = parser.parse_args(argv)
    if options.version is None and options.bump is None:
        parser.error("either a bump type (break, feature, bugfix) or --version is required.")
    return options


def createRelease(argv: Sequence[str] | None = None) -> None:
    options = parseArgs(argv)

    if not inProjectRoot(PROJECT_NAME):
        msg = "Run this command from inside the bikeshed project root folder."
        raise ReleaseError(msg)

    projectRoot = Path.cwd()
    semverPath = projectRoot / SEMVER_FILE
    versionInfoPath = projectRoot / VERSION_INFO_FILE
    secretsPath = projectRoot / SECRETS_FILE

    if not semverPath.is_file():
        msg = f"Could not find {SEMVER_FILE} in {projectRoot}."
        raise ReleaseError(msg)

    dirtyFiles = getDirtyFiles()
    if dirtyFiles:
        dirtySummary = "\n".join(f"  {line}" for line in dirtyFiles)
        if options.dry_run:
            print(f"Warning: Working tree is dirty (continuing because --dry-run was passed):\n{dirtySummary}")
        else:
            msg = f"Working tree is dirty. Finish committing files or stash, then try again.\n{dirtySummary}"
            raise ReleaseError(msg)

    originalSemverContent = semverPath.read_text(encoding="utf-8")
    currentVersion = originalSemverContent.strip()
    semver = parseSemver(currentVersion)

    if options.version is not None:
        major, minor, patch = options.version
        if major < 0 or minor < 0 or patch < 0:
            msg = "Invalid --version: version components must be non-negative."
            raise ReleaseError(msg)
        newVersion = f"{major}.{minor}.{patch}"
        releaseKind = "explicit"
    else:
        newVersion = bumpSemver(semver, options.bump)
        releaseKind = options.bump
    tagName = f"v{newVersion}"

    if not options.test and not options.dry_run and not options.no_tag and gitTagExists(tagName):
        msg = f"Git tag {tagName} already exists."
        raise ReleaseError(msg)

    buildCmd = findToolCommand("build", "pyproject-build")
    twineCmd = findToolCommand("twine", "twine")
    checkManifestCmd = findToolCommand("check_manifest", "check-manifest")
    missingTools: list[str] = []
    if buildCmd is None:
        missingTools.append("build")
    if twineCmd is None:
        missingTools.append("twine")
    if checkManifestCmd is None:
        missingTools.append("check-manifest")

    if missingTools and (not options.dry_run or buildCmd is None or checkManifestCmd is None):
        packages = " ".join(missingTools)
        msg = "\n".join(
            [
                f"Missing required release tool(s): {', '.join(missingTools)}",
                f"Active Python: {sys.executable}",
                "Install them with:",
                f"  python -m pip install {packages}",
                "Or install all dev dependencies with:",
                "  python -m pip install -r requirements-dev.txt",
            ],
        )
        raise ReleaseError(msg)

    token, tokenFromEnv = loadPyPiToken(secretsPath, isTest=options.test, required=not options.dry_run)

    targetRepo = "test.pypi.org" if options.test else "pypi.org"
    modeSuffix = " (dry run)" if options.dry_run else ""
    print(f"Preparing {releaseKind} release for {targetRepo}{modeSuffix}: {currentVersion} -> {newVersion}")

    if not options.skip_lint:
        lintScript = projectRoot / "lint"
        if not lintScript.is_file():
            msg = "Could not find ./lint script. Pass --skip-lint to bypass."
            raise ReleaseError(msg)
        runCommand(["sh", str(lintScript)], "Running ./lint")
        if not options.dry_run:
            postLintDirty = getDirtyFiles()
            if postLintDirty:
                dirtySummary = "\n".join(f"  {line}" for line in postLintDirty)
                msg = f"./lint modified the working tree. Commit those changes before releasing:\n{dirtySummary}"
                raise ReleaseError(msg)
    else:
        assert checkManifestCmd is not None
        runCommand([*checkManifestCmd, "--no-build-isolation"], "Checking MANIFEST.in")

    bikeshedVersion = getBikeshedVersionString()
    originalVersionInfoContent = versionInfoPath.read_text(encoding="utf-8") if versionInfoPath.is_file() else None

    print(f"Bumping {SEMVER_FILE} to {newVersion}...")
    versionInfoPath.parent.mkdir(parents=True, exist_ok=True)
    versionInfoPath.write_text(bikeshedVersion, encoding="utf-8")
    semverPath.write_text(newVersion, encoding="utf-8")

    keepVersionBump = False
    try:
        cleanBuildArtifacts(projectRoot)
        assert buildCmd is not None
        runCommand(buildCmd, "Building sdist and wheel")

        distDir = projectRoot / "dist"
        distFiles = sorted(distDir.iterdir()) if distDir.is_dir() else []
        if not distFiles:
            msg = "Build succeeded, but no distribution files were created in dist/."
            raise ReleaseError(msg)

        if twineCmd is not None:
            runCommand(
                [*twineCmd, "check", *(str(path) for path in distFiles)],
                "Checking built distributions with twine",
            )
        else:
            print("Warning: twine is not installed; skipping `twine check`.")

        if options.dry_run:
            print("\nDry run succeeded. Built artifacts:")
            for path in distFiles:
                print(f"  - {path.relative_to(projectRoot)}")
            print(f"Would write version info: {bikeshedVersion}")
            print(f"Would upload {newVersion} to {targetRepo}.")
            if options.test:
                print("Would roll back version files and skip git commit/tag/push (--test).")
            else:
                print(f"Would commit {SEMVER_FILE} and {VERSION_INFO_FILE} ('Bump semver to {newVersion}') and push.")
                if not options.no_tag:
                    print(f"Would create and push annotated tag {tagName}.")
            return

        assert twineCmd is not None
        assert token is not None
        uploadCmd = [*twineCmd, "upload"]
        if options.test:
            uploadCmd.extend(["--repository-url", TEST_PYPI_URL])
        uploadCmd.extend(str(path) for path in distFiles)

        uploadEnv = os.environ.copy()
        if tokenFromEnv:
            uploadEnv.setdefault("TWINE_USERNAME", "__token__")
        else:
            uploadEnv["TWINE_USERNAME"] = "__token__"
        uploadEnv["TWINE_PASSWORD"] = token

        runCommand(uploadCmd, f"Uploading {newVersion} to {targetRepo}", env=uploadEnv)

        if options.test:
            print(f"Uploaded {newVersion} to {targetRepo}. Rolling back version files and skipping git commit/push.")
            return

        keepVersionBump = True
    finally:
        cleanBuildArtifacts(projectRoot)
        if not keepVersionBump:
            semverPath.write_text(originalSemverContent, encoding="utf-8")
            if originalVersionInfoContent is not None:
                versionInfoPath.write_text(originalVersionInfoContent, encoding="utf-8")
            elif versionInfoPath.exists():
                versionInfoPath.unlink()

    versionFiles = [str(SEMVER_FILE), str(VERSION_INFO_FILE)]
    try:
        runCommand(["git", "add", "--", *versionFiles], "Staging version files")
        runCommand(
            ["git", "commit", "-m", f"Bump semver to {newVersion}", "--", *versionFiles],
            "Committing version bump",
        )
        if not options.no_tag:
            runCommand(
                ["git", "tag", "-a", tagName, "-m", f"Release {newVersion}"],
                f"Tagging {tagName}",
            )
        pushCmd = ["git", "push"] if options.no_tag else ["git", "push", "--follow-tags"]
        runCommand(pushCmd, "Pushing release commit")
    except subprocess.CalledProcessError as exc:
        msg = "\n".join(
            [
                f"Version {newVersion} was ALREADY uploaded to {targetRepo}, "
                + f"but the git step failed (exit code {exc.returncode}).",
                "Do NOT re-upload; finish committing/tagging/pushing manually.",
            ],
        )
        raise ReleaseError(msg) from exc

    print(f"Successfully released {newVersion}!")


def inProjectRoot(projectName: str) -> bool:
    """Checks whether the cwd is the root of the expected git repository."""
    try:
        topLevel = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        if not topLevel or Path(topLevel).resolve() != Path.cwd().resolve():
            return False
        remotes = subprocess.run(
            ["git", "remote", "-v"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return False
    return projectName in remotes


def getDirtyFiles() -> list[str]:
    """Returns git status --porcelain lines for any uncommitted or untracked changes."""
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in result.stdout.splitlines() if line.strip()]


def getBikeshedVersionString() -> str:
    return subprocess.run(
        ["git", "log", "-1", "--format=Bikeshed version %h, updated %cd"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def gitTagExists(tagName: str) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"refs/tags/{tagName}"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def parseSemver(s: str) -> tuple[int, int, int]:
    parts = s.strip().split(".")
    if len(parts) != 3:
        msg = f"Invalid semver '{s.strip()}': expected MAJOR.MINOR.PATCH."
        raise ReleaseError(msg)
    try:
        major, minor, patch = (int(part) for part in parts)
    except ValueError as exc:
        msg = f"Invalid semver '{s.strip()}': version components must be integers."
        raise ReleaseError(msg) from exc
    if major < 0 or minor < 0 or patch < 0:
        msg = f"Invalid semver '{s.strip()}': version components must be non-negative."
        raise ReleaseError(msg)
    return (major, minor, patch)


def bumpSemver(semver: tuple[int, int, int], bumpType: str) -> str:
    major, minor, patch = semver
    if bumpType == "break":
        return f"{major + 1}.0.0"
    if bumpType == "feature":
        return f"{major}.{minor + 1}.0"
    if bumpType == "bugfix":
        return f"{major}.{minor}.{patch + 1}"
    msg = f"Unknown bump type: {bumpType}"
    raise ReleaseError(msg)


def findToolCommand(moduleName: str, executableName: str) -> list[str] | None:
    """Resolve a Python CLI tool, preferring `sys.executable -m <module>` over PATH shims."""
    if importlib.util.find_spec(moduleName) is not None:
        return [sys.executable, "-m", moduleName]
    exePath = shutil.which(executableName)
    if exePath is None:
        return None
    # Verify the executable actually runs; managers like pyenv install shims
    # for binaries present in other virtualenvs that fail at runtime.
    try:
        result = subprocess.run(
            [exePath, "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if result.returncode == 0:
        return [exePath]
    return None


def loadPyPiToken(secretsPath: Path, isTest: bool, required: bool) -> tuple[str | None, bool]:
    secretKey = "test.pypi.org release key" if isTest else "pypi.org release key"
    if secretsPath.is_file():
        try:
            rawData = json.loads(secretsPath.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            msg = f"Error loading {secretsPath.name}: {exc}"
            raise ReleaseError(msg) from exc
        if not isinstance(rawData, dict):
            msg = f"Invalid {secretsPath.name}: expected a JSON object."
            raise ReleaseError(msg)
        token = rawData.get(secretKey)
        if isinstance(token, str) and token.strip():
            return (token.strip(), False)
        if required:
            msg = "\n".join(
                [
                    f"Missing or empty '{secretKey}' in {secretsPath.name}.",
                    "Expected format:",
                    '  {"pypi.org release key": "pypi-...", "test.pypi.org release key": "pypi-..."}',
                ],
            )
            raise ReleaseError(msg)
        print(f"Warning: '{secretKey}' not found in {secretsPath.name} (required for actual upload).")
        return (None, False)

    envToken = os.environ.get("TWINE_PASSWORD", "").strip()
    if envToken:
        return (envToken, True)

    if required:
        msg = "\n".join(
            [
                f"Could not find {secretsPath.name} (and TWINE_PASSWORD is not set).",
                f"Create {secretsPath.name} with:",
                f'  {{"{secretKey}": "pypi-..."}}',
            ],
        )
        raise ReleaseError(msg)
    print(f"Warning: {secretsPath.name} not found and TWINE_PASSWORD is not set (required for actual upload).")
    return (None, False)


def cleanBuildArtifacts(projectRoot: Path) -> None:
    for dirName in BUILD_DIRS:
        target = projectRoot / dirName
        if target.exists():
            shutil.rmtree(target)


def runCommand(
    cmd: Sequence[str],
    description: str,
    env: Mapping[str, str] | None = None,
) -> None:
    print(f"==> {description}...")
    subprocess.run(cmd, check=True, env=env)


def main() -> None:
    try:
        createRelease()
    except ReleaseError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError as exc:
        print(f"Error: Command failed with exit code {exc.returncode}.", file=sys.stderr)
        sys.exit(exc.returncode or 1)
    except KeyboardInterrupt:
        print("\nRelease cancelled.", file=sys.stderr)
        sys.exit(130)


if __name__ == "__main__":
    main()

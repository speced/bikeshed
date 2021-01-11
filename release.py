import argparse
import json
import os
import subprocess
import sys


def createRelease():
    if not inBikeshedRoot():
        print("Run this command from inside the bikeshed root folder.")
        sys.exit(1)

    treeDirty = (
        subprocess.check_output("git diff --stat", shell=True).decode(encoding="utf-8")
        != ""
    )
    if treeDirty:
        print(
            "Working tree is dirty. Finish committing files or stash, then try again."
        )
        sys.exit(1)

    with open("semver.txt") as fh:
        currentVersion = fh.read().strip()
        semver = parseSemver(currentVersion)

    try:
        with open("secrets.json") as fh:
            secrets = json.load(fh)
    except OSError:
        print("Error trying to load the secrets.json file.")
        raise

    args = argparse.ArgumentParser(
        description="Releases a new Bikeshed version to pypi.org."
    )
    args.add_argument(
        "bump",
        choices=["break", "feature", "bugfix"],
        help="Which type of release is this?",
    )
    args.add_argument(
        "--test",
        dest="test",
        action="store_true",
        help="Upload to test.pypi.org instead.",
    )
    options, extras = args.parse_known_args()

    # Bump the semver
    if options.bump == "break":
        semver[0] += 1
        semver[1] = 0
        semver[2] = 0
    elif options.bump == "feature":
        semver[1] += 1
        semver[2] = 0
    elif options.bump == "bugfix":
        semver[2] += 1
    newVersion = ".".join(str(x) for x in semver)
    print(f"Bumping to {newVersion}...")

    # Update the hash-version
    bikeshedVersion = (
        subprocess.check_output(
            r"git log -1 --format='Bikeshed version %h, updated %cd'", shell=True
        )
        .decode(encoding="utf-8")
        .strip()
    )
    with open("bikeshed/spec-data/readonly/bikeshed-version.txt", "w") as fh:
        fh.write(bikeshedVersion)

    # Update the semver
    with open("semver.txt", "w") as fh:
        fh.write(newVersion)

    try:
        # Clear out the build artifacts, build it, upload, and clean up again.
        subprocess.call("rm -r build dist", shell=True)
        subprocess.check_call("python setup.py sdist bdist_wheel", shell=True)
        if options.test:
            subprocess.check_call(
                " ".join(
                    [
                        "twine upload",
                        "--repository-url https://test.pypi.org/legacy/",
                        "--username __token__",
                        "--password",
                        secrets["test.pypi.org release key"],
                        "dist/*",
                    ]
                ),
                shell=True,
            )
        else:
            subprocess.check_call(
                " ".join(
                    [
                        "twine upload",
                        "--username __token__",
                        "--password",
                        secrets["pypi.org release key"],
                        "dist/*",
                    ]
                ),
                shell=True,
            )
        subprocess.call("rm -r build dist", shell=True)
    except:
        # roll back the semver
        with open("semver.txt", "w") as fh:
            fh.write(currentVersion)
        raise

    # Clean up with a final commit of the changed version files
    subprocess.check_call(
        "git add semver.txt bikeshed/spec-data/readonly/bikeshed-version.txt",
        shell=True,
    )
    subprocess.check_call(f"git commit -m 'Bump semver to {newVersion}'", shell=True)
    subprocess.check_call("git push", shell=True)


def inBikeshedRoot():
    # Checks whether the cwd is in the Bikeshed root
    try:
        remotes = subprocess.check_output(
            "git remote -v", stderr=subprocess.DEVNULL, shell=True
        ).decode("utf-8")
        if "bikeshed" in remotes:
            return os.path.isdir(".git")
        else:
            return False
    except:
        return False


def parseSemver(s):
    # TODO: replace with the semver module
    return [int(x) for x in s.strip().split(".")]


if __name__ == "__main__":
    createRelease()

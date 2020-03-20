# -*- coding: utf-8 -*-

import argparse
import json
import os
import subprocess
import sys

def createRelease():
    if not inBikeshedRoot():
        print("Run this command from inside the bikeshed root folder.")
        sys.exit(1)

    with open("semver.txt", 'r') as fh:
        currentVersion = fh.read().strip()

    try:
        with open("secrets.json", 'r') as fh:
            secrets = json.load(fh)
    except IOError:
        print("Error trying to load the secrets.json file.")
        raise

    args = argparse.ArgumentParser(description="Releases a new Bikeshed version to pypi.org.")
    args.add_argument("version", help=f"Version number to publish as; currently {currentVersion}")
    args.add_argument("--test", dest="test", action="store_true", help="Upload to test.pypi.org instead.")
    options, extras = args.parse_known_args()

    # Is the semver correct?
    if parseSemver(options.version) <= parseSemver(currentVersion):
        print(f"Specified version ({options.version}) must be greater than current version ({currentVersion}).")
        sys.exit(1)

    # Update the hash-version
    bikeshedVersion = subprocess.check_output(
        r"git log -1 --format='Bikeshed version %h, updated %cd'",
        shell=True).decode(encoding="utf-8").strip()
    with open("bikeshed/spec-data/readonly/bikeshed-version.txt", 'w') as fh:
        fh.write(bikeshedVersion)

    # Update the semver
    with open("semver.txt", 'w') as fh:
        fh.write(options.version)

    try:
        # Clear out the build artifacts, build it, upload, and clean up again.
        subprocess.call("rm -r build dist", shell=True)
        subprocess.check_call("python setup.py sdist bdist_wheel", shell=True)
        if options.test:
            subprocess.check_call(' '.join([
                "twine upload",
                "--repository-url https://test.pypi.org/legacy/",
                "--username __token__",
                "--password", secrets["test.pypi.org release key"],
                "dist/*",
            ]), shell=True)
        else:
            subprocess.check_call(' '.join([
                "twine upload",
                "--username __token__",
                "--password", secrets["pypi.org release key"],
                "dist/*",
            ]), shell=True)
        subprocess.call("rm -r build dist", shell=True)
    except:
        # roll back the semver
        with open("semver.txt", 'w') as fh:
            fh.write(currentVersion)
        raise

    # Clean up with a final commit of the changed version files
    subprocess.check_call("git add semver.txt bikeshed/spec-data/readonly/bikeshed-version.txt", shell=True)
    subprocess.check_call("git commit -m 'bump version info'", shell=True)




def inBikeshedRoot():
    # Checks whether the cwd is in the Bikeshed root
    try:
        remotes = subprocess.check_output(
            "git remote -v",
            stderr=subprocess.DEVNULL,
            shell=True).decode("utf-8")
        if "bikeshed" in remotes:
            return os.path.isdir(".git")
        else:
            return False
    except:
        return False


def parseSemver(s):
    # TODO: replace with the semver module
    return tuple(int(x) for x in s.strip().split("."))


if __name__ == "__main__":
    createRelease()
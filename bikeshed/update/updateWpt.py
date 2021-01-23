import os

import requests

from ..messages import *


def update(path, dryRun=False):
    try:
        say("Downloading web-platform-tests data...")
        response = requests.get("https://wpt.fyi/api/manifest")
        sha = response.headers["x-wpt-sha"]
        jsonData = response.json()
    except Exception as e:
        die("Couldn't download web-platform-tests data.\n{0}", e)
        return

    if "version" not in jsonData:
        die(
            "Can't figure out the WPT data version. Please report this to the maintainer!"
        )
        return

    if jsonData["version"] != 8:
        die(
            "Bikeshed currently only knows how to handle WPT v8 manifest data, but got v{0}. Please report this to the maintainer!",
            jsonData["version"],
        )
        return

    paths = []
    for testType, typePaths in jsonData["items"].items():
        if testType in (
            "crashtest",
            "manual",
            "print-reftest",
            "reftest",
            "testharness",
            "visual",
            "wdspec",
        ):
            collectPaths(paths, typePaths, testType + " ")
    if not dryRun:
        try:
            with open(os.path.join(path, "wpt-tests.txt"), "w", encoding="utf-8") as f:
                f.write(f"sha: {sha}\n")
                for ordered_path in sorted(paths):
                    f.write(ordered_path + "\n")
        except Exception as e:
            die("Couldn't save web-platform-tests data to disk.\n{0}", e)
            return
    say("Success!")


def collectPaths(pathListSoFar, pathTrie, pathPrefix):
    for k, v in pathTrie.items():
        if isinstance(v, dict):
            collectPaths(pathListSoFar, v, f"{pathPrefix}{k}/")
        else:
            pathListSoFar.append(pathPrefix + k)
    return pathListSoFar

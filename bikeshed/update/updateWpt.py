# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals
import io
import json
import os
import urllib2
from contextlib import closing

from ..messages import *

def update(path, dryRun=False):
    try:
        say("Downloading web-platform-tests data...")
        with closing(urllib2.urlopen("https://wpt.fyi/api/manifest")) as fh:
            sha = fh.info().getheader("x-wpt-sha")
            jsonData = json.load(fh, encoding="utf-8")
    except Exception as e:
        die("Couldn't download web-platform-tests data.\n{0}", e)
        return

    if "version" not in jsonData:
        die("Can't figure out the WPT data version. Please report this to the maintainer!")
        return

    if jsonData["version"] != 8:
        die("Bikeshed currently only knows how to handle WPT v8 manifest data, but got v{0}. Please report this to the maintainer!", jsonData["version"])
        return

    paths = []
    for testType, typePaths in jsonData["items"].items():
        if testType not in ("manual", "reftest", "testharness", "wdspec"):
            # Not tests
            continue
        collectPaths(paths, typePaths, testType + " ")

    if not dryRun:
        try:
            with io.open(os.path.join(path, "wpt-tests.txt"), 'w', encoding="utf-8") as f:
                f.write("sha: {0}\n".format(sha))
                for path in sorted(paths):
                    f.write(path+"\n")
        except Exception as e:
            die("Couldn't save web-platform-tests data to disk.\n{0}", e)
            return
    say("Success!")


def collectPaths(pathListSoFar, pathTrie, pathPrefix):
    for k,v in pathTrie.items():
        if isinstance(v, dict):
            collectPaths(pathListSoFar, v, "{0}{1}/".format(pathPrefix, k))
        else:
            pathListSoFar.append(pathPrefix+k)
    return pathListSoFar
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
        with closing(urllib2.urlopen("https://wpt.fyi/api/manifest?sha=latest")) as fh:
            sha = fh.info().getheader("x-wpt-sha")
            jsonData = json.load(fh, encoding="utf-8")
    except Exception, e:
        die("Couldn't download web-platform-tests data.\n{0}", e)
        return

    paths = []
    for testType, typePaths in jsonData["items"].items():
        if testType in ("support", "reftest_node"):
            # Not tests
            continue
        paths.extend(typePaths.keys())

    if not dryRun:
        try:
            with io.open(os.path.join(path, "wpt-tests.txt"), 'w', encoding="utf-8") as f:
                f.write(sha + "\n")
                for path in sorted(paths):
                    f.write(path + "\n")
        except Exception, e:
            die("Couldn't save web-platform-tests data to disk.\n{0}", e)
            return
    say("Success!")

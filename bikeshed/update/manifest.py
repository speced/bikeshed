# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals

import datetime
import hashlib
import io
import os

def createManifest(path):
    '''Generates a manifest file for all the data files.'''
    manifests = []
    try:
        for absPath, relPath in getDatafilePaths(path):
            if relPath in knownFiles:
                pass
            elif relPath.partition("/")[0] in knownFolders:
                pass
            else:
                continue
            with io.open(absPath, 'r', encoding="utf-8") as fh:
                manifests.append((relPath, hashFile(fh)))
    except Exception, err:
        raise
    try:
        with io.open(os.path.join(localPath, "manifest.txt"), 'w', encoding="utf-8") as fh:
            fh.write(unicode(datetime.datetime.utcnow()) + "\n")
            for p,h in sorted(manifests, key=keyManifest):
                fh.write("{0} {1}\n".format(h, p))
    except Exception, err:
        raise


knownFiles = [
    "fors.json",
    "specs.json",
    "caniuse.json", 
    "methods.json",
    "languages.json",
    "biblio-keys.json", 
    "test-suites.json",
    "link-defaults.infotree"
]
knownFolders = [
    "anchors",
    "biblio",
    "headings"
]


def keyManifest(manifest):
    name = manifest[0]
    if "/" in name:
        dir,_,file = name.partition("/")
        return 1, dir, file
    else:
        return 0, len(name), name


def hashFile(fh):
    return hashlib.md5(fh.read().encode("ascii", "xmlcharrefreplace")).hexdigest()


def getDatafilePaths(basePath):
    for root, dirs, files in os.walk(basePath):
        if "readonly" in dirs:
            dirs.remove("readonly")
        for filename in files:
            filePath = os.path.join(root, filename)
            yield filePath, os.path.relpath(filePath, basePath)

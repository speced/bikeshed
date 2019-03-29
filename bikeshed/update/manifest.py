# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals

import datetime
import hashlib
import io
import os
import urllib2
from contextlib import closing

from ..messages import *

def createManifest(path, dryRun=False):
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
    except Exception as err:
        raise
    if not dryRun:
        try:
            with io.open(os.path.join(path, "manifest.txt"), 'w', encoding="utf-8") as fh:
                fh.write(unicode(datetime.datetime.utcnow()) + "\n")
                for p,h in sorted(manifests, key=keyManifest):
                    fh.write("{0} {1}\n".format(h, p))
        except Exception as err:
            raise


knownFiles = [
    "fors.json",
    "specs.json",
    "methods.json",
    "wpt-tests.txt",
    "languages.json",
    "biblio-keys.json",
    "test-suites.json",
    "link-defaults.infotree",
]
knownFolders = [
    "anchors",
    "biblio",
    "headings",
    "caniuse"
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


def updateByManifest(path, dryRun=False):
    '''
    Attempts to update only the recently updated datafiles by using a manifest file.
    Returns False if updating failed and a full update should be performed;
    returns True if updating was a success.
    '''
    ghPrefix = "https://raw.githubusercontent.com/tabatkins/bikeshed-data/master/data/"
    say("Updating via manifest...")
    try:
        with io.open(os.path.join(path, "manifest.txt"), 'r', encoding="utf-8") as fh:
            oldManifest = fh.readlines()
    except Exception as e:
        warn("Couldn't find local manifest file.\n{0}", e)
        return False
    try:
        with closing(urllib2.urlopen(ghPrefix + "manifest.txt")) as fh:
            newManifest = [unicode(line, encoding="utf-8") for line in fh]
    except Exception as e:
        warn("Couldn't download remote manifest file.\n{0}", e)
        return False

    # First manifest line is a datetime string,
    # which luckily sorts lexicographically.
    if oldManifest[0] == newManifest[0]:
        say("Local data is already up-to-date ({0}). Done!", oldManifest[0].strip())
        return True
    elif oldManifest[0] > newManifest[0]:
        # No need to update, local data is more recent.
        say("Local data is fresher ({0}) than remote ({1}), so nothing to update.", oldManifest[0].strip(), newManifest[0].strip())
        return True

    oldFiles = dictFromManifest(oldManifest)
    newFiles = dictFromManifest(newManifest)
    newPaths = []
    for filePath,hash in newFiles.items():
        if hash != oldFiles.get(filePath):
            newPaths.append(filePath)

    if not dryRun:
        deletedPaths = []
        for filePath in oldFiles.keys():
            if filePath not in newFiles and os.path.exists(localizePath(path, filePath)):
                os.remove(localizePath(path, filePath))
                deletedPaths.append(filePath)
        if deletedPaths:
            print "Deleted {0} old data files.".format(len(deletedPaths))

    if not dryRun:
        import time
        messageDelta = .5 # seconds of *processor* time, not wall time :(
        lastMsgTime = time.clock()
        if newPaths:
            say("Updating {0} file{1}...", len(newPaths), "s" if len(newPaths) > 1 else "")
        for i,filePath in enumerate(newPaths):
            remotePath = ghPrefix + filePath
            localPath = localizePath(path, filePath)
            try:
                with closing(urllib2.urlopen(remotePath)) as fh:
                    newFile = unicode(fh.read(), encoding="utf-8")
            except Exception,e:
                warn("Couldn't download file '{0}'.\n{1}", remotePath, e)
                return False
            try:
                dirPath = os.path.dirname(localPath)
                if not os.path.exists(dirPath):
                    os.makedirs(dirPath)
                with io.open(localPath, 'w', encoding="utf-8") as fh:
                    fh.write(newFile)
            except Exception,e:
                warn("Couldn't save file '{0}'.\n{1}", localPath, e)
                return False

            currFileTime = time.clock()
            if (currFileTime - lastMsgTime) >= messageDelta:
                say("Updated {0}/{1}...", i+1, len(newPaths))
                lastMsgTime = currFileTime
        try:
            with io.open(os.path.join(path, "manifest.txt"), 'w', encoding="utf-8") as fh:
                fh.write("".join(newManifest))
        except Exception,e:
            warn("Couldn't save new manifest file.\n{0}", e)
            return False
    say("Done!")
    return True


def localizePath(root, relPath):
    return os.path.join(root, *relPath.split("/"))



def dictFromManifest(lines):
    '''
    Converts a manifest file, where each line is
    <hash>[space]<filepath>
    into a dict of {path:hash}.
    First line of file is a datetime string, which we skip.
    '''
    ret = {}
    for line in lines[1:]:
        hash,_,path = line.strip().partition(" ")
        ret[path] = hash
    return ret

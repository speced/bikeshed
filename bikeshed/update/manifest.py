# -*- coding: utf-8 -*-


import hashlib
import io
import os
import requests
from datetime import datetime

from ..messages import *

# Manifest creation relies on these data structures.
# Add to them whenever new types of data files are created.
knownFiles = [
    "biblio-keys.json",
    "biblio-numeric-suffixes.json",
    "bikeshed-version.txt",
    "fors.json",
    "languages.json",
    "link-defaults.infotree",
    "mdn.json",
    "methods.json",
    "specs.json",
    "test-suites.json",
    "version.txt",
    "wpt-tests.txt",
]
knownFolders = [
    "anchors",
    "biblio",
    "caniuse",
    "headings",
    "mdn",
]

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
                fh.write(str(datetime.utcnow()) + "\n")
                for p,h in sorted(manifests, key=keyManifest):
                    fh.write("{0} {1}\n".format(h, p))
        except Exception as err:
            raise

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
            localManifest = fh.readlines()
    except Exception as e:
        warn("Couldn't find local manifest file.\n{0}", e)
        return False
    try:
        remoteManifest = requests.get(ghPrefix + "manifest.txt").text.splitlines()
    except Exception as e:
        warn("Couldn't download remote manifest file.\n{0}", e)
        return False

    localDt = datetime.strptime(localManifest[0].strip(), "%Y-%m-%d %H:%M:%S.%f")
    remoteDt = datetime.strptime(remoteManifest[0].strip(), "%Y-%m-%d %H:%M:%S.%f")

    if (remoteDt - datetime.utcnow()).days >= 2:
        warn("Remote data is more than two days old; the update process has probably fallen over. Please report this!")
    if localDt == remoteDt:
        say("Local data is already up-to-date with remote ({0})", localDt.strftime("%Y-%m-%d %H:%M:%S"))
        return True
    elif localDt > remoteDt:
        # No need to update, local data is more recent.
        say("Local data is fresher ({0}) than remote ({1}), so nothing to update.", localDt.strftime("%Y-%m-%d %H:%M:%S"), remoteDt.strftime("%Y-%m-%d %H:%M:%S"))
        return True

    localFiles = dictFromManifest(localManifest)
    remoteFiles = dictFromManifest(remoteManifest)
    newPaths = []
    for filePath,hash in remoteFiles.items():
        if hash != localFiles.get(filePath):
            newPaths.append(filePath)

    if not dryRun:
        deletedPaths = []
        for filePath in localFiles.keys():
            if filePath not in remoteFiles and os.path.exists(localizePath(path, filePath)):
                os.remove(localizePath(path, filePath))
                deletedPaths.append(filePath)
        if deletedPaths:
            print("Deleted {0} old data file{1}.".format(len(deletedPaths), "s" if len(deletedPaths) > 1 else ""))

    if not dryRun:
        import time
        messageDelta = 2.5 # wall time
        lastMsgTime = time.time()
        if newPaths:
            say("Updating {0} file{1}...", len(newPaths), "s" if len(newPaths) > 1 else "")
        for i,filePath in enumerate(newPaths):
            remotePath = ghPrefix + filePath
            localPath = localizePath(path, filePath)
            try:
                newFile = requests.get(remotePath).text
            except Exception as e:
                warn("Couldn't download file '{0}'.\n{1}", remotePath, e)
                return False
            try:
                dirPath = os.path.dirname(localPath)
                if not os.path.exists(dirPath):
                    os.makedirs(dirPath)
                with io.open(localPath, 'w', encoding="utf-8") as fh:
                    fh.write(newFile)
            except Exception as e:
                warn("Couldn't save file '{0}'.\n{1}", localPath, e)
                return False

            currFileTime = time.time()
            if (currFileTime - lastMsgTime) >= messageDelta:
                say("Updated {0}/{1}...", i+1, len(newPaths))
                lastMsgTime = currFileTime
        try:
            with io.open(os.path.join(path, "manifest.txt"), 'w', encoding="utf-8") as fh:
                fh.write("".join(remoteManifest))
        except Exception as e:
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

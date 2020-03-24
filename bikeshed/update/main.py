# -*- coding: utf-8 -*-


import os

from . import updateBackRefs
from . import updateCrossRefs
from . import updateBiblio
from . import updateCanIUse
from . import updateMdn
from . import updateLinkDefaults
from . import updateTestSuites
from . import updateLanguages
from . import updateWpt
from . import manifest
from .. import config
from ..messages import *


def update(anchors=False, backrefs=False, biblio=False, caniuse=False, linkDefaults=False, mdn=False, testSuites=False, languages=False, wpt=False, path=None, dryRun=False, force=False):
    if path is None:
        path = config.scriptPath("spec-data")

    # Update via manifest by default, falling back to a full update only if failed or forced.
    if not force:
        success = manifest.updateByManifest(path=path, dryRun=dryRun)
        if not success:
            say("Falling back to a manual update...")
            force = True
    if force:
        # If all are False, update everything
        if  anchors == backrefs == biblio == caniuse == linkDefaults == mdn == testSuites == languages == wpt == False:
            anchors  = backrefs  = biblio  = caniuse  = linkDefaults  = mdn  = testSuites  = languages  = wpt  = True

        touchedPaths = {
            "anchors": updateCrossRefs.update(path=path, dryRun=dryRun) if anchors else None,
            "backrefs": updateBackRefs.update(path=path, dryRun=dryRun) if backrefs else None,
            "biblio": updateBiblio.update(path=path, dryRun=dryRun) if biblio else None,
            "caniuse": updateCanIUse.update(path=path, dryRun=dryRun) if caniuse else None,
            "mdnspeclinks": updateMdn.update(path=path, dryRun=dryRun) if mdn else None,
            "linkDefaults": updateLinkDefaults.update(path=path, dryRun=dryRun) if linkDefaults else None,
            "testSuites": updateTestSuites.update(path=path, dryRun=dryRun) if testSuites else None,
            "languages": updateLanguages.update(path=path, dryRun=dryRun) if languages else None,
            "wpt": updateWpt.update(path=path, dryRun=dryRun)if wpt else None
        }

        cleanupFiles(path, touchedPaths=touchedPaths, dryRun=dryRun)
        manifest.createManifest(path=path, dryRun=dryRun)



def fixupDataFiles():
    '''
    Checks the readonly/ version is more recent than your current mutable data files.
    This happens if I changed the datafile format and shipped updated files as a result;
    using the legacy files with the new code is quite bad!
    '''
    try:
        localVersion = int(open(localPath("version.txt"), 'r').read())
    except IOError:
        localVersion = None
    try:
        remoteVersion = int(open(remotePath("version.txt"), 'r').read())
    except IOError as err:
        warn("Couldn't check the datafile version. Bikeshed may be unstable.\n{0}", err)
        return

    if localVersion == remoteVersion:
        # Cool
        return

    # If versions don't match, either the remote versions have been updated
    # (and we should switch you to them, because formats may have changed),
    # or you're using a historical version of Bikeshed (ditto).
    try:
        for filename in os.listdir(remotePath()):
            copyanything(remotePath(filename), localPath(filename))
    except Exception as err:
        warn("Couldn't update datafiles from cache. Bikeshed may be unstable.\n{0}", err)
        return


def updateReadonlyDataFiles():
    '''
    Like fixupDataFiles(), but in the opposite direction --
    copies all my current mutable data files into the readonly directory.
    This is a debugging tool to help me quickly update the built-in data files,
    and will not be called as part of normal operation.
    '''
    try:
        for filename in os.listdir(localPath()):
            if filename.startswith("readonly"):
                continue
            copyanything(localPath(filename), remotePath(filename))
    except Exception as err:
        warn("Error copying over the datafiles:\n{0}", err)
        return


def cleanupFiles(root, touchedPaths, dryRun=False):
    if dryRun:
        return
    paths = set()
    deletableFiles = []
    deletableFolders = []
    if touchedPaths["anchors"] is not None:
        deletableFiles.extend(["specs.json", "methods.json", "fors.json"])
        deletableFolders.extend(["headings", "anchors"])
        paths.update(touchedPaths["anchors"])
    if touchedPaths["biblio"] is not None:
        deletableFiles.extend(["biblio-keys.json", "biblio-numeric-suffixes.json"])
        deletableFolders.extend(["biblio"])
        paths.update(touchedPaths["biblio"])
    if touchedPaths["caniuse"] is not None:
        deletableFiles.extend(["caniuse.json"])
        deletableFolders.extend(["caniuse"])
        paths.update(touchedPaths["caniuse"])
    if touchedPaths["mdnspeclinks"] is not None:
        deletableFolders.extend(["mdnspeclinks"])
        paths.update(touchedPaths["mdnspeclinks"])

    say("Cleaning up old data files...")
    oldPaths = []
    for absPath, relPath in getDatafilePaths(root):
        if "/" not in relPath and relPath not in deletableFiles:
            continue
        if "/" in relPath and relPath.partition("/")[0] not in deletableFolders:
            continue
        if absPath not in paths:
            os.remove(absPath)
            oldPaths.append(relPath)
    if oldPaths:
        say("Success! Deleted {0} old files.".format(len(oldPaths)))
    else:
        say("Success! Nothing to delete.")


def copyanything(src, dst):
    import shutil
    import errno
    try:
        shutil.rmtree(dst, ignore_errors=True)
        shutil.copytree(src, dst)
    except OSError as exc:
        if exc.errno in [errno.ENOTDIR, errno.EINVAL]:
            shutil.copy(src, dst)
        else:
            raise

def localPath(*segs):
    return config.scriptPath("spec-data", *segs)

def remotePath(*segs):
    return config.scriptPath("spec-data", "readonly", *segs)

def getDatafilePaths(basePath):
    for root, dirs, files in os.walk(basePath):
        for filename in files:
            filePath = os.path.join(root, filename)
            yield filePath, os.path.relpath(filePath, basePath)

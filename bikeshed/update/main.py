# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals

import os

from . import updateBackRefs
from . import updateCrossRefs
from . import updateBiblio
from . import updateCanIUse
from . import updateLinkDefaults
from . import updateTestSuites
from . import updateLanguages
from . import updateWpt
from . import manifest
from .. import config
from ..messages import *


def update(anchors=False, backrefs=False, biblio=False, caniuse=False, linkDefaults=False, testSuites=False, languages=False, wpt=False, path=None, dryRun=False, force=False):
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
        if  anchors == backrefs == biblio == caniuse == linkDefaults == testSuites == languages == wpt == False:
            anchors  = backrefs  = biblio  = caniuse  = linkDefaults  = testSuites  = languages  = wpt  = True
        anchorPaths = updateCrossRefs.update(path=path, dryRun=dryRun) if anchors else set()
        if backrefs:
            updateBackRefs.update(path=path, dryRun=dryRun)
        if biblio:
            updateBiblio.update(path=path, dryRun=dryRun)
        if caniuse:
            updateCanIUse.update(path=path, dryRun=dryRun)
        if linkDefaults:
            updateLinkDefaults.update(path=path, dryRun=dryRun)
        if testSuites:
            updateTestSuites.update(path=path, dryRun=dryRun)
        if languages:
            updateLanguages.update(path=path, dryRun=dryRun)
        if wpt:
            updateWpt.update(path=path, dryRun=dryRun)
        manifest.createManifest(path=path, dryRun=dryRun)

        cleanupFiles(path, anchors=anchorPaths)


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
    except IOError, err:
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
    except Exception, err:
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
    except Exception, err:
        warn("Error copying over the datafiles:\n{0}", err)
        return


def cleanupFiles(root, anchors=None):
    paths = set()
    checkedFiles = []
    checkedFolders = []
    if anchors is not None:
        checkedFiles.extend(["specs.json", "methods.json", "fors.json"])
        checkedFolders.extend(["headings", "anchors"])
        paths.update(anchors)

    for absPath, relPath in getDatafilePaths(root):
        if "/" not in relPath and relPath not in checkedFiles:
            continue
        if "/" in relPath and relPath.partition("/")[0] not in checkedFolders:
            continue
        if absPath not in paths:
            os.remove(absPath)


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

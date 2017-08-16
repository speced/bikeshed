# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals

import os

from . import updateCrossRefs
from . import updateBiblio
from . import updateCanIUse
from . import updateLinkDefaults
from . import updateTestSuites
from . import updateLanguages
from .. import config


def update(anchors=False, biblio=False, caniuse=False, linkDefaults=False, testSuites=False, languages=False):
    # If all are False, update everything
    updateAnyway = not (anchors or biblio or caniuse or linkDefaults or testSuites or languages)
    if anchors or updateAnyway:
        updateCrossRefs.update()
    if biblio or updateAnyway:
        updateBiblio.update()
    if caniuse or updateAnyway:
        updateCanIUse.update()
    if linkDefaults or updateAnyway:
        updateLinkDefaults.update()
    if testSuites or updateAnyway:
        updateTestSuites.update()
    if languages or updateAnyway:
        updateLanguages.update()


def fixupDataFiles():
    import os
    localPath = os.path.join(config.scriptPath, "spec-data")
    remotePath = os.path.join(config.scriptPath, "spec-data", "readonly")
    try:
        localVersion = int(open(os.path.join(localPath, "version.txt"), 'r').read())
    except IOError:
        localVersion = None
    try:
        remoteVersion = int(open(os.path.join(remotePath, "version.txt"), 'r').read())
    except IOError, err:
        warn("Couldn't check the datafile version. Bikeshed may be unstable.\n{0}", err)
        return

    if localVersion == remoteVersion:
        # Cool
        return

    # If versions don't match, either the remote versions have been updated
    # (and we should switch you to them, because formats may have changed),
    # or you're using a historical version of Bikeshed (ditto).
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
    try:
        for filename in os.listdir(remotePath):
            copyanything(os.path.join(remotePath, filename), os.path.join(localPath, filename))
    except Exception, err:
        warn("Couldn't update datafiles from cache. Bikeshed may be unstable.\n{0}", err)
        return

# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals

import io
import os

from ..messages import *
from .main import scriptPath

def retrieveDataFile(filename, quiet=False, str=False, okayToFail=False):
    import os
    cacheLocation = scriptPath + "/spec-data/" + filename
    fallbackLocation = scriptPath + "/spec-data/readonly/" + filename
    try:
        fh = open(cacheLocation, 'r')
    except IOError:
        try:
            fh = open(fallbackLocation, 'r')
        except IOError:
            if not okayToFail:
                die("Couldn't retrieve the file '{0}' from cache. Something's wrong, please report this.", filename)
            if str:
                return ""
            else:
                return open(os.devnull)
        import shutil
        try:
            if not quiet:
                say("Attempting to save the {0} file to cache...", type)
            if not dryRun:
                shutil.copy(fallbackLocation, cacheLocation)
            if not quiet:
                say("Successfully saved the {0} file to cache.", type)
        except:
            if not quiet:
                warn("Couldn't save the {0} file to cache. Proceeding...", type)
    if str:
        return unicode(fh.read(), encoding="utf-8")
    else:
        return fh


def retrieveBoilerplateFile(doc, name, group=None, status=None, error=True):
    # Looks in three locations, in order:
    # the folder the spec source is in, the group's boilerplate folder, and the generic boilerplate folder.
    # In each location, it first looks for the file specialized on status, and then for the generic file.
    # Filenames must be of the format NAME.include or NAME-STATUS.include
    if group is None and doc.md.group is not None:
        group = doc.md.group.lower()
    if status is None:
        status = doc.md.rawStatus

    localFolder = localFolderPath(doc)
    includeFolder = os.path.join(scriptPath, "boilerplate")
    statusFile = "{0}-{1}.include".format(name, status)
    genericFile = "{0}.include".format(name)
    filenames = []
    if localFolder:
        filenames.append(os.path.join(localFolder, statusFile))
        filenames.append(os.path.join(localFolder, genericFile))
    if group:
        filenames.append(os.path.join(includeFolder, group, statusFile))
        filenames.append(os.path.join(includeFolder, group, genericFile))
    filenames.append(os.path.join(includeFolder, statusFile))
    filenames.append(os.path.join(includeFolder, genericFile))

    for filename in filenames:
        if os.path.isfile(filename):
            try:
                with io.open(filename, 'r', encoding="utf-8") as fh:
                    return fh.read()
            except IOError:
                if error:
                    die("The include file for {0} disappeared underneath me.", name)
                return ""
            break
    else:
        if error:
            die("Couldn't find an appropriate include file for the {0} inclusion, given group='{1}' and status='{2}'.", name, group, status)
        return ""


def localFolderPath(doc):
    if doc.inputSource == "-":
        return None
    return os.path.dirname(os.path.abspath(doc.inputSource))

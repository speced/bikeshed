# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals

import io
import os

from ..messages import *
from .main import scriptPath, docPath

def retrieveDataFile(*segs, **kwargs):
    quiet = kwargs.get("quiet", False)
    str = kwargs.get("str", False)
    okayToFail = kwargs.get("okayToFail", False)
    filename = "/".join(segs)
    filetype = segs[0]
    import os
    cacheLocation = scriptPath("spec-data", *segs)
    fallbackLocation = scriptPath("spec-data", "readonly", *segs)
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
                say("Attempting to save the {0} file to cache...", filetype)
            if not dryRun:
                shutil.copy(fallbackLocation, cacheLocation)
            if not quiet:
                say("Successfully saved the {0} file to cache.", filetype)
        except:
            if not quiet:
                warn("Couldn't save the {0} file to cache. Proceeding...", filetype)
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

    def boilerplatePath(*segs):
        return scriptPath("boilerplate", *segs)
    statusFile = "{0}-{1}.include".format(name, status)
    genericFile = "{0}.include".format(name)
    filenames = []
    if docPath(doc):
        filenames.append(docPath(doc, statusFile))
        filenames.append(docPath(doc, genericFile))
    if group:
        filenames.append(boilerplatePath(group, statusFile))
        filenames.append(boilerplatePath(group, genericFile))
    filenames.append(boilerplatePath(statusFile))
    filenames.append(boilerplatePath(genericFile))

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

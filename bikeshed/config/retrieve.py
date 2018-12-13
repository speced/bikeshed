# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals

import io
import os

from ..messages import *
from .main import scriptPath, docPath, useReadonlyData


class DataFileRequester(object):
    def __init__(self, type=None, fallback=None):
        self.type = type
        if self.type not in ("readonly", "latest"):
            raise Exception("Bad value for DataFileRequester.type, got '{0}'.", type)
        # fallback is another requester, used if the main one fails.
        self.fallback = fallback

    def fetch(self, *segs, **kwargs):
        str = kwargs.get("str", False)
        okayToFail = kwargs.get("okayToFail", False)
        location = self._buildPath(*segs)
        try:
            if str:
                with io.open(location, "r", encoding="utf-8") as fh:
                    return fh.read()
            else:
                return io.open(location, "r", encoding="utf-8")
        except IOError:
            if self.fallback:
                try:
                    return self.fallback.fetch(*segs, str=str, okayToFail=okayToFail)
                except IOError:
                    return self._fail(location, str, okayToFail)
            return self._fail(location, str, okayToFail)

    def _buildPath(self, *segs):
        if self.type == "readonly":
            return scriptPath("spec-data", "readonly", *segs)
        else:
            return scriptPath("spec-data", *segs)

    def _fail(self, location, str, okayToFail):
        if okayToFail:
            if str:
                return ""
            else:
                return io.StringIO("")
        raise IOError("Couldn't find file '{0}'".format(location))

defaultRequester = DataFileRequester(type="latest", fallback=DataFileRequester(type="readonly"))


def retrieveBoilerplateFile(doc, name, group=None, status=None, error=True):
    # Looks in three locations, in order:
    # the folder the spec source is in, the group's boilerplate folder, and the generic boilerplate folder.
    # In each location, it first looks for the file specialized on status, and then for the generic file.
    # Filenames must be of the format NAME.include or NAME-STATUS.include
    if group is None and doc.md.group is not None:
        group = doc.md.group.lower()
    if status is None:
        megaGroup,_,status = doc.md.rawStatus.partition("/")
        if status == "":
            status = megaGroup

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

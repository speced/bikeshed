# -*- coding: utf-8 -*-

from __future__ import division, unicode_literals
import tempfile
import tarfile
import os
import logging

from .messages import *
from . import extensions
from .requests import requests


def publishEchidna(doc, username, password, decision):
    logging.captureWarnings(True)  # Silence SNIMissingWarning
    tar = prepareTar(doc, visibleTar=False)
    # curl 'https://labs.w3.org/echidna/api/request' --user '<username>:<password>' -F "tar=@/some/path/spec.tar" -F "decision=<decisionUrl>"
    r = requests.post("https://labs.w3.org/echidna/api/request", auth=(username, password), data={"decision": decision}, files={"tar": tar.read()})
    os.remove(tar.name)

    if r.status_code == 202:
        print "https://labs.w3.org/echidna/api/status?id=" + r.text
    else:
        print "There was an error publishing your spec. Here's some information that might help?"
        print r.status_code
        print r.text
        print r.headers


def prepareTar(doc, visibleTar=False):
    # Finish the spec
    specOutput = tempfile.NamedTemporaryFile(delete=False)
    doc.finish(outputFilename=specOutput.name)
    # Build the TAR file
    if visibleTar:
        tar = tarfile.open(name="test.tar", mode='w')
    else:
        f = tempfile.NamedTemporaryFile(delete=False)
        tar = tarfile.open(fileobj=f, mode='w')
    tar.add(specOutput.name, arcname="Overview.html")
    additionalFiles = extensions.BSPublishAdditionalFiles(["images", "diagrams", "examples"])
    for fname in additionalFiles:
        try:
            if isinstance(fname, basestring):
                tar.add(fname)
            elif isinstance(fname, list):
                tar.add(fname[0], arcname=fname[1])
        except OSError:
            pass
    tar.close()
    specOutput.close()
    os.remove(specOutput.name)
    if visibleTar:
        return open("test.tar", "rb")
    else:
        f.seek(0)
        return f

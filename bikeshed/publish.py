# -*- coding: utf-8 -*-

from __future__ import division, unicode_literals
import tempfile
import tarfile
import requests
import os

from .messages import *
from . import extensions

def publishEchidna(doc, username, password, decision):
	tar = prepareTar(doc)
	# curl 'https://labs.w3.org/echidna/api/request' --user '<username>:<password>' -F "tar=@/some/path/spec.tar" -F "decision=<decisionUrl>"
	r = requests.post("https://labs.w3.org/echidna/api/request", auth=(username, password), data={"decision": decision}, files={"tar": tar})
	os.remove(tar.name)
	print r.text
	print r.headers
	print r.status_code

def prepareTar(doc):
	# Finish the spec
	specOutput = tempfile.NamedTemporaryFile(delete=False)
	doc.finish(outputFilename=specOutput.name)
	# Build the TAR file
	f = tempfile.NamedTemporaryFile(delete=False)
	tar = tarfile.open(fileobj=f, mode='w')
	#tar = tarfile.open(name="test.tar", mode='w')
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
	return f

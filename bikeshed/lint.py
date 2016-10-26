# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals
from .messages import *
from .htmlhelpers import *

def lintExampleIDs(doc):
	if not doc.md.complainAbout['missing-example-ids']:
		return
	for el in findAll(".example:not([id])", doc):
		warn("Example needs ID:\n{0}", outerHTML(el)[0:100], el=el)


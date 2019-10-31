# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals

from .htmlhelpers import *

fingerprintId = "b732b3fe" # hashlib.md5("tracking-vector").hexdigest()[0:8], to minimize chance of collision

def addFingerprinting(doc):
	if doc.md.fingerprintClass is None:
		return

	els = findAll(".{0}".format(doc.md.fingerprintClass), doc)

	if len(els) == 0:
		return

	if doc.md.fingerprintImage is None:
		# Generate an SVG and <use> it in all the individual spots
		appendChild(doc.body,
			E.svg({"viewBox":"0 0 46 64", "style":"display:none"},
				E.defs({},
					E.path({"id":fingerprintId,
					        "stroke":"black",
					        "stroke-linecap":"round",
					        "stroke-linejoin":"round",
					        "stroke-dasharray":"3,2,35,2,20,2",
					        "fill":"none",
					        "d":"M2 23Q17 -16 40 12M1 35Q17 -20 43 20M2 40Q18 -19 44 25M3 43Q19 -16 45 29M5 46Q20 -12 45 32M5 49Q11 40 15 27T27 16T45 37M5 49Q15 38 19 25T34 27T44 41M6 52Q17 40 21 28T32 29T43 44M6 52Q21 42 23 31T30 32T42 47M7 54Q23 47 24 36T28 34T41 50M8 56Q26 50 26 35Q28 48 40 53M10 58Q24 54 27 45Q30 52 38 55M27 50Q28 53 36 57M25 52Q28 56 31 57M22 55L26 57M10 58L37 57M13 60L32 60M16 62L28 63"}))))

	for el in els:
		prependChild(el,
			fingerprintImage(doc.md.fingerprintImage, doc.md.fingerprintTitle))


def fingerprintImage(url, title):
	if url is None:
		return E.svg({"width":"46", "height":"64", "role":"img"},
			E.title({}, title),
			E.use({"href":"#"+fingerprintId}))
	else:
		return E.img({"title":title, "alt":title, "src":url})

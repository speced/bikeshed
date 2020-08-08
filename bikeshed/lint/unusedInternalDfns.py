# -*- coding: utf-8 -*-

import re
from ..h import *
from ..messages import *
from ..config import dfnElementsSelector

def unusedInternalDfns(doc):
	'''
	The export/noexport distinction assumes that noexport dfns are meant to be internal-only.
	If you don't actually *use* a noexport dfn, that's probably an error.
	In particular, this'll probably help find *untagged* dfns that are defaulting to noexport.
	'''
	noexportDfns = [el for el in findAll(dfnElementsSelector, doc) if el.get("data-noexport") == "by-default"]

	def local(el):
		return (el.get("href") is not None
			and el.get("href").startswith("#")
			and not hasClass(el, "self-link")
			and closestAncestor(el, lambda x:hasClass(x, "index")) is None)
	localHrefs = [el.get("href")[1:] for el in findAll("a", doc) if local(el)]

	for el in noexportDfns:
		if el.get("id") not in localHrefs:
			warn("Unexported dfn that's not referenced locally - did you mean to export it?\n{0}", outerHTML(el), el=el)

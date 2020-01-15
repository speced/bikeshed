# -*- coding: utf-8 -*-


from ..htmlhelpers import *
from ..messages import *

def requiredIDs(doc):
	for id in doc.md.requiredIDs:
		if id.startswith("#"):
			id = id[1:]
		if find("#{0}".format(escapeCSSIdent(id)), doc) is None:
			die("Required ID '{0}' was not found in the document.", id)
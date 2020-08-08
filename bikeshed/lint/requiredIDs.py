# -*- coding: utf-8 -*-


from ..h import *
from ..messages import *

def requiredIDs(doc):
	if not doc.md.requiredIDs:
		return
	doc_ids = {e.get("id") for e in findAll("[id]", doc)}
	for id in doc.md.requiredIDs:
		if id.startswith("#"):
			id = id[1:]
		if id not in doc_ids:
			die("Required ID '{0}' was not found in the document.", id)

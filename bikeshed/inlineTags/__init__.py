# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals

import io

from subprocess import Popen, PIPE

from ..htmlhelpers import *
from ..messages import *

def processTags(doc):
	for el in findAll("[data-span-tag]", doc):
		tag = el.get("data-span-tag")
		if tag not in doc.md.inlineTagCommands:
			die("Unknown inline tag '{0}' found:\n  {1}", tag, outerHTML(el), el=el)
			continue
		command = doc.md.inlineTagCommands[tag]
		p = Popen(command, stdin=PIPE, stdout=PIPE, stderr=PIPE, shell=True)
		out,err = p.communicate(innerHTML(el))
		if p.returncode:
			die("When trying to process {0}, got return code {1} and the following stderr:\n{2}", outerHTML(el), p.returncode, err)
			continue
		replaceContents(el, parseHTML(out))

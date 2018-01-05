# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals

from . import attr

@attr.s(slots=True)
class Line(object):
	i = attr.ib()
	text = attr.ib()

def rectify(lines):
	if any(isinstance(l, unicode) for l in lines):
		return [Line(0, l) for l in lines]
	return lines

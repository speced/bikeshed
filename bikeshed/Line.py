# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals

from . import attr

@attr.s(slots=True)
class Line(object):
	i = attr.ib(validator=[attr.validators.instance_of(int)])
	text = attr.ib(validator=[attr.validators.instance_of(unicode)])

	def __unicode__(self):
		return self.text

def rectify(lines):
	if any(isinstance(l, unicode) for l in lines):
		return [Line(-1, l) for l in lines]
	return lines

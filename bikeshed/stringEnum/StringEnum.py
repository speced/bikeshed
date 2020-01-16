# -*- coding: utf-8 -*-

class StringEnum(object):
	'''
	Simple Enum class.

	Takes strings, returns an object that acts set-like (you can say `"foo" in someEnum`),
	but also hangs the strings off of the object as attributes (you can say `someEnum.foo`)
	or as a dictionary (`someEnum["foo"]`).
	'''

	def __init__(self, *vals):
		self._vals = {}
		for val in vals:
			self._vals[val] = val
			setattr(self, val, val)

	def __iter__(self):
		return iter(self._vals)

	def __len__(self):
		return len(self._vals)

	def __contains__(self, val):
		return val in self._vals

	def __getitem__(self, val):
		return self._vals[val]
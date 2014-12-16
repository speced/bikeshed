# -*- coding: utf-8 -*-

from __future__ import division, unicode_literals
import re
import StringIO

class HTMLSerializer(object):
	inlineEls = frozenset(["a", "em", "strong", "small", "s", "cite", "q", "dfn", "abbr", "data", "time", "code", "var", "samp", "kbd", "sub", "sup", "i", "b", "u", "mark", "ruby", "bdi", "bdo", "span", "br", "wbr", "img", "meter", "progress"])
	rawEls = frozenset(["xmp", "script", "style"])
	def __init__(self, tree):
		self.tree = tree

	def serialize(self):
		output = StringIO.StringIO()
		writer = output.write
		writer("<!doctype html>")
		root = self.tree.getroot()
		self._serializeEl(root, writer)
		str = output.getvalue()
		output.close()
		return str

	def _serializeEl(self, el, write, indent=0, pre=False):
		if el.tag not in self.inlineEls:
			write("\n")
			write("  "*indent)
		write("<")
		write(el.tag)
		for attrName, attrVal in sorted(el.items()):
			write(" ")
			write(attrName)
			write('="')
			write(self.escapeAttrVal(attrVal))
			write('"')
		write(">")
		if el.tag == "pre":
			pre = True
		if el.text:
			write(self.escapeText(el.text))
		blockChildren = False
		for child in el.iterchildren():
			if not blockChildren and child.tag not in self.inlineEls:
				blockChildren = True
			self._serializeEl(child, write, indent+1)
			if child.tail:
				if not pre and child.tag not in self.inlineEls:
					write("\n")
					write("  "*(indent+1))
				write(self.escapeText(child.tail))
		if not pre and blockChildren:
			write("\n")
			write("  "*indent)
		write("</")
		write(el.tag)
		write(">")

	def escapeAttrVal(self, val):
		return val.replace("&", "&amp;").replace('"', "&quot;")

	def escapeText(self, val):
		return val.replace('&', "&amp;").replace("<", "&lt;")

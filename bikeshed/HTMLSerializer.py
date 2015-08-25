# -*- coding: utf-8 -*-

from __future__ import division, unicode_literals
import re
import StringIO
from .htmlhelpers import childNodes, isElement, outerHTML, escapeHTML, escapeAttr

class HTMLSerializer(object):
	inlineEls = frozenset(["a", "em", "strong", "small", "s", "cite", "q", "dfn", "abbr", "data", "time", "code", "var", "samp", "kbd", "sub", "sup", "i", "b", "u", "mark", "ruby", "bdi", "bdo", "span", "br", "wbr", "img", "meter", "progress", "[]"])
	rawEls = frozenset(["xmp", "script", "style"])
	voidEls = frozenset(["area", "base", "br", "col", "command", "embed", "hr", "img", "input", "keygen", "link", "meta", "param", "source", "track", "wbr"])
	omitEndTagEls = frozenset(["td", "th", "tr", "thead", "tbody", "tfoot", "li", "dt", "dd"])
	def __init__(self, tree, opaqueElements):
		self.tree = tree
		self.opaqueElements = opaqueElements

	def serialize(self):
		output = StringIO.StringIO()
		writer = output.write
		writer("<!doctype html>")
		root = self.tree.getroot()
		self._serializeEl(root, writer)
		str = output.getvalue()
		output.close()
		return str

	def _serializeEl(self, el, write, indent=0, pre=False, inline=False):
		def unfuckName(n):
			# LXML does namespaces stupidly
			if n.startswith("{"):
				return n.partition("}")[2]
			return n
		def groupIntoBlocks(nodes):
			collect = []
			for node in nodes:
				if isElement(node) and node.tag not in self.inlineEls:
					yield collect
					collect = []
					yield node
					continue
				else:
					collect.append(node)
			yield collect
		def fixWS(text):
			t1 = text.lstrip()
			if text != t1:
				t1 = " " + t1
			t2 = t1.rstrip()
			if t1 != t2:
				t2 = t2 + " "
			return t2
		def startTag():
			if not isElement(el): # Is an array
				return
			write("<")
			write(unfuckName(el.tag))
			for attrName, attrVal in sorted(el.items()):
				write(" ")
				write(unfuckName(attrName))
				write('="')
				write(escapeAttr(attrVal))
				write('"')
			write(">")
		def endTag():
			if not isElement(el): # Is an array
				return
			write("</")
			write(unfuckName(el.tag))
			write(">")

		if isElement(el):
			tag = unfuckName(el.tag)
		else:
			# el is an array
			tag = "[]"

		if tag in self.voidEls:
			write(" "*indent)
			startTag()
			return
		if pre or tag in self.rawEls or tag in self.opaqueElements:
			startTag()
			for node in childNodes(el):
				if isElement(node):
					self._serializeEl(node, write, indent=indent, pre=True)
				else:
					write(escapeHTML(node))
			endTag()
			return
		if inline or tag in self.inlineEls:
			startTag()
			for node in childNodes(el):
				if isElement(node):
					self._serializeEl(node, write, inline=inline)
				else:
					write(escapeHTML(fixWS(node)))
			endTag()
			return
		# Otherwise I'm a block element
		blocks = list(groupIntoBlocks(childNodes(el, skipWS=True)))
		if len(blocks) == 1 and not isElement(blocks[0]):
			# Contains only inlines, print accordingly
			write(" "*indent)
			startTag()
			self._serializeEl(blocks[0], write, inline=True)
			if el.tag not in self.omitEndTagEls:
				endTag()
			return
		# Otherwise I'm a block that contains at least one block
		write(" "*indent)
		startTag()
		for block in blocks:
			if isElement(block):
				write("\n")
				self._serializeEl(block, write, indent=indent+1)
			else:
				# is an array of inlines
				if len(block) > 0:
					write("\n")
					write(" "*(indent+1))
					self._serializeEl(block, write, inline=True)
		if el.tag not in self.omitEndTagEls:
			write("\n")
			write(" "*indent)
			endTag()
		return

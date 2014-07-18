# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals
import re
import json
from itertools import *

def parse(lines, features=None):
	tokens = tokenizeLines(lines, features)
	return parseTokens(tokens)

def tokenizeLines(lines, features=None):
	# Turns lines of text into block tokens,
	# which'll be turned into MD blocks later.
	# Every token *must* have 'type', 'raw', and 'prefix' keys.

	if features is None:
		features = set(["headings"])

	# Inline elements that are allowed to start a "normal" line of text.
	# Any other element will instead be an HTML line and will close paragraphs, etc.
	allowedStartElements = "a|em|strong|small|s|cite|q|dfn|abbr|data|time|code|var|samp|kbd|sub|sup|i|b|u|mark|ruby|bdi|bdo|span|br|wbr|img|meter|progress"

	tokens = []
	preDepth = 0
	rawElements = "pre|style|script|xmp"

	for rawline in lines:
		# Dont' parse anything while you're inside certain elements
		if re.search(r"<({0})[ >]".format(rawElements), rawline):
			preDepth += 1
		if preDepth:
			tokens.append({'type':'raw', 'raw':rawline, 'prefix': re.match(r"[ \t]*", rawline).group(0)})
		if re.search(r"</({0})>".format(rawElements), rawline):
			preDepth = max(0, preDepth - 1)
			continue
		if preDepth:
			continue

		line = rawline.strip()

		if line == "":
			token = {'type':'blank', 'raw': '\n'}
		# FIXME: Detect the heading ID from heading lines
		elif "headings" in features and re.match(r"={3,}\s*(\{#[\w-]+\})?\s*$", line):
			# h1 underline
			match = re.match(r"={3,}\s*(\{#[\w-]+\})?\s*$", line)
			token = {'type':'equals-line', 'raw': rawline}
			if match.group(1):
				token['id'] = match.group(1)[2:-1]
		elif "headings" in features and re.match(r"-{3,}\s*(\{#[\w-]+\})?\s*$", line):
			# h2 underline
			match = re.match(r"-{3,}\s*(\{#[\w-]+\})?\s*$", line)
			token = {'type':'dash-line', 'raw': rawline}
			if match.group(1):
				token['id'] = match.group(1)[2:-1]
		elif "headings" in features and re.match(r"(#{1,5})\s+(.+?)(\1\s*\{#[\w-]+\})?\s*$", line):
			# single-line heading
			match = re.match(r"(#{1,5})\s+(.+?)(\1\s*\{#[\w-]+\})?\s*$", line)
			level = len(match.group(1))+1
			token = {'type':'heading', 'text': match.group(2).strip(), 'raw':rawline, 'level': level}
			match = re.search(r"\{#([\w-]+)\}\s*$", line)
			if match:
				token['id'] = match.group(1)
		elif re.match(r"\d+\.\s", line):
			match = re.match(r"\d+\.\s+(.*)", line)
			token = {'type':'numbered', 'text': match.group(1), 'raw':rawline}
		elif re.match(r"[*+-]\s", line):
			match = re.match(r"[*+-]\s+(.*)", line)
			token = {'type':'bulleted', 'text': match.group(1), 'raw':rawline}
		elif re.match(r"<", line):
			if re.match(r"<<", line) or re.match(r"<({0})[ >]".format(allowedStartElements), line):
				token = {'type':'text', 'text': line, 'raw': rawline}
			else:
				token = {'type':'raw', 'raw': rawline}
		else:
			token = {'type':'text', 'text': line, 'raw': rawline}
		token['prefix'] = re.match(r"( {4}|\t)*", rawline).group(0)
		tokens.append(token)
		#print (" " * (11 - len(token['type']))) + token['type'] + ": " + token['raw'],

	return tokens

def parseTokens(tokens):
	'''
	Token types:
	eof
	blank
	equals-line
	dash-line
	heading
	numbered
	bulleted
	text
	raw
	'''
	stream = TokenStream(tokens)
	lines = []

	while True:
		if stream.ended():
			break
		elif stream.currtype() == 'raw':
			lines.append(stream.currraw())
			stream.advance()
		elif stream.currtype() == 'heading':
			lines += parseSingleLineHeading(stream)
		elif stream.currtype() == 'text' and stream.nexttype() in ('equals-line', 'dash-line'):
			lines += parseMultiLineHeading(stream)
		elif stream.currtype() == 'text' and stream.prevtype() == 'blank':
			lines += parseParagraph(stream)
		elif stream.currtype() == 'bulleted':
			lines += parseBulleted(stream)
		else:
			lines.append(stream.currraw())
			stream.advance()

	#for line in lines:
	#	print line,

	return lines

# Each parser gets passed the stream
# and must return the lines it returns.
# The stream should be advanced to the *next* line,
# after the lines you've used up dealing with the construct.

def parseSingleLineHeading(stream):
	if "id" in stream.curr():
		idattr = " id='{0}'".format(stream.currid())
	else:
		idattr = ""
	lines = ["<h{level}{idattr}>{text}</h{level}>\n".format(idattr=idattr, **stream.curr())]
	stream.advance()
	return lines

def parseMultiLineHeading(stream):
	if stream.nexttype() == "equals-line":
		level = 2
	elif stream.nexttype() == "dash-line":
		level = 3
	else:
		die("Markdown parser error: tried to parse a multiline heading from:\n{0}{1}{2}", stream.prevraw(), stream.currraw(), stream.nextraw())
	if "id" in stream.next():
		idattr = " id='{0}'".format(stream.nextid())
	else:
		idattr = ""
	lines = ["<h{level}{idattr}>{text}</h{level}>\n".format(idattr=idattr, level=level, **stream.curr())]
	stream.advance(2)
	return lines

def parseParagraph(stream):
	line = stream.currtext()
	initialPrefix = stream.currprefix()
	endTag = "</p>"
	if line.lower().startswith("note: ") or line.lower().startswith("note, "):
		p = "<p class='note'>"
	elif line.lower().startswith("issue: "):
		line = line[7:]
		p = "<p class='issue'>"
	elif line.lower().startswith("advisement: "):
		line = line[12:]
		p = "<strong class='advisement'>"
		endTag = "</strong>"
	else:
		p = "<p>"
	lines = ["{0}{1}\n".format(p, line)]
	while True:
		stream.advance()
		try:
			if stream.currtype() in ("eof", "blank") or not stream.currprefix().startswith(initialPrefix):
				lines[-1] = lines[-1].rstrip() + endTag + "\n"
				return lines
		except AttributeError, e:
			print stream.curr()
			print str(e)
		lines.append(stream.currraw())

def parseBulleted(stream):
	prefix = stream.currprefix()
	prefixLen = len(prefix)

	def parseItem(stream):
		# Assumes it's being called with curr being a bulleted line.
		# Remove the bulleted part from the line
		firstLine = re.match(r"\s*[*+-]\s+(.*)", stream.currraw()).group(1)
		lines = [firstLine]
		while True:
			stream.advance()
			# All the conditions that indicate we're *past* the end of the item.
			if stream.currtype() == 'bulleted' and stream.currprefix() == prefix:
				return lines
			if not stream.currprefix().startswith(prefix):
				return lines
			if stream.currtype() == 'blank' and stream.nexttype() != 'bulleted':
				return lines
			if stream.currtype() == 'eof':
				return lines
			# Remove the prefix from each line before adding it.
			lines.append(stream.currraw()[prefixLen:])

	def getItems(stream):
		while True:
			# The conditions that indicate we're past the end of the list itself
			if stream.currtype() == 'eof':
				return
			if stream.currtype() == 'blank' and stream.nexttype() != 'bulleted':
				return
			yield parseItem(stream)

	lines = ["<ul>"]
	for li_lines in getItems(stream):
		lines.append("<li>")
		lines.extend(li_lines)
		lines.append("</li>")
	lines.append("</ul>")
	return lines


class TokenStream:
	def __init__(self, tokens, before={'type':'blank','raw':'\n','prefix':''}, after={'type':'eof','raw':'','prefix':''}):
		self.tokens = tokens
		self.i = 0
		self.before = before
		self.after = after

	def __len__(self):
		return len(self.tokens)

	def ended(self):
		return self.i >= len(self)

	def nth(self, i):
		if i < 0:
			return self.before
		elif i >= len(self):
			return self.after
		else:
			return self.tokens[i]

	def prev(self, i=1):
		return self.nth(self.i - i)

	def curr(self):
		return self.nth(self.i)

	def next(self, i=1):
		return self.nth(self.i + i)

	def advance(self, i=1):
		self.i += i
		return self.curr()

	def __getattr__(self, name):
		if len(name) >= 5 and name[0:4] in ("prev", "curr", "next"):
			tokenDir = name[0:4]
			attrName = name[4:]
			def _missing(i=1):
				if tokenDir == "prev":
					tok = self.prev(i)
				elif tokenDir == "next":
					tok = self.next(i)
				else:
					tok = self.curr()
				if attrName in tok:
					return tok[attrName]
				else:
					raise AttributeError, attrName
			return _missing

# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals
import re
import json
from itertools import *
from .messages import *

def parse(lines, numSpacesForIndentation, features=None):
	tokens = tokenizeLines(lines, numSpacesForIndentation, features)
	return parseTokens(tokens, numSpacesForIndentation)

def tokenizeLines(lines, numSpacesForIndentation, features=None):
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

	for i, rawline in enumerate(lines):
		# Don't parse anything while you're inside certain elements
		if re.search(r"<({0})[ >]".format(rawElements), rawline):
			preDepth += 1
		if preDepth:
			tokens.append({'type':'raw', 'raw':rawline, 'prefixlen': float('inf'), 'line': i})
		if re.search(r"</({0})>".format(rawElements), rawline):
			preDepth = max(0, preDepth - 1)
			continue
		if preDepth:
			continue

		line = rawline.strip()

		if line == "":
			token = {'type':'blank', 'raw': '\n'}
		# FIXME: Detect the heading ID from heading lines
		elif "headings" in features and re.match(r"={3,}\s*$", line):
			# h1 underline
			match = re.match(r"={3,}\s$", line)
			token = {'type':'equals-line', 'raw': rawline}
		elif "headings" in features and re.match(r"-{3,}\s*$", line):
			# h2 underline
			match = re.match(r"-{3,}\s*$", line)
			token = {'type':'dash-line', 'raw': rawline}
		elif "headings" in features and re.match(r"(#{1,5})\s+(.+?)(\1\s*\{#[^ }]+\})?\s*$", line):
			# single-line heading
			match = re.match(r"(#{1,5})\s+(.+?)(\1\s*\{#[^ }]+\})?\s*$", line)
			level = len(match.group(1))+1
			token = {'type':'heading', 'text': match.group(2).strip(), 'raw':rawline, 'level': level}
			match = re.search(r"\{#([\w-]+)\}\s*$", line)
			if match:
				token['id'] = match.group(1)
		elif re.match(r"\d+\.\s", line):
			match = re.match(r"\d+\.\s+(.*)", line)
			token = {'type':'numbered', 'text': match.group(1), 'raw':rawline}
		elif re.match(r"\d+\.$", line):
			token = {'type':'numbered', 'text': "", 'raw':rawline}
		elif re.match(r"[*+-]\s", line):
			match = re.match(r"[*+-]\s+(.*)", line)
			token = {'type':'bulleted', 'text': match.group(1), 'raw':rawline}
		elif re.match(r"[*+-]$", line):
			token = {'type':'bulleted', 'text': "", 'raw':rawline}
		elif re.match(r":{1,2}\s+", line):
			match = re.match(r"(:{1,2})\s+(.*)", line)
			type = 'dt' if len(match.group(1)) == 1 else 'dd'
			token = {'type':type, 'text': match.group(2), 'raw':rawline}
		elif re.match(r":{1,2}$", line):
			match = re.match(r"(:{1,2})", line)
			type = 'dt' if len(match.group(1)) == 1 else 'dd'
			token = {'type':type, 'text': "", 'raw':rawline}
		elif re.match(r"<", line):
			if re.match(r"<<", line) or re.match(r"</?({0})[ >]".format(allowedStartElements), line):
				token = {'type':'text', 'text': line, 'raw': rawline}
			else:
				token = {'type':'htmlblock', 'raw': rawline}
		else:
			token = {'type':'text', 'text': line, 'raw': rawline}

		if token['type'] == "blank":
			token['prefixlen'] = float('inf')
		else:
			token['prefixlen'] = prefixLen(rawline, numSpacesForIndentation)
		token['line'] = i
		tokens.append(token)
		#print (" " * (11 - len(token['type']))) + token['type'] + ": " + token['raw'],

	return tokens

def prefixLen(text, numSpacesForIndentation):
	i = 0
	prefixLen = 0
	while i < len(text):
		if text[i] == "\t":
			i += 1
			prefixLen += 1
		elif text[i:i+numSpacesForIndentation] == " " * numSpacesForIndentation:
			i += numSpacesForIndentation
			prefixLen += 1
		else:
			break
	return prefixLen

def stripPrefix(token, numSpacesForIndentation, len):
	'''Removes len number of prefix groups'''

	text = token['raw']

	# Don't mess with "infinite" prefix lines
	if token['prefixlen'] == float('inf'):
		return text

	# Allow empty lines
	if text.strip() == "":
		return text

	offset = 0
	for x in range(len):
		if text[offset] == "\t":
			offset += 1
		elif text[offset:offset+numSpacesForIndentation] == " " * numSpacesForIndentation:
			offset += numSpacesForIndentation
		else:
			die("Line {i} isn't indented enough (needs {0} indent{plural}) to be valid Markdown:\n\"{1}\"", len, text[:-1], plural="" if len==1 else "s", i=token['line'])
	return text[offset:]


def parseTokens(tokens, numSpacesForIndentation):
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
	htmlblock
	raw
	'''
	stream = TokenStream(tokens, numSpacesForIndentation)
	lines = []

	while True:
		if stream.ended():
			break
		elif stream.currtype() in ('raw', 'htmlblock'):
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
		elif stream.currtype() == 'numbered':
			lines += parseNumbered(stream)
		elif stream.currtype() in ("dt", "dd"):
			lines += parseDl(stream)
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
	match = re.search(r"(.*?)\s*\{\s*#([\w-]+)\s*\}\s*$", stream.currtext())
	if match:
		text = match.group(1)
		idattr = "id='{0}'".format(match.group(2))
	else:
		text = stream.currtext()
		idattr = ""
	lines = ["<h{level} {idattr} >{htext}</h{level}>\n".format(idattr=idattr, level=level, htext=text, **stream.curr())]
	stream.advance(2)
	return lines

def parseParagraph(stream):
	line = stream.currtext()
	initialPrefixLen = stream.currprefixlen()
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
		if stream.currtype() not in ["text"] or stream.currprefixlen() < initialPrefixLen:
			lines[-1] = lines[-1].rstrip() + endTag + "\n"
			return lines
		lines.append(stream.currraw())

def parseBulleted(stream):
	prefixLen = stream.currprefixlen()
        numSpacesForIndentation = stream.numSpacesForIndentation

	def parseItem(stream):
		# Assumes it's being called with curr being a bulleted line.
		# Remove the bulleted part from the line
		firstLine = stream.currtext() + "\n"
		lines = [firstLine]
		while True:
			stream.advance()
			# All the conditions that indicate we're *past* the end of the item.
			if stream.currtype() == 'bulleted' and stream.currprefixlen() == prefixLen:
				return lines
			if stream.currprefixlen() < prefixLen:
				return lines
			if stream.currtype() == 'blank' and stream.nexttype() != 'bulleted' and stream.nextprefixlen() <= prefixLen:
				return lines
			if stream.currtype() == 'eof':
				return lines
			# Remove the prefix from each line before adding it.
			lines.append(stripPrefix(stream.curr(), numSpacesForIndentation, prefixLen+1))

	def getItems(stream):
		while True:
			# The conditions that indicate we're past the end of the list itself
			if stream.currtype() == 'eof':
				return
			if stream.currtype() == 'blank' and stream.nexttype() != 'bulleted' and stream.nextprefixlen() <= prefixLen:
				return
			if stream.currtype() == 'blank':
				stream.advance()
			yield parseItem(stream)

	lines = ["<ul>"]
	for li_lines in getItems(stream):
		lines.append("<li data-md>")
		lines.extend(parse(li_lines, numSpacesForIndentation))
		lines.append("</li>")
	lines.append("</ul>")
	return lines

def parseNumbered(stream):
	prefixLen = stream.currprefixlen()
        numSpacesForIndentation = stream.numSpacesForIndentation

	def parseItem(stream):
		# Assumes it's being called with curr being a numbered line.
		# Remove the numbered part from the line
		firstLine = stream.currtext() + "\n"
		lines = [firstLine]
		while True:
			stream.advance()
			# All the conditions that indicate we're *past* the end of the item.
			if stream.currtype() == 'numbered' and stream.currprefixlen() == prefixLen:
				return lines
			if stream.currprefixlen() < prefixLen:
				return lines
			if stream.currtype() == 'blank' and stream.nexttype() != 'numbered' and stream.nextprefixlen() <= prefixLen:
				return lines
			if stream.currtype() == 'eof':
				return lines
			# Remove the prefix from each line before adding it.
			lines.append(stripPrefix(stream.curr(), numSpacesForIndentation, prefixLen+1))

	def getItems(stream):
		while True:
			# The conditions that indicate we're past the end of the list itself
			if stream.currtype() == 'eof':
				return
			if stream.currtype() == 'blank' and stream.nexttype() != 'numbered' and stream.nextprefixlen() <= prefixLen:
				return
			if stream.currtype() == 'blank':
				stream.advance()
			yield parseItem(stream)

	lines = ["<ol>"]
	for li_lines in getItems(stream):
		lines.append("<li data-md>")
		lines.extend(parse(li_lines, numSpacesForIndentation))
		lines.append("</li>")
	lines.append("</ol>")
	return lines

def parseDl(stream):
	prefixLen = stream.currprefixlen()
        numSpacesForIndentation = stream.numSpacesForIndentation

	def parseItem(stream):
		# Assumes it's being called with curr being a numbered line.
		# Remove the numbered part from the line
		firstLine = stream.currtext() + "\n"
		type = stream.currtype()
		lines = [firstLine]
		while True:
			stream.advance()
			# All the conditions that indicate we're *past* the end of the item.
			if stream.currtype() in ('dt', 'dd') and stream.currprefixlen() == prefixLen:
				return type, lines
			if stream.currprefixlen() < prefixLen:
				return type, lines
			if stream.currtype() == 'blank' and stream.nexttype() not in ('dt', 'dd') and stream.nextprefixlen() <= prefixLen:
				return type, lines
			if stream.currtype() == 'eof':
				return type, lines
			# Remove the prefix from each line before adding it.
			lines.append(stripPrefix(stream.curr(), numSpacesForIndentation, prefixLen+1))

	def getItems(stream):
		while True:
			# The conditions that indicate we're past the end of the list itself
			if stream.currtype() == 'eof':
				return
			if stream.currtype() == 'blank' and stream.nexttype() not in ('dt', 'dd') and stream.nextprefixlen() <= prefixLen:
				return
			if stream.currtype() == 'blank':
				stream.advance()
			yield parseItem(stream)

	lines = ["<dl>"]
	for type, di_lines in getItems(stream):
		lines.append("<{0} data-md>".format(type))
		lines.extend(parse(di_lines, numSpacesForIndentation))
		lines.append("</{0}>".format(type))
	lines.append("</dl>")
	return lines



class TokenStream:
	def __init__(self, tokens, numSpacesForIndentation, before={'type':'blank','raw':'\n','prefixlen':0}, after={'type':'eof','raw':'','prefixlen':0}):
		self.tokens = tokens
		self.i = 0
                self.numSpacesForIndentation = numSpacesForIndentation
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
					return tok['raw']
					raise AttributeError, attrName
			return _missing

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

	if features is None:
		features = set(["headings"])

	# Inline elements that are allowed to start a "normal" line of text.
	# Any other element will instead be an HTML line and will close paragraphs, etc.
	allowedStartElements = "em|strong|i|b|u|dfn|a|code|var"

	tokens = []
	preDepth = 0
	rawElements = "pre|code|style|script"

	for rawline in lines:
		# Dont' parse anything while you're inside certain elements
		if re.search(r"<({0})".format(rawElements), rawline):
			preDepth += 1
		if preDepth:
			tokens.append({'type':'raw', 'raw':rawline})
		if re.search(r"</({0})>".format(rawElements), rawline):
			preDepth = max(0, preDepth - 1)
			continue
		if preDepth:
			continue

		line = rawline.strip()

		if line == "":
			token = {'type':'blank', 'raw': '\n'}
		# FIXME: Detect the heading ID from heading lines
		elif "headings" in features and re.match(r"={3,}(\{#[\w-]+\})?\s*$", line):
			# h1 underline
			match = re.match(r"={3,}(\{#[\w-]+\})?\s*$", line)
			token = {'type':'equals-line', 'raw': rawline}
			if match.group(1):
				token['id'] = match.group(1)[2:-1]
		elif "headings" in features and re.match(r"-{3,}(\{#[\w-]+\})?\s*$", line):
			# h2 underline
			match = re.match(r"-{3,}(\{#[\w-]+\})?\s*$", line)
			token = {'type':'dash-line', 'raw': rawline}
			if match.group(1):
				token['id'] = match.group(1)[2:-1]
		elif "headings" in features and re.match(r"(#{2,6})\s*(.+)(\1\{#[\w-]+\})?", line):
			# single-line heading
			match = re.match(r"(#{2,6})\s*(.+)(\1\{#[\w-]+\})?", line)
			level = len(match.group(1))+1
			token = {'type':'heading', 'text': line.strip("#"), 'raw':rawline, 'level': level}
			if re.search(r"\{#[\w-]+\}\s*$", line):
				token['id'] = re.search(r"\{#([\w-]+)\}\s*$", line)
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
		token['prefix'] = re.match(r"([ \t]*)\n?", rawline).group(1)
		tokens.append(token)
		#print (" " * (11 - len(token['type']))) + token['type'] + ": " + token['raw'],

	return tokens

def parseTokens(tokens):
	stream = TokenStream(tokens)
	lines = []

	while True:
		if stream.ended():
			break
		elif stream.currtype() == 'raw':
			lines.append(stream.currraw())
			stream.advance()
		elif stream.currtype() == 'heading':
			newlines, stream = parseSingleLineHeading(stream)
			lines += newlines
		elif stream.currtype() == 'text' and stream.nexttype() in ('equals-line', 'dash-line'):
			newlines, stream = parseMultiLineHeading(stream)
			lines += newlines
		elif stream.currtype() == 'text' and stream.prevtype() == 'blank':
			newlines, stream = parseParagraph(stream)
			lines += newlines

		else:
			lines.append(stream.currraw())
			stream.advance()

	return lines

# Each parser gets passed the prev, current, and next tokens,
# plus the rest of the stream.
# It must return an array of lines to be added to the document
# (which must end in a \n)
# and the "next" token back
# (typically just what was passed, unless you're consuming more lines)

def parseSingleLineHeading(stream):
	if "id" in stream.curr():
		idattr = " id='{0}'".format(stream.currid())
	else:
		idattr = ""
	lines = ["<h{level}{idattr}>{text}</h{level}>\n".format(idattr=idattr, **stream.curr())]
	stream.advance()
	return lines, stream

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
	return lines, stream

def parseParagraph(stream):
	line = stream.currtext()
	if line.startswith("Note: ") or line.startswith("Note, "):
		p = "<p class='note'>"
	elif line.startswith("Issue: "):
		p = "<p class='issue'>"
	else:
		p = "<p>"
	lines = ["{0}{1}\n".format(p, line)]
	while True:
		stream.advance()
		if stream.currtype() in ("eof", "blank", "raw"):
			lines[-1] = lines[-1][0:-1] + "</p>" + "\n"
			return lines, stream
		lines.append(stream.currraw())





class TokenStream:
	def __init__(self, tokens, before={'type':'blank','raw':'\n'}, after={'type':'eof','raw':''}):
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

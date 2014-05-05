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
			token = {'type':'blank', 'raw': rawline}
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
			if re.match(r"<<", line) or re.match(r"<({0})".format(allowedStartElements), line):
				token = {'type':'text', 'text': line, 'raw': rawline}
			else:
				token = {'type':'raw', 'raw': rawline}
		else:
			token = {'type':'text', 'text': line, 'raw': rawline}
		token['prefix'] = re.match(r"([ \t]*)\n?", rawline).group(1)
		tokens.append(token)

	return tokens

def parseTokens(tokens):
	tokens = streamFromList(tokens)
	lines = []

	token = {'type':'blank', 'raw': ''}
	next = consume(tokens)
	while True:
		prev = token
		prevType = prev['type']
		token = next
		tokenType = token['type']
		next = consume(tokens)
		nextType = next['type']

		if tokenType == 'eof':
			break
		elif tokenType == 'raw':
			lines.append(token['raw'])
		elif tokenType == 'heading':
			newlines, next = parseSingleLineHeading(prev, token, next, tokens)
			lines += newlines
		elif tokenType == 'text' and nextType in ('equals-line', 'dash-line'):
			newlines, next = parseMultiLineHeading(prev, token, next, tokens)
			lines += newlines
		elif tokenType == 'text' and prevType == 'blank':
			newlines, next = parseParagraph(prev, token, next, tokens)
			lines += newlines
		else:
			lines.append(token['raw'])

	return lines

# Each parser gets passed the prev, current, and next tokens,
# plus the rest of the stream.
# It must return an array of lines to be added to the document
# (which must end in a \n)
# and the "next" token back
# (typically just what was passed, unless you're consuming more lines)

def parseSingleLineHeading(prev, token, next, stream):
	if "id" in next:
		idattr = " id='{0}'".format(next['id'])
	else:
		idattr = ""
	return ["<h{level}{idattr}>{text}</h{level}>\n".format(idattr=idattr, **token)], next

def parseMultiLineHeading(prev, token, next, stream):
	if next['type'] == "equals-line":
		level = 2
	elif next['type'] == "dash-line":
		level = 3
	else:
		die("Markdown parser error: tried to parse a multiline heading from:\n{0}{1}{2}", prev['raw'], token['raw'], next['raw'])
	if "id" in next:
		idattr = " id='{0}'".format(next['id'])
	else:
		idattr = ""
	lines = ["<h{level}{idattr}>{text}</h{level}>\n".format(idattr=idattr, level=level **token)]
	next = consume(tokens)
	return lines, next

def parseParagraph(prev, token, next, stream):
	line = token['text']
	if line.startswith("Note: ") or line.startswith("Note, "):
		p = "<p class='note'>"
	elif line.startswith("Issue: "):
		p = "<p class='issue'>"
	else:
		p = "<p>"
	lines = ["{0}{1}\n".format(p, line)]
	while True:
		if next['type'] in ("eof", "blank", "raw"):
			return lines, next
		token = next
		next = consume(stream)
		lines.append(token['text'])




def streamFromList(l):
	return chain(l, repeat({'type':'eof'}))

def consume(iterable):
    "Returns the first items in the iterable."
    return list(islice(iterable, 1))[0]

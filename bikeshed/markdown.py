# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals
import itertools, collections, re

def consume(iterator, n):
	# Advances an iterator by n steps.
	# If n is None, advances to the end.
	collections.deque(itertools.islice(iterator, n))

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

	it = enumerate(lines)
	for i,rawline in it:
		# Dont' parse anything while you're inside a pre
		if rawline.contains("<pre"):
			preDepth += 1
		if preDepth:
			tokens.append({'type':'raw': 'raw':rawline})
		if rawline.contains("</pre>"):
			preDepth = max(0, preDepth - 1)
			continue
		if preDepth:
			continue

		line = rawline.strip()
		if line == "":
			# blank line
			token = {'type':'blank'}
		elif features.has("headings"):
			elif re.match("-{3,}\s*$", line):
				# h2 underline
				token = {'type':'dash-line', 'raw': rawline}
			elif re.match("(#{2,6})\s*(.+)"):
				# single-line heading
				level = len(re.match("#*").group(0))
				token = {'type':'heading', 'text': line.strip("#"), 'raw':rawline, 'level': level}
		elif re.match("\d+\.\s", line):
			match = re.match("\d+\.\s+(.*)", line)
			token = {'type':'numbered', 'text': match.group(1), 'raw':rawline}
		elif re.match("[*+-]\s", line):
			match = re.match("[*+-]\s+(.*)", line)
			token = {'type':'bulleted', 'text': match.group(1), 'raw':rawline}
		elif re.match("<"):
			if re.match("<<") or re.match("<({0})".format(allowedStartElements)):
				token = {'type':'text', 'text': line, 'raw': rawline}
			else:
				token = {'type':'raw', 'raw': rawline}
		else:
			token = {'type':'text', 'text': line, 'raw': rawline}

		token['prefix'] = re.match("\s*").group(0)
		tokens.append(token)

	return tokens

def parseTokens(tokens):
	start = "start"
	tokens.append({'type':'eof'})
	currElem = None
	elems = []

	it = enumerate(tokens)
	for i, token in it:
		type = token['type']
		nextToken = tokens[i+1]
		nextType = nextToken['type']

		if(state == "start"):
			currElem = None
			if type == "eof":
				break
			elif type == "blank":
				elems.append({'type':'raw', 'raw':''})
			elif type == "heading":
				elems.append(token)


# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals
import re
from itertools import *

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
			# FIXME: Detect the heading ID from heading lines
			if re.match("={3,}\s*$", line):
				# h1 underline
				token = {'type':'equals-line', 'raw': rawline}
			elif re.match("-{3,}\s*$", line):
				# h2 underline
				token = {'type':'dash-line', 'raw': rawline}
			elif re.match("(#{2,6})\s*(.+)"):
				# single-line heading
				level = len(re.match("#*").group(0))+1
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
	tokens = streamFromList(tokens)
	lines = []

	while True:
		token = next(tokens)
		tokenType = token['type']
		next = peek(tokens)
		nextType = next['type']

		if tokenType == 'eof':
			break
		elif tokenType == 'raw':
			lines.append(token['raw'])
		elif tokenType == 'heading':
			lines.append("<h{level}>{text}</h{level}>".format(**token))
		elif tokenType == 'text' and nextType == 'equals-line':
			lines.append("<h2>{text}</h2>".format(**tokens))
			next(tokens)
		elif tokenType == 'text' and nextType == 'dash-line':
			lines.append("<h3>{text}</h3>".format(**tokens))
			next(tokens)
		else:
			lines.append(token['raw'])

	return lines




def streamFromList(l):
	return tee(chain(tokens, repeat({'type':'eof'})), n=1)

def peek(t, i=1):
    """Inspect the i-th upcomping value from a tee object
       while leaving the tee object at its current position.

       Raise an IndexError if the underlying iterator doesn't
       have enough values.

    """
    for value in islice(t.__copy__(), i, None):
        return value
    raise IndexError(i)

def next(iterable):
    "Returns the first items in the iterable."
    return list(islice(iterable, 1))[0]

import re
from .. import h
from ..config import flatten
from . import steps
from .biblio import BiblioShorthand
from .section import SectionShorthand

def walk(doc):
	shorthands = [BiblioShorthand, SectionShorthand]
	processEl(doc.body, shorthands)


def processEl(el, shorthands):
	nodes = h.childNodes(el, clear=True, skipOddNodes=False)
	doneChildren = []
	while nodes:
		node = nodes.pop(0)
		if h.isOddNode(node):
			# Skip non-text, non-element nodes
			doneChildren.append(node)
			continue
		elif h.isElement(node):
			processEl(node, shorthands)
			doneChildren.append(node)
			continue
		elif isinstance(node, str):
			if node.strip() == "":
				doneChildren.append(node)
				continue
			# If I have multiple adjacent text nodes, merge them,
			# since I consider text node boundaries to be significant
			while nodes and isinstance(nodes[0], str):
				node += nodes.pop(0)
			# Find all possible early-matches in the text
			matches = runShorthands(shorthands, node)
			# if no early-matches, we can skip the entire node
			if not matches:
				doneChildren.append(node)
				continue
			# see if any of the early-matches can complete successfully
			for match,shClass in matches:
				result = runMatcher(shClass, match, node[match.end(0):], nodes)
				if not result:
					# nope, try the next one
					continue
				# success! Push the text *before* the match into doneChildren
				# and replace the rest of the nodes with the result
				# then restart the loop
				doneChildren.append(node[:match.start(0)])
				doneChildren.append(result.skips)
				nodes = result.nodes
				break
			else:
				# all of the matchers failed,
				# so the whole text node is unchanged
				doneChildren.append(node)
				continue
	h.appendChild(el, *doneChildren)


def runShorthands(shorthands, text):
	# Given a list of shorthand classes,
	# run each one's associated startRe
	# and return a list of those that matched,
	# sorted by how early they matched
	matches = []
	for sh in shorthands:
		match = sh.startRe.search(text)
		if not match:
			continue
		matches.append([match, sh])
		# See if there are any more, possibly overlapping, matches in the text
		i = match.end()
		while True:
			match = sh.startRe.search(text, i)
			if not match:
				break
			matches.append([match, sh])
			i = match.end()
	# Sort the matches by index in the string
	return sorted(matches, key=lambda x:x[0].start())


def runMatcher(shClass, match, text, restNodes):
	sh = shClass()
	bodyNodes = []
	while True:
		result = sh.respond(match, bodyNodes)
		bodyNodes = []
		if type(result) is steps.Failure:
			return False
		elif type(result) is steps.Success:
			break
		elif type(result) is steps.NextLiteral:
			# next literal needs to match *immediately*,
			# starting from the beginning of the remaining text
			match = result.regex.match(text)
			if not match:
				# couldn't find it, so the whole shorthand is a failure
				return False
			# Set up the text for the next round
			text = text[match.end(0):]
			continue
		elif type(result) is steps.NextBody:
			while True:
				# try to find the body-ending regex anywhere in this text fragment
				match = result.regex.search(text)
				if match:
					# cool, the text before it was in the body
					bodyNodes.append(text[0:match.start(0)])
					# now shorten the text node for the next iteration of the outer loop
					text = text[match.end(0):]
					break
				else:
					# not in this text node
					# so all this text is in the body
					bodyNodes.append(text)
					# search forward for the next text node,
					# popping into bodyNodes as I go
					while restNodes and not isinstance(restNodes[0], str):
						bodyNodes.append(restNodes.pop(0))
					# Whoops, ran out, this is a failure then
					if not restNodes:
						return False
					# I've hit another text node,
					# set it up for the next round of this inner loop
					text = restNodes.pop(0)
		else:
			raise Exception(f"{type(sh)}.respond() returned an unknown value '{result}'; this is a programming error.")

	# I've hit a Succeed result!
	# Now to return the nodes that should be put back into the parent element
	result.nodes = list(flatten([result.nodes, text, *restNodes]))
	return result
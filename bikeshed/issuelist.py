# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals
import io
import re
import sys
from .messages import *

statusStyle = {
  'accepted'  : 'a',
  'retracted' : 'a',
  'rejected'  : 'r',
  'objection' : 'fo',
  'deferred'  : 'd',
  'invalid'   : 'oi',
  'outofscope': 'oi',
};

def printIssueList(infilename=None, outfilename=None):
	if infilename is None:
		printHelpMessage()
		return
	if infilename == "-":
		infile = sys.stdin
	else:
		try:
			infile = io.open(infilename, 'r', encoding="utf-8")
		except Exception, e:
			die("Couldn't read from the infile:\n{0}", str(e))
			return

	lines = infile.readlines()
	headerInfo = extractHeaderInfo(lines, infilename)

	if outfilename is None:
		if infilename == "-":
			outfilename = "issues-{status}-{cdate}.html".format(**headerInfo).lower()
		elif infilename.endswith(".txt"):
			outfilename = infilename[:-4] + ".html"
		else:
			outfilename = infilename + ".html"
	if outfilename == "-":
		outfile = sys.stdout
	else:
		try:
			outfile = io.open(outfilename, 'w', encoding="utf-8")
		except Exception, e:
			die("Couldn't write to outfile:\n{0}", str(e))
			return

	printHeader(outfile, headerInfo)

	printIssues(outfile, lines)


def extractHeaderInfo(lines, infilename):
	title = None
	url = None
	status = None
	for line in lines:
		match = re.match("(Draft|Title|Status):\s*(.*)", line)
		if match:
			if match.group(1) == "Draft":
				url = match.group(2)
			elif match.group(1) == "Title":
				title = match.group(2)
			elif match.group(1) == "Status":
				status = match.group(2).upper()
	if url is None:
		die("Missing 'Draft' metadata.")
		return
	if title is None:
		die("Missing 'Title' metadata.")
		return

	match = re.search("([A-Z]{2,})-([a-z0-9-]+)-(\d{8})", url)
	if match:
		if status is None:
			# Auto-detect from the URL and filename.
			status = match.group(1)
			if status == "WD" and re.search("LC", infilename, re.I):
				status = "LCWD"
		shortname = match.group(2)
		cdate = match.group(3)
		date = "{0}-{1}-{2}".format(*re.match("(\d{4})(\d\d)(\d\d)", cdate).groups())
	else:
		die("Draft url needs to have the format /status-shortname-date/. Got:\n{0}", url)
		return
	return {
		'title': title,
		'date': date,
		'cdate': cdate,
		'shortname': shortname,
		'status': status,
		'url': url
	}


def printHelpMessage():
		die('''
Pass in issues list filename for processing!

~~~~~~~~~~~~~~~~~~~~~ Template for issues-list.txt ~~~~~~~~~~~~~~~~~~~~~

Draft:    http://www.w3.org/TR/2013/WD-css-foo-3-20130103/
Title:    CSS Foo Level 3
... anything else you want here, except 4 dashes ...

----
Issue 1.
Summary:  [summary]
From:     [name]
Comment:  [url]
Response: [url]
Closed:   [Accepted/OutOfScope/Invalid/Rejected/Retracted ... or replace this "Closed" line with "Open"]
Verified: [url]
Resolved: Editorial/Bugfix (for obvious fixes)/Editors' discretion/[url to minutes]
----
Issue 2.
...''')


def printHeader(outfile, headerInfo):
	outfile.write('''<!DOCTYPE html>
<title>{title} Disposition of Comments for {date} {status}</title>
<style type="text/css">
  .a  {{ background: lightgreen }}
  .d  {{ background: lightblue  }}
  .r  {{ background: orange     }}
  .fo {{ background: red        }}
  .open   {{ border: solid red; padding: 0.2em; }}
  :target {{ box-shadow: 0.25em 0.25em 0.25em;  }}
</style>

<h1>{title} Disposition of Comments for {date} {status}</h1>

<p>Last call document: <a href="{url}">{url}</a>

<p>Editor's draft: <a href="http://dev.w3.org/csswg/{shortname}/">http://dev.w3.org/csswg/{shortname}/</a>

<p>The following color coding convention is used for comments:</p>

<ul>
 <li class="a">Accepted or Rejected and positive response
 <li class="r">Rejected and no response
 <li class="fo">Rejected and negative response
 <li class="d">Deferred
 <li class="oi">Out-of-Scope or Invalid and not verified
</ul>

<p class=open>Open issues are marked like this</p>

<p>An issue can be closed as <code>Accepted</code>, <code>OutOfScope</code>,
<code>Invalid</code>, <code>Rejected</code>, or <code>Retracted</code>.
<code>Verified</code> indicates commentor's acceptance of the response.</p>
		'''.format(**headerInfo))


def printIssues(outfile, lines):
	text = ''.join(lines)
	issues = text.split('----\n')[1:]
	for issue in issues:
		issue = issue.strip().replace("&", "&amp;").replace("<", "&lt;")
		if issue == "":
			continue
		originaltext = issue[:]

		# Issue number
		issue = re.sub(r"Issue (\d+)\.", r"Issue \1. <a href='#issue-\1'>#</a>", issue)
		match = re.search(r"Issue (\d+)\.", issue)
		if match:
			index = match.group(1)
		else:
			die("Issues must contain a line like 'Issue 1.'. Got:\n{0}", originaltext)

		# Color coding
		if re.search(r"\nVerified:\s+http", issue):
			code = 'a'
		elif re.search(r"\n(Closed|Open):\s+\S+", issue):
			code = re.search(r"\n(Closed|Open):\s+(\S+)", issue).group(2)
			code = statusStyle[code.lower()]
		else:
			code = ''
		if re.search(r"\nOpen", issue):
			code += " open"

		# Linkify urls
		issue = re.sub(r"(http:\S+)", r"<a href='\1'>\1</a>", issue)

		# And print it
		outfile.write("<pre class='{0}' id='issue-{1}'>\n".format(code, index))
		outfile.write(issue)
		outfile.write("</pre>\n")

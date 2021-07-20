# pylint: disable=R1732

import glob
import re
import sys

from .messages import *

statusStyle = {
    "accepted": "a",
    "retracted": "a",
    "rejected": "r",
    "objection": "fo",
    "deferred": "d",
    "invalid": "oi",
    "outofscope": "oi",
}


def printIssueList(infilename=None, outfilename=None):
    if infilename is None:
        infilename = findIssuesFile()
        if infilename is None:
            printHelpMessage()
            return
    if infilename == "-":
        infile = sys.stdin
    else:
        for suffix in [".txt", "txt", ""]:
            try:
                infile = open(infilename + suffix, encoding="utf-8")
                infilename += suffix
                break
            except Exception:
                pass
        else:
            die("Couldn't read from the infile(s)")
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
            outfile = open(outfilename, "w", encoding="utf-8")
        except Exception as e:
            die("Couldn't write to outfile:\n{0}", str(e))
            return

    printHeader(outfile, headerInfo)

    printIssues(outfile, lines)
    printScript(outfile)


def findIssuesFile():
    # Look for digits in the filename, and use the one with the largest number if it's unique.
    def extractNumber(filename):
        number = re.sub(r"\D", "", filename)
        return number if number else None

    possibleFiles = [*glob.glob("issues*.txt"), *glob.glob("*.bsi")]
    if len(possibleFiles) == 0:
        die(
            "Can't find an 'issues*.txt' or '*.bsi' file in this folder. Explicitly pass a filename."
        )
        return
    if len(possibleFiles) == 1:
        return possibleFiles[0]

    # If there are more than one, assume they contain either an index or a YYYYMMDD date,
    # and select the largest such value.
    possibleFiles = [
        (extractNumber(fn), fn) for fn in possibleFiles if extractNumber(fn) is not None
    ]
    if len(possibleFiles) == 1:
        return possibleFiles[0][1]

    possibleFiles.sort(reverse=True)
    if len(possibleFiles) == 0 or possibleFiles[0][0] == possibleFiles[1][0]:
        die(
            "Can't tell which issues-list file is the most recent. Explicitly pass a filename."
        )
        return
    return possibleFiles[0][1]


def extractHeaderInfo(lines, infilename):
    title = None
    url = None
    status = None
    ed = None
    date = None
    cdate = None
    for line in lines:
        match = re.match(r"(Draft|Title|Status|Date|ED):\s*(.*)", line)
        if match:
            if match.group(1) == "Draft":
                url = match.group(2)
            elif match.group(1) == "Title":
                title = match.group(2)
            elif match.group(1) == "Status":
                status = match.group(2).rstrip()
            elif match.group(1) == "Date":
                date = match.group(2).rstrip()
                cdate = date
                if not re.match(r"(\d{4})-(\d\d)-(\d\d)$", date):
                    die(
                        "Incorrect Date format. Expected YYYY-MM-DD, but got:\n{0}",
                        date,
                    )
            elif match.group(1) == "ED":
                ed = match.group(2).rstrip()
    if url is None:
        die("Missing 'Draft' metadata.")
        return
    if title is None:
        die("Missing 'Title' metadata.")
        return

    match = re.search(r"([A-Z]{2,})-([a-z0-9-]+)-(\d{8})", url)
    if match:
        if status is None:
            # Auto-detect from the URL and filename.
            status = match.group(1)
            if status == "WD" and re.search("LC", infilename, re.I):
                status = "LCWD"
        if ed is None:
            shortname = match.group(2)
            ed = f"http://dev.w3.org/csswg/{shortname}/"
        if date is None:
            cdate = match.group(3)
            date = "{}-{}-{}".format(*re.match(r"(\d{4})(\d\d)(\d\d)", cdate).groups())
    else:
        warn(
            "Autodetection of Shortname, Date, and Status failed; draft url does not match the format /status-shortname-date/. Got:\n{0}",
            url,
        )

    if date is None:
        die("Missing 'Date' metadata.")
        return
    if status is None:
        die("Missing 'Status' metadata.")
        return
    if ed is None:
        die("Missing 'ED' metadata.")
        return

    return {
        "title": title,
        "date": date,
        "cdate": cdate,
        "ed": ed,
        "status": status,
        "url": url,
    }


def printHelpMessage():
    say(
        """Draft:    http://www.w3.org/TR/2013/WD-css-foo-3-20130103/ (Mandatory)
Title:    CSS Foo Level 3 (Mandatory)
Date:     YYYY-MM-DD (Optional if can be autodetected from the Draft's URL)
Status:   CR/FPWD/LCWD/LS/Version/… (Optional if can be autodetected from the Draft's URL)
ED:       https://url.to.the.editor.s/draft/ (Optional, defaults to a csswg editor's draft if shortname can be infered from the Draft's URL)
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
..."""
    )


def printHeader(outfile, headerInfo):
    outfile.write(
        """<!DOCTYPE html>
<meta charset="utf-8">
<title>{title} Disposition of Comments for {date} {status}</title>
<style>
  .a  {{ background: lightgreen }}
  .d  {{ background: lightblue  }}
  .r  {{ background: orange     }}
  .fo {{ background: red        }}
  .open   {{ border: solid red; padding: 0.2em; }}
  :target {{ box-shadow: 0.25em 0.25em 0.25em;  }}
</style>

<h1>{title} Disposition of Comments for {date} {status}</h1>

<p>Review document: <a href="{url}">{url}</a>

<p>Editor's draft: <a href="{ed}">{ed}</a>

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
        """.format(
            **headerInfo
        )
    )


def printIssues(outfile, lines):
    text = "".join(lines)
    issues = text.split("----\n")[1:]
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
        if re.search(r"\nVerified:\s*\S+", issue):
            code = "a"
        elif re.search(r"\n(Closed|Open):\s+\S+", issue):
            match = re.search(r"\n(Closed|Open):\s+(\S+)", issue)
            code = match.group(2)
            if code.lower() in statusStyle:
                code = statusStyle[code.lower()]
            else:
                code = ""
                if match.group(1) == "Closed":
                    warn(
                        "Unknown status value found for issue #{num}: “{code}”",
                        code=code,
                        num=index,
                    )
        else:
            code = ""
        if re.search(r"\nOpen", issue):
            code += " open"

        # Linkify urls
        issue = re.sub(r"((http|https):\S+)", r"<a href='\1'>\1</a>", issue)

        # And print it
        outfile.write(f"<pre class='{code}' id='issue-{index}'>\n")
        outfile.write(issue)
        outfile.write("</pre>\n")


def printScript(outfile):
    outfile.write(
        """<script>
(function () {
    var sheet = document.styleSheets[0];
    function addCheckbox(className) {
        var element = document.querySelector('*.' + className);
        var label = document.createElement('label');
        label.innerHTML = element.innerHTML;
        element.innerHTML = null;
        var check = document.createElement('input');
        check.type = 'checkbox';
        if (className == 'open') {
            check.checked = false;
            sheet.insertRule('pre:not(.open)' + '{}', sheet.cssRules.length);
            check.onchange = function (e) {
                rule.style.display = this.checked ? 'none' : 'block';
            }
        }
        else {
            check.checked = true;
            sheet.insertRule('pre.' + className + '{}', sheet.cssRules.length);
            check.onchange = function (e) {
                rule.style.display = this.checked ? 'block' : 'none';
            }
        }
        var rule = sheet.cssRules[sheet.cssRules.length - 1];
        element.appendChild(label);
        label.insertBefore(check, label.firstChild);
    }
    ['a', 'd', 'fo', 'oi', 'r', 'open'].forEach(addCheckbox);
}());
</script>
"""
    )

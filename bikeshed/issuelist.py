# pylint: disable=R1732

from __future__ import annotations

import dataclasses
import glob
import re
import sys

from . import messages as m
from . import t

if t.TYPE_CHECKING:
    import io  # pylint: disable=unused-import

statusStyle = {
    "accepted": "a",
    "retracted": "a",
    "rejected": "r",
    "objection": "fo",
    "deferred": "d",
    "invalid": "oi",
    "outofscope": "oi",
}


@dataclasses.dataclass
class HeaderInfo:
    title: str
    url: str
    status: str
    ed: str
    date: str
    cdate: str
    intro: str | None = None


def printIssueList(infilename: str | None = None, outfilename: str | None = None) -> None:
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
                infile = open(infilename + suffix, encoding="utf-8")  # noqa: SIM115
                infilename += suffix
                break
            except Exception:  # noqa: S110
                pass
        else:
            m.die("Couldn't read from the infile(s)")
            return

    lines = infile.readlines()
    headerInfo = extractHeaderInfo(lines, infilename)
    if headerInfo is None:
        m.die("Couldn't parse header info.")
        return

    if outfilename is None:
        if infilename == "-":
            outfilename = f"issues-{headerInfo.status}-{headerInfo.cdate}.html".lower()
        elif infilename.endswith(".txt"):
            outfilename = infilename[:-4] + ".html"
        else:
            outfilename = infilename + ".html"
    if outfilename == "-":
        outfile = sys.stdout
    else:
        try:
            outfile = open(outfilename, "w", encoding="utf-8")  # noqa: SIM115
        except Exception as e:
            m.die(f"Couldn't write to outfile:\n{e}")
            return

    printHeader(outfile, headerInfo)

    printIssues(outfile, lines)
    printScript(outfile)


def findIssuesFile() -> str | None:
    # Look for digits in the filename, and use the one with the largest number if it's unique.
    def extractNumber(filename: str) -> str | None:
        number = re.sub(r"\D", "", filename)
        return number if number else None

    possibleFiles = [*glob.glob("issues*.txt"), *glob.glob("*.bsi")]
    if len(possibleFiles) == 0:
        m.die("Can't find an 'issues*.txt' or '*.bsi' file in this folder. Explicitly pass a filename.")
        return None
    if len(possibleFiles) == 1:
        return possibleFiles[0]

    # If there are more than one, assume they contain either an index or a YYYYMMDD date,
    # and select the largest such value.
    possibleFilesNum = [(extractNumber(fn), fn) for fn in possibleFiles if extractNumber(fn) is not None]
    if len(possibleFilesNum) == 1:
        return possibleFilesNum[0][1]

    possibleFilesNum.sort(reverse=True)
    if len(possibleFilesNum) == 0 or possibleFilesNum[0][0] == possibleFilesNum[1][0]:
        m.die("Can't tell which issues-list file is the most recent. Explicitly pass a filename.")
        return None
    return possibleFilesNum[0][1]


def extractHeaderInfo(lines: t.Sequence[str], infilename: str) -> HeaderInfo | None:
    title = None
    url = None
    status = None
    ed = None
    date = None
    cdate = None
    intro = None
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
                    m.die(f"Incorrect Date format. Expected YYYY-MM-DD, but got:\n{date}")
                    return None
            elif match.group(1) == "ED":
                ed = match.group(2).rstrip()
    if url is None:
        m.die("Missing 'Draft' metadata.")
        return None
    if title is None:
        m.die("Missing 'Title' metadata.")
        return None

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
            match = re.match(r"(\d{4})(\d\d)(\d\d)", cdate)
            assert match is not None
            date = f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    else:
        m.warn(
            f"Autodetection of Shortname, Date, and Status failed; draft url does not match the format /status-shortname-date/. Got:\n{url}",
        )

    if date is None:
        m.die("Missing 'Date' metadata.")
        return None
    if status is None:
        m.die("Missing 'Status' metadata.")
        return None
    if ed is None:
        m.die("Missing 'ED' metadata.")
        return None

    match = re.search(r"^Intro:\s*(.*(\n^$|\n[ \t]+.*)*)", "".join(lines), re.M)
    if match:
        intro = match.group(1)

    return HeaderInfo(
        title=title,
        date=date,
        cdate=t.cast(str, cdate),
        ed=ed,
        status=status,
        url=url,
        intro=intro,
    )


def printHelpMessage() -> None:
    m.say(
        """Draft:    http://www.w3.org/TR/2013/WD-css-foo-3-20130103/ (Mandatory)
Title:    CSS Foo Level 3 (Mandatory)
Date:     YYYY-MM-DD (Optional if can be autodetected from the Draft's URL)
Status:   CR/FPWD/LCWD/LS/Version/… (Optional if can be autodetected from the Draft's URL)
ED:       https://url.to.the.editor.s/draft/ (Optional, defaults to a csswg editor's draft if shortname can be infered from the Draft's URL)
Intro:    <p>Optional markup to be injected into the output document.
          the intro can continue on multiple lines
          as long as they're indented.

          <p>Blank lines in the middle are fine.

... anything else you want here, except 4 dashes ...
... this will not be included in the output ...

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
...""",
    )


def printHeader(outfile: t.TextIO, hi: HeaderInfo) -> None:
    outfile.write(
        f"""<!DOCTYPE html>
<meta charset="utf-8">
<title>{hi.title} Disposition of Comments for {hi.date} {hi.status}</title>
<style>
  .a  {{ background: lightgreen }}
  .d  {{ background: lightblue  }}
  .r  {{ background: orange     }}
  .fo {{ background: red        }}
  .open   {{ border: solid red; padding: 0.2em; }}
  :target {{ box-shadow: 0.25em 0.25em 0.25em;  }}
</style>

<h1>{hi.title} Disposition of Comments for {hi.date} {hi.status}</h1>

<p>Review document: <a href="{hi.url}">{hi.url}</a>

<p>Editor's draft: <a href="{hi.ed}">{hi.ed}</a></p>

{hi.intro or ""}

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
""",
    )


def printIssues(outfile: t.TextIO, lines: list[str]) -> None:
    text = "".join(lines)
    issues = text.split("----\n")[1:]
    for issue in issues:
        issue = issue.strip().replace("&", "&amp;").replace("<", "&lt;")
        if issue == "":
            continue
        originalText = issue[:]

        # Issue number
        issue = re.sub(r"Issue (\d+)\.", r"Issue \1. <a href='#issue-\1'>#</a>", issue)
        match = re.search(r"Issue (\d+)\.", issue)
        if match:
            index = match.group(1)
        else:
            m.die(f"Issues must contain a line like 'Issue 1.'. Got:\n{originalText}")
            continue

        # Color coding
        if re.search(r"\nVerified:\s*\S+", issue):
            code = "a"
        elif re.search(r"\n(Closed|Open):\s+\S+", issue):
            match = re.search(r"\n(Closed|Open):\s+(\S+)", issue)
            assert match is not None
            code = match.group(2)
            if code.lower() in statusStyle:
                code = statusStyle[code.lower()]
            else:
                code = ""
                if match.group(1) == "Closed":
                    m.warn(f"Unknown status value found for issue #{index}: “{code}”")
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


def printScript(outfile: t.TextIO) -> None:
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
""",
    )

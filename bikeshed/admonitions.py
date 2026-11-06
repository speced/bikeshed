from __future__ import annotations

import json
import logging
import re
from collections import namedtuple

import requests

from . import config, h, printjson, repository, t
from . import messages as m
from .translate import _t


def processIssuesAndExamples(doc: t.SpecT) -> None:
    # Add an auto-genned and stable-against-changes-elsewhere id to all issues and
    # examples, and link to remote issues if possible:
    for el in h.findAll(".issue:not([id])", doc):
        el.set("id", h.safeID(doc, "issue-" + h.hashContents(el)))
    for el in h.findAll(".example:not([id])", doc):
        el.set("id", h.safeID(doc, "example-" + h.hashContents(el)))
    for el in h.findAll("[data-remote-issue-id]", doc):
        remoteIssueID = el.get("data-remote-issue-id", "").strip()
        del el.attrib["data-remote-issue-id"]
        # Eventually need to support a way to trigger other repo url structures,
        # but defaulting to GH is fine for now.
        githubMatch = re.match(r"([\w-]+)/([\w-]+)#(\d+)$", remoteIssueID)
        numberMatch = re.match(r"#?(\d+)$", remoteIssueID)
        remoteIssueURL = None
        if githubMatch:
            org, repo, num = githubMatch.groups()
            text = f"[{org}/{repo} Issue #{num}]"
            remoteIssueURL = f"https://github.com/{org}/{repo}/issues/{num}"
            if doc.md.inlineGithubIssues:
                el.set("data-inline-github", f"{org} {repo} {num}")
        elif numberMatch:
            if isinstance(doc.md.repository, repository.GithubRepository):
                remoteIssueURL = doc.md.repository.formatIssueUrl(numberMatch.group(1))
                num = numberMatch.group(1)
                text = f"[Issue #{num}]"
                if doc.md.inlineGithubIssues:
                    org = doc.md.repository.user
                    repo = doc.md.repository.repo
                    el.set("data-inline-github", f"{org} {repo} {num}")
            elif doc.md.issueTrackerTemplate:
                text = f"[Issue {remoteIssueID}]"
                remoteIssueURL = doc.md.issueTrackerTemplate.format(remoteIssueID)
            else:
                m.die(
                    "Saw numeric issue markup, but can't find either a GitHub repo or manual Issue Tracker Template to format it.",
                    el=el,
                )
                continue
        elif doc.md.issueTrackerTemplate:
            text = f"[Issue {remoteIssueID}]"
            remoteIssueURL = doc.md.issueTrackerTemplate.format(remoteIssueID)
        else:
            m.die(f"Can't parse '{remoteIssueID}' as an issue ID.", el=el)
            continue
        if remoteIssueURL:
            if h.tagName(el) == "a":
                el.set("href", remoteIssueURL)
            else:
                h.appendChild(
                    el,
                    " ",
                    h.E.a({"href": remoteIssueURL}, text),
                )
    h.fixupIDs(doc, h.findAll(".issue, .example", doc))


def inlineRemoteIssues(doc: t.SpecT) -> None:
    # Finds properly-marked-up "remote issues",
    # and inlines their contents into the issue.

    # Right now, only github inline issues are supported.
    # More can be supported when someone cares.

    if not isinstance(doc.md.repository, repository.GithubRepository):
        return

    # Collect all the inline issues in the document
    inlineIssues = []
    GitHubIssue = namedtuple("GitHubIssue", ["user", "repo", "num", "el"])
    for el in h.findAll("[data-inline-github]", doc):
        user, repo, num = el.get("data-inline-github", "").split()
        inlineIssues.append(GitHubIssue(user, repo, num, el=el))
        h.removeAttr(el, "data-inline-github")
    if not inlineIssues:
        return

    logging.captureWarnings(True)

    responses = json.loads(doc.dataFile.fetch("github-issues.json", str=True))
    for i, issue in enumerate(inlineIssues):
        issueUserRepo = "{}/{}".format(*issue)
        key = f"{issueUserRepo}/{issue.num}"
        href = "https://github.{}/{}/issues/{}".format(doc.md.repository.ns, issueUserRepo, issue.num)
        url = "{}/repos/{}/issues/{}".format(doc.md.repository.api, issueUserRepo, issue.num)
        m.say("Fetching issue {:-3d}/{:d}: {:s}".format(i + 1, len(inlineIssues), key))

        # Fetch the issues
        headers = {"Accept": "application/vnd.github.v3.html+json"}
        if doc.token is not None:
            headers["Authorization"] = "token " + doc.token
        if key in responses:
            # Have a cached response, see if it changed
            headers["If-None-Match"] = responses[key]["ETag"]

        res = None
        try:
            res = requests.get(url, headers=headers, timeout=5)
        except requests.exceptions.ConnectionError:
            # Offline or something, recover if possible
            if key in responses:
                data = responses[key]
            else:
                m.warn(f"Connection error fetching issue #{issue.num}")
                continue
        except requests.exceptions.ReadTimeout:
            # Took too long
            if key in responses:
                data = responses[key]
            else:
                m.warn(f"Timeout while fetching issue #{issue.num}")
                continue
        except Exception as e:
            # Something else
            if key in responses:
                data = responses[key]
            else:
                m.warn(f"Error while fetching issue #{issue.num}:\n{e}")
                continue

        if res is None:
            # Already handled in the except block
            pass
        elif res.status_code == 304:
            # Unchanged, I can use the cache
            data = responses[key]
        elif res.status_code == 200:
            # Fresh data, prep it for storage
            data = res.json()
            data["ETag"] = res.headers["ETag"]
        elif res.status_code == 401:
            error = res.json()
            if error["message"] == "Bad credentials":
                m.die(f"'{doc.token}' is not a valid GitHub OAuth token. See https://github.com/settings/tokens")
            else:
                m.die(
                    "401 error when fetching GitHub Issues:\n" + printjson.printjson(error),
                )
            continue
        elif res.status_code == 403:
            error = res.json()
            if error["message"].startswith("API rate limit exceeded"):
                m.die(
                    "GitHub Issues API rate limit exceeded. Get an OAuth token from https://github.com/settings/tokens to increase your limit, or just wait an hour for your limit to refresh; Bikeshed has cached all the issues so far and will resume from where it left off.",
                )
            else:
                m.die(
                    "403 error when fetching GitHub Issues:\n" + printjson.printjson(error),
                )
            continue
        elif res.status_code >= 400:
            try:
                error = printjson.printjson(res.json())
            except ValueError:
                error = "First 100 characters of error:\n" + res.text[0:100]
            m.die(f"{res.status_code} error when fetching GitHub Issues:\n" + error)
            continue
        responses[key] = data
        # Put the issue data into the DOM
        el = issue.el
        data = responses[key]
        h.clearContents(el)
        if doc.md.inlineGithubIssues == "title":
            h.appendChild(
                el,
                h.E.a(
                    {"href": href, "class": "marker", "style": "text-transform:none"},
                    key,
                ),
                h.E.a({"href": href}, data["title"]),
            )
            h.addClass(doc, el, "no-marker")
        else:
            h.appendChild(
                el,
                h.E.a(
                    {"href": href, "class": "marker"},
                    _t("Issue #{number} on GitHub: “{title}”").format(number=data["number"], title=data["title"]),
                ),
                *h.parseHTML(data["body_html"]),
            )
            h.addClass(doc, el, "no-marker")
        if el.tag == "p":
            el.tag = "div"
    # Save the cache for later
    try:
        with open(config.scriptPath("spec-data", "github-issues.json"), "w", encoding="utf-8") as f:
            f.write(json.dumps(responses, ensure_ascii=False, indent=2, sort_keys=True))
    except Exception as e:
        m.warn(f"Couldn't save GitHub Issues cache to disk.\n{e}")
    return


def addNoteHeaders(doc: t.SpecT) -> None:
    # Finds <foo heading="bar"> and turns it into a marker-heading
    for el in h.findAll("[heading]", doc):
        h.addClass(doc, el, "no-marker")
        if h.hasClass(doc, el, "note"):
            preText = _t("NOTE: ")
        elif h.hasClass(doc, el, "issue"):
            preText = _t("ISSUE: ")
        elif h.hasClass(doc, el, "example"):
            preText = _t("EXAMPLE: ")
        else:
            preText = ""
        lineNum = lineNumberFromBsLineNumber(el.get("bs-line-number"))
        parseConfig = h.ParseConfig.fromSpec(doc=doc, context="heading='' attribute")
        parsedHeading = h.parseHTML(h.parseText(el.get("heading", ""), parseConfig, startLine=lineNum, context=el))
        h.prependChild(el, h.E.div({"class": "marker"}, preText, *parsedHeading))
        h.removeAttr(el, "heading")


def lineNumberFromBsLineNumber(value: str | None) -> int:
    if value is None:
        return 1
    try:
        return int(value)
    except:
        pass
    try:
        # If it's a 'loc' value: line:col + maybe other context
        num, _, _ = value.partition(":")
        return int(num)
    except:
        pass
    return 1

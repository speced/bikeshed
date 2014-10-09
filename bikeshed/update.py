# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals
import json
import re
import io
from collections import defaultdict
from contextlib import closing
import urllib2

from . import config
from . import biblio
from .messages import *

from .apiclient.apiclient import apiclient

def update(anchors=False, biblio=False, linkDefaults=False, testSuites=False):
    # If all are False, update everything
    updateAnyway = not (anchors or biblio or linkDefaults or testSuites)
    if anchors or updateAnyway:
        updateCrossRefs()
    if biblio or updateAnyway:
        updateBiblio()
    if linkDefaults or updateAnyway:
        updateLinkDefaults()
    if testSuites or updateAnyway:
        updateTestSuites()

def updateCrossRefs():
    try:
        say("Downloading anchor data...")
        shepherd = apiclient.APIClient("https://api.csswg.org/shepherd/", version = "vnd.csswg.shepherd.v1")
        res = shepherd.get("specifications", anchors = True, draft = True)
        # http://test.csswg.org/shepherd/api/spec/?spec=css-flexbox-1&anchors&draft, for manual looking
        if ((not res) or (406 == res.status)):
            die("This version of the anchor-data API is no longer supported. Please update Bikeshed.")
            return
        if res.contentType not in config.anchorDataContentTypes:
            die("Unrecognized anchor-data content-type '{0}'.", res.contentType)
            return
        rawSpecData = res.data
    except Exception, e:
        die("Couldn't download anchor data.  Error was:\n{0}", str(e))
        return

    def linearizeAnchorTree(multiTree, list=None):
        if list is None:
            list = []
        # Call with multiTree being a list of trees
        for item in multiTree:
            if item['type'] not in ("section", "other"):
                list.append(item)
            if item.get('children'):
                linearizeAnchorTree(item['children'], list)
        return list

    specs = dict()
    anchors = defaultdict(list)
    for rawSpec in rawSpecData.values():
        spec = {
            'vshortname': rawSpec['name'],
            'TR': rawSpec.get('base_uri'),
            'ED': rawSpec.get('draft_uri'),
            'title': rawSpec.get('title'),
            'description': rawSpec.get('description')
        }
        match = re.match("(.*)-(\d+)", rawSpec['name'])
        if match:
            spec['shortname'] = match.group(1)
            spec['level'] = int(match.group(2))
        else:
            spec['shortname'] = spec['vshortname']
            spec['level'] = 1
        specs[spec['vshortname']] = spec

        def setStatus(status):
            def temp(obj):
                obj['status'] = status
                return obj
            return temp
        rawAnchorData = map(setStatus('TR'), linearizeAnchorTree(rawSpec.get('anchors', []))) + map(setStatus('ED'), linearizeAnchorTree(rawSpec.get('draft_anchors',[])))
        for rawAnchor in rawAnchorData:
            linkingTexts = rawAnchor.get('linking_text', [rawAnchor.get('title')])
            if linkingTexts[0] is None:
                continue
            anchorType = rawAnchor['type']
            if rawAnchor.get('export_draft'):
                exportED = True
            elif rawAnchor.get('export_official') and not spec['ED']:
                # If it's only exported in TR, normally don't consider it exported for EDs.
                # But do so if it only *exists* as a TR, so an ED export is impossible.
                exportED = True
            else:
                exportED = False
            anchor = {
                'status': rawAnchor['status'],
                'type': anchorType,
                'spec': spec['vshortname'],
                'shortname': spec['shortname'],
                'level': int(spec['level']),
                'export': rawAnchor.get('export', False),
                'normative': rawAnchor.get('normative', False),
                'url': spec[rawAnchor['status']] + rawAnchor['uri'],
                'for': rawAnchor.get('for', [])
            }
            for text in linkingTexts:
                text = re.sub(r'\s+', ' ', text)
                anchors[text.lower()].append(anchor)

    if not config.dryRun:
        try:
            with io.open(config.scriptPath+"/spec-data/specs.json", 'w', encoding="utf-8") as f:
                f.write(unicode(json.dumps(specs, ensure_ascii=False, indent=2)))
        except Exception, e:
            die("Couldn't save spec database to disk.\n{0}", e)
            return
        try:
            with io.open(config.scriptPath+"/spec-data/anchors.data", 'w', encoding="utf-8") as f:
                writeAnchorsFile(f, anchors)
        except Exception, e:
            die("Couldn't save anchor database to disk.\n{0}", e)
            return
    say("Success!")


def updateBiblio():
    say("Downloading biblio data...")
    biblios = defaultdict(list)
    try:
        with closing(urllib2.urlopen("http://specref.jit.su/bibrefs")) as fh:
            biblio.processSpecrefBiblioFile(unicode(fh.read(), encoding="utf-8"), biblios, order=3)
        with closing(urllib2.urlopen("http://dev.w3.org/csswg/biblio.ref")) as fh:
            lines = [unicode(line, encoding="utf-8") for line in fh.readlines()]
            biblio.processReferBiblioFile(lines, biblios, order=4)
    except Exception, e:
        die("Couldn't download the biblio data.\n{0}", e)
    if not config.dryRun:
        try:
            with io.open(config.scriptPath + "/spec-data/biblio.data", 'w', encoding="utf-8") as fh:
                writeBiblioFile(fh, biblios)
        except Exception, e:
            die("Couldn't save biblio database to disk.\n{0}", e)
            return
    say("Success!")


def updateLinkDefaults():
    try:
        say("Downloading link defaults...")
        with closing(urllib2.urlopen("http://dev.w3.org/csswg/autolinker-config.md")) as fh:
            lines = [unicode(line, encoding="utf-8") for line in fh.readlines()]
    except Exception, e:
        die("Couldn't download link defaults data.\n{0}", e)
        return

    currentSpec = None
    currentType = None
    currentFor = None
    data = defaultdict(list)
    data["css21Replacements"] = []
    data["ignoredSpecs"] = []
    data["customDfns"] = []
    for i, line in enumerate(lines):
        # Look for h2
        if re.match("^\s*-+\s*$", line):
            currentSpec = lines[i-1].strip()
            currentType = None
            currentFor = None
        elif line.startswith("## "):
            currentSpec = line.strip(" #")
            currentType = None
            currentFor = None
        elif line.startswith("### "):
            line = line.strip(" #")
            if line in config.dfnTypes:
                currentType = line
                currentFor = None
            elif re.match("([\w-]+)\s+for\s+(.+)", line):
                match = re.match("([\w-]+)\s+for\s+(.+)", line)
                if match.group(1) in config.dfnTypes:
                    currentType = match.group(1)
                else:
                    die("Unknown definition type '{0}' on line {1}", match.group(1), i)
                currentFor = match.group(2).strip()
        elif re.match("[*+-]\s+", line):
            term = re.match("^[*+-]\s+(.*)", line).group(1).strip()
            if currentSpec == "CSS 2.1 Replacements":
                data["css21Replacements"].append(term)
            elif currentSpec == "Ignored Specs":
                data["ignoredSpecs"].append(term)
            elif currentSpec.startswith("Custom "):
                match = re.match("Custom ([\w-]+) (.*)", currentSpec)
                specName = match.group(1)
                specUrl = match.group(2).strip()
                match = re.match("(.*) \(([\w-]+)\) (.*)", term)
                if match is None:
                    die("Custom link lines must be of the form '<term> (<type>) <hash-link>'.Got:\n  {0}", term)
                    continue
                dfnText = match.group(1).strip()
                dfnType = match.group(2)
                dfnUrl = match.group(3).strip()
                data["customDfns"].append((specName, specUrl, dfnText, dfnType, dfnUrl))
            elif currentSpec:
                if currentType:
                    data[term].append((currentSpec, currentType, None, currentFor))
                elif term.startswith("<") and term.endswith(">"):
                    data[term].append((currentSpec, "type", None, None))
                elif term.startswith(u"〈") and term.endswith(u"〉"):
                    data[term].append((currentSpec, "token", None, None))
                elif term.endswith("()"):
                    data[term].append((currentSpec, "function", None, None))
                elif re.match("(@[\w-])/([\w-])", term):
                    match = re.match("(@[\w-])/([\w-])", term)
                    data[match.group(2)].append((currentSpec, "descriptor", None, match.group(1)))
                elif term.startswith("@"):
                    data[term].append((currentSpec, "at-rule", None, None))
                else:
                    data[term].append((currentSpec, "property", None, None))

    if not config.dryRun:
        try:
            with io.open(config.scriptPath+"/spec-data/link-defaults.json", 'w', encoding="utf-8") as f:
                f.write(unicode(json.dumps(data, indent=2)))
        except Exception, e:
            die("Couldn't save link-defaults database to disk.\n{0}", e)
            return
    say("Success!")

def updateTestSuites():
    try:
        say("Downloading test suite data...")
        shepherd = apiclient.APIClient("https://api.csswg.org/shepherd/", version = "vnd.csswg.shepherd.v1")
        res = shepherd.get("test_suites")
        if ((not res) or (406 == res.status)):
            die("This version of the test suite API is no longer supported. Please update Bikeshed.")
            return
        if res.contentType not in config.testSuiteDataContentTypes:
            die("Unrecognized test suite content-type '{0}'.", res.contentType)
            return
        rawTestSuiteData = res.data
    except Exception, e:
        die("Couldn't download test suite data.  Error was:\n{0}", str(e))
        return

    testSuites = dict()
    for rawTestSuite in rawTestSuiteData.values():
        testSuite = {
            'vshortname': rawTestSuite['name'],
            'title': rawTestSuite.get('title'),
            'description': rawTestSuite.get('description'),
            'status': rawTestSuite.get('status'),
            'url': rawTestSuite.get('uri'),
            'spec': rawTestSuite['specs'][0]
        }
        testSuites[testSuite['spec']] = testSuite

    if not config.dryRun:
        try:
            with io.open(config.scriptPath+"/spec-data/test-suites.json", 'w', encoding="utf-8") as f:
                f.write(unicode(json.dumps(testSuites, ensure_ascii=False, indent=2)))
        except Exception, e:
            die("Couldn't save test-suite database to disk.\n{0}", e)
    say("Success!")



def writeBiblioFile(fh, biblios):
    '''
    Each line is a value for a specific key, in the order:

    key
    linkText
    date
    status
    title
    url
    other
    etAl (as a boolish string)
    authors* (each on a separate line, an indeterminate number of lines)

    Each entry (including last) is ended by a line containing a single - character.
    '''
    for key, entries in biblios.items():
        b = sorted(entries, key=lambda x:x['order'])[0]
        fh.write(key.lower() + "\n")
        for field in ["linkText", "date", "status", "title", "url", "other"]:
            fh.write(b.get(field, "") + "\n")
        if b.get("etAl", False):
            fh.write("1\n")
        else:
            fh.write("\n")
        for author in b.get("authors", []):
            fh.write(author+"\n")
        fh.write("-" + "\n")

def writeAnchorsFile(fh, anchors):
    '''
    Keys may be duplicated.

    key
    type
    spec
    shortname
    level
    status
    url
    export (boolish string)
    normative (boolish string)
    for* (one per line, unknown #)
    - (by itself, ends the segment)
    '''
    for key, entries in anchors.items():
        for e in entries:
            fh.write(key + "\n")
            for field in ["type", "spec", "shortname", "level", "status", "url"]:
                fh.write(unicode(e.get(field, "")) + "\n")
            for field in ["export", "normative"]:
                if e.get(field, False):
                    fh.write("1\n")
                else:
                    fh.write("\n")
            for forValue in e.get("for", []):
                fh.write(forValue+"\n")
            fh.write("-" + "\n")

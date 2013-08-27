# -*- coding: utf-8 -*-

import json
import re
from collections import defaultdict
from contextlib import closing
import urllib2
import lib.config as config
from lib.messages import *

def update(anchors=False, biblio=False, linkDefaults=False):
    # If all are False, update everything
    updateAnyway = not (anchors or biblio or linkDefaults)
    if anchors or updateAnyway:
        updateCrossRefs()
    if biblio or updateAnyway:
        updateBiblio()
    if linkDefaults or updateAnyway:
        updateLinkDefaults()

def updateCrossRefs():
    try:
        say("Downloading anchor data...")
        res = urllib2.urlopen(urllib2.Request("https://api.csswg.org/shepherd/spec/?anchors&draft", headers={"Accept":"application/vnd.csswg.shepherd.v1+json"}))
        if res.getcode() == 406:
            die("This version of the anchor-data API is no longer supported. Please update Bikeshed.")
            return
        if res.info().gettype() not in config.anchorDataContentTypes:
            die("Unrecognized anchor-data content-type '{0}'.", res.inf().gettype())
            return
        with closing(res) as f:
            rawSpecData = json.load(f)
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
            type = rawAnchor['type']
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
                'type': type,
                'spec': spec['vshortname'],
                'shortname': spec['shortname'],
                'level': int(spec['level']),
                'export': rawAnchor.get('export', False),
                'normative': rawAnchor.get('normative', False),
                'url': spec[rawAnchor['status']] + rawAnchor['uri'],
                'for': rawAnchor.get('for', [])
            }
            for text in linkingTexts:
                anchors[text.lower()].append(anchor)
        
    if not config.dryRun:
        try:
            with open(config.scriptPath+"/spec-data/specs.json", 'w') as f:
                json.dump(specs, f, ensure_ascii=False, indent=2)
        except Exception, e:
            die("Couldn't save spec database to disk.\n{0}", e)
        try:
            with open(config.scriptPath+"/spec-data/anchors.json", 'w') as f:
                json.dump(anchors, f, indent=2)
        except Exception, e:
            die("Couldn't save anchor database to disk.\n{0}", e)
    say("Success!")


def updateBiblio():
    pass


def updateLinkDefaults():
    try:
        say("Downloading link defaults...")
        with closing(urllib2.urlopen("http://dev.w3.org/csswg/autolinker-config.md")) as f:
            lines = f.readlines()
        say("Success!")
    except Exception, e:
        die("Couldn't download link defaults data.\n{0}", e)

    currentSpec = None
    currentType = None
    currentFor = None
    data = defaultdict(list)
    data["css21Replacements"] = []
    data["ignoredSpecs"] = []
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
            with open(config.scriptPath+"/spec-data/link-defaults.json", 'w') as f:
                json.dump(data, f, indent=2)
        except Exception, e:
            die("Couldn't save link-defaults database to disk.\n{0}", e)
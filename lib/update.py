# -*- coding: utf-8 -*-

import json
import re
from collections import defaultdict
from contextlib import closing
from urllib2 import urlopen
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
        say("Downloading spec database...")
        with closing(urlopen("http://test.csswg.org/shepherd/api/spec")) as f:
            rawSpecData = json.load(f)
    except Exception, e:
        die("Couldn't download spec database.\n{0}", str(e))

    specData = dict()
    for rawSpec in rawSpecData.values():
        spec = {
            'vshortname': rawSpec['name'],
            'TR': rawSpec['base_uri'],
            'ED': rawSpec['draft_uri'],
            'title': rawSpec['title'],
            'description': rawSpec['description']
        }
        match = re.match("(.*)-(\d+)", rawSpec['name'])
        if match:
            spec['shortname'] = match.group(1)
            spec['level'] = int(match.group(2))
        else:
            spec['shortname'] = spec['vshortname']
            spec['level'] = 1
        specData[spec['vshortname']] = spec
    if not config.dryRun:
        try:
            with open(config.scriptPath+"/spec-data/specs.json", 'w') as f:
                json.dump(specData, f, ensure_ascii=False, indent=2)
        except Exception, e:
            die("Couldn't save spec database to disk.\n{0}", e)

    def linearizeAnchorTree(multiTree, list=None):
        if list is None:
            list = []
        # Call with multiTree being a list of trees
        for item in multiTree:
            if item['type'] not in ("section", "other"):
                list.append(item)
            if item['children']:
                linearizeAnchorTree(item['children'], list)
            item['children'] = False
        return list
    
    anchors = defaultdict(list)
    for i, spec in enumerate(specData.values()):
        progress("Fetching xref data", i+1, len(specData))
        try:
            with closing(urlopen("http://test.csswg.org/shepherd/api/spec?spec={0}&anchors=1".format(spec['vshortname']))) as f:
                rawData = json.load(f)
                rawAnchors = linearizeAnchorTree(rawData['anchors'])
        except Exception, e:
            die("Couldn't download spec data for {0}.\n{1}", spec['vshortname'], e)
        for rawAnchor in rawAnchors:
            linkingTexts = rawAnchor.get('linking_text') or [rawAnchor.get('title')]
            type = rawAnchor['type']
            anchor = {
                'type': type,
                'spec': spec['vshortname'],
                'shortname': spec['shortname'],
                'level': int(spec['level']),
                'exported': True if rawAnchor.get('export') else False
            }
            if rawAnchor.get('draft'):
                anchor['ED_url'] = spec['ED'] + rawAnchor['uri']
            if rawAnchor.get('official'):
                anchor['TR_url'] = spec['TR'] + rawAnchor['uri']
            for text in linkingTexts:
                anchors[text].append(anchor)
    if not config.dryRun:
        try:
            with open(config.scriptPath+"/spec-data/anchors.json", 'w') as f:
                json.dump(anchors, f, indent=2)
        except Exception, e:
            die("Couldn't save xref database to disk.\n{0}", e)


def updateBiblio():
    pass


def updateLinkDefaults():
    try:
        say("Downloading link defaults...")
        with closing(urlopen("http://dev.w3.org/csswg/autolinker-config.md")) as f:
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
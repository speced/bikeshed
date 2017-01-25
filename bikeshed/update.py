# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals
import json
import re
import io
from collections import defaultdict, OrderedDict
from contextlib import closing
import urllib2

from . import config
from . import biblio
from DefaultOrderedDict import DefaultOrderedDict
from .messages import *

from .apiclient.apiclient import apiclient

def update(anchors=False, biblio=False, caniuse=False, linkDefaults=False, testSuites=False, languages=False):
    # If all are False, update everything
    updateAnyway = not (anchors or biblio or caniuse or linkDefaults or testSuites or languages)
    if anchors or updateAnyway:
        updateCrossRefs()
    if biblio or updateAnyway:
        updateBiblio()
    if caniuse or updateAnyway:
        updateCanIUse()
    if linkDefaults or updateAnyway:
        updateLinkDefaults()
    if testSuites or updateAnyway:
        updateTestSuites()
    if languages or updateAnyway:
        updateLanguages()


def updateCrossRefs():
    try:
        say("Downloading anchor data...")
        shepherd = apiclient.APIClient("https://api.csswg.org/shepherd/", version="vnd.csswg.shepherd.v1")
        res = shepherd.get("specifications", anchors=True, draft=True)
        # http://api.csswg.org/shepherd/spec/?spec=css-flexbox-1&anchors&draft, for manual looking
        if ((not res) or (406 == res.status)):
            die("Either this version of the anchor-data API is no longer supported, or (more likely) there was a transient network error. Try again in a little while, and/or update Bikeshed. If the error persists, please report it on GitHub.")
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
            if item['type'] in config.dfnTypes.union(["dfn", "heading"]):
                list.append(item)
            if item.get('children'):
                linearizeAnchorTree(item['children'], list)
                del item['children']
        return list

    specs = dict()
    anchors = defaultdict(list)
    headings = defaultdict(dict)
    for rawSpec in rawSpecData.values():
        spec = {
            'vshortname': rawSpec['name'],
            'shortname': rawSpec.get('short_name'),
            'snapshot_url': rawSpec.get('base_uri'),
            'current_url': rawSpec.get('draft_uri'),
            'title': rawSpec.get('title'),
            'description': rawSpec.get('description'),
            'work_status': rawSpec.get('work_status'),
            'working_group': rawSpec.get('working_group'),
            'domain': rawSpec.get('domain'),
            'status': rawSpec.get('status'),
            'abstract': rawSpec.get('abstract')
        }
        if spec['shortname'] is not None and spec['vshortname'].startswith(spec['shortname']):
            # S = "foo", V = "foo-3"
            # Strip the prefix
            level = spec['vshortname'][len(spec['shortname']):]
            if level.startswith("-"):
                level = level[1:]
            if level.isdigit():
                spec['level'] = int(level)
            else:
                spec['level'] = 1
        elif spec['shortname'] is None and re.match(r"(.*)-(\d+)", spec['vshortname']):
            # S = None, V = "foo-3"
            match = re.match(r"(.*)-(\d+)", spec['vshortname'])
            spec['shortname'] = match.group(1)
            spec['level'] = int(match.group(2))
        else:
            spec['shortname'] = spec['vshortname']
            spec['level'] = 1
        specs[spec['vshortname']] = spec
        specHeadings = headings[spec['vshortname']]

        def setStatus(status):
            def temp(obj):
                obj['status'] = status
                return obj
            return temp
        rawAnchorData = map(setStatus('snapshot'), linearizeAnchorTree(rawSpec.get('anchors', []))) + map(setStatus('current'), linearizeAnchorTree(rawSpec.get('draft_anchors',[])))
        for rawAnchor in rawAnchorData:
            rawAnchor = fixupAnchor(rawAnchor)
            linkingTexts = rawAnchor.get('linking_text', [rawAnchor.get('title')])
            if linkingTexts[0] is None:
                continue
            if len(linkingTexts) == 1 and linkingTexts[0].strip() == "":
                continue
            # If any smart quotes crept in, replace them with ASCII.
            for i,t in enumerate(linkingTexts):
                if "’" in t or "‘" in t:
                    t = re.sub(r"‘|’", "'", t)
                    linkingTexts[i] = t
                if "“" in t or "”" in t:
                    t = re.sub(r"“|”", '"', t)
                    linkingTexts[i] = t
            if rawAnchor['type'] == "heading":
                uri = rawAnchor['uri']
                if uri.startswith("??"):
                    # css3-tables has this a bunch, for some strange reason
                    uri = uri[2:]
                if uri[0] == "#":
                    # Either single-page spec, or link on the top page of a multi-page spec
                    heading = {
                        'url': spec["{0}_url".format(rawAnchor['status'])] + uri,
                        'number': rawAnchor['name'] if re.match(r"[\d.]+$", rawAnchor['name']) else "",
                        'text': rawAnchor['title'],
                        'spec': spec['title']
                    }
                    fragment = uri
                    shorthand = "/" + fragment
                else:
                    # Multi-page spec, need to guard against colliding IDs
                    if "#" in uri:
                        # url to a heading in the page, like "foo.html#bar"
                        match = re.match(r"([\w-]+).*?(#.*)", uri)
                        if not match:
                            die("Unexpected URI pattern '{0}' for spec '{1}'. Please report this to the Bikeshed maintainer.", uri, spec['vshortname'])
                            continue
                        page, fragment = match.groups()
                        page = "/" + page
                    else:
                        # url to a page itself, like "foo.html"
                        page, _, _ = uri.partition(".")
                        page = "/" + page
                        fragment = "#"
                    shorthand = page + fragment
                    heading = {
                        'url': spec["{0}_url".format(rawAnchor['status'])] + uri,
                        'number': rawAnchor['name'] if re.match(r"[\d.]+$", rawAnchor['name']) else "",
                        'text': rawAnchor['title'],
                        'spec': spec['title']
                    }
                if shorthand not in specHeadings:
                    specHeadings[shorthand] = {}
                specHeadings[shorthand][rawAnchor['status']] = heading
                if fragment not in specHeadings:
                    specHeadings[fragment] = []
                if shorthand not in specHeadings[fragment]:
                    specHeadings[fragment].append(shorthand)
            else:
                anchor = {
                    'status': rawAnchor['status'],
                    'type': rawAnchor['type'],
                    'spec': spec['vshortname'],
                    'shortname': spec['shortname'],
                    'level': int(spec['level']),
                    'export': rawAnchor.get('export', False),
                    'normative': rawAnchor.get('normative', False),
                    'url': spec["{0}_url".format(rawAnchor['status'])] + rawAnchor['uri'],
                    'for': rawAnchor.get('for', [])
                }
                for text in linkingTexts:
                    if anchor['type'] in config.lowercaseTypes:
                        text = text.lower()
                    text = re.sub(r'\s+', ' ', text)
                    anchors[text].append(anchor)

    # Headings data was purposely verbose, assuming collisions even when there wasn't one.
    # Want to keep the collision data for multi-page, so I can tell when you request a non-existent page,
    # but need to collapse away the collision stuff for single-page.
    for specHeadings in headings.values():
        for k, v in specHeadings.items():
            if k[0] == "#" and len(v) == 1 and v[0][0:2] == "/#":
                # No collision, and this is either a single-page spec or a non-colliding front-page link
                # Go ahead and collapse them.
                specHeadings[k] = specHeadings[v[0]]
                del specHeadings[v[0]]

    # Compile a db of {argless methods => {argfull method => {args, fors, url, shortname}}
    methods = defaultdict(dict)
    for key, anchors_ in anchors.items():
        # Extract the name and arguments
        match = re.match(r"([^(]+)\((.*)\)", key)
        if not match:
            continue
        methodName, argstring = match.groups()
        arglessMethod = methodName + "()"
        args = [x.strip() for x in argstring.split(",")] if argstring else []
        for anchor in anchors_:
            if anchor['type'] not in config.idlMethodTypes:
                continue
            if key not in methods[arglessMethod]:
                methods[arglessMethod][key] = {"args":args, "for": set(), "shortname":anchor['shortname']}
            methods[arglessMethod][key]["for"].update(anchor["for"])
    # Translate the "for" set back to a list for JSONing
    for signatures in methods.values():
        for signature in signatures.values():
            signature["for"] = list(signature["for"])

    # Compile a db of {for value => dict terms that use that for value}
    fors = defaultdict(set)
    for key, anchors_ in anchors.items():
        for anchor in anchors_:
            for for_ in anchor["for"]:
                if for_ == "":
                    continue
                fors[for_].add(key)
            if not anchor["for"]:
                fors["/"].add(key)
    for key, val in fors.items():
        fors[key] = list(val)

    if not config.dryRun:
        try:
            with io.open(config.scriptPath + "/spec-data/specs.json", 'w', encoding="utf-8") as f:
                f.write(unicode(json.dumps(specs, ensure_ascii=False, indent=2, sort_keys=True)))
        except Exception, e:
            die("Couldn't save spec database to disk.\n{0}", e)
            return
        try:
            with io.open(config.scriptPath + "/spec-data/headings.json", 'w', encoding="utf-8") as f:
                f.write(unicode(json.dumps(headings, ensure_ascii=False, indent=2, sort_keys=True)))
        except Exception, e:
            die("Couldn't save headings database to disk.\n{0}", e)
            return
        try:
            with io.open(config.scriptPath + "/spec-data/anchors.data", 'w', encoding="utf-8") as f:
                writeAnchorsFile(f, anchors)
        except Exception, e:
            die("Couldn't save anchor database to disk.\n{0}", e)
            return
        try:
            with io.open(config.scriptPath + "/spec-data/methods.json", 'w', encoding="utf-8") as f:
                f.write(unicode(json.dumps(methods, ensure_ascii=False, indent=2, sort_keys=True)))
        except Exception, e:
            die("Couldn't save methods database to disk.\n{0}", e)
            return
        try:
            with io.open(config.scriptPath + "/spec-data/fors.json", 'w', encoding="utf-8") as f:
                f.write(unicode(json.dumps(fors, ensure_ascii=False, indent=2, sort_keys=True)))
        except Exception, e:
            die("Couldn't save fors database to disk.\n{0}", e)
            return

    say("Success!")


def updateBiblio():
    say("Downloading biblio data...")
    biblios = defaultdict(list)
    try:
        with closing(urllib2.urlopen("https://specref.herokuapp.com/bibrefs")) as fh:
            biblio.processSpecrefBiblioFile(unicode(fh.read(), encoding="utf-8"), biblios, order=3)
        with closing(urllib2.urlopen("https://raw.githubusercontent.com/w3c/csswg-drafts/master/biblio.ref")) as fh:
            lines = [unicode(line, encoding="utf-8") for line in fh.readlines()]
            biblio.processReferBiblioFile(lines, biblios, order=4)
    except Exception, e:
        die("Couldn't download the biblio data.\n{0}", e)
    if not config.dryRun:
        # Group the biblios by the first two letters of their keys
        groupedBiblios = DefaultOrderedDict(DefaultOrderedDict)
        allNames = []
        for k,v in sorted(biblios.items(), key=lambda x:x[0].lower()):
            allNames.append(k)
            group = k[0:2]
            groupedBiblios[group][k] = v
        for group, biblios in groupedBiblios.items():
            try:
                with io.open(config.scriptPath + "/spec-data/biblio/biblio-{0}.data".format(group), 'w', encoding="utf-8") as fh:
                    writeBiblioFile(fh, biblios)
            except Exception, e:
                die("Couldn't save biblio database to disk.\n{0}", e)
                return
        try:
            with io.open(config.scriptPath + "/spec-data/biblio-keys.json", 'w', encoding="utf-8") as fh:
                fh.write(unicode(json.dumps(allNames, indent=0, ensure_ascii=False, sort_keys=True)))
        except Exception, e:
            die("Couldn't save biblio database to disk.\n{0}", e)
            return
    say("Success!")


def updateCanIUse():
    say("Downloading Can I Use data...")
    try:
        with closing(urllib2.urlopen("https://raw.githubusercontent.com/Fyrd/caniuse/master/fulldata-json/data-2.0.json")) as fh:
            jsonString = fh.read()
    except Exception, e:
        die("Couldn't download the Can I Use data.\n{0}", e)
        return

    try:
        data = json.loads(unicode(jsonString), encoding="utf-8", object_pairs_hook=OrderedDict)
    except Exception, e:
        die("The Can I Use data wasn't valid JSON for some reason. Try downloading again?\n{0}", e)
        return

    # Remove some unused data
    if "cats" in data:
        del data["cats"]
    if "statuses" in data:
        del data["statuses"]

    # Trim agent data to minimum required - mapping codename to full name
    codeNames = {}
    agentData = {}
    for codename,agent in data["agents"].items():
        codeNames[codename] = agent["browser"]
        agentData[agent["browser"]] = codename
    data["agents"] = agentData

    # Trim feature data to minimum - notes and minimum supported version
    def simplifyStatus(s, *rest):
        if "x" in s or "d" in s or "n" in s or "p" in s:
            return "n"
        elif "a" in s:
            return "a"
        elif "y" in s:
            return "y"
        elif "u" in s:
            return "u"
        else:
            die("Unknown CanIUse Status '{0}' for {1}/{2}/{3}. Please report this as a Bikeshed issue.", s, *rest)
            return None
    def simplifyVersion(v):
        if "-" in v:
            # Use the earliest version in a range.
            v,_,_ = v.partition("-")
        return v
    featureData = {}
    for featureName,feature in data["data"].items():
        notes = feature["notes"]
        url = feature["spec"]
        browserData = {}
        for browser,versions in feature["stats"].items():
            descendingVersions = list(reversed(versions.items()))
            mostRecent = descendingVersions[0]
            version = simplifyVersion(mostRecent[0])
            status = simplifyStatus(mostRecent[1], featureName, browser, version)
            if status == "n":
                # Most recent version is broken, so we're done
                pass
            elif status == "u":
                # Seek backwards until I find something other than "u"
                for v,s in descendingVersions:
                    if simplifyStatus(s) != "u":
                        status = simplifyStatus(s)
                        version = simplifyVersion(v)
                        break
            else:
                # Status is either (a)lmost or (y)es,
                # seek backwards thru time as long as it's the same.
                for v,s in descendingVersions:
                    if simplifyStatus(s) == status:
                        version = simplifyVersion(v)
                    else:
                        break
            browserData[codeNames[browser]] = "{0} {1}".format(status, version)
        featureData[featureName] = {"notes":notes, "url":url, "support":browserData}
    data["data"] = featureData

    if not config.dryRun:
        try:
            with closing(io.open(config.scriptPath + "/spec-data/caniuse.json", 'w', encoding="utf-8")) as fh:
                fh.write(unicode(json.dumps(data, indent=1, ensure_ascii=False, sort_keys=True)))
        except Exception, e:
            die("Couldn't save Can I Use database to disk.\n{0}", e)
            return
    say("Success!")


def updateLinkDefaults():
    try:
        say("Downloading link defaults...")
        with closing(urllib2.urlopen("https://raw.githubusercontent.com/tabatkins/bikeshed/master/bikeshed/spec-data/readonly/link-defaults.infotree")) as fh:
            lines = [unicode(line, encoding="utf-8") for line in fh.readlines()]
    except Exception, e:
        die("Couldn't download link defaults data.\n{0}", e)
        return

    if not config.dryRun:
        try:
            with io.open(config.scriptPath + "/spec-data/link-defaults.infotree", 'w', encoding="utf-8") as f:
                f.write(''.join(lines))
        except Exception, e:
            die("Couldn't save link-defaults database to disk.\n{0}", e)
            return
    say("Success!")


def updateTestSuites():
    try:
        say("Downloading test suite data...")
        shepherd = apiclient.APIClient("https://api.csswg.org/shepherd/", version="vnd.csswg.shepherd.v1")
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
            with io.open(config.scriptPath + "/spec-data/test-suites.json", 'w', encoding="utf-8") as f:
                f.write(unicode(json.dumps(testSuites, ensure_ascii=False, indent=2, sort_keys=True)))
        except Exception, e:
            die("Couldn't save test-suite database to disk.\n{0}", e)
    say("Success!")


def updateLanguages():
    try:
        say("Downloading languages...")
        with closing(urllib2.urlopen("https://raw.githubusercontent.com/tabatkins/bikeshed/master/bikeshed/spec-data/readonly/languages.json")) as fh:
            lines = [unicode(line, encoding="utf-8") for line in fh.readlines()]
    except Exception, e:
        die("Couldn't download languages data.\n{0}", e)
        return

    if not config.dryRun:
        try:
            with io.open(config.scriptPath + "/spec-data/languages.json", 'w', encoding="utf-8") as f:
                f.write(''.join(lines))
        except Exception, e:
            die("Couldn't save languages database to disk.\n{0}", e)
            return
    say("Success!")


def writeBiblioFile(fh, biblios):
    '''
    Each line is a value for a specific key, in the order:

    key
    linkText
    date
    status
    title
    snapshot url
    current url
    other
    etAl (as a boolish string)
    authors* (each on a separate line, an indeterminate number of lines)

    Each entry (including last) is ended by a line containing a single - character.
    '''
    typePrefixes = {
        "dict": "d",
        "string": "s",
        "alias": "a"
    }
    for key, entries in biblios.items():
        b = sorted(entries, key=lambda x:x['order'])[0]
        format = b['biblioFormat']
        fh.write("{prefix}:{key}\n".format(prefix=typePrefixes[format], key=key.lower()))
        if format == "dict":
            for field in ["linkText", "date", "status", "title", "snapshot_url", "current_url", "other"]:
                fh.write(b.get(field, "") + "\n")
            if b.get("etAl", False):
                fh.write("1\n")
            else:
                fh.write("\n")
            for author in b.get("authors", []):
                fh.write(author + "\n")
        elif format == "string":
            fh.write(b['linkText'] + "\n")
            fh.write(b['data'] + "\n")
        elif format == "alias":
            fh.write(b['linkText'] + "\n")
            fh.write(b['aliasOf'] + "\n")
        else:
            die("The biblio key '{0}' has an unknown biblio type '{1}'.", key, format)
            continue
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
                if forValue:  # skip empty strings
                    fh.write(forValue + "\n")
            fh.write("-" + "\n")


def fixupDataFiles():
    import os
    localPath = os.path.join(config.scriptPath, "spec-data")
    remotePath = os.path.join(config.scriptPath, "spec-data", "readonly")
    try:
        localVersion = int(open(os.path.join(localPath, "version.txt"), 'r').read())
    except IOError:
        localVersion = None
    try:
        remoteVersion = int(open(os.path.join(remotePath, "version.txt"), 'r').read())
    except IOError, err:
        warn("Couldn't check the datafile version. Bikeshed may be unstable.\n{0}", err)
        return

    if localVersion == remoteVersion:
        # Cool
        return

    # If versions don't match, either the remote versions have been updated
    # (and we should switch you to them, because formats may have changed),
    # or you're using a historical version of Bikeshed (ditto).
    def copyanything(src, dst):
        import shutil
        import errno
        try:
            shutil.rmtree(dst, ignore_errors=True)
            shutil.copytree(src, dst)
        except OSError as exc:
            if exc.errno in [errno.ENOTDIR, errno.EINVAL]:
                shutil.copy(src, dst)
            else:
                raise
    try:
        for filename in os.listdir(remotePath):
            copyanything(os.path.join(remotePath, filename), os.path.join(localPath, filename))
    except Exception, err:
        warn("Couldn't update datafiles from cache. Bikeshed may be unstable.\n{0}", err)
        return


def fixupAnchor(anchor):
    # Miscellaneous fixes
    if anchor.get('title', None) == "'@import'":
        anchor['title'] = "@import"
    for k,v in anchor.items():
        # Normalize whitespace
        if isinstance(v, basestring):
            anchor[k] = re.sub(r"\s+", " ", v.strip())
        elif isinstance(v, list):
            for k1, v1 in enumerate(v):
                if isinstance(v1, basestring):
                    anchor[k][k1] = re.sub(r"\s+", " ", v1.strip())
    return anchor

# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals
import io
import json
import re
import urllib2
from collections import defaultdict
from contextlib import closing

from .. import biblio
from .. import config
from ..apiclient.apiclient import apiclient
from ..DefaultOrderedDict import DefaultOrderedDict
from ..messages import *



def update():
    say("Downloading biblio data...")
    biblios = defaultdict(list)
    biblio.processSpecrefBiblioFile(getSpecrefData(), biblios, order=3)
    biblio.processSpecrefBiblioFile(getWG21Data(), biblios, order=3)
    biblio.processReferBiblioFile(getCSSWGData(), biblios, order=4)
    if not config.dryRun:
        groupedBiblios, allNames = groupBiblios(biblios)
        # Save each group to a file
        for group, biblios in groupedBiblios.items():
            try:
                with io.open(config.scriptPath + "/spec-data/biblio/biblio-{0}.data".format(group), 'w', encoding="utf-8") as fh:
                    writeBiblioFile(fh, biblios)
            except Exception, e:
                die("Couldn't save biblio database to disk.\n{0}", e)
                return
        # Save the list of all names to a file
        reducedNames = []
        for name in allNames:
            if re.search(r"-\d{8}$", name):
                continue
            if re.match(r"cwg\d+$", name):
                continue
            if re.match(r"ewg\d+$", name):
                continue
            if re.match(r"fs\d+$", name):
                continue
            if re.match(r"lewg\d+$", name):
                continue
            if re.match(r"lwg\d+$", name):
                continue
            if re.match(r"n\d+$", name):
                continue
            if re.match(r"p\d+r\d+$", name):
                continue
            if re.match(r"rfc\d+$", name):
                continue
            if re.match(r"wg21-", name):
                continue
            reducedNames.append(name)
        try:
            with io.open(config.scriptPath + "/spec-data/biblio-keys.json", 'w', encoding="utf-8") as fh:
                fh.write(unicode(json.dumps(reducedNames, indent=0, ensure_ascii=False, sort_keys=True)))
        except Exception, e:
            die("Couldn't save biblio database to disk.\n{0}", e)
            return
    say("Success!")


def getSpecrefData():
    try:
        with closing(urllib2.urlopen("https://api.specref.org/bibrefs")) as fh:
            return unicode(fh.read(), encoding="utf-8")
    except urllib2.URLError:
        # SpecRef uses SNI, which old Pythons (pre-2.7.10) don't understand.
        # First try the older herokuapp.com URL.
        try:
            with closing(urllib2.urlopen("https://specref.herokuapp.com/bibrefs")) as fh:
                return unicode(fh.read(), encoding="utf-8")
        except:
            # Try the CSSWG proxy.
            try:
                with closing(urllib2.urlopen("https://api.csswg.org/bibrefs")) as fh:
                    return unicode(fh.read(), encoding="utf-8")
            except:
                warn("Your Python is too old (pre-2.7.10) to talk to SpecRef over HTTPS, and something's wrong with the CSSWG proxy as well. Report this to the Bikeshed repo, please?")
                raise
                return "{}"
    except Exception, e:
        die("Couldn't download the SpecRef biblio data.\n{0}", e)
        return "{}"


def getWG21Data():
    try:
        with closing(urllib2.urlopen("https://wg21.link/specref.json")) as fh:
            return unicode(fh.read(), encoding="utf-8")
    except Exception, e:
        die("Couldn't download the WG21 biblio data.\n{0}", e)
        return "{}"


def getCSSWGData():
    try:
        with closing(urllib2.urlopen("https://raw.githubusercontent.com/w3c/csswg-drafts/master/biblio.ref")) as fh:
            return [unicode(line, encoding="utf-8") for line in fh.readlines()]
    except Exception, e:
        die("Couldn't download the CSSWG biblio data.\n{0}", e)
        return []


def groupBiblios(biblios):
    # Group the biblios by the first two letters of their keys
    groupedBiblios = DefaultOrderedDict(DefaultOrderedDict)
    allNames = []
    for k,v in sorted(biblios.items(), key=lambda x:x[0].lower()):
        allNames.append(k)
        group = k[0:2]
        groupedBiblios[group][k] = v
    return groupedBiblios, allNames


def writeBiblioFile(fh, biblios):
    '''
    Each line is a value for a specific key, in the order:

    key
    linkText
    date
    status
    title
    snapshot_url
    current_url
    obsoletedBy
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
            for field in ["linkText", "date", "status", "title", "snapshot_url", "current_url", "obsoletedBy", "other"]:
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
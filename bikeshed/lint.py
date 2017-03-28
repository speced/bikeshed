# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals
import logging
import re
from .messages import *
from .htmlhelpers import *
from .requests import requests

def lintExampleIDs(doc):
    if not doc.md.complainAbout['missing-example-ids']:
        return
    for el in findAll(".example:not([id])", doc):
        warn("Example needs ID:\n{0}", outerHTML(el)[0:100], el=el)

def lintBrokenLinks(doc):
    if not doc.md.complainAbout['broken-links']:
        return

    say("Checking links, this may take a while...")
    logging.captureWarnings(True) # Silence the requests library :/
    for el in findAll("a", doc):
        href = el.get('href')
        if not href or href[0] == "#":
            continue
        res = requests.get(href)
        if res.status_code >= 400:
            warn("Got a {0} status when fetching the link for:\n{1}", res.status_code, outerHTML(el))
    say("Done checking links!")

def lintAccidental2119(doc):
    if not doc.md.complainAbout['accidental-2119']:
        return
    keywords = r"\b(may|must|should|shall|optional|recommended|required)\b"

    def searchFor2119(el):
        if isNormative(el):
            # 2119 is fine, just look at children
            pass
        elif hasClass(el, "allow-2119"):
            # Override 2119 detection on this element's text specifically,
            # so you can use the keywords in examples *describing* the keywords.
            pass
        else:
            if el.text is not None:
                match = re.search(keywords, el.text)
                if match:
                    warn("RFC2119 keyword in non-normative section (use: might, can, has to, or override with <span class=allow-2119>): {0}", el.text, el=el)
            for child in el:
                if child.tail is not None:
                    match = re.search(keywords, child.tail)
                    if match:
                        warn("RFC2119 keyword in non-normative section (use: might, can, has to, or override with <span class=allow-2119>): {0}", child.tail, el=el)
        for child in el:
            searchFor2119(child)
    searchFor2119(doc.body)

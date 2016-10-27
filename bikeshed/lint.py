# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals
import logging
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

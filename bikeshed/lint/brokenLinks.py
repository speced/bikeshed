from __future__ import annotations

import logging
import time

import requests

from .. import h, t
from .. import messages as m


def brokenLinks(doc: t.SpecT) -> None:
    """
    Check every external link in the document to make sure it returns a 2XX or 3XX response.
    Auto-skips mailto: links.
    """
    if not doc.md.complainAbout["broken-links"]:
        return

    timeout = doc.md.linkCheckerTimeout

    m.say("Checking links, this may take a while...")
    logging.captureWarnings(True)  # Silence the requests library :/
    startTime = time.time()
    for el in h.findAll("a", doc):
        if time.time() - startTime > timeout.total:
            m.lint(f"Link checking took longer than {timeout.total} seconds, skipping the rest.")
            break
        href = el.get("href")
        if not href or href[0] == "#":
            # Local link
            continue
        if href.startswith("mailto:"):
            # Can't check mailto links
            continue
        try:
            res = requests.get(href, timeout=timeout.each)
        except requests.exceptions.Timeout:
            m.lint(f"Checking the following link timed out:\n{href}", lineNum=el)
            continue
        except:  # pylint: disable=bare-except
            m.lint(f"The following link caused an error when I tried to request it:\n{href}", lineNum=el)
            continue
        if res.status_code >= 400:
            m.lint(f"Got a {res.status_code} status when fetching the link for:\n{href}", lineNum=el)
    m.say("Done checking links!")

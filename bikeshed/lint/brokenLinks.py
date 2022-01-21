import logging

from .. import h, messages as m


def brokenLinks(doc):
    """
    Check every external link in the document to make sure it returns a 2XX or 3XX response.
    Auto-skips mailto: links.
    """
    if not doc.md.complainAbout["broken-links"]:
        return
    import requests

    m.say("Checking links, this may take a while...")
    logging.captureWarnings(True)  # Silence the requests library :/
    for el in h.findAll("a", doc):
        href = el.get("href")
        if not href or href[0] == "#":
            # Local link
            continue
        if href.startswith("mailto:"):
            # Can't check mailto links
            continue
        try:
            res = requests.get(href, verify=False)
        except Exception as e:
            m.warn(f"The following link caused an error when I tried to request it:\n{h.outerHTML(el)}\n{e}")
            continue
        if res.status_code >= 400:
            m.warn(f"Got a {res.status_code} status when fetching the link for:\n{h.outerHTML(el)}")
    m.say("Done checking links!")

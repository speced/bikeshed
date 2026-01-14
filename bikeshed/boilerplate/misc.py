from __future__ import annotations

import os
import subprocess
from datetime import datetime

from .. import config, h, retrieve, t
from . import main


def addBikeshedVersion(doc: t.SpecT, head: t.ElementT) -> None:
    # Adds a <meta> containing the current Bikeshed semver.
    if "generator" not in doc.md.boilerplate:
        return
    try:
        # Check that we're in the bikeshed repo
        origin = subprocess.check_output(
            "git remote -v",
            cwd=config.scriptPath(),
            stderr=subprocess.DEVNULL,
            shell=True,
        ).decode(encoding="utf-8")
        if "bikeshed" not in origin:
            # In a repo, but not bikeshed's;
            # probably pip-installed into an environment's repo or something.
            raise Exception
        # Otherwise, success, this is a -e install,
        # so we're in Bikeshed's repo.
        bikeshedVersion = (
            subprocess.check_output(
                r"git log -1 --format='Bikeshed version %h, updated %cd'",
                cwd=config.scriptPath(),
                stderr=subprocess.DEVNULL,
                shell=True,
            )
            .decode(encoding="utf-8")
            .strip()
        )
    except Exception:
        # Not in Bikeshed's repo, so instead grab from the datafile.
        bikeshedVersion = doc.dataFile.fetch("bikeshed-version.txt", fileType="readonly", str=True).strip()
    h.appendChild(head, h.E.meta({"name": "generator", "content": bikeshedVersion}))


def addCanonicalURL(doc: t.SpecT, head: t.ElementT) -> None:
    # Adds a <link rel=canonical> to the configured canonical url
    if doc.md.canonicalURL:
        h.appendChild(head, h.E.link({"rel": "canonical", "href": doc.md.canonicalURL}))


def addFavicon(doc: t.SpecT, head: t.ElementT) -> None:
    # Adds a <link rel=icon> to the configured favicon url
    if doc.md.favicon:
        h.appendChild(head, h.E.link({"rel": "icon", "href": doc.md.favicon}))


def addSpecVersion(doc: t.SpecT, head: t.ElementT) -> None:
    # Adds a <meta> with the current spec revision, if one was detected
    if "document-revision" not in doc.md.boilerplate:
        return

    if not doc.inputSource.hasDirectory():
        return

    revision = None
    source_dir = doc.inputSource.directory()
    try:
        # Check for a Git repo
        with open(os.devnull, "wb") as fnull:
            revision = (
                subprocess.check_output("git rev-parse HEAD", stderr=fnull, shell=True, cwd=source_dir)
                .decode(encoding="utf-8")
                .strip()
            )
    except subprocess.CalledProcessError:
        try:
            # Check for an Hg repo
            with open(os.devnull, "wb") as fnull:
                revision = (
                    subprocess.check_output(
                        "hg parent --temp='{node}'",
                        stderr=fnull,
                        shell=True,
                        cwd=source_dir,
                    )
                    .decode(encoding="utf-8")
                    .strip()
                )
        except subprocess.CalledProcessError:
            pass
    if revision:
        h.appendChild(head, h.E.meta({"name": "revision", "content": revision}))


def addHeaderFooter(doc: t.SpecT) -> None:
    header = retrieve.retrieveBoilerplateFile(doc, "header") if "header" in doc.md.boilerplate else ""
    footer = retrieve.retrieveBoilerplateFile(doc, "footer") if "footer" in doc.md.boilerplate else ""

    doc.html = "\n".join(
        [
            h.parseText(header, h.ParseConfig.fromSpec(doc, context="header.include"), context=None),
            doc.html,
            h.parseText(footer, h.ParseConfig.fromSpec(doc, context="footer.include"), context=None),
        ],
    )


def addLogo(doc: t.SpecT, body: t.ElementT) -> None:
    main.loadBoilerplate("logo", tree=body, doc=doc)


def addCopyright(doc: t.SpecT, body: t.ElementT) -> None:
    main.loadBoilerplate("copyright", tree=body, doc=doc)


def addAbstract(doc: t.SpecT, body: t.ElementT) -> None:
    if not doc.md.noAbstract:
        main.loadBoilerplate("abstract", tree=body, doc=doc)
    else:
        container = main.getFillContainer("abstract", doc=doc, tree=doc.root)
        if container is not None:
            h.removeNode(container)


def addStatusSection(doc: t.SpecT, body: t.ElementT) -> None:
    main.loadBoilerplate("status", doc=doc, tree=body)


def addExpiryNotice(doc: t.SpecT, body: t.ElementT) -> None:
    if doc.md.expires is None:
        return
    if doc.md.date >= doc.md.expires or datetime.utcnow().date() >= doc.md.expires:
        boilerplate = "warning-expired"
    else:
        boilerplate = "warning-expires"
        doc.extraJC.addExpires()
    main.loadBoilerplate(bpname="warning", filename=boilerplate, tree=body, doc=doc)
    h.addClass(doc, body, boilerplate)


def addObsoletionNotice(doc: t.SpecT, body: t.ElementT) -> None:
    if doc.md.warning:
        main.loadBoilerplate(bpname="warning", filename=doc.md.warning[0], doc=doc, tree=body)


def addAtRisk(doc: t.SpecT, body: t.ElementT) -> None:
    if len(doc.md.atRisk) == 0:
        return
    html = [
        h.E.p({}, "The following features are at-risk, and may be dropped during the CR period:\n"),
    ]
    ul = h.E.ul()
    html.append(ul)
    for feature in doc.md.atRisk:
        li = h.E.li()
        normFeature = h.safeBikeshedHtml(
            feature,
            h.ParseConfig.fromSpec(doc, context="At Risk metadata"),
            context="At Risk metadata",
        )
        h.parseInto(li, normFeature)
        h.appendChild(ul, li)
    html.append(
        h.E.p(
            {},
            "“At-risk” is a W3C Process term-of-art, and does not necessarily imply that the feature is in danger of being dropped or delayed. "
            + "It means that the WG believes the feature may have difficulty being interoperably implemented in a timely manner, "
            + "and marking it as such allows the WG to drop the feature if necessary when transitioning to the Proposed Rec stage, "
            + "without having to publish a new Candidate Rec without the feature first.",
        ),
    )
    main.fillWith("at-risk", html, doc=doc, tree=body)


def addStyles(doc: t.SpecT, head: t.ElementT) -> None:
    el = main.getFillContainer("stylesheet", doc=doc, tree=head)
    if el is not None:
        el.text = retrieve.retrieveBoilerplateFile(doc, "stylesheet")


def addCustomBoilerplate(doc: t.SpecT, root: t.ElementT) -> None:
    # boilerplate="" elements manually replace data-fill-with elements
    # that would otherwise be auto-generated by some means.
    for el in h.findAll("[boilerplate]", root):
        tag = el.get("boilerplate", "")
        if (container := main.getFillContainer(tag, doc=doc, tree=root)) is not None:
            h.replaceContents(container, el)
            h.removeNode(el)


def removeUnwantedBoilerplate(doc: t.SpecT, root: t.ElementT) -> None:
    for el in h.findAll("[data-fill-with]", root):
        tag = el.get("data-fill-with")
        if tag not in doc.md.boilerplate:
            h.removeNode(el)


def w3cStylesheetInUse(doc: t.SpecT) -> bool:
    return doc.md.prepTR or doc.doctype.group.name == "W3C"


def addBikeshedStyleScripts(doc: t.SpecT, head: t.ElementT) -> None:
    for style in doc.extraJC.getStyles(doc.md.boilerplate):
        container = main.getFillContainer("style-" + style.name, doc=doc, tree=head)
        if container is None:
            container = main.getFillContainer("bs-styles", doc=doc, tree=head, default=head)
        if container is not None:
            h.appendChild(container, style.toElement(darkMode=doc.md.darkMode))
    for script in doc.extraJC.getScripts(doc.md.boilerplate):
        container = main.getFillContainer("script-" + script.name, doc=doc, tree=head)
        if container is None:
            container = main.getFillContainer("bs-scripts", doc=doc, tree=head, default=head)
        if container is not None:
            h.appendChild(container, script.toElement())


def addDarkmodeIndicators(doc: t.SpecT, head: t.ElementT) -> None:
    # Unless otherwise indicated, Bikeshed docs are assumed
    # to be darkmode-aware.
    if not doc.md.darkMode:
        return

    # If a boilerplate already contains a color-scheme,
    # assume they know what they're doing.
    # Otherwise, add the color-scheme meta to indicate darkmode-ness.
    existingColorScheme = h.find('meta[name="color-scheme"]', head)
    if existingColorScheme is not None:
        allowsDark = "dark" in existingColorScheme.get("color-scheme", "")
    else:
        h.appendChild(
            head,
            h.E.meta({"name": "color-scheme", "content": "dark light"}),
        )
        allowsDark = True

    if allowsDark:
        # Specs using the Bikeshed stylesheet will get darkmode colors
        # automatically, but W3C specs don't. Instead, auto-add their
        # darkmode styles.
        w3cStylesheet = h.find('link[href^="https://www.w3.org/StyleSheets/TR"]', doc)
        if w3cStylesheet is not None:
            h.appendChild(
                head,
                h.E.link(
                    {
                        "rel": "stylesheet",
                        "href": "https://www.w3.org/StyleSheets/TR/2021/dark.css",
                        "type": "text/css",
                        "media": "(prefers-color-scheme: dark)",
                    },
                ),
            )

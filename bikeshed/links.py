from __future__ import annotations

import re
from collections import defaultdict
from urllib import parse

from . import biblio, config, dfnpanels, h, t
from . import messages as m
from .translate import _t
from .unset import UNSET

if t.TYPE_CHECKING:
    from . import refs


def fixIntraDocumentReferences(doc: t.SpecT) -> None:
    ids = {el.get("id"): el for el in h.findAll("[id]", doc)}
    headingIDs = {el.get("id"): el for el in h.findAll("[id].heading", doc)}
    for el in h.findAll("a[href^='#']:not([href='#']):not(.self-link):not([data-link-type])", doc):
        href = t.cast(str, el.get("href"))
        targetID = parse.unquote(href[1:])
        if el.get("bs-section") is not None and targetID not in headingIDs:
            m.die(f"Couldn't find target document section {targetID}:\n{h.outerHTML(el)}", el=el)
            continue
        if targetID not in ids:
            m.die(f"Couldn't find target anchor {targetID}:\n{h.outerHTML(el)}", el=el)
            continue
        if h.isEmpty(el):
            # TODO Allow this to respect "safe" markup (<sup>, etc) in the title
            target = ids[targetID]
            content = h.find(".content", target)
            if content is None:
                m.die(
                    f"Tried to generate text for a section link, but the target isn't a heading:\n{h.outerHTML(el)}",
                    el=el,
                )
                continue
            text = h.textContent(content).strip()
            if target.get("data-level") is not None:
                text = f"§\u202f{target.get('data-level')} {text}"
            h.appendChild(el, text)


def fixInterDocumentReferences(doc: t.SpecT) -> None:
    for el in h.findAll("[bs-spec-section]", doc):
        if el.get("bs-link-spec") is None:
            m.die(
                f"Spec-section autolink doesn't have a 'spec' attribute:\n{h.outerHTML(el)}",
                el=el,
            )
            continue
        spec = el.get("bs-link-spec", "").lower()
        if el.get("bs-spec-section") is None:
            m.die(
                f"Spec-section autolink doesn't have a 'spec-section' attribute:\n{h.outerHTML(el)}",
                el=el,
            )
            continue
        section = el.get("bs-spec-section", "")
        if spec in doc.refs.specs:
            # Bikeshed recognizes the spec
            fillInterDocumentReferenceFromShepherd(doc, el, spec, section)
            continue
        if not re.search(r"\d$", spec):
            # Unnumbered, check if there's a numbered variant in Shepherd
            vNames = doc.refs.vNamesFromSpecNames(spec)
            if len(vNames) > 0:
                fillInterDocumentReferenceFromShepherd(doc, el, vNames[0], section)
                if len(vNames) > 1:
                    m.die(
                        f"Section autolink {h.outerHTML(el)} attempts to link to unversioned spec name '{spec}', "
                        + "but that spec is versioned as {}. ".format(config.englishFromList(f"'{x}'" for x in vNames))
                        + "Please choose a versioned spec name.",
                        el=el,
                    )
                continue
        if doc.refs.getBiblioRef(spec):
            # Bikeshed doesn't know the spec, but it's in biblio
            fillInterDocumentReferenceFromSpecref(doc, el, spec, section)
            continue
        # Unknown spec
        m.die(
            f"Spec-section autolink tried to link to non-existent '{spec}' spec:\n{h.outerHTML(el)}",
            el=el,
        )


def fillInterDocumentReferenceFromShepherd(doc: t.SpecT, el: t.ElementT, specName: str, section: str) -> None:
    heading = doc.refs.fetchHeading(specName, section, el=el)
    if heading is None:
        # Error message already handled in fetchHeading
        return
    el.tag = "a"
    el.set("href", heading["url"])
    if h.isEmpty(el):
        h.appendChild(el, h.E.cite("{spec}".format(**heading)))
        h.appendChild(el, " §\u202f{number} {text}".format(**heading))
    # Remove so the second fixInterDocumentReferences() pass doesn't reprocess this link.
    h.removeAttr(el, "bs-spec-section")

    # Mark this as a used biblio ref
    biblioRef = doc.refs.getBiblioRef(
        specName,
        status=doc.md.defaultRefStatus,
        generateFakeRef=True,
        quiet=False,
    )
    if biblioRef:
        biblio.registerBiblioUsage(doc, biblioRef, el=el)


def fillInterDocumentReferenceFromSpecref(doc: t.SpecT, el: t.ElementT, spec: str, section: str) -> None:
    bib = doc.refs.getBiblioRef(spec)
    if bib is None:
        m.die(f"Can't find spec '{spec}' when filling in cross-spec section refs.", el=el)
        return
    if bib.url is None:
        m.die(f"Can't generate a cross-spec section ref for '{spec}', because the biblio entry has no url.", el=el)
        return
    if bib.title is None:
        m.die(
            f"Can't generate a cross-spec section ref for '{spec}', because the biblio entry has no spec title.",
            el=el,
        )
        return
    el.tag = "a"
    el.set("href", bib.url + section)
    if h.isEmpty(el):
        el.text = bib.title + " §\u202f" + section[1:]
    # Remove so the second fixInterDocumentReferences() pass doesn't reprocess this link.
    h.removeAttr(el, "bs-spec-section")

    # Mark this as a used biblio ref
    biblio.registerBiblioUsage(doc, bib, el=el)


class _LinkAttrTupleT(t.NamedTuple):
    type: str | None = None
    status: str | None = None
    for_: str | None = None
    spec: str | None = None
    forHint: str | None = None


_EMPTY_LINK_ATTRS = _LinkAttrTupleT()


def _getInheritedLinkAttrs(
    el: t.ElementT | None,
    cache: dict[t.ElementT, _LinkAttrTupleT],
) -> _LinkAttrTupleT:
    if el is None:
        return _EMPTY_LINK_ATTRS
    if (res := cache.get(el)) is not None:
        return res
    pType, pStatus, pFor, pSpec, pForHint = _getInheritedLinkAttrs(el.getparent(), cache)
    attrib = el.attrib
    res = _LinkAttrTupleT(
        attrib.get("bs-link-type", attrib.get("data-link-type", pType)),
        attrib.get("bs-link-status", pStatus),
        attrib.get("bs-link-for", pFor),
        attrib.get("bs-link-spec", pSpec),
        attrib.get("bs-link-for-hint", pForHint),
    )
    cache[el] = res
    return res


def determineLinkType(
    el: t.ElementT,
    *,
    typeFromParent: str | t.UnsetT | None = UNSET,
    contents: str | None = None,
) -> str:
    """
    Determines the linkType for the element and returns it.
    The inherited type and text content can be passed if you already have them, otherwise it'll compute them fresh.
    """
    # 1. Look at data-link-type (on <a>) or bs-link-type (inherited from ancestors)
    linkType = el.get("data-link-type", typeFromParent)
    if linkType is UNSET:
        _, linkType = h.closestAttr(el, "bs-link-type", "data-link-type")
    if linkType:
        if linkType in config.linkTypes:
            return linkType
        m.die(f"Unknown link type '{linkType}':\n{h.outerHTML(el)}", el=el)
        return "unknown-type"
    # 2. Introspect on the text
    if contents is None:
        contents = h.textContent(el)
    if config.typeRe["at-rule"].match(contents):
        return "at-rule"
    if config.typeRe["type"].match(contents):
        return "type"
    if config.typeRe["selector"].match(contents):
        return "selector"
    if config.typeRe["function"].match(contents):
        return "functionish"
    return "dfn"


_FUNC_AUTOLINK_RE = re.compile(r"^([\w-]+)\(.*\)$")


def determineLinkText(el: t.ElementT, *, linkType: str | None = None, contents: str | None = None) -> str:
    """
    Determines the linking text for the element and returns it.
    linkType and text content can be passed if you already have them, otherwise it'll compute them fresh.
    """
    rawLt = el.get("bs-lt")
    if rawLt:
        linkText = rawLt
    else:
        if contents is None:
            contents = h.textContent(el)
        if linkType is None:
            linkType = determineLinkType(el, contents=contents)
        if config.linkTypeIn(linkType, "function") and (match := _FUNC_AUTOLINK_RE.match(contents)):
            # Remove arguments from CSS function autolinks,
            # as they should always be defined argument-less
            # (and this allows filled-in examples to still autolink).
            linkText = match.group(1) + "()"
        else:
            linkText = contents
    linkText = h.foldWhitespace(linkText)
    if not linkText:
        m.die("Autolink has no linktext.", el=el)
    return linkText


def classifyLink(
    el: t.ElementT,
    attrCache: dict[t.ElementT, _LinkAttrTupleT] | None = None,
) -> tuple[str, str]:
    """
    Determine and return a link's type and linking text.
    Additionally, find its status, for, spec, and for-hint, which might be on an ancestor,
    and save them directly on the element.
    (type might also be on an ancestor)
    If this is being called more than once, you should pass and reuse an attrCache empty dict
    so it can skip a lot of tree-crawling on subsequent calls.
    """
    if attrCache is None:
        attrCache = {}
    attrib = el.attrib
    pType, pStatus, pFor, pSpec, pForHint = _getInheritedLinkAttrs(el.getparent(), attrCache)
    if "bs-link-status" not in attrib and pStatus is not None:
        el.set("bs-link-status", pStatus)
    if "bs-link-for" not in attrib and pFor is not None:
        el.set("bs-link-for", pFor)
    if "bs-link-spec" not in attrib and pSpec is not None:
        el.set("bs-link-spec", pSpec)
    if "bs-link-for-hint" not in attrib and pForHint is not None:
        el.set("bs-link-for-hint", pForHint)

    if not (attrib.get("data-link-type") or pType) and not attrib.get("bs-lt"):
        contents = h.textContent(el)
    else:
        contents = None
    linkType = determineLinkType(el, typeFromParent=pType, contents=contents)
    el.set("data-link-type", linkType)

    linkText = determineLinkText(el, linkType=linkType, contents=contents)
    el.set("bs-lt", linkText)

    return linkType, linkText


def processAutolinks(doc: t.SpecT) -> None:
    refsJSON = doc.extraJC.addRefHints()

    # An <a> without an href is an autolink.
    # <i> is a legacy syntax for term autolinks. If it links up, we change it into an <a>.
    # We exclude bibliographical links, as those are processed in `processBiblioLinks`.
    autolinks = h.collectAutolinks(doc.body)
    linkAttrCache: dict[t.ElementT, _LinkAttrTupleT] = {}
    for el in autolinks:
        if el.tag == "bs-link":
            el.tag = "a"
        # Explicitly empty linking text indicates this shouldn't be an autolink.
        if el.get("bs-lt") == "":
            continue

        linkType, linkText = classifyLink(el, linkAttrCache)

        # Properties and descriptors are often written like 'foo-*'. Just ignore these.
        if linkType in ("property", "descriptor", "propdesc") and "*" in linkText:
            continue

        # Links can have multiple for values in cases like IDL constructors,
        # where there are several valid ways to set up the dfn
        # and my autogenerated links want to make sure that they'll link successfully
        # to any variant that the spec author uses.
        linkFors = config.splitForValues(el.get("bs-link-for"))

        # Status used to use ED/TR, so convert those if they appear,
        # and verify
        status = el.get("bs-link-status")
        if status == "ED":
            status = "current"
        elif status == "TR":
            status = "snapshot"
        elif status in config.linkStatuses or status is None:
            pass
        else:
            m.die(f"Unknown link status '{status}' on {h.outerHTML(el)}")
            continue

        # Some links are okay to fail, and so should do so silently.
        okayToFail = el.get("bs-okay-to-fail") is not None
        ignorable = linkText.lower() in doc.md.ignoredTerms

        ref = doc.refs.getRef(
            text=linkText,
            linkType=linkType,
            spec=el.get("bs-link-spec"),
            status=status,
            linkFor=linkFors,
            linkForHint=el.get("bs-link-for-hint"),
            explicitFor=doc.md.assumeExplicitFor,
            el=el,
            error=not okayToFail and not ignorable,
        )

        if isinstance(ref, str):
            # Error message, annotate the link with it and continue.
            el.tag = "u"
            h.removeAttr(el, "data-link-type")
            h.addClass(doc, el, "link-error")
            el.set("title", f"LINK ERROR: {ref}")
            continue

        # Capture the reference (and ensure we add a biblio entry) if it
        # points to an external specification.
        if ref and ref.status != "local":
            spec = ref.spec.upper()
            forVal = ref.for_[0] if ref.for_ else None

            # If the ref is from an anchor block, it knows what it's doing.
            # Don't follow obsoletion chains.
            allowObsolete = ref.status == "anchor-block"

            biblioRef = doc.refs.getBiblioRef(
                ref.spec,
                status=doc.md.defaultRefStatus,
                generateFakeRef=True,
                quiet=False,
                allowObsolete=allowObsolete,
            )
            if biblioRef:
                spec = biblioRef.linkText.upper()
                biblio.registerBiblioUsage(doc, biblioRef, el=el)
            doc.externalRefsUsed.addRef(spec, ref, forVal)

        if ref:
            el.set("href", ref.url)
            el.tag = "a"
            replacementText = el.get("bs-replace-text-on-link-success")
            if replacementText is not None:
                h.clearContents(el)
                el.text = replacementText
            decorateAutolink(doc, el, linkType=linkType, linkText=linkText, ref=ref)

            # Store the ref so ref-hint panels can get generated for it
            cachedRef = refsJSON.get(ref.url)
            if cachedRef is None:
                refsJSON[ref.url] = ref
            elif cachedRef is not ref and cachedRef != ref:
                # whoops, multiple refs with the same URL
                subKey = ref.refKey() + "_" + ref.url
                if subKey not in refsJSON:
                    refsJSON[subKey] = ref
                el.set("data-refhint-key", ref.refKey())
            else:
                # Ref was already stored
                pass
        else:
            if linkType == "maybe":
                el.tag = "css"
                if el.get("data-link-type"):
                    del el.attrib["data-link-type"]
            elif el.get("bs-unwrap-on-link-fail") is not None:
                # Optional link that found nothing: leave the text as if it had never been a link.
                h.replaceWithContents(el)

    h.dedupIDs(doc)


def decorateAutolink(doc: t.SpecT, el: t.ElementT, linkType: str, linkText: str, ref: refs.Ref) -> None:
    # Add additional effects to autolinks.
    if doc.md.slimBuildArtifact:
        return

    # Put an ID on every reference, so I can link to references to a term.
    if el.get("id") is None:
        _, _, id = ref.url.partition("#")
        if id:
            el.set("id", f"ref-for-{id}")
        else:
            el.set("id", "ref-for-something")
        el.set("bs-silently-dedup", "")

    # Get all the values that the type expands to, add it as a title.
    if linkType == "type":
        titleText = None
        if linkText in doc.typeExpansions:
            titleText = doc.typeExpansions[linkText]
        else:
            typeRefs = doc.refs.queryAllRefs(linkFor=linkText, ignoreObsoletes=True)
            if typeRefs:
                texts = sorted({ref.text for ref in typeRefs})
                titleText = _t("Expands to: ") + " | ".join(texts)
            doc.typeExpansions[linkText] = titleText
        if titleText:
            titleData = doc.extraJC.addLinkTitles()
            titleData[ref.url] = titleText


def removeMultipleLinks(doc: t.SpecT) -> None:
    # If there are multiple autolinks to the same thing in a paragraph,
    # only keep the first.
    if not doc.md.removeMultipleLinks:
        return
    paras: defaultdict[tuple[t.ElementT, str], list[t.ElementT]]
    paras = defaultdict(list)
    for el in h.findAll("a[data-link-type]", doc):
        if h.hasAncestor(el, lambda x: x.tag in ["pre", "xmp"]):
            # Don't strip out repeated links from opaque elements
            continue
        linkType = el.get("data-link-type")
        if linkType in ("biblio", "section"):
            # Leave biblio links alone.
            continue
        if (parent := h.parentElement(el)) is not None:
            paras[parent, el.get("href", "")].append(el)
    for links in paras.values():
        if len(links) > 1:
            for el in links[1:]:
                el.tag = "span"
                h.removeAttr(el, "href", "data-link-type")


def addSelfLinks(doc: t.SpecT) -> None:
    if doc.md.slimBuildArtifact:
        return

    def makeSelfLink(el: t.ElementT) -> t.ElementT:
        return h.E.a({"href": "#" + h.escapeUrlFrag(el.get("id", "")), "class": "self-link"})

    dfnElements = h.findAll(config.dfnElementsSelector, doc)

    foundFirstNumberedSection = False
    for el in h.findAll("h2, h3, h4, h5, h6", doc):
        foundFirstNumberedSection = foundFirstNumberedSection or (el.get("data-level") is not None)
        if foundFirstNumberedSection:
            h.appendChild(el, makeSelfLink(el))
    for el in h.findAll(".issue[id], .example[id], .note[id], li[id], dt[id]", doc):
        if list(el.iterancestors("figure")):
            # Skipping - element is inside a figure and is part of an example.
            continue
        if el.get("bs-no-self-link") is not None:
            continue
        if el.tag == "details":
            summary = h.find("summary", el)
            if summary is not None:
                h.insertAfter(summary, makeSelfLink(el))
                continue
        h.prependChild(el, makeSelfLink(el))
    if doc.md.useDfnPanels:
        dfnpanels.addDfnPanels(doc, dfnElements)
    else:
        for el in dfnElements:
            if list(el.iterancestors("a")):
                m.warn(
                    f"Found <a> ancestor, skipping self-link. Swap <dfn>/<a> order?\n  {h.outerHTML(el)}",
                    el=el,
                )
                continue
            h.appendChild(el, makeSelfLink(el))

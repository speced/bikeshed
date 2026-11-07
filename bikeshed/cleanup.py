from __future__ import annotations

import re

from PIL import Image

from . import config, h, t
from . import messages as m


def cleanupHTML(doc: t.SpecT) -> None:
    # Cleanup done immediately before serialization.

    head = None
    inBody = False
    strayHeadEls = []
    styleScoped = []
    nestedLists = []
    flattenEls = []
    for el in doc.document.iter():
        if head is None and el.tag == "head":
            head = el
            continue
        if el.tag == "body":
            inBody = True

        # Move any stray <link>, <meta>, or <style> into the <head>.
        if inBody and el.tag in ["link", "meta", "style"]:
            strayHeadEls.append(el)

        if el.tag == "style" and el.get("scoped") is not None:
            m.die(
                "<style scoped> is no longer part of HTML. Ensure your styles can apply document-globally and remove the scoped attribute.",
                el=el,
            )
            styleScoped.append(el)

        # Convert the technically-invalid <nobr> element to an appropriate <span>
        if el.tag == "nobr":
            el.tag = "span"
            el.set("style", el.get("style", "") + ";white-space:nowrap")

        # And convert <xmp> to <pre>
        if el.tag == "xmp":
            el.tag = "pre"

        # If we accidentally recognized an autolink shortcut in SVG, kill it.
        if el.tag == "{http://www.w3.org/2000/svg}a" and el.get("data-link-type") is not None:
            h.removeAttr(el, "data-link-type")
            el.tag = "{http://www.w3.org/2000/svg}tspan"

        # Add .algorithm to [algorithm] elements, for styling
        if el.get("data-algorithm") is not None and not h.hasClass(doc, el, "algorithm"):
            h.addClass(doc, el, "algorithm")

        # Allow MD-generated lists to be surrounded by HTML list containers,
        # so you can add classes/etc without an extraneous wrapper.
        if el.tag in ["ol", "ul", "dl"] and el.get("data-md") is None:
            if el.tag in ["ol", "ul"]:
                onlyChild = h.hasOnlyChild(el)
                if onlyChild is not None and el.tag == onlyChild.tag and onlyChild.get("data-md") is not None:
                    # The md-generated list container is featureless,
                    # so we can just throw it away and move its children into its parent.
                    nestedLists.append(onlyChild)
            else:
                # dls can contain both dt/dds
                # (which'll make an md-generated dl)
                # and divs, so I need to account for multiple children
                for child in h.childElements(el):
                    if child.tag == "dl" and child.get("data-md") is not None:
                        nestedLists.append(child)
                    elif child.tag == "div":
                        pass
                    elif child.tag in ["dt", "dd"]:
                        pass
                    else:
                        # misnested element; leave alone for now
                        pass

        # HTML allows dt/dd to be grouped by a div, so recognize
        # when a markdown-generated dl has a div parent and dl grandparent
        # and remove it.
        if (
            h.tagName(el) == "dl"
            and el.get("data-md") is not None
            and h.tagName(h.parentElement(el)) == "div"
            and h.tagName(h.parentElement(el, 2)) == "dl"
        ):
            # Also featureless and can be safely thrown away
            # with its children merged into the parent div
            nestedLists.append(el)

        # Remove any lingering data-md attributes on lists
        if el.tag in ["ol", "ul", "dl"] and el.get("data-md") is not None:
            h.removeAttr(el, "data-md")

        # Mark pre.idl blocks as .def, for styling
        if el.tag == "pre" and h.hasClass(doc, el, "idl") and not h.hasClass(doc, el, "def"):
            h.addClass(doc, el, "def")

        # Mark pre.cddl blocks as .def, for styling
        if el.tag == "pre" and h.hasClass(doc, el, "cddl") and not h.hasClass(doc, el, "def"):
            h.addClass(doc, el, "def")

        # Tag classes on wide types of dfns/links
        if el.tag == "dfn":
            if el.get("data-dfn-type") in config.idlTypes:
                h.addClass(doc, el, "idl-code")
            if el.get("data-dfn-type") in config.maybeTypes.union(config.linkTypeToDfnType["propdesc"]):
                if not h.hasAncestor(el, lambda x: x.tag == "pre"):
                    h.addClass(doc, el, "css")
        if el.tag == "a":
            if el.get("data-link-type") in config.idlTypes:
                h.addClass(doc, el, "idl-code")
            if el.get("data-link-type") in config.maybeTypes.union(config.linkTypeToDfnType["propdesc"]):
                if not h.hasAncestor(el, lambda x: x.tag == "pre"):
                    h.addClass(doc, el, "css")

        # Remove duplicate linking texts.
        if (
            el.tag in config.anchorishElements
            and el.get("data-lt") is not None
            and el.get("data-lt") == h.textContent(el, exact=True)
        ):
            h.removeAttr(el, "data-lt")

        # Transform the <css> fake tag into markup.
        # (Used when the ''foo'' shorthand doesn't work.)
        if el.tag == "css":
            el.tag = "span"
            h.addClass(doc, el, "css")

        # Assert IDs are used to tag arbitrary sections with an ID so you can point tests at it.
        # (The ID will be guaranteed stable across publications, but guaranteed to change when the text changes.)
        #
        # Transform the <assert> fake tag into a span with a unique ID based on its contents.
        if el.tag == "assert":
            el.tag = "span"
            el.set("id", h.safeID(doc, "assert-" + h.hashContents(el)))
        # For any <div assert> elements, add a unique ID based on its contents.
        if el.tag == "div" and el.get("assert") is not None:
            h.removeAttr(el, "assert")
            el.set("id", h.safeID(doc, "assert-" + h.hashContents(el)))

        # Add ARIA role of "note" to class="note" elements
        if el.tag in ["div", "p"] and h.hasClass(doc, el, doc.md.noteClass):
            el.set("role", "note")

        # Look for nested <a> elements, and warn about them.
        if el.tag == "a" and h.hasAncestor(el, lambda x: x.tag == "a"):
            m.warn(
                f"The following (probably auto-generated) link is illegally nested in another link:\n{h.outerHTML(el)}",
                el=el,
            )

        # If the <h1> contains only capital letters, add a class=allcaps for styling hook
        if el.tag == "h1":
            for letter in h.textContent(el):
                if letter.isalpha() and letter.islower():
                    break
            else:
                h.addClass(doc, el, "allcaps")

        # If a markdown-generated <dt> contains only a single paragraph,
        # remove that paragraph so it just contains naked text.
        if el.tag == "dt" and el.get("data-md") is not None:
            dtChild = h.hasOnlyChild(el)
            if dtChild is not None and h.tagName(dtChild) == "p" and h.emptyText(el.text) and h.emptyText(dtChild.tail):
                flattenEls.append(el)

        # Remove a bunch of attributes
        if el.get("data-attribute-info") is not None or el.get("data-dict-member-info") is not None:
            h.removeAttr(el, "data-attribute-info", "data-dict-member-info", "for")
        if el.tag in ["a", "span"]:
            h.removeAttr(
                el,
                "data-link-for",
                "data-link-for-hint",
                "data-link-status",
                "data-link-spec",
                "data-section",
                "data-biblio-type",
                "data-biblio-status",
                "data-okay-to-fail",
                "data-lt",
            )
        if el.tag != "a":
            h.removeAttr(el, "data-link-for", "data-link-type")
        if el.tag not in config.dfnElements:
            h.removeAttr(el, "data-dfn-for", "data-dfn-type", "data-export", "data-noexport")
        if el.tag == "var":
            h.removeAttr(el, "data-var-ignore")
        # Strip the control attributes
        if el.tag == "pre":
            h.removeAttr(
                el,
                "path",
                "highlight",
                "line-start",
                "data-code-show",
                "line-highlight",
                "line-numbers",
            )
        h.removeAttr(
            el,
            "bs-autolink-syntax",
            "data-alternate-id",
            "highlight",
            "nohighlight",
            "line-numbers",
            "data-opaque",
            "data-no-self-link",
            "caniuse",
            "data-silently-dedup",
            "nocrossorigin",
        )

        # Remove the internal-use-only detail of whether export/noexport is manual or default
        if el.get("data-export"):
            el.set("data-export", "")
        if el.get("data-noexport"):
            el.set("data-noexport", "")

        if doc.md.slimBuildArtifact:
            # Remove *all* data- attributes.
            for attrName in el.attrib:
                if str(attrName).startswith("data-"):
                    h.removeAttr(el, str(attrName))
    if head is not None:
        for el in strayHeadEls:
            head.append(el)
    for el in styleScoped:
        parent = h.parentElement(el)
        if parent is not None:
            h.prependChild(parent, el)
    for el in nestedLists:
        h.replaceWithContents(el)
    for el in flattenEls:
        h.moveContents(fromEl=el[0], toEl=el)


def forceCrossorigin(doc: t.SpecT) -> None:
    if not doc.md.forceCrossorigin:
        return
    for el in h.findAll("link, script[src], audio, video, img", doc):
        if el.get("crossorigin") is not None or h.treeAttr(el, "nocrossorigin") is not None:
            continue
        el.set("crossorigin", "")


def addImageSize(doc: t.SpecT) -> None:
    if doc.md.imgAutoSize is False:
        return
    imgElements = h.findAll("img", doc)
    for el in imgElements:
        if el.get("width") or el.get("height"):
            continue
        if el.get("no-autosize") is not None:
            h.removeAttr(el, "no-autosize")
            continue
        src = el.get("src")
        srcset = el.get("srcset")
        res = 1
        if src is None and srcset is None:
            m.warn(
                "<img> elements must have at least one of src or srcset.",
                el=el,
            )
            continue
        elif src is not None and srcset is not None:
            continue
        elif src is None:
            match = re.match(r"^[ \t\n]*([^ \t\n]+)[ \t\n]+(\d+)x[ \t\n]*$", srcset or "")
            if match is None:
                m.die(
                    f"Couldn't parse 'srcset' attribute: \"{srcset}\"\n"
                    + "Bikeshed only supports a single image followed by an integer resolution. If not targeting Bikeshed specifically, HTML requires a 'src' attribute (and probably a 'width' and 'height' attribute too). This warning can also be suppressed by adding a 'no-autosize' attribute.",
                    el=el,
                )
                continue
            else:
                src = match.group(1)
                el.set("src", src)
                res = int(match.group(2) or "1")
        assert src is not None
        if not doc.inputSource.cheaplyExists(""):
            # If the input source can't tell whether a file cheaply exists,
            # PIL very likely can't use it either.
            m.warn(
                f"At least one <img> doesn't have its size set ({h.outerHTML(el)}), but given the type of input document, Bikeshed can't figure out what the size should be.\nEither set 'width'/'height' manually, or opt out of auto-detection by setting the 'no-autosize' attribute.",
                el=el,
            )
            return
        if re.match(r"^(https?:/)?/", src):
            m.warn(
                f"Autodetection of image dimensions is only supported for local files, skipping this image: {h.outerHTML(el)}\nConsider setting 'width' and 'height' manually or opting out of autodetection by setting the 'no-autosize' attribute.",
                el=el,
            )
            continue
        localImg = doc.inputSource.relative(src)
        if localImg is None:
            continue
        imgPath = localImg.sourceName
        try:
            im = Image.open(imgPath)
            width, height = im.size
        except FileNotFoundError:
            m.warn(
                f"Image doesn't exist, so I couldn't determine its width and height: '{src}'",
                el=el,
            )
            continue
        except Exception as e:
            m.warn(
                f"Couldn't determine width and height of this image: '{src}'\n{e}",
                el=el,
            )
            continue
        if width % res == 0:
            el.set("width", str(int(width / res)))
        else:
            m.warn(
                f"The width ({width}px) of this image is not a multiple of the declared resolution ({res}): {src}\nConsider fixing the image so its width is a multiple of the resolution, or setting its 'width' and 'height' attribute manually.",
                el=el,
            )
        if height % res == 0:
            el.set("height", str(int(height / res)))
        else:
            m.warn(
                f"The height ({height}px) of this image is not a multiple of the declared resolution ({res}): {src}\nConsider fixing the image so its height is a multiple of the resolution, or setting its 'width' and 'height' attribute manually.",
                el=el,
            )

# pylint: disable=unused-argument
from __future__ import annotations

import io
import re
from collections import OrderedDict, defaultdict

from . import biblio, config, constants, h, printjson, railroadparser, refs, t
from . import messages as m

if t.TYPE_CHECKING:
    InfoTreeT: t.TypeAlias = list[defaultdict[str, list[str]]]

    class TransformFuncT(t.Protocol):
        def __call__(
            self,
            data: str,
            el: t.ElementT,
            doc: t.SpecT,
        ) -> t.ElementT | None: ...


def transformDataBlocks(doc: t.SpecT, tree: t.SpecT | t.ElementT) -> None:
    blockTypes: dict[str, TransformFuncT] = {
        "simpledef": transformSimpleDef,
        "propdef": transformPropdef,
        "descdef": transformDescdef,
        "elementdef": transformElementdef,
        "argumentdef": transformArgumentdef,
        "railroad": transformRailroad,
        "biblio": transformBiblio,
        "anchors": transformAnchors,
        "link-defaults": transformLinkDefaults,
        "ignored-specs": transformIgnoredSpecs,
        "info": transformInfo,
        "include": transformInclude,
        "include-code": transformIncludeCode,
        "include-raw": transformIncludeRaw,
        "pre": transformPre,
        "raw": transformRaw,
        "opaque": transformOpaque,
    }
    for el in h.findAll("[bs-datablock-type]", tree):
        if el == tree:
            continue
        blockType = el.get("bs-datablock-type")
        blockData = el.get("bs-datablock-data", "")
        if blockType not in blockTypes:
            m.die(f"Unknown datablock type '{blockType}'.", el=el)
            continue
        transformer = blockTypes[blockType]
        blockData = blockData.replace(constants.virtualLineBreak, "\n")
        newEl = transformer(blockData, el, doc)
        if newEl is not None:
            h.replaceNode(el, newEl)
            transformDataBlocks(doc, newEl)
        else:
            h.removeNode(el)


def transformPre(data: str, el: t.ElementT, doc: t.SpecT) -> t.ElementT | None:
    # Removes empty initial lines, removes shared indent, and possibly re-adds a <code> wrapper.
    h.clearContents(el)
    lines = data.split("\n")
    while lines and lines[0].strip() == "":
        lines = lines[1:]
    # Remove smallest indent, and replace tabs with 2 spaces,
    # since these will be displayed and 2 is the right size for display,
    # regardless of the page's own indent.
    lines = removeIndent(lines, 2)
    if lines:
        # If the parser pulled out a start/end <code> tag, put it back now.
        lines[0] = el.get("bs-code-start-tag", "") + lines[0]
        lines[-1] = lines[-1] + el.get("bs-code-end-tag", "")
    return h.parseInto(el, "\n".join(lines))


def transformOpaque(data: str, el: t.ElementT, doc: t.SpecT) -> t.ElementT | None:
    # Just removes indent, nothing else.
    h.clearContents(el)
    lines = data.split("\n")
    lines = removeIndent(lines, 2)
    return h.parseInto(el, "\n".join(lines))


def transformRaw(data: str, el: t.ElementT, doc: t.SpecT) -> t.ElementT | None:
    # Elements like <script> and <style>, do literally nothing.
    h.clearContents(el)
    h.appendChild(el, data)
    return el


def transformSimpleDef(data: str, el: t.ElementT, doc: t.SpecT) -> t.ElementT | None:
    rows = parseDefBlock(data, "simpledef", el, doc, capitalizeKeys=False)
    table = h.transferAttributes(el, h.E.table())
    h.addClass(doc, table, "def")
    tbody = h.appendChild(table, h.E.tbody())
    for key, val in rows.items():
        th = h.E.th()
        h.parseInto(th, key)
        td = h.E.td()
        h.parseInto(td, val)
        h.appendChild(tbody, h.E.tr({}, th, td))
    return table


def transformPropdef(data: str, el: t.ElementT, doc: t.SpecT) -> t.ElementT | None:
    parsedAttrs = parseDefBlock(data, "propdef", el, doc)
    attrs: OrderedDict[str, str | None] = OrderedDict()
    # Displays entries in the order specified in attrs,
    # then if there are any unknown parsedAttrs values,
    # they're displayed afterward in the order they were specified.
    # attrs with a value of None are required to be present in parsedAttrs;
    # attrs with any other value are optional, and use the specified value if not present in parsedAttrs
    table = h.transferAttributes(el, h.E.table())
    h.addClass(doc, table, "def")
    h.addClass(doc, table, "propdef")
    tbody = h.appendChild(table, h.E.tbody())

    if "Name" in parsedAttrs:
        table.set("data-link-for-hint", h.escapeAttr(parsedAttrs["Name"].split(",")[0].strip()))
    if h.hasClass(doc, table, "partial") or "New values" in parsedAttrs:
        attrs["Name"] = None
        attrs["New values"] = None
    elif h.hasClass(doc, table, "shorthand"):
        attrs["Name"] = None
        attrs["Value"] = None
        for defaultKey in [
            "Initial",
            "Applies to",
            "Inherited",
            "Percentages",
            "Computed value",
            "Animation type",
        ]:
            attrs[defaultKey] = "see individual properties"
        attrs["Canonical order"] = "per grammar"
    else:
        attrs["Name"] = None
        attrs["Value"] = None
        attrs["Initial"] = None
        attrs["Applies to"] = "all elements"
        attrs["Inherited"] = None
        attrs["Percentages"] = "n/a"
        attrs["Computed value"] = "as specified"
        attrs["Canonical order"] = "per grammar"
        attrs["Animation type"] = None
    if "Animatable" in parsedAttrs:
        parsedAttrs["Animation type"] = parsedAttrs.pop("Animatable")

    attrsToPrint = canonicalizeAttrs(parsedAttrs, attrs, "propdef", el)
    for key, val in attrsToPrint:
        tr = h.appendChild(tbody, h.E.tr())
        th = h.parseInto(h.E.th(), key + ":")
        td = h.parseInto(h.E.td(), val)
        h.appendChild(tr, th, td)

        if key in ("Value", "New values"):
            h.addClass(doc, tr, "value")
            h.wrapContents(th, h.E.a({"href": "https://www.w3.org/TR/css-values/#value-defs"}))
            h.addClass(doc, td, "prod")
        elif key == "Initial":
            h.wrapContents(th, h.E.a({"href": "https://www.w3.org/TR/css-cascade/#initial-values"}))
        elif key == "Inherited":
            h.wrapContents(th, h.E.a({"href": "https://www.w3.org/TR/css-cascade/#inherited-property"}))
        elif key == "Percentages":
            h.wrapContents(th, h.E.a({"href": "https://www.w3.org/TR/css-values/#percentages"}))
        elif key == "Computed value":
            h.wrapContents(th, h.E.a({"href": "https://www.w3.org/TR/css-cascade/#computed"}))
        elif key in ("Animatable", "Animation type"):
            h.wrapContents(th, h.E.a({"href": "https://www.w3.org/TR/web-animations/#animation-type"}))
        elif key == "Canonical order":
            h.wrapContents(th, h.E.a({"href": "https://www.w3.org/TR/cssom/#serializing-css-values"}))
        elif key == "Applies to":
            h.wrapContents(th, h.E.a({"href": "https://www.w3.org/TR/css-cascade/#applies-to"}))
            if val and val.lower() == "all elements":
                h.wrapContents(
                    td,
                    h.E.a(
                        {
                            "href": "https://www.w3.org/TR/css-pseudo/#generated-content",
                            "title": "Includes ::before and ::after pseudo-elements.",
                        },
                    ),
                )
        elif key == "Logical property group":
            h.wrapContents(th, h.E.a({"href": "https://drafts.csswg.org/css-logical-1/#logical-property-group"}))
            h.wrapContents(td, h.E.a({"data-link-type": "property", "data-okay-to-fail": ""}))

    return table


# TODO: Make these functions match transformPropdef's new structure


def transformDescdef(data: str, el: t.ElementT, doc: t.SpecT) -> t.ElementT | None:
    parsedAttrs = parseDefBlock(data, "descdef", el, doc)
    table = h.transferAttributes(el, h.E.table())
    h.addClass(doc, table, "def")
    h.addClass(doc, table, "descdef")
    tbody = h.appendChild(table, h.E.tbody())

    if "For" in parsedAttrs:
        table.set("data-dfn-for", h.escapeAttr(parsedAttrs["For"]))
    if h.hasClass(doc, table, "partial") or "New values" in parsedAttrs:
        requiredKeys = ["Name", "For"]
    if h.hasClass(doc, table, "mq"):
        requiredKeys = ["Name", "For", "Value"]
    else:
        requiredKeys = ["Name", "For", "Value", "Initial"]

    for key in requiredKeys:
        tr = h.appendChild(tbody, h.E.tr())
        th = h.parseInto(h.E.th(), key + ":")
        td = h.parseInto(h.E.td(), parsedAttrs.get(key, f"(no {key} specified)"))
        h.appendChild(tr, th, td)

        if key == "For":
            h.wrapContents(td, h.E.a({"data-link-type": "at-rule"}))
        elif key == "Value":
            h.addClass(doc, td, "prod")
        elif key in parsedAttrs:
            pass
        else:
            name = parsedAttrs.get("Name", "(no Name specified)")
            m.die(f"The descdef for '{name}' is missing a '{key}' line", el=el)
    for key, val in parsedAttrs.items():
        if key in requiredKeys:
            continue
        tr = h.appendChild(tbody, h.E.tr())
        th = h.parseInto(h.E.th(), key + ":")
        td = h.parseInto(h.E.td(), val)
        h.appendChild(tr, th, td)

    return table


def transformElementdef(data: str, el: t.ElementT, doc: t.SpecT) -> t.ElementT | None:
    parsedAttrs = parseDefBlock(data, "elementdef", el, doc)
    table = h.transferAttributes(el, h.E.table())
    h.addClass(doc, table, "def")
    h.addClass(doc, table, "elementdef")
    tbody = h.appendChild(table, h.E.tbody())

    attributeList = None
    if "Attribute groups" in parsedAttrs or "Attributes" in parsedAttrs:
        attributeList = h.E.ul()
        if "Attribute groups" in parsedAttrs:
            groups = [x.strip() for x in parsedAttrs["Attribute groups"].split(",")]
            for group in groups:
                h.appendChild(
                    attributeList,
                    h.E.li(
                        {},
                        h.E.a({"data-link-type": "dfn", "data-element-attr-group": ""}, group),
                    ),
                )
            del parsedAttrs["Attribute groups"]
        if "Attributes" in parsedAttrs:
            atts = [x.strip() for x in parsedAttrs["Attributes"].split(",")]
            if "Name" in parsedAttrs:
                dataFor = parsedAttrs.get("Name", "")
            else:
                dataFor = ""
            for att in atts:
                h.appendChild(
                    attributeList,
                    h.E.li(
                        {},
                        h.E.a({"data-link-type": "element-attr", "data-link-for": dataFor}, att),
                    ),
                )
        # Give a dummy value to signal that it was specified
        parsedAttrs["Attributes"] = ""

    attrs: OrderedDict[str, str | None] = OrderedDict()
    attrs["Name"] = None
    attrs["Categories"] = None
    attrs["Contexts"] = None
    attrs["Content model"] = None
    attrs["Attributes"] = None
    attrs["Dom interfaces"] = None

    attrsToPrint = canonicalizeAttrs(parsedAttrs, attrs, "elementdef", el)
    for key, val in attrsToPrint:
        tr = h.appendChild(tbody, h.E.tr())
        th = h.parseInto(h.E.th(), key + ":")
        if key == "Attributes":
            if attributeList is not None:
                td = h.E.td({}, attributeList)
            else:
                continue
        else:
            td = h.parseInto(h.E.td(), val, allowEmpty=True)
        h.appendChild(tr, th, td)

        if key == "Name":
            h.replaceContents(td, wrapCommaList(val, "dfn", "element"))
        elif key == "Categories":
            h.replaceContents(td, wrapCommaList(val, "a", "dfn"))
        elif key == "Dom interfaces":
            h.replaceContents(th, "DOM Interfaces:")
            h.replaceContents(td, wrapCommaList(val, "a", "interface"))

    return table


def transformArgumentdef(data: str, el: t.ElementT, doc: t.SpecT) -> t.ElementT | None:
    parsedAttrs = parseDefBlock(data, "argumentdef", el, doc, capitalizeKeys=False)
    table = h.transferAttributes(el, h.E.table())
    h.addClass(doc, table, "data")
    h.addClass(doc, table, "argumentdef")
    if h.hasAttr(table, "for"):
        h.renameAttr(table, "for", "data-dfn-for")
    if h.hasAttr(table, "data-dfn-for"):
        forValue = table.get("data-dfn-for", "")
        interface, _, method = forValue.partition("/")
        interface = interface.strip()
        method = method.strip()
        if not interface or not method:
            m.die(f"Argumentdef for='' values need to specify 'interface/method()'. Got '{forValue}'.", el=el)
            return None
    else:
        m.die("Argumentdef blocks need a for='interface/method()' attribute.", el=el)
        return None

    h.appendChild(
        table,
        h.E.caption(
            {},
            "Arguments for the ",
            h.E.a(
                {"data-link-type": "idl", "data-lt": method, "data-link-for": interface},
                f"{interface}.{method}",
            ),
            " method.",
        ),
        h.E.thead(
            {},
            h.E.tr(
                {},
                h.E.th({}, "Parameter"),
                h.E.th({}, "Type"),
                h.E.th({"style": "text-align:center"}, "Nullable"),
                h.E.th({"style": "text-align:center"}, "Optional"),
                h.E.th("Description"),
            ),
        ),
    )
    tbody = h.appendChild(table, h.E.tbody())

    for param, desc in parsedAttrs.items():
        tr = h.appendChild(tbody, h.E.tr())
        h.appendChild(
            tr,
            h.E.td({}, h.parseInto(h.E.dfn({"data-dfn-type": "argument"}), param)),
            h.E.td(),
            h.E.td({"style": "text-align:center"}),
            h.E.td({"style": "text-align:center"}),
            h.parseInto(h.E.td(), desc, allowEmpty=True),
        )
    return table


def parseDefBlock(
    data: str,
    type: str,
    el: t.ElementT,
    doc: t.SpecT,
    capitalizeKeys: bool = True,
) -> OrderedDict[str, str]:
    # Parses a 'def block' (lines of key:val pairs)
    # Returns a dict of the (bs-parsed) key and value.
    # Concatenates values (with a newline) from lines with the same key
    vals: OrderedDict[str, tuple[int, str]] = OrderedDict()
    startLine = h.parseLineNumber(el)
    if startLine is None:
        startLine = 1
    lines = data.split("\n")
    if lines[0].strip() == "":
        lines = lines[1:]
        startLine += 1
    if lines and lines[-1].strip() == "":
        lines = lines[:-1]
    if not lines:
        return OrderedDict()
    lastKey = None
    for lineNum, line in enumerate(lines, startLine):
        if "<!--" in line:
            commentMatch = re.match(r"(.*)<!--.*?-->(.*)", line)
            if not commentMatch:
                m.die(
                    f"Detected the start of a comment on a line, but couldn't find the end. Please remove the comment, or keep it on a single line:\n{line}",
                    lineNum=lineNum,
                )
                continue
            # Just pull the comment out, and continue
            line = commentMatch[1] + commentMatch[2]
            if line.strip() == "":
                # If the whole line was a comment, just ignore it.
                continue
        match = re.match(r"\s*([^:]+):\s*(\S.*)?", line)
        if match is None:
            if lastKey is not None and (line.strip() == "" or re.match(r"\s+", line)):
                key = lastKey
                val = line.strip()
            else:
                m.die(f"Incorrectly formatted {type} line for '{vals.get('Name', '???')}':\n{line}", lineNum=lineNum)
                continue
        else:
            key = match.group(1).strip()
            if capitalizeKeys:
                key = key.capitalize()
            lastKey = key
            val = (match.group(2) or "").strip()
        if key in vals:
            vals[key] = (vals[key][0], vals[key][1] + "\n" + val)
        else:
            vals[key] = (lineNum, val)
    retVals: OrderedDict[str, str] = OrderedDict()
    for key, (lineNum, val) in vals.items():
        keyConfig = h.ParseConfig.fromSpec(doc, "the line's key (before the colon)")
        valConfig = h.ParseConfig.fromSpec(doc, "lineNum line's value (after the colon)")
        key = h.parseText(key, keyConfig, startLine=lineNum, closeElements=True, context=el)
        if type in ("propdef", "descdef") and key == "Name":
            newVal = ""
            for node in h.nodesFromHtml(val, valConfig, startLine=1, closeElements=True, context=el):
                if isinstance(node, h.parser.Text):
                    newVal += str(node)
                else:
                    m.die(
                        f"'Name' key should contain just the property/descriptor name, or a comma-separated list. Found markup:\n  {val}",
                        lineNum=lineNum,
                    )
            retVals[key] = newVal
        else:
            retVals[key] = h.parseText(val, valConfig, startLine=lineNum, closeElements=True, context=el)
    return retVals


def wrapCommaList(text: str, tagName: str, type: str) -> list[t.NodeT]:
    # Takes a comma-separated list of terms,
    # and wraps each term in a dfn or link of the specified type.
    ret: list[t.NodeT] = []
    for term in [x.strip() for x in text.split(",")]:
        typeAttr = "data-dfn-type" if tagName == "dfn" else "data-link-type"
        ret.append(h.createElement(tagName, {typeAttr: type}, term))
        ret.append(", ")
    # Drop the trailing comma
    return ret[:-1]


def canonicalizeAttrs(
    parsedAttrs: OrderedDict[str, str],
    attrs: OrderedDict[str, str | None],
    type: str,
    el: t.ElementT,
) -> list[tuple[str, str]]:
    # Processes and re-orders parsedAttrs.
    # attrs specifies the keys that are required (with a value of None)
    # and optional (with a non-None default value).
    # The order of attrs keys is also respected,
    # with any additional keys in parsedAttrs put at the end.
    # Returns a list of (key, value) tuples, in the desired order.
    attrsToPrint = []
    for key, defaultVal in attrs.items():
        if key in parsedAttrs:
            # Key was provided
            attrsToPrint.append((key, parsedAttrs[key]))
            continue
        elif defaultVal is None:
            # Required key, not provided
            if "Name" in parsedAttrs:
                m.die(f"The {type} block for '{parsedAttrs.get('Name')}' is missing a '{key}' line.", el=el)
            else:
                m.die(f"The {type} block is missing a '{key}' line.", el=el)
            continue
        else:
            # Optional key, just use default
            attrsToPrint.append((key, defaultVal))
    for key, val in parsedAttrs.items():
        # Find any "custom" provided keys
        if key not in attrs:
            attrsToPrint.append((key, val))
    return attrsToPrint


def transformRailroad(data: str, el: t.ElementT, doc: t.SpecT) -> t.ElementT | None:
    ret = h.transferAttributes(el, h.E.div())
    h.addClass(doc, ret, "railroad")
    lines = data.split("\n")
    if lines[0].strip() == "":
        lines = lines[1:]
    if lines and lines[-1].strip() == "":
        lines = lines[:-1]
    data = "\n".join(lines)
    diagram = railroadparser.parse(data)
    if diagram:
        doc.extraJC.addRailroad()
        temp = io.StringIO()
        diagram.writeSvg(temp.write)
        return h.parseInto(ret, temp.getvalue())
    return None


def transformBiblio(data: str, el: t.ElementT, doc: t.SpecT) -> t.ElementT | None:
    storage: t.BiblioStorageT = defaultdict(list)
    biblio.processSpecrefBiblioFile(data, storage, order=1)
    for k, vs in storage.items():
        doc.refs.biblioKeys.add(k)
        doc.refs.biblios[k].extend(vs)
    return None


def transformAnchors(data: str, el: t.ElementT, doc: t.SpecT) -> t.ElementT | None:
    lineNum = h.parseLineNumber(el)
    anchors = parseInfoTree(data.split("\n"), doc.md.indent, lineNum)
    processAnchors(anchors, doc, lineNum)
    return None


def processAnchors(anchors: InfoTreeT, doc: t.SpecT, lineNum: int | None = None) -> None:
    for anchor in anchors:
        if "type" not in anchor or len(anchor["type"]) != 1:
            m.die(f"Each anchor needs exactly one type. Got:\n{printjson.printjson(anchor)}", lineNum=lineNum)
            continue
        if "text" not in anchor or len(anchor["text"]) != 1:
            m.die(f"Each anchor needs exactly one text. Got:\n{printjson.printjson(anchor)}", lineNum=lineNum)
            continue
        if "url" not in anchor and "urlPrefix" not in anchor:
            m.die(
                f"Each anchor needs a url and/or at least one urlPrefix. Got:\n{printjson.printjson(anchor)}",
                lineNum=lineNum,
            )
            continue
        if "urlPrefix" in anchor:
            urlPrefix = "".join(anchor["urlPrefix"])
        else:
            urlPrefix = ""
        if "url" in anchor:
            urlSuffix = anchor["url"][0]
        else:
            urlSuffix = config.simplifyText(anchor["text"][0])
        if "#" in urlPrefix or "#" in urlSuffix or urlPrefix == "":
            urlJoiner = ""
        else:
            urlJoiner = "#"
        url = urlPrefix + urlJoiner + urlSuffix

        if url.startswith("#"):
            m.die(
                f"<pre class=anchors> anchor was defined with a local link '{url}'. Please use urlPrefix and/or url to define an external URL.",
            )
        shortname = None
        level = None
        if "shortname" in anchor and "level" in anchor:
            shortname = anchor["shortname"][0]
            level = anchor["level"][0]
        spec = anchor["spec"][0] if "spec" in anchor else None
        if shortname and not spec:
            if level:
                spec = f"{shortname}-{level}"
            else:
                spec = shortname
        elif spec and not shortname:
            match = re.match(r"(.*)-(\d+)$", spec)
            if match:
                shortname = match.group(1)
                level = match.group(2)
            else:
                shortname = spec
                level = ""
        if "status" in anchor:
            status = anchor["status"][0]
            if status in config.linkStatuses:
                pass
            else:
                m.die(
                    f"Anchor statuses must be {config.englishFromList(config.linkStatuses)}. Got '{status}'.",
                    lineNum=lineNum,
                )
                continue
        else:
            status = "anchor-block"
        aType = anchor["type"][0].lower()
        refData = refs.RefDataT(
            {
                "type": aType,
                "url": url,
                "shortname": shortname.lower() if shortname is not None else doc.md.shortname,
                "level": level if level is not None else doc.md.level,
                "for_": anchor.get("for", []),
                "export": True,
                "normative": True,
                "status": status,
                "spec": spec.lower() if spec is not None else "",
                # anchor-block refs sometimes share URLs between different refs
                # (for example, just linking them all to an ID-less PDF)
                # so add a uniquifier other code can rely on to tell them apart.
                "uniquifier": h.uniqueID(url, *anchor["text"], *anchor["for"]),
            },
        )
        for displayText in anchor["text"]:
            if aType in config.lowercaseTypes:
                aText = displayText.lower()
            else:
                aText = displayText
            doc.refs.anchorBlockRefs.refs[aText].append(
                refs.RefWrapper(
                    aText,
                    displayText,
                    refData,
                ),
            )
        methodishStart = re.match(r"([^(]+\()[^)]", anchor["text"][0])
        if methodishStart:
            doc.refs.anchorBlockRefs.addMethodVariants(anchor["text"][0], anchor.get("for", []), doc.md.shortname)


def transformLinkDefaults(data: str, el: t.ElementT, doc: t.SpecT) -> t.ElementT | None:
    lineNum = h.parseLineNumber(el)
    lds = parseInfoTree(data.split("\n"), doc.md.indent, lineNum)
    processLinkDefaults(lds, doc, lineNum)
    return None


def processLinkDefaults(lds: InfoTreeT, doc: t.SpecT, lineNum: int | None = None) -> None:
    for ld in lds:
        if len(ld.get("type", [])) != 1:
            m.die(f"Every link default needs exactly one type. Got:\n{printjson.printjson(ld)}", lineNum=lineNum)
            continue

        type = ld["type"][0]

        if len(ld.get("spec", [])) != 1:
            m.die(f"Every link default needs exactly one spec. Got:\n{printjson.printjson(ld)}", lineNum=lineNum)
            continue

        spec = ld["spec"][0]

        if len(ld.get("text", [])) != 1:
            m.die(f"Every link default needs exactly one text. Got:\n{printjson.printjson(ld)}", lineNum=lineNum)
            continue

        text = ld["text"][0]
        if "status" in ld:
            status = ld["status"][0]
        else:
            status = None

        if "for" in ld:
            for _for in ld["for"]:
                doc.md.linkDefaults[text].append((spec, type, status, _for))
        else:
            doc.md.linkDefaults[text].append((spec, type, status, None))


def transformIgnoredSpecs(data: str, el: t.ElementT, doc: t.SpecT) -> t.ElementT | None:
    specs = parseInfoTree(data.split("\n"), doc.md.indent, h.parseLineNumber(el))
    processIgnoredSpecs(specs, doc, h.parseLineNumber(el))
    return None


def processIgnoredSpecs(specs: InfoTreeT, doc: t.SpecT, lineNum: int | None = None) -> None:
    for spec in specs:
        if len(spec.get("spec", [])) == 0:
            m.die(
                f"Every ignored spec line needs at least one 'spec' value. Got:\n{printjson.printjson(spec)}",
                lineNum=lineNum,
            )
            continue
        specNames = spec["spec"]
        if len(spec.get("replacedBy", [])) > 1:
            m.die(
                f"Every ignored spec line needs at most one 'replacedBy' value. Got:\n{printjson.printjson(spec)}",
                lineNum=lineNum,
            )
            continue
        replacedBy = spec["replacedBy"][0] if "replacedBy" in spec else None
        for specName in specNames:
            if replacedBy:
                doc.refs.replacedSpecs.add((specName, replacedBy))
            else:
                doc.refs.ignoredSpecs.add(specName)


def transformInfo(data: str, el: t.ElementT, doc: t.SpecT) -> t.ElementT | None:
    # More generic InfoTree system.
    # A <pre class=info> can contain any of the InfoTree collections,
    # identified by an 'info' line.
    infos = parseInfoTree(data.split("\n"), doc.md.indent, h.parseLineNumber(el))
    processInfo(infos, doc, h.parseLineNumber(el))
    return None


def processInfo(infos: InfoTreeT, doc: t.SpecT, lineNum: int | None = None) -> None:
    knownInfoTypes = {
        "anchors": processAnchors,
        "link-defaults": processLinkDefaults,
        "ignored-specs": processIgnoredSpecs,
    }
    infoCollections = defaultdict(list)
    for info in infos:
        if len(info.get("info", [])) != 1:
            m.die(
                f"Every info-block line needs exactly one 'info' type. Got:\n{printjson.printjson(info)}",
                lineNum=lineNum,
            )
            continue
        infoType = info["info"][0].lower()
        if infoType not in knownInfoTypes:
            m.die(f"Unknown info-block type '{infoType}'", lineNum=lineNum)
            continue
        infoCollections[infoType].append(info)
    for infoType, infoItem in infoCollections.items():
        knownInfoTypes[infoType](infoItem, doc, lineNum=0)


def transformInclude(data: str, el: t.ElementT, doc: t.SpecT) -> t.ElementT | None:
    infos = parseInfoTree(data.split("\n"), doc.md.indent, h.parseLineNumber(el))
    path = None
    macros = {}
    for info in infos:
        if "path" in info:
            if path is None:
                path = info["path"][0]
            else:
                m.die("Include blocks must only contain a single 'path'.", el=el)
                return None
        if "macros" in info:
            for k, v in info.items():
                if k == "macros":
                    continue
                if k not in macros and len(v) == 1:
                    macros[k] = v[0]
                else:
                    m.die(
                        f"Include block defines the '{k}' local macro more than once.",
                        el=el,
                    )
                    return None
    if not path:
        m.die("Include blocks must contain a 'path' info.", el=el)
        return None

    ret = h.transferAttributes(el, h.E.pre())
    h.addClass(doc, ret, "include")
    ret.set("path", path)
    for i, (macroName, macroVal) in enumerate(macros.items()):
        ret.set(f"macro-{i}", f"{macroName} {macroVal}")
    return ret


def transformIncludeCode(data: str, el: t.ElementT, doc: t.SpecT) -> t.ElementT | None:
    infos = parseInfoTree(data.split("\n"), doc.md.indent, h.parseLineNumber(el))
    path = None
    highlight = None
    lineStart = None
    show = []
    lineHighlight = []
    lineNumbers = False
    for info in infos:
        if "path" in info:
            if path is None:
                path = info["path"][0]
            else:
                m.die(
                    "Include-code blocks must only contain a single 'path'.",
                    el=el,
                )
        if "highlight" in info:
            if highlight is None:
                highlight = info["highlight"][0]
            else:
                m.die(
                    "Include-code blocks must only contain a single 'highlight'.",
                    el=el,
                )
        if "line-start" in info:
            if lineStart is None:
                lineStart = info["line-start"][0]
            else:
                m.die(
                    "Include-code blocks must only contain a single 'line-start'.",
                    el=el,
                )
        if "show" in info:
            show.extend(info["show"])
        if "line-highlight" in info:
            lineHighlight.extend(info["line-highlight"])
        if "line-numbers" in info:
            lineNumbers = True
        if "no-line-numbers" in info:
            lineNumbers = False

    if not path:
        m.die("Include-code blocks must contain a 'path' info.", el=el)
        return None

    ret = h.transferAttributes(el, h.E.pre())
    h.addClass(doc, ret, "include-code")
    ret.set("path", path)
    if highlight:
        ret.set("highlight", highlight)
    if lineStart:
        ret.set("line-start", lineStart)
    if show:
        ret.set("data-code-show", ",".join(show))
    if lineHighlight:
        ret.set("line-highlight", ",".join(lineHighlight))
    if lineNumbers:
        ret.set("line-numbers", "")
    return ret


def transformIncludeRaw(data: str, el: t.ElementT, doc: t.SpecT) -> t.ElementT | None:
    infos = parseInfoTree(data.split("\n"), doc.md.indent, h.parseLineNumber(el))
    path = None
    for info in infos:
        if "path" in info:
            if path is None:
                path = info["path"][0]
            else:
                m.die("Include blocks must only contain a single 'path'.", el=el)
                return None
    if not path:
        m.die("Include-raw blocks must contain a 'path' info.", el=el)
        return None

    ret = h.transferAttributes(el, h.E.pre())
    h.addClass(doc, ret, "include-raw")
    ret.set("path", path)
    return ret


def parseInfoTree(lines: list[str], indent: int = 4, lineNum: int | None = 0) -> InfoTreeT:
    # Parses sets of info, which can be arranged into trees.
    # Each info is a set of key/value pairs, semicolon-separated:
    # key1: val1; key2: val2; key3: val3
    # Intead of semicolon-separating, pieces can be nested with higher indentation
    # key1: val1
    #     key2: val2
    #         key3: val3
    # Multiple fragments can be chained off of a single higher-level piece,
    # to avoid repetition:
    # key1: val1
    #     key2: val2
    #     key2a: val2a
    # ===
    # key1: val1; key2: val2
    # key1: val1; key2a: val2a
    # Starting a line with # will comment it out.

    lines = removeCommentLines(lines)
    lines = removeIndent(lines, indent)

    def extendData(datas: InfoTreeT, infoLevels: InfoTreeT) -> None:
        if not infoLevels:
            return
        newData = defaultdict(list)
        for infos in infoLevels:
            for k, v in infos.items():
                newData[k].extend(v)
        datas.append(newData)

    # Determine the indents, separate the lines.
    datas: InfoTreeT = []
    infoLevels: InfoTreeT = []
    lastIndent = -1
    indentSpace = " " * indent
    for i, line in enumerate(lines):
        if lineNum is not None:
            thisLine = int(lineNum) + i
        else:
            thisLine = None
        if line.strip() == "":
            continue
        if re.match(r"^\s*<!--.*-->\s*$", line):
            # HTML comment filling the whole line,
            # go ahead and strip it
            continue
        ws, text = t.cast("re.Match", re.match(r"(\s*)(.*)", line)).groups()
        if text.startswith("#"):  # comment
            continue
        wsLen = len(ws.replace("\t", indentSpace))
        if wsLen % indent != 0:
            visibleWs = ws.replace("\t", "\\t").replace(" ", "\\s")
            m.die(
                f"Line has inconsistent indentation; use tabs or {indent} spaces:\n{visibleWs + text}",
                lineNum=thisLine,
            )
            return []
        wsLen = wsLen // indent
        if wsLen >= lastIndent + 2:
            m.die(
                f"Line jumps {wsLen - lastIndent} indent levels:\n{text}",
                lineNum=thisLine,
            )
            return []
        if wsLen <= lastIndent:
            # Previous line was a leaf node; build its full data and add to the list
            extendData(datas, infoLevels[: lastIndent + 1])
        # Otherwise, chained data. Parse it, put it into infoLevels
        info = defaultdict(list)
        for piece in text.split(";"):
            if piece.strip() == "":
                continue
            match = re.match(r"([^:]+):\s*(.*)", piece)
            if not match:
                m.die(f"Line doesn't match the grammar `k:v; k:v; k:v`:\n{line}", lineNum=thisLine)
                return []
            key = match.group(1).strip()
            val = match.group(2).strip()
            info[key].append(val)
        if wsLen < len(infoLevels):
            infoLevels[wsLen] = info
        else:
            infoLevels.append(info)
        lastIndent = wsLen
    # Grab the last bit of data.
    extendData(datas, infoLevels[: lastIndent + 1])
    return datas


def removeCommentLines(lines: list[str]) -> list[str]:
    # removes comments from a line
    for i in range(len(lines)):
        while match := re.search(r"(.*)(<!--.*?-->)(.*)", lines[i]):
            lines[i] = match[1] + match[3]
    return lines


def removeBlankLines(lines: list[str]) -> list[str]:
    # removes lines that are blank (save for possibly whitespace)
    ret = []
    for line in lines:
        if line.strip() == "":
            continue
        ret.append(line)
    return ret


def removeIndent(lines: list[str], tabSize: int) -> list[str]:
    # Finds the smallest indent from non-WS lines,
    # and removes it from all lines.
    minIndentSize = 1000
    for i, line in enumerate(lines):
        if line.strip() == "":
            lines[i] = ""
            continue
        match = re.match(r"([ \t]+)(.*)", line)
        if not match:
            minIndentSize = 0
            continue
        indent = match[1]
        if "\t" in indent:
            indent = indent.replace("\t", " " * tabSize)
            lines[i] = indent + match[2]
        indentSize = len(indent)
        minIndentSize = min(minIndentSize, indentSize)
    if minIndentSize in (0, 1000):
        # nothing to remove
        return lines
    minIndent = " " * minIndentSize
    for i, line in enumerate(lines):
        if line.startswith(minIndent):
            lines[i] = line[minIndentSize:]
    return lines

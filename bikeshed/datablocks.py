# pylint: disable=unused-argument
from __future__ import annotations

import dataclasses
import re
from collections import OrderedDict, defaultdict
from functools import reduce

from . import biblio, config, h, messages as m, t
from .refs.wrapper import RefWrapper


# When writing a new transformFoo function,
# PAY ATTENTION TO THE INDENT OF THE FIRST LINE
# OR ELSE YOU'LL MESS UP THE MARKDOWN PARSER.
# Generally, just spam the first-line's indent onto every line;
# if you're outputting a raw element (<pre>/etc),
# just spam it onto the first line.

if t.TYPE_CHECKING:
    InfoTreeT: t.TypeAlias = list[defaultdict[str, list[str]]]

    class TransformFuncT(t.Protocol):
        def __call__(
            self, lines: list[str], startTag: h.StartTag, indent: str, doc: t.SpecT
        ) -> list[str] | list[h.ParserNode]:
            ...


def transformDataBlocks(doc: t.SpecT, nodes: list[h.ParserNode]) -> list[h.ParserNode]:
    """
    This function does a single pass through the doc,
    finding all the "data blocks" and processing them.
    A "data block" is any <pre> or <xmp> element.
    #
    When a data block is found, the *contents* of the block
    are passed to the appropriate processing function as an
    array of lines.  The function should return a new array
    of lines to replace the *entire* block.
    #
    That is, we give you the insides, but replace the whole
    thing.
    #
    Additionally, we pass in the tag-name used (pre or xmp)
    and the line with the content, in case it has useful data in it.
    """

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
    }
    newNodes: list[h.ParserNode] = []
    for node in groupDataBlocks(nodes):
        if not isinstance(node, DataBlock):
            newNodes.append(node)
            continue
        blockType = blockTypeFromTag(node.startTag, list(blockTypes.keys()))
        lines = node.data
        if lines and lines[0].strip() == "":
            lines = lines[1:]
        if lines and lines[-1].strip() == "":
            lines = lines[:-1]

        replacements = blockTypes[blockType](
            lines=removeCommonPrefix(lines, startLine=node.startTag.line),
            startTag=node.startTag,
            indent=node.indent,
            doc=doc,
        )
        if replacements and isinstance(replacements[0], str):
            replacementLines = t.cast("list[str]", replacements)
            replacementNodes = list(h.nodesFromHtml("\n".join(replacementLines)))
            # Raw string lines means I haven't thought about line numbers,
            # so just reset them to the start tag's for attribution.
            for rNode in replacementNodes:
                rNode.line = node.startTag.line
            replacementHeight = len(replacements)
        else:
            replacementNodes = t.cast("list[h.ParserNode]", replacements)
            replacementHeight = len(h.linesFromNodes(replacementNodes))
        newNodes.extend(replacementNodes)
        if replacementHeight != node.height:
            newNodes.append(h.Text(-1, -1, "\n"))
            newNodes.append(
                h.Comment(
                    line=-1,
                    endLine=-1,
                    data=f"LINE NUMBER RESET {node.startTag.line + node.height - 2}",
                    # -2 because I'm introducing two linebreaks
                )
            )
            newNodes.append(h.Text(-1, -1, "\n"))

    return newNodes


@dataclasses.dataclass
class DataBlock:
    startTag: h.StartTag
    height: int
    indent: str
    data: list[str]


def groupDataBlocks(nodes: list[h.ParserNode]) -> t.Generator[h.ParserNode | DataBlock, None, None]:
    if not nodes:
        return
    prevNode = nodes[0]
    yield prevNode
    nodeIter = iter(nodes[1:])
    for node in nodeIter:
        if isinstance(node, h.RawElement) and node.tag.lower() == "xmp":
            indent = indentFromNode(prevNode, node)
            if indent is None:
                yield node
                prevNode = node
                continue
            yield DataBlock(
                startTag=node.startTag.finalize(),
                height=node.endLine - node.line + 1,
                indent=indent,
                data=node.data.split("\n"),
            )
            prevNode = node
        elif isinstance(node, h.StartTag) and node.tag.lower() == "pre":
            indent = indentFromNode(prevNode, node)
            if indent is None:
                yield node
                prevNode = node
                continue
            startTag = node
            contents = []
            endTag = None
            for innerNode in nodeIter:
                if isinstance(innerNode, h.EndTag) and innerNode.tag.lower() == "pre":
                    endTag = innerNode
                    break
                if isinstance(innerNode, h.StartTag) and innerNode.tag.lower() == "pre":
                    m.die(
                        f"Nested <pre> elements will break at the moment, sorry. (Parent is at line {startTag.line}.)",
                        lineNum=innerNode.line,
                    )
                contents.append(innerNode)
            if endTag is None:
                m.die("Hit EOF while trying to find the </pre>.", lineNum=startTag.line)
                endTag = h.EndTag(startTag.endLine, startTag.endLine, "pre")
            yield DataBlock(
                startTag=startTag.finalize(),
                height=endTag.endLine - startTag.line + 1,
                indent=indent,
                data="".join(str(x) for x in contents).split("\n"),
            )
            prevNode = endTag
        else:
            yield node
            prevNode = node


def indentFromNode(node: h.ParserNode, nextNode: h.ParserNode) -> str | None:
    if not isinstance(node, h.Text):
        m.die("<pre>/<xmp> elements must be the first tag on their line.", lineNum=nextNode.line)
        return None
    lastLine = node.text.split("\n")[-1]
    if lastLine.strip() != "":
        m.die("<pre>/<xmp> elements must not have any text on the line before their start tag.", lineNum=nextNode.line)
        return None
    return lastLine


def stripCodeWrapper(lines: list[str], startLine: int) -> tuple[list[str], h.StartTag | None]:
    # Removes the <code> that people sometimes wrap their <pre>
    # contents in.
    if len(lines) <= 1:
        return lines, None

    startMatch = splitOnStartTag(lines[0], "code", startLine=startLine)
    endMatch = splitOnEndTag(lines[-1], "code", startLine=startLine)
    if not startMatch or not endMatch:
        return lines, None

    beforeStartTag, startTag, afterStartTag = startMatch
    beforeEndTag, afterEndTag = endMatch
    if beforeStartTag.strip() != "" or afterEndTag.strip() != "":
        return lines, None

    lines[0] = afterStartTag
    lines[-1] = beforeEndTag
    return lines, startTag


def removeCommonPrefix(lines: list[str], startLine: int) -> list[str]:
    # Remove the longest common whitespace prefix from the lines.

    # Skip over empty lines, as their indent might get stripped.
    indents = [getWsPrefix(line) for line in lines if line.strip() != ""]
    if len(indents) == 0:
        return lines

    commonIndent = reduce(commonPrefix, indents)
    if commonIndent != "":
        for i, line in enumerate(lines):
            if line.startswith(commonIndent):
                lines[i] = line[len(commonIndent) :]
    return lines


def commonPrefix(line1: str, line2: str) -> str:
    prefixSoFar = ""
    for i, char in enumerate(line1):
        if i == len(line2):
            break
        if char == line2[i]:
            prefixSoFar += char
        else:
            break
    return prefixSoFar


def getWsPrefix(line: str) -> str:
    match = t.cast("re.Match", re.match(r"(\s*)", line))
    return t.cast(str, match.group(1))


def blockTypeFromTag(tag: h.StartTag, blockTypes: t.Sequence[str]) -> str:
    # See which of the designated blockTypes classes
    # are present in the tag's classes.
    foundTypes = list(tag.classes & set(blockTypes))

    if len(foundTypes) > 1:
        typeList = config.englishFromList((f"'{x}'" for x in foundTypes), "and")
        m.die(
            f"Found {typeList} classes on the <{tag.tag}>, so can't tell which to process the block as. Please use only one.",
            lineNum=tag.line,
        )
        return "pre"
    elif len(foundTypes) == 0:
        return "pre"
    else:
        return foundTypes[0]


def splitOnStartTag(text: str, tagName: str, startLine: int) -> tuple[str, h.StartTag, str] | None:
    nodes = list(h.nodesFromHtml(text, startLine=startLine))
    startTagIndex: int
    for i, node in enumerate(nodes):
        if isinstance(node, h.StartTag) and node.tag.lower() == tagName:
            startTagIndex = i
            startTag = node
            break
    else:
        return None
    return (
        "".join(str(x) for x in nodes[:startTagIndex]),
        startTag,
        "".join(str(x) for x in nodes[startTagIndex + 1 :]),
    )


def splitOnEndTag(text: str, tagName: str, startLine: int) -> tuple[str, str] | None:
    nodes = list(h.nodesFromHtml(text, startLine=startLine))
    endTagIndex: int
    for i, node in enumerate(nodes):
        if isinstance(node, h.EndTag) and node.tag.lower() == tagName:
            endTagIndex = i
            break
    else:
        return None
    return ("".join(str(x) for x in nodes[:endTagIndex]), "".join(str(x) for x in nodes[endTagIndex + 1 :]))


def transformPre(lines: list[str], startTag: h.StartTag, indent: str, doc: t.SpecT) -> list[str]:
    lines, codeTag = stripCodeWrapper(lines, startLine=startTag.line)

    if not lines:
        return lines

    lines = [line.replace("\t", "  ") for line in lines]

    if codeTag:
        lines[0] = str(codeTag) + lines[0]
        lines[-1] += codeTag.printEndTag()

    lines[0] = indent + str(startTag) + lines[0]
    lines[-1] += startTag.printEndTag()

    return lines


def transformSimpleDef(lines: list[str], startTag: h.StartTag, indent: str, doc: t.SpecT) -> list[str]:
    rows = parseDefBlock(lines, "simpledef", lineNum=startTag.line)
    newStartTag = startTag.clone(tag="table")
    newStartTag.classes.remove("simpledef")
    newStartTag.classes.add("def")
    ret = [str(newStartTag)]
    for key, val in rows.items():
        ret.append(f"<tr><th>{key}<td>{val}")
    ret.append("</table>")

    ret = [indent + x for x in ret]

    return ret


def transformPropdef(lines: list[str], startTag: h.StartTag, indent: str, doc: t.SpecT) -> list[str]:
    attrs: OrderedDict[str, str | None] = OrderedDict()
    parsedAttrs = parseDefBlock(lines, "propdef", lineNum=startTag.line)
    # Displays entries in the order specified in attrs,
    # then if there are any unknown parsedAttrs values,
    # they're displayed afterward in the order they were specified.
    # attrs with a value of None are required to be present in parsedAttrs;
    # attrs with any other value are optional, and use the specified value if not present in parsedAttrs
    newStartTag = startTag.clone(tag="table")
    newStartTag.classes.add("def")
    newStartTag.classes.add("propdef")
    if "Name" in parsedAttrs:
        newStartTag.attrs["data-link-for-hint"] = parsedAttrs["Name"].split(",")[0].strip()
    if "partial" in newStartTag.classes or "New values" in parsedAttrs:
        attrs["Name"] = None
        attrs["New values"] = None
        newStartTag.classes.add("partial")
    elif "shorthand" in newStartTag.classes:
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
    # We are in the process of migrating specs from using 'Animatable' to
    # using 'Animation type'. If we find 'Animatable' in the parsed attributes,
    # drop the default 'Animation type' entry.
    if "Animatable" in parsedAttrs:
        attrs.pop("Animation type")

    attrsToPrint = []
    for key, val in attrs.items():
        if key in parsedAttrs:
            # Key was provided
            val = parsedAttrs[key]
        elif val is None:
            # Required key, not provided
            m.die(
                f"The propdef for '{parsedAttrs.get('Name', '???')}' is missing a '{key}' line.", lineNum=startTag.line
            )
            continue
        else:
            # Optional key, just use default
            pass
        attrsToPrint.append((key, val))
    for key, val in parsedAttrs.items():
        # Find any "custom" provided keys
        if key not in attrs:
            attrsToPrint.append((key, val))

    ret = [str(newStartTag)]
    for key, val in attrsToPrint:
        tr = "<tr>"
        th = f"<th>{key}:"
        td = f"<td>{val}"
        if key in ("Value", "New values"):
            tr = "<tr class=value>"
            th = f"<th><a href='https://www.w3.org/TR/css-values/#value-defs'>{key}:</a>"
            td = f"<td class=prod>{val}"
        elif key == "Initial":
            th = f"<th><a href='https://www.w3.org/TR/css-cascade/#initial-values'>{key}:</a>"
        elif key == "Inherited":
            th = f"<th><a href='https://www.w3.org/TR/css-cascade/#inherited-property'>{key}:</a>"
        elif key == "Percentages":
            th = f"<th><a href='https://www.w3.org/TR/css-values/#percentages'>{key}:</a>"
        elif key == "Computed value":
            th = f"<th><a href='https://www.w3.org/TR/css-cascade/#computed'>{key}:</a>"
        elif key in ("Animatable", "Animation type"):
            th = f"<th><a href='https://www.w3.org/TR/web-animations/#animation-type'>{key}:</a>"
        elif key == "Canonical order":
            th = f"<th><a href='https://www.w3.org/TR/cssom/#serializing-css-values'>{key}:</a>"
        elif key == "Applies to":
            th = f"<th><a href='https://www.w3.org/TR/css-cascade/#applies-to'>{key}:</a>"
            if val and val.lower() == "all elements":
                td = "<td><a href='https://www.w3.org/TR/css-pseudo/#generated-content' title='Includes ::before and ::after pseudo-elements.'>all elements</a>"
        elif key == "Logical property group":
            th = f"<th><a href='https://drafts.csswg.org/css-logical-1/#logical-property-group'>{key}:</a>"
            td = f"<td><a data-link-type=property data-okay-to-fail>{val}</a>"
        ret.append(tr + th + td)
    ret.append("</table>")

    ret = [indent + x for x in ret]

    return ret


# TODO: Make these functions match transformPropdef's new structure


def transformDescdef(lines: list[str], startTag: h.StartTag, indent: str, doc: t.SpecT) -> list[str]:
    newStartTag = startTag.clone(tag="table")
    newStartTag.classes.add("def")
    newStartTag.classes.add("descdef")
    vals = parseDefBlock(lines, "descdef", lineNum=startTag.line)
    newStartTag.attrs["data-dfn-for"] = vals.get("For", "")
    if "partial" in newStartTag.classes or "New values" in vals:
        requiredKeys = ["Name", "For"]
        newStartTag.classes.add("partial")
    if "mq" in newStartTag.classes:
        requiredKeys = ["Name", "For", "Value"]
        newStartTag.classes.add("mq")
    else:
        requiredKeys = ["Name", "For", "Value", "Initial"]
    ret = [str(newStartTag)]
    for key in requiredKeys:
        val = vals.get(key, "")
        if key == "For":
            ret.append("<tr><th>{}:<td><a at-rule>{}</a>".format(key, val))
        elif key == "Value":
            ret.append("<tr><th>{}:<td class='prod'>{}".format(key, val))
        elif key in vals:
            ret.append("<tr><th>{}:<td>{}".format(key, val))
        else:
            m.die(f"The descdef for '{vals.get('Name', '???')}' is missing a '{key}' line.", lineNum=startTag.line)
            continue
    for key, val in vals.items():
        if key in requiredKeys:
            continue
        ret.append("<tr><th>{}:<td>{}".format(key, val))
    ret.append("</table>")

    ret = [indent + x for x in ret]

    return ret


def transformElementdef(lines: list[str], startTag: h.StartTag, indent: str, doc: t.SpecT) -> list[str]:
    newStartTag = startTag.clone(tag="table")
    newStartTag.classes.add("def")
    newStartTag.classes.add("elementdef")
    attrs: OrderedDict[str, str | None] = OrderedDict()
    parsedAttrs = parseDefBlock(lines, "elementdef", lineNum=startTag.line)
    if "Attribute groups" in parsedAttrs or "Attributes" in parsedAttrs:
        html = "<ul>"
        if "Attribute groups" in parsedAttrs:
            groups = [x.strip() for x in parsedAttrs["Attribute groups"].split(",")]
            for group in groups:
                html += f"<li><a dfn data-element-attr-group line-number={startTag.line}>{group}</a>"
            del parsedAttrs["Attribute groups"]
        if "Attributes" in parsedAttrs:
            atts = [x.strip() for x in parsedAttrs["Attributes"].split(",")]
            for att in atts:
                forVal = parsedAttrs.get("Name", "")
                html += f"<li><a element-attr for='{forVal}' line-number={startTag.line}>{att}</a>"
        html += "</ul>"
        parsedAttrs["Attributes"] = html

    # Displays entries in the order specified in attrs,
    # then if there are any unknown parsedAttrs values,
    # they're displayed afterward in the order they were specified.
    # attrs with a value of None are required to be present in parsedAttrs;
    # attrs with any other value are optional, and use the specified value if not present in parsedAttrs
    attrs["Name"] = None
    attrs["Categories"] = None
    attrs["Contexts"] = None
    attrs["Content model"] = None
    attrs["Attributes"] = None
    attrs["Dom interfaces"] = None
    ret = [str(newStartTag)]
    for key, val in attrs.items():
        if key in parsedAttrs or val is not None:
            if key in parsedAttrs:
                val = parsedAttrs[key]
            assert val is not None
            if key == "Name":
                ret.append("<tr><th>Name:<td>")
                ret.append(
                    ", ".join(f"<dfn element line-number={startTag.line}>{x.strip()}</dfn>" for x in val.split(","))
                )
            elif key == "Content model":
                ret.append(f"<tr><th>{key}:<td>")
                ret.extend(val.split("\n"))
            elif key == "Categories":
                ret.append("<tr><th>Categories:<td>")
                ret.append(", ".join(f"<a dfn line-number={startTag.line}>{x.strip()}</a>" for x in val.split(",")))
            elif key == "Dom interfaces":
                ret.append("<tr><th>DOM Interfaces:<td>")
                ret.append(
                    ", ".join(f"<a interface line-number={startTag.line}>{x.strip()}</a>" for x in val.split(","))
                )
            else:
                ret.append(f"<tr><th>{key}:<td>{val}")
        else:
            m.die(
                f"The elementdef for '{parsedAttrs.get('Name', '???')}' is missing a '{key}' line.",
                lineNum=startTag.line,
            )
            continue
    for key, val in parsedAttrs.items():
        if key in attrs:
            continue
        ret.append(f"<tr><th>{key}:<td>{val}")
    ret.append("</table>")

    ret = [indent + x for x in ret]

    return ret


def transformArgumentdef(lines: list[str], startTag: h.StartTag, indent: str, doc: t.SpecT) -> list[str]:
    newStartTag = startTag.clone(tag="table")
    newStartTag.classes.add("def")
    newStartTag.classes.add("argumentdef")
    attrs = parseDefBlock(lines, "argumentdef", capitalizeKeys=False, lineNum=startTag.line)
    if "for" in newStartTag.attrs:
        forValue = newStartTag.attrs["for"]
        if "/" in forValue:
            interface, method = forValue.split("/")
        else:
            m.die(
                f"Argumentdef for='' values need to specify interface/method(). Got '{forValue}'.",
                lineNum=startTag.line,
            )
            return []
        newStartTag.attrs["data-dfn-for"] = newStartTag.attrs["for"]
        del newStartTag.attrs["for"]
    else:
        m.die("Argumentdef blocks need a for='' attribute specifying their method.", lineNum=startTag.line)
        return []
    newStartTag.classes.add("data")
    text = (
        f"""
{newStartTag}
<caption>Arguments for the <a idl lt='{method}' for='{interface}' line-number={startTag.line}>{interface}.{method}</a> method.</caption>
<thead>
<tr>
<th>Parameter
<th>Type
<th style="text-align:center">Nullable
<th style="text-align:center">Optional
<th>Description
<tbody>"""
        + "\n".join(
            [
                f"""
<tr>
<td><dfn argument line-number={startTag.line}>{param}</dfn>
<td>
<td style="text-align:center">
<td style="text-align:center">
<td>{desc}"""
                for param, desc in attrs.items()
            ]
        )
        + """
</table>"""
    )

    lines = [indent + line for line in text.split("\n")]

    return lines


def parseDefBlock(
    lines: list[str], type: str, capitalizeKeys: bool = True, lineNum: int | None = None
) -> OrderedDict[str, str]:
    vals: OrderedDict[str, str] = OrderedDict()
    lastKey = None
    for line in lines:
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
            vals[key] += "\n" + val
        else:
            vals[key] = val
    return vals


def transformRailroad(lines: list[str], startTag: h.StartTag, indent: str, doc: t.SpecT) -> list[str]:
    import io

    from . import railroadparser

    newStartTag = startTag.clone(tag="div")
    newStartTag.classes.add("railroad")

    ret = [str(newStartTag)]
    doc.extraStyles[
        "style-railroad"
    ] = """
    :root {
        --railroad-bg: hsl(30, 20%, 95%);
        --railroad-stroke: black;
        --railroad-fill: hsl(120,100%,90%);
    }
    svg.railroad-diagram {
        background-color: var(--railroad-bg);
    }
    svg.railroad-diagram path {
        stroke-width:3px;
        stroke: var(--railroad-stroke);
        fill:transparent;
    }
    svg.railroad-diagram text {
        font: bold 14px monospace;
        fill: var(--text, currentcolor);
        text-anchor:middle;
    }
    svg.railroad-diagram text.label {
        text-anchor:start;
    }
    svg.railroad-diagram text.comment {
        font:italic 12px monospace;
    }
    svg.railroad-diagram rect {
        stroke-width:3px;
        stroke: var(--railroad-stroke);
        fill: var(--railroad-fill);
    }"""
    doc.extraStyles[
        "style-darkmode"
    ] += """
    @media (prefers-color-scheme: dark) {
        :root {
            --railroad-bg: rgba(255, 255, 255, .05);
            --railroad-stroke: #bbb;
            --railroad-fill: hsla(240deg, 20%, 15%);
        }
    }"""
    code = "\n".join(lines)
    diagram = railroadparser.parse(code)
    if diagram:
        temp = io.StringIO()
        diagram.writeSvg(temp.write)
        ret.append(temp.getvalue())
        temp.close()
        ret.append("</div>")

        ret = [indent + x for x in ret]

        return ret
    return []


def transformBiblio(lines: list[str], startTag: h.StartTag, indent: str, doc: t.SpecT) -> list[str]:
    storage: t.BiblioStorageT = defaultdict(list)
    biblio.processSpecrefBiblioFile("\n".join(lines), storage, order=1)
    for k, vs in storage.items():
        doc.refs.biblioKeys.add(k)
        doc.refs.biblios[k].extend(vs)
    return []


def transformAnchors(lines: list[str], startTag: h.StartTag, indent: str, doc: t.SpecT) -> list[str]:
    anchors = parseInfoTree(lines, doc.md.indent, lineNum=startTag.line)
    processAnchors(anchors, doc, lineNum=startTag.line)
    return []


def processAnchors(anchors: InfoTreeT, doc: t.SpecT, lineNum: int | None = None) -> None:
    for anchor in anchors:
        if "type" not in anchor or len(anchor["type"]) != 1:
            m.die(f"Each anchor needs exactly one type. Got:\n{config.printjson(anchor)}", lineNum=lineNum)
            continue
        if "text" not in anchor or len(anchor["text"]) != 1:
            m.die(f"Each anchor needs exactly one text. Got:\n{config.printjson(anchor)}", lineNum=lineNum)
            continue
        if "url" not in anchor and "urlPrefix" not in anchor:
            m.die(
                f"Each anchor needs a url and/or at least one urlPrefix. Got:\n{config.printjson(anchor)}",
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
                f"<pre class=anchors> anchor was defined with a local link '{url}'. Please use urlPrefix and/or url to define an external URL."
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
        if anchor["type"][0] in config.lowercaseTypes:
            anchor["text"][0] = anchor["text"][0].lower()
        doc.refs.anchorBlockRefs.refs[anchor["text"][0]].append(
            RefWrapper(
                anchor["text"][0],
                {
                    "type": anchor["type"][0].lower(),
                    "url": url,
                    "shortname": shortname.lower() if shortname is not None else doc.md.shortname,
                    "level": level if level is not None else doc.md.level,
                    "for_": anchor.get("for", []),
                    "export": True,
                    "normative": True,
                    "status": status,
                    "spec": spec.lower() if spec is not None else "",
                },
            )
        )
        methodishStart = re.match(r"([^(]+\()[^)]", anchor["text"][0])
        if methodishStart:
            doc.refs.anchorBlockRefs.addMethodVariants(anchor["text"][0], anchor.get("for", []), doc.md.shortname)


def transformLinkDefaults(lines: list[str], startTag: h.StartTag, indent: str, doc: t.SpecT) -> list[str]:
    lds = parseInfoTree(lines, doc.md.indent, lineNum=startTag.line)
    processLinkDefaults(lds, doc, lineNum=startTag.line)
    return []


def processLinkDefaults(lds: InfoTreeT, doc: t.SpecT, lineNum: int | None = None) -> None:
    for ld in lds:
        if len(ld.get("type", [])) != 1:
            m.die(f"Every link default needs exactly one type. Got:\n{config.printjson(ld)}", lineNum=lineNum)
            continue

        type = ld["type"][0]

        if len(ld.get("spec", [])) != 1:
            m.die(f"Every link default needs exactly one spec. Got:\n{config.printjson(ld)}", lineNum=lineNum)
            continue

        spec = ld["spec"][0]

        if len(ld.get("text", [])) != 1:
            m.die(f"Every link default needs exactly one text. Got:\n{config.printjson(ld)}", lineNum=lineNum)
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


def transformIgnoredSpecs(lines: list[str], startTag: h.StartTag, indent: str, doc: t.SpecT) -> list[str]:
    specs = parseInfoTree(lines, doc.md.indent, lineNum=startTag.line)
    processIgnoredSpecs(specs, doc, lineNum=startTag.line)
    return []


def processIgnoredSpecs(specs: InfoTreeT, doc: t.SpecT, lineNum: int | None = None) -> None:
    for spec in specs:
        if len(spec.get("spec", [])) == 0:
            m.die(
                f"Every ignored spec line needs at least one 'spec' value. Got:\n{config.printjson(spec)}",
                lineNum=lineNum,
            )
            continue
        specNames = spec["spec"]
        if len(spec.get("replacedBy", [])) > 1:
            m.die(
                f"Every ignored spec line needs at most one 'replacedBy' value. Got:\n{config.printjson(spec)}",
                lineNum=lineNum,
            )
            continue
        replacedBy = spec["replacedBy"][0] if "replacedBy" in spec else None
        for specName in specNames:
            if replacedBy:
                doc.refs.replacedSpecs.add((specName, replacedBy))
            else:
                doc.refs.ignoredSpecs.add(specName)


def transformInfo(lines: list[str], startTag: h.StartTag, indent: str, doc: t.SpecT) -> list[str]:
    # More generic InfoTree system.
    # A <pre class=info> can contain any of the InfoTree collections,
    # identified by an 'info' line.
    infos = parseInfoTree(lines, doc.md.indent, lineNum=startTag.line)
    processInfo(infos, doc, lineNum=startTag.line)
    return []


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
                f"Every info-block line needs exactly one 'info' type. Got:\n{config.printjson(info)}", lineNum=lineNum
            )
            continue
        infoType = info["info"][0].lower()
        if infoType not in knownInfoTypes:
            m.die(f"Unknown info-block type '{infoType}'", lineNum=lineNum)
            continue
        infoCollections[infoType].append(info)
    for infoType, infoItem in infoCollections.items():
        knownInfoTypes[infoType](infoItem, doc, lineNum=0)


def transformInclude(lines: list[str], startTag: h.StartTag, indent: str, doc: t.SpecT) -> list[str]:
    newStartTag = startTag.clone(tag="pre")
    newStartTag.classes.add("include")
    infos = parseInfoTree(lines, doc.md.indent, lineNum=startTag.line)
    path = None
    macros = {}
    for info in infos:
        if "path" in info:
            if path is None:
                path = info["path"][0]
            else:
                m.die("Include blocks must only contain a single 'path'.", lineNum=startTag.line)
                return []
        if "macros" in info:
            for k, v in info.items():
                if k == "macros":
                    continue
                if k not in macros and len(v) == 1:
                    macros[k] = v[0]
                else:
                    m.die(
                        f"Include block defines the '{k}' local macro more than once.",
                        lineNum=startTag.line,
                    )
                    return []
    if path:
        newStartTag.attrs["path"] = path
        for i, (macroName, macroVal) in enumerate(macros.items()):
            newStartTag.attrs[f"macro-{i}"] = f"{macroName} {macroVal}"

        return [indent + str(newStartTag) + "</pre>"]
    return []


def transformIncludeCode(lines: list[str], startTag: h.StartTag, indent: str, doc: t.SpecT) -> list[str]:
    newStartTag = startTag.clone(tag="pre")
    newStartTag.classes.add("include-code")
    infos = parseInfoTree(lines, doc.md.indent, lineNum=startTag.line)
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
                    lineNum=startTag.line,
                )
        if "highlight" in info:
            if highlight is None:
                highlight = info["highlight"][0]
            else:
                m.die(
                    "Include-code blocks must only contain a single 'highlight'.",
                    lineNum=startTag.line,
                )
        if "line-start" in info:
            if lineStart is None:
                lineStart = info["line-start"][0]
            else:
                m.die(
                    "Include-code blocks must only contain a single 'line-start'.",
                    lineNum=startTag.line,
                )
        if "show" in info:
            show.extend(info["show"])
        if "line-highlight" in info:
            lineHighlight.extend(info["line-highlight"])
        if "line-numbers" in info:
            lineNumbers = True
        if "no-line-numbers" in info:
            lineNumbers = False

    if path:
        newStartTag.attrs["path"] = path
        if highlight:
            newStartTag.attrs["highlight"] = highlight
        if lineStart:
            newStartTag.attrs["line-start"] = lineStart
        if show:
            newStartTag.attrs["data-code-show"] = ",".join(show)
        if lineHighlight:
            newStartTag.attrs["line-highlight"] = ",".join(lineHighlight)
        if lineNumbers:
            newStartTag.attrs["line-numbers"] = ""
        return [indent + str(newStartTag) + "</pre>"]
    return []


def transformIncludeRaw(lines: list[str], startTag: h.StartTag, indent: str, doc: t.SpecT) -> list[str]:
    newStartTag = startTag.clone(tag="pre")
    newStartTag.classes.add("include-raw")
    infos = parseInfoTree(lines, doc.md.indent, lineNum=startTag.line)
    path = None
    for info in infos:
        if "path" in info:
            if path is None:
                path = info["path"][0]
            else:
                m.die(
                    "Include-raw blocks must only contain a single 'path'.",
                    lineNum=startTag.line,
                )

    if path:
        newStartTag.attrs["path"] = path
        return [indent + str(newStartTag) + "</pre>"]
    return []


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
            thisLine = int(lineNum) + i + 1
        else:
            thisLine = None
        if line.strip() == "":
            continue
        ws, text = t.cast("re.Match", re.match(r"(\s*)(.*)", line)).groups()
        if text.startswith("#"):  # comment
            continue
        wsLen = len(ws.replace("\t", indentSpace))
        if wsLen % indent != 0:
            visibleWs = ws.replace("\t", "\\t").replace(" ", "\\s")
            m.die(
                f"Line has inconsistent indentation; use tabs or {indent} spaces:\n{visibleWs + text}", lineNum=thisLine
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

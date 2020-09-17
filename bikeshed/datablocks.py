# -*- coding: utf-8 -*-

import re
from collections import OrderedDict, defaultdict

import attr

from . import biblio
from . import config
from . import Line
from .h import *
from .messages import *
from functools import reduce

# This function does a single pass through the doc,
# finding all the "data blocks" and processing them.
# A "data block" is any <pre> or <xmp> element.
#
# When a data block is found, the *contents* of the block
# are passed to the appropriate processing function as an
# array of lines.  The function should return a new array
# of lines to replace the *entire* block.
#
# That is, we give you the insides, but replace the whole
# thing.
#
# Additionally, we pass in the tag-name used (pre or xmp)
# and the line with the content, in case it has useful data in it.


def transformDataBlocks(doc, lines):
    fromStrings = False
    if any(isinstance(l, str) for l in lines):
        fromStrings = True
        lines = [Line.Line(-1, l) for l in lines]
    inBlock = False
    blockTypes = {
        'propdef': transformPropdef,
        'descdef': transformDescdef,
        'elementdef': transformElementdef,
        'argumentdef': transformArgumentdef,
        'railroad': transformRailroad,
        'biblio': transformBiblio,
        'anchors': transformAnchors,
        'link-defaults': transformLinkDefaults,
        'ignored-specs': transformIgnoredSpecs,
        'info': transformInfo,
        'include': transformInclude,
        'include-code': transformIncludeCode,
        'include-raw': transformIncludeRaw,
        'pre': transformPre
    }
    blockType = ""
    tagName = ""
    blockLines = []
    newLines = []
    for line in lines:
        # Look for the start of a block.
        match = re.match(r"\s*<(pre|xmp)[\s>]", line.text, re.I)
        # Note that, by design, I don't pay attention to anything on the same line as the start tag,
        # unless it's single-line.
        if match and not inBlock:
            inBlock = True
            tagName = match.group(1)
            blockClasses = classesFromLine(line)
            seenClasses = []
            for t in blockTypes.keys():
                if t in blockClasses:
                    seenClasses.append(t)
            if not seenClasses:
                blockType = "pre"
            elif len(seenClasses) == 1:
                blockType = seenClasses[0]
            else:
                die("Found {0} classes on the <{1}>, so can't tell which to process the block as. Please use only one.", config.englishFromList(("'{0}'".format(x) for x in seenClasses), "and"), tagName, lineNum=line.i)
                blockType = "pre"
        # Look for the end of a block.
        match = re.match(r"(.*)</" + tagName + ">(.*)", line.text, re.I)
        if match and inBlock:
            inBlock = False
            if len(blockLines) == 0:
                # Single-line <pre>.
                match = re.match(r"(\s*<{0}[^>]*>)(.*)</{0}>(.*)".format(tagName), line.text, re.I)
                if not match:
                    die("Can't figure out how to parse this datablock line:\n{0}", line.text, lineNum=line.i)
                    blockLines = []
                    continue
                repl = blockTypes[blockType](
                    lines=[match.group(2)],
                    tagName=tagName,
                    firstLine=match.group(1),
                    lineNum=line.i,
                    doc=doc)
                newLines.extend(Line.Line(line.i,l) for l in repl)
                line.text = match.group(3)
                newLines.append(line)
            elif re.match(r"^\s*$", match.group(1)):
                # End tag was the first tag on the line.
                # Remove the tag from the line.
                repl = blockTypes[blockType](
                    lines=cleanPrefix([l.text for l in blockLines[1:]], doc.md.indent),
                    tagName=tagName,
                    firstLine=blockLines[0].text,
                    lineNum=blockLines[0].i,
                    doc=doc)
                newLines.extend(Line.Line(blockLines[0].i, l) for l in repl)
                line.text = match.group(2)
                newLines.append(line)
            else:
                # End tag was at the end of line of useful content.
                # Process the stuff before it, preserve the stuff after it.
                repl = blockTypes[blockType](
                    lines=cleanPrefix([l.text for l in blockLines[1:]] + [match.group(1)], doc.md.indent),
                    tagName=tagName,
                    firstLine=blockLines[0].text,
                    lineNum=blockLines[0].i,
                    doc=doc)
                newLines.extend(Line.Line(blockLines[0].i, l) for l in repl)
                line.text = match.group(2)
                newLines.append(line)
            tagName = ""
            blockType = ""
            blockLines = []
            continue
        elif inBlock:
            blockLines.append(line)
        else:
            newLines.append(line)

    #for line in newLines:
    #    print line

    if fromStrings:
        return [l.text for l in newLines]
    else:
        return newLines

def cleanPrefix(lines, tabSize):
    # Remove the longest common whitespace prefix from the lines.
    # Returns a fresh array, does not mutate the passed lines.
    if not lines:
        return []
    prefix = reduce(commonPrefix, map(getWsPrefix, lines))
    prefixLen = len(prefix)
    return [line[prefixLen:] for line in lines]

def commonPrefix(line1, line2):
    prefixSoFar = ""
    for i,char in enumerate(line1):
        if i == len(line2):
            break
        if char == line2[i]:
            prefixSoFar += char
        else:
            break
    return prefixSoFar

def getWsPrefix(line):
    return re.match(r"(\s*)", line).group(1)


'''
When writing a new transformFoo function,
PAY ATTENTION TO THE INDENT OF THE FIRST LINE
OR ELSE YOU'LL MESS UP THE MARKDOWN PARSER.
Generally, just spam the first-line's indent onto every line;
if you're outputting a raw element (<pre>/etc),
just spam it onto the first line.
'''

def transformPre(lines, tagName, firstLine, **kwargs):
    # If the last line in the source is a </code></pre>,
    # the generic processor will turn that into a final </code> line,
    # which'll mess up the indent finding.
    # Instead, specially handle this case.
    if len(lines) == 0:
        return [firstLine, "</{0}>".format(tagName)]

    if re.match(r"\s*</code>\s*$", lines[-1]):
        lastLine = "</code></{0}>".format(tagName)
        lines = lines[:-1]
    else:
        lastLine = "</{0}>".format(tagName)

    if len(lines) == 0:
        return [firstLine, lastLine]

    indent = float("inf")
    for (i, line) in enumerate(lines):
        if line.strip() == "":
            continue

        # Use tabs in the source, but spaces in the output,
        # because tabs are ginormous in HTML.
        lines[i] = lines[i].replace("\t", "  ")

        # Find the line with the shortest whitespace prefix.
        # (It might not be the first!)
        indent = min(indent, len(re.match(r" *", lines[i]).group(0)))

    if indent == float("inf"):
        indent = 0

    # Strip off the whitespace prefix from each line
    for (i, line) in enumerate(lines):
        if line.strip() == "":
            continue
        lines[i] = lines[i][indent:]
    # Put the first/last lines back into the results.
    lines[0] = firstLine.rstrip() + lines[0]
    lines.append(lastLine)
    return lines


def transformPropdef(lines, doc, firstLine, lineNum=None, **kwargs):
    attrs = OrderedDict()
    parsedAttrs = parseDefBlock(lines, "propdef")
    # Displays entries in the order specified in attrs,
    # then if there are any unknown parsedAttrs values,
    # they're displayed afterward in the order they were specified.
    # attrs with a value of None are required to be present in parsedAttrs;
    # attrs with any other value are optional, and use the specified value if not present in parsedAttrs
    forHint = ""
    if "Name" in parsedAttrs:
        forHint = " data-link-for-hint='{0}'".format(parsedAttrs["Name"].split(",")[0].strip())
    lineNumAttr = ""
    if lineNum is not None:
        lineNumAttr = " line-number={0}".format(lineNum)
    if "partial" in firstLine or "New values" in parsedAttrs:
        attrs["Name"] = None
        attrs["New values"] = None
        ret = ["<table class='def propdef partial'{forHint}{lineNumAttr}>".format(forHint=forHint, lineNumAttr=lineNumAttr)]
    elif "shorthand" in firstLine:
        attrs["Name"] = None
        attrs["Value"] = None
        for defaultKey in ["Initial", "Applies to", "Inherited", "Percentages", "Computed value", "Animation type"]:
            attrs[defaultKey] = "see individual properties"
        attrs["Canonical order"] = "per grammar"
        ret = ["<table class='def propdef'{forHint}{lineNumAttr}>".format(forHint=forHint, lineNumAttr=lineNumAttr)]
    else:
        attrs["Name"] = None
        attrs["Value"] = None
        attrs["Initial"] = None
        attrs["Applies to"] = "all elements"
        attrs["Inherited"] = None
        attrs["Percentages"] = "n/a"
        attrs["Computed value"] = "as specified"
        attrs["Canonical order"] = "per grammar"
        attrs["Animation type"] = "discrete"
        ret = ["<table class='def propdef'{forHint}{lineNumAttr}>".format(forHint=forHint, lineNumAttr=lineNumAttr)]
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
            die("The propdef for '{0}' is missing a '{1}' line.", parsedAttrs.get("Name", "???"), key, lineNum=lineNum)
            continue
        else:
            # Optional key, just use default
            pass
        attrsToPrint.append((key,val))
    for key,val in parsedAttrs.items():
        # Find any "custom" provided keys
        if key not in attrs:
            attrsToPrint.append((key,val))

    for key,val in attrsToPrint:
        tr = "<tr>"
        th = "<th>{0}:".format(key)
        td = "<td>{0}".format(val)
        if key in ("Value", "New values"):
            tr = "<tr class=value>"
            th = "<th><a href='https://www.w3.org/TR/css-values/#value-defs'>{0}:</a>".format(key)
            td = "<td class=prod>{0}".format(val)
        elif key == "Initial":
            th = "<th><a href='https://www.w3.org/TR/css-cascade/#initial-values'>{0}:</a>".format(key)
        elif key == "Inherited":
            th = "<th><a href='https://www.w3.org/TR/css-cascade/#inherited-property'>{0}:</a>".format(key)
        elif key == "Percentages":
            th = "<th><a href='https://www.w3.org/TR/css-values/#percentages'>{0}:</a>".format(key)
        elif key == "Computed value":
            th = "<th><a href='https://www.w3.org/TR/css-cascade/#computed'>{0}:</a>".format(key)
        elif key in ("Animatable", "Animation type"):
            th = "<th><a href='https://www.w3.org/TR/web-animations/#animation-type'>{0}:</a>".format(key)
        elif key == "Applies to" and val.lower() == "all elements":
            td = "<td><a href='https://www.w3.org/TR/css-pseudo/#generated-content' title='Includes ::before and ::after pseudo-elements.'>all elements</a>"
        ret.append(tr+th+td)
    ret.append("</table>")

    indent = getWsPrefix(firstLine)
    ret = [indent+l for l in ret]

    return ret

# TODO: Make these functions match transformPropdef's new structure


def transformDescdef(lines, doc, firstLine, lineNum=None, **kwargs):
    lineNumAttr = ""
    if lineNum is not None:
        lineNumAttr = " line-number={0}".format(lineNum)
    vals = parseDefBlock(lines, "descdef")
    if "partial" in firstLine or "New values" in vals:
        requiredKeys = ["Name", "For"]
        ret = ["<table class='def descdef partial' data-dfn-for='{0}'{lineNumAttr}>".format(vals.get("For", ""), lineNumAttr=lineNumAttr)]
    if "mq" in firstLine:
        requiredKeys = ["Name", "For", "Value"]
        ret = ["<table class='def descdef mq' data-dfn-for='{0}'{lineNumAttr}>".format(vals.get("For",""), lineNumAttr=lineNumAttr)]
    else:
        requiredKeys = ["Name", "For", "Value", "Initial"]
        ret = ["<table class='def descdef' data-dfn-for='{0}'{lineNumAttr}>".format(vals.get("For", ""), lineNumAttr=lineNumAttr)]
    for key in requiredKeys:
        if key == "For":
            ret.append("<tr><th>{0}:<td><a at-rule>{1}</a>".format(key, vals.get(key,'')))
        elif key == "Value":
            ret.append("<tr><th>{0}:<td class='prod'>{1}".format(key, vals.get(key,'')))
        elif key in vals:
            ret.append("<tr><th>{0}:<td>{1}".format(key, vals.get(key,'')))
        else:
            die("The descdef for '{0}' is missing a '{1}' line.", vals.get("Name", "???"), key, lineNum=lineNum)
            continue
    for key, val in vals.items():
        if key in requiredKeys:
            continue
        ret.append("<tr><th>{0}:<td>{1}".format(key, vals[key]))
    ret.append("</table>")

    indent = getWsPrefix(firstLine)
    ret = [indent+l for l in ret]

    return ret


def transformElementdef(lines, doc, firstLine, lineNum=None, **kwargs):
    lineNumAttr = ""
    if lineNum is not None:
        lineNumAttr = " line-number={0}".format(lineNum)
    attrs = OrderedDict()
    parsedAttrs = parseDefBlock(lines, "elementdef")
    if "Attribute groups" in parsedAttrs or "Attributes" in parsedAttrs:
        html = "<ul>"
        if "Attribute groups" in parsedAttrs:
            groups = [x.strip() for x in parsedAttrs["Attribute groups"].split(",")]
            for group in groups:
                html += "<li><a dfn data-element-attr-group{lineNumAttr}>{0}</a>".format(group, lineNumAttr=lineNumAttr)
            del parsedAttrs["Attribute groups"]
        if "Attributes" in parsedAttrs:
            atts = [x.strip() for x in parsedAttrs["Attributes"].split(",")]
            for att in atts:
                html += "<li><a element-attr for='{1}'{lineNumAttr}>{0}</a>".format(att, parsedAttrs.get("Name", ""), lineNumAttr=lineNumAttr)
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
    ret = ["<table class='def elementdef'{lineNumAttr}>".format(lineNumAttr=lineNumAttr)]
    for key, val in attrs.items():
        if key in parsedAttrs or val is not None:
            if key in parsedAttrs:
                val = parsedAttrs[key]
            if key == "Name":
                ret.append("<tr><th>Name:<td>")
                ret.append(', '.join("<dfn element{lineNumAttr}>{0}</dfn>".format(x.strip(), lineNumAttr=lineNumAttr) for x in val.split(",")))
            elif key == "Content model":
                ret.append("<tr><th>{0}:<td>".format(key))
                ret.extend(val.split("\n"))
            elif key == "Categories":
                ret.append("<tr><th>Categories:<td>")
                ret.append(', '.join("<a dfn{lineNumAttr}>{0}</a>".format(x.strip(), lineNumAttr=lineNumAttr) for x in val.split(",")))
            elif key == "Dom interfaces":
                ret.append("<tr><th>DOM Interfaces:<td>")
                ret.append(', '.join("<a interface{lineNumAttr}>{0}</a>".format(x.strip(), lineNumAttr=lineNumAttr) for x in val.split(",")))
            else:
                ret.append("<tr><th>{0}:<td>{1}".format(key, val))
        else:
            die("The elementdef for '{0}' is missing a '{1}' line.", parsedAttrs.get("Name", "???"), key, lineNum=lineNum)
            continue
    for key, val in parsedAttrs.items():
        if key in attrs:
            continue
        ret.append("<tr><th>{0}:<td>{1}".format(key, val))
    ret.append("</table>")

    indent = getWsPrefix(firstLine)
    ret = [indent+l for l in ret]

    return ret


def transformArgumentdef(lines, firstLine, lineNum=None, **kwargs):
    lineNumAttr = ""
    if lineNum is not None:
        lineNumAttr = " line-number={0}".format(lineNum)
    attrs = parseDefBlock(lines, "argumentdef", capitalizeKeys=False, lineNum=lineNum)
    el = parseHTML(firstLine + "</pre>")[0]
    if "for" in el.attrib:
        forValue = el.get('for')
        el.set("data-dfn-for", forValue)
        if "/" in forValue:
            interface, method = forValue.split("/")
        else:
            die("Argumentdef for='' values need to specify interface/method(). Got '{0}'.", forValue, lineNum=lineNum)
            return []
        removeAttr(el, "for")
    else:
        die("Argumentdef blocks need a for='' attribute specifying their method.", lineNum=lineNum)
        return []
    addClass(el, "data")
    rootAttrs = " ".join("{0}='{1}'".format(k,escapeAttr(v)) for k,v in el.attrib.items())
    text = ('''
<table {attrs}{lineNumAttr}>
    <caption>Arguments for the <a idl lt='{method}' for='{interface}'{lineNumAttr}>{interface}.{method}</a> method.</caption>
    <thead>
        <tr>
            <th>Parameter
            <th>Type
            <th>Nullable
            <th>Optional
            <th>Description
    <tbody>'''.format(attrs=rootAttrs, interface=interface, method=method, lineNumAttr=lineNumAttr)
+ '\n'.join(['''
        <tr>
            <td><dfn argument{lineNumAttr}>{0}</dfn>
            <td>
            <td>
            <td>
            <td>{1}'''.format(param, desc, lineNumAttr=lineNumAttr)
    for param,desc in attrs.items()])
+ '''
</table>''')

    indent = getWsPrefix(firstLine)
    lines = [indent+line for line in text.split("\n")]

    return lines


def parseDefBlock(lines, type, capitalizeKeys=True, lineNum=None):
    vals = OrderedDict()
    lastKey = None
    for line in lines:
        match = re.match(r"\s*([^:]+):\s*(\S.*)?", line)
        if match is None:
            if lastKey is not None and (line.strip() == "" or re.match(r"\s+", line)):
                key = lastKey
                val = line.strip()
            else:
                die("Incorrectly formatted {2} line for '{0}':\n{1}", vals.get("Name", "???"), line, type, lineNum=lineNum)
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


def transformRailroad(lines, doc, firstLine, **kwargs):
    import io
    from . import railroadparser
    ret = ["<div class='railroad'>"]
    doc.extraStyles['style-railroad'] = '''
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
    }'''
    doc.extraStyles['style-darkmode'] += '''
    @media (prefers-color-scheme: dark) {
        :root {
            --railroad-bg: rgba(255, 255, 255, .05);
            --railroad-stroke: #bbb;
            --railroad-fill: hsla(240deg, 20%, 15%);
        }
    }'''
    code = ''.join(lines)
    diagram = railroadparser.parse(code)
    if diagram:
        temp = io.StringIO()
        diagram.writeSvg(temp.write)
        ret.append(temp.getvalue())
        temp.close()
        ret.append("</div>")

        indent = getWsPrefix(firstLine)
        ret = [indent+l for l in ret]

        return ret
    else:
        return []


def transformBiblio(lines, doc, **kwargs):
    storage = defaultdict(list)
    biblio.processSpecrefBiblioFile(''.join(lines), storage, order=1)
    for k,vs in storage.items():
        doc.refs.biblioKeys.add(k)
        doc.refs.biblios[k].extend(vs)
    return []


def transformAnchors(lines, doc, lineNum=None, **kwargs):
    anchors = parseInfoTree(lines, doc.md.indent, lineNum)
    processAnchors(anchors, doc, lineNum)
    return []


def processAnchors(anchors, doc, lineNum=None):
    for anchor in anchors:
        if "type" not in anchor or len(anchor['type']) != 1:
            die("Each anchor needs exactly one type. Got:\n{0}", config.printjson(anchor), lineNum=lineNum)
            continue
        if "text" not in anchor or len(anchor['text']) != 1:
            die("Each anchor needs exactly one text. Got:\n{0}", config.printjson(anchor), lineNum=lineNum)
            continue
        if "url" not in anchor and "urlPrefix" not in anchor:
            die("Each anchor needs a url and/or at least one urlPrefix. Got:\n{0}", config.printjson(anchor), lineNum=lineNum)
            continue
        if "urlPrefix" in anchor:
            urlPrefix = ''.join(anchor['urlPrefix'])
        else:
            urlPrefix = ""
        if "url" in anchor:
            urlSuffix = anchor['url'][0]
        else:
            urlSuffix = config.simplifyText(anchor['text'][0])
        url = urlPrefix + ("" if "#" in urlPrefix or "#" in urlSuffix else "#") + urlSuffix
        status = "local"
        shortname = None
        level = None
        if "shortname" in anchor and "level" in anchor:
            shortname = anchor['shortname'][0]
            level = anchor['level'][0]
        spec = anchor["spec"][0] if "spec" in anchor else None
        if shortname and not spec:
            if level:
                spec = "{0}-{1}".format(shortname, level)
            else:
                spec = shortname
        elif spec and not shortname:
            match = re.match("(.*)-(\d+)$", spec)
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
                die("Anchor statuses must be {1}. Got '{0}'.", status, config.englishFromList(config.linkStatuses), lineNum=lineNum)
                continue
        else:
            status = "anchor-block"
        if anchor['type'][0] in config.lowercaseTypes:
            anchor['text'][0] = anchor['text'][0].lower()
        doc.refs.anchorBlockRefs._refs[anchor['text'][0]].append({
            "linkingText": anchor['text'][0],
            "type": anchor['type'][0].lower(),
            "url": url,
            "shortname": shortname.lower() if shortname is not None else doc.md.shortname,
            "level": level if level is not None else doc.md.level,
            "for": anchor.get('for', []),
            "export": True,
            "status": status,
            "spec": spec.lower() if spec is not None else ''
        })
        methodishStart = re.match(r"([^(]+\()[^)]", anchor['text'][0])
        if methodishStart:
            doc.refs.anchorBlockRefs.addMethodVariants(anchor['text'][0], anchor.get('for', []), doc.md.shortname)


def transformLinkDefaults(lines, doc, lineNum=None, **kwargs):
    lds = parseInfoTree(lines, doc.md.indent, lineNum)
    processLinkDefaults(lds, doc, lineNum)
    return []


def processLinkDefaults(lds, doc, lineNum=None):
    for ld in lds:
        if len(ld.get('type', [])) != 1:
            die("Every link default needs exactly one type. Got:\n{0}", config.printjson(ld), lineNum=lineNum)
            continue
        else:
            type = ld['type'][0]
        if len(ld.get('spec', [])) != 1:
            die("Every link default needs exactly one spec. Got:\n{0}", config.printjson(ld), lineNum=lineNum)
            continue
        else:
            spec = ld['spec'][0]
        if len(ld.get('text', [])) != 1:
            die("Every link default needs exactly one text. Got:\n{0}", config.printjson(ld), lineNum=lineNum)
            continue
        else:
            text = ld['text'][0]
        if 'for' in ld:
            for _for in ld['for']:
                doc.md.linkDefaults[text].append((spec, type, ld.get('status', None), _for))
        else:
            doc.md.linkDefaults[text].append((spec, type, ld.get('status', None), None))


def transformIgnoredSpecs(lines, doc, lineNum=None, **kwargs):
    specs = parseInfoTree(lines, doc.md.indent, lineNum)
    processIgnoredSpecs(specs, doc, lineNum)
    return []


def processIgnoredSpecs(specs, doc, lineNum=None):
    for spec in specs:
        if len(spec.get('spec', [])) == 0:
            die("Every ignored spec line needs at least one 'spec' value. Got:\n{0}", config.printjson(spec), lineNum=lineNum)
            continue
        specNames = spec.get('spec')
        if len(spec.get('replacedBy', [])) > 1:
            die("Every ignored spec line needs at most one 'replacedBy' value. Got:\n{0}", config.printjson(spec), lineNum=lineNum)
            continue
        replacedBy = spec.get('replacedBy')[0] if 'replacedBy' in spec else None
        for specName in specNames:
            if replacedBy:
                doc.refs.replacedSpecs.add((specName, replacedBy))
            else:
                doc.refs.ignoredSpecs.add(specName)


def transformInfo(lines, doc, lineNum=None, **kwargs):
    # More generic InfoTree system.
    # A <pre class=info> can contain any of the InfoTree collections,
    # identified by an 'info' line.
    infos = parseInfoTree(lines, doc.md.indent, lineNum)
    processInfo(infos, doc, lineNum)
    return []


def processInfo(infos, doc, lineNum=None):
    knownInfoTypes = {
        "anchors": processAnchors,
        "link-defaults": processLinkDefaults,
        "ignored-specs": processIgnoredSpecs
    }
    infoCollections = defaultdict(list)
    for info in infos:
        if len(info.get('info', [])) != 1:
            die("Every info-block line needs exactly one 'info' type. Got:\n{0}", config.printjson(info), lineNum=lineNum)
            continue
        infoType = info.get('info')[0].lower()
        if infoType not in knownInfoTypes:
            die("Unknown info-block type '{0}'", infoType, lineNum=lineNum)
            continue
        infoCollections[infoType].append(info)
    for infoType, infos in infoCollections.items():
        knownInfoTypes[infoType](infos, doc, lineNum=0)


def transformInclude(lines, doc, firstLine, lineNum=None, **kwargs):
    lineNumAttr = ""
    if lineNum is not None:
        lineNumAttr = " line-number={0}".format(lineNum)
    infos = parseInfoTree(lines, doc.md.indent, lineNum)
    path = None
    macros = {}
    for info in infos:
        if "path" in info:
            if path is None:
                path = info['path'][0]
            else:
                die("Include blocks must only contain a single 'path'.", lineNum=lineNum)
        if "macros" in info:
            for k,v in info.items():
                if k == "macros":
                    continue
                if k not in macros and len(v) == 1:
                    macros[k] = v[0]
                else:
                    die("Include block defines the '{0}' local macro more than once.", k, lineNum=lineNum)
    if path:
        el = "<pre class=include path='{0}'".format(escapeAttr(path))
        for i,(k,v) in enumerate(macros.items()):
            el += " macro-{0}='{1} {2}'".format(i, k, escapeAttr(v))
        el += "{lineNumAttr}></pre>".format(lineNumAttr=lineNumAttr)

        indent = getWsPrefix(firstLine)
        return [indent+el]
    else:
        return []


def transformIncludeCode(lines, doc, firstLine, lineNum=None, **kwargs):
    lineNumAttr = ""
    if lineNum is not None:
        lineNumAttr = " line-number={0}".format(lineNum)
    infos = parseInfoTree(lines, doc.md.indent, lineNum)
    path = None
    highlight = None
    lineStart = None
    show = []
    lineHighlight = []
    lineNumbers = False
    for info in infos:
        if "path" in info:
            if path is None:
                path = info['path'][0]
            else:
                die("Include-code blocks must only contain a single 'path'.", lineNum=lineNum)
        if "highlight" in info:
            if highlight is None:
                highlight = info['highlight'][0]
            else:
                die("Include-code blocks must only contain a single 'highlight'.", lineNum=lineNum)
        if "line-start" in info:
            if lineStart is None:
                lineStart = info['line-start'][0]
            else:
                die("Include-code blocks must only contain a single 'line-start'.", lineNum=lineNum)
        if "show" in info:
            show.extend(info['show'])
        if "line-highlight" in info:
            lineHighlight.extend(info['line-highlight'])
        if "line-numbers" in info:
            lineNumbers = True
        if "no-line-numbers" in info:
            lineNumbers = False


    if path:
        attrs = lineNumAttr
        attrs += " path='{0}'".format(escapeAttr(path))
        if highlight:
            attrs += " highlight='{0}'".format(escapeAttr(highlight))
        if lineStart:
            attrs += " line-start='{0}'".format(escapeAttr(lineStart))
        if show:
            attrs += " data-code-show='{0}'".format(escapeAttr(",".join(show)))
        if lineHighlight:
            attrs += " line-highlight='{0}'".format(escapeAttr(",".join(lineHighlight)))
        if lineNumbers:
            attrs += " line-numbers"
        el = "<pre class=include-code{0}></pre>".format(attrs)
        indent = getWsPrefix(firstLine)
        return [indent+el]
    else:
        return []


def transformIncludeRaw(lines, doc, firstLine, lineNum=None, **kwargs):
    lineNumAttr = ""
    if lineNum is not None:
        lineNumAttr = " line-number={0}".format(lineNum)
    infos = parseInfoTree(lines, doc.md.indent, lineNum)
    path = None
    highlight = None
    lineStart = None
    show = []
    lineHighlight = []
    lineNumbers = False
    for info in infos:
        if "path" in info:
            if path is None:
                path = info['path'][0]
            else:
                die("Include-raw blocks must only contain a single 'path'.", lineNum=lineNum)

    if path:
        attrs = lineNumAttr
        attrs += " path='{0}'".format(escapeAttr(path))
        el = "<pre class=include-raw{0}></pre>".format(attrs)
        indent = getWsPrefix(firstLine)
        return [indent+el]
    else:
        return []



def parseInfoTree(lines, indent=4, lineNum=0):
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

    def extendData(datas, infoLevels):
        if not infoLevels:
            return
        newData = defaultdict(list)
        for infos in infoLevels:
            for k,v in infos.items():
                newData[k].extend(v)
        datas.append(newData)

    # Determine the indents, separate the lines.
    datas = []
    infoLevels = []
    lastIndent = -1
    indentSpace = " " * indent
    for i,line in enumerate(lines):
        if lineNum is not None:
            thisLine = int(lineNum) + i + 1
        else:
            thisLine = None
        if line.strip() == "":
            continue
        ws, text = re.match("(\s*)(.*)", line).groups()
        if text.startswith("#"): # comment
            continue
        wsLen = len(ws.replace("\t", indentSpace))
        if wsLen % indent != 0:
            visibleWs = ws.replace("\t", "\\t").replace(" ", "\\s")
            die("Line has inconsistent indentation; use tabs or {1} spaces:\n{0}", visibleWs+text, indent, lineNum=thisLine)
            return []
        wsLen = wsLen // indent
        if wsLen >= lastIndent + 2:
            die("Line jumps {1} indent levels:\n{0}", text, wsLen - lastIndent, lineNum=thisLine)
            return []
        if wsLen <= lastIndent:
            # Previous line was a leaf node; build its full data and add to the list
            extendData(datas, infoLevels[:lastIndent + 1])
        # Otherwise, chained data. Parse it, put it into infoLevels
        info = defaultdict(list)
        for piece in text.split(";"):
            if piece.strip() == "":
                continue
            match = re.match("([^:]+):\s*(.*)", piece)
            if not match:
                die("Line doesn't match the grammar `k:v; k:v; k:v`:\n{0}", line, lineNum=thisLine)
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
    extendData(datas, infoLevels[:lastIndent + 1])
    return datas


def classesFromLine(line):
    tag = parseTag(line.text.strip(), lineNumber=line.i)
    if tag is None:
        return set()
    if "class" not in tag.attrs:
        return set()
    return set(tag.attrs["class"].strip().split())

@attr.s(slots=True)
class StartTag(object):
    tag = attr.ib()
    attrs = attr.ib(default=attr.Factory(dict))

def parseTag(text, lineNumber):
    '''
    Parses a tag from a string,
    conformant to the HTML parsing algorithm.
    The text must start with the opening < character.
    '''

    def parseerror(index, state):
        die("Tried to parse a start tag from '{0}', but failed at character {1} '{2}' and parse-state '{3}'.", text, index, text[index], state, lineNum=lineNumber)
        return
    def eof(i,text):
        return i >= len(text)
    i = 0
    state = "data"
    while True:
        if eof(i, text):
            parseerror(i, state)
            return
        if state == "data":
            if text[i] == "<":
                state = "tag-open"
                i += 1
                continue
            else:
                parseerror(i, state)
                return
        elif state == "tag-open":
            if text[i].isalpha():
                state = "tag-name"
                continue
            else:
                parseerror(i, state)
                return
        elif state == "tag-name":
            tagname = ""
            while not eof(i,text) and re.match(r"[^\s/>]", text[i]):
                tagname += text[i].lower()
                i += 1
            tag = StartTag(tagname)
            if text[i] == ">":
                return tag
            elif text[i] == "/":
                state = "self-closing-start-tag"
                i += 1
                continue
            elif text[i].isspace():
                state = "before-attribute-name"
                i += 1
                continue
            else:
                parseerror(i, state)
                return
        elif state == "self-closing-start-tag":
            if text[i] == ">":
                return tag
            else:
                parseerror(i, state)
                return
        elif state == "before-attribute-name":
            if text[i].isspace():
                i += 1
                continue
            elif text[i] == "/" or text[i] == ">":
                state = "after-attribute-name"
                continue
            elif text[i] == "=":
                parseerror(i, state)
                return
            else:
                state = "attribute-name"
                continue
        elif state == "attribute-name":
            attrName = ""
            while not eof(i,text) and re.match(r"[^\s/>=\"'<]", text[i]):
                attrName += text[i]
                i += 1
            tag.attrs[attrName] = ""
            if text[i].isspace() or text[i] == "/" or text[i] == ">":
                state = "after-attribute-name"
                continue
            elif text[i] == "=":
                state = "before-attribute-value"
                i += 1
                continue
            else:
                parseerror(i,state)
                return
        elif state == "after-attribute-name":
            if text[i].isspace():
                i += 1
                continue
            elif text[i] == "/":
                state = "self-closing-start-tag"
                i += 1
                continue
            elif text[i] == "=":
                state = "before-attribute-value"
                i += 1
                continue
            elif text[i] == ">":
                return tag
            else:
                state = "attribute-name"
                continue
        elif state == "before-attribute-value":
            if text[i].isspace():
                i += 1
                continue
            elif text[i] == '"':
                state = "attribute-value-double-quoted"
                i += 1
                continue
            elif text[i] == "'":
                state = "attribute-value-single-quoted"
                i += 1
                continue
            elif text[i] == "=":
                parseerror(i,state)
                return
            else:
                state = "attribute-value-unquoted"
                continue
        elif state == "attribute-value-double-quoted":
            attrValue = ""
            while not eof(i,text) and not text[i] == '"':
                attrValue += text[i]
                i += 1
            tag.attrs[attrName] = attrValue
            if text[i] == '"':
                state = "after-attribute-value-quoted"
                i += 1
                continue
            else:
                parseerror(i,state)
                return
        elif state == "attribute-value-single-quoted":
            attrValue = ""
            while not eof(i,text) and not text[i] == "'":
                attrValue += text[i]
                i += 1
            tag.attrs[attrName] = attrValue
            if text[i] == "'":
                state = "after-attribute-value-quoted"
                i += 1
                continue
            else:
                parseerror(i,state)
                return
        elif state == "attribute-value-unquoted":
            attrValue = ""
            while not eof(i,text) and re.match("[^\s<>'\"=`]", text[i]):
                attrValue += text[i]
                i += 1
            tag.attrs[attrName] = attrValue
            if text[i].isspace():
                state = "before-attribute-name"
                i += 1
                continue
            elif text[i] == ">":
                return tag
            else:
                parseerror(i,state)
                return
        elif state == "after-attribute-value-quoted":
            if text[i].isspace():
                state = "before-attribute-name"
                i += 1
                continue
            elif text[i] == "/":
                state = "self-closing-start-tag"
                i += 1
                continue
            elif text[i] == ">":
                return tag
            else:
                parseerror(i,state)
                return

from __future__ import annotations

from lxml import etree

from .. import t
from . import dom

# Precomputed indentation strings to avoid repeated `" " * indent` allocations.
_INDENTS: list[str] = [" " * i for i in range(128)]
_NL_INDENTS: list[str] = ["\n" + " " * i for i in range(128)]

# Per-tag metadata tuple: (unaliased_tag, kind, is_block, bare_open_tag, close_tag)
# `kind` integer codes avoid chained method calls per node:
#   -1: LXML odd node (Comment, ProcessingInstruction, Entity) - ignored during serialization
#    0: normal element
#    1: void element (area, base, br, etc.)
#    2: Bikeshed wrapper element (bs-inline, bs-block) - no start/end tags emitted
#    3: opaque element (pre, etc.) - whitespace preserved, children serialized inline
#    4: raw CDATA element (xmp, script, style) - text not HTML-escaped
#    5: <title> element - raw if `bs-title-contents` attr is present, else normal
# `close_tag` is:
#   ""         if the end tag is always omitted (or for wrapper elements)
#   None       for <dt>/<dd>, whose end tag is omitted only before another <dt>/<dd> or end of parent
#   f"</{tag}>" otherwise
type TagInfoT = tuple[str, int, bool, str, str | None]

_ODD_INFO: TagInfoT = ("", -1, False, "", "")

_INLINE_ELS: frozenset[str] = frozenset(
    [
        "a",
        "bs-inline",
        "em",
        "strong",
        "small",
        "s",
        "cite",
        "q",
        "dfn",
        "abbr",
        "data",
        "time",
        "code",
        "var",
        "samp",
        "kbd",
        "sub",
        "sup",
        "i",
        "b",
        "u",
        "mark",
        "ruby",
        "bdi",
        "bdo",
        "span",
        "br",
        "wbr",
        "img",
        "meter",
        "progress",
        "math",
        "[]",
    ],
)
_RAW_ELS: frozenset[str] = frozenset(["xmp", "script", "style"])
_VOID_ELS: frozenset[str] = frozenset(
    [
        "area",
        "base",
        "br",
        "col",
        "command",
        "embed",
        "hr",
        "img",
        "input",
        "keygen",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    ],
)
_OMIT_END_TAG_ELS: frozenset[str] = frozenset(
    [
        "td",
        "th",
        "tr",
        "thead",
        "tbody",
        "tfoot",
        "colgroup",
        "col",
        "li",
        "dt",
        "dd",
        "html",
        "head",
        "body",
    ],
)
_ALWAYS_OMIT_END_TAG_ELS: frozenset[str] = _OMIT_END_TAG_ELS - {"dt", "dd"}
_DEFAULT_OPAQUE_ELS: frozenset[str] = frozenset(["pre", "xmp", "script", "style"])
_DEFAULT_BLOCK_ELS: frozenset[str] = frozenset(["bs-block"])

# Cache of tag metadata dicts keyed by `(opaqueEls, blockEls)` so repeated Serializer
# runs (e.g. during tests) reuse already-computed tag entries without recreating or copying.
_TAG_INFO_CACHE: dict[tuple[frozenset[str], frozenset[str]], dict[t.Any, TagInfoT]] = {}


class Serializer:
    inlineEls = _INLINE_ELS
    rawEls = _RAW_ELS
    voidEls = _VOID_ELS
    omitEndTagEls = _OMIT_END_TAG_ELS
    alwaysOmitEndTagEls = _ALWAYS_OMIT_END_TAG_ELS

    def __init__(self, opaqueElements: t.Iterable[str], blockElements: t.Iterable[str]) -> None:
        self.opaqueEls = frozenset(opaqueElements) | _DEFAULT_OPAQUE_ELS
        self.blockEls = frozenset(blockElements) | _DEFAULT_BLOCK_ELS

    def serialize(self, root: t.ElementT) -> str:
        """
        Serializes an LXML element tree into an HTML string.

        All hot helpers are defined as nested closures inside `serialize()` so that
        `out`, `write` (`out.append`), `tagInfo`, and `classCache` are accessed via fast
        local/cell variable lookups (`LOAD_FAST`/`LOAD_DEREF`) instead of `self.*`
        attribute lookups and bound-method dispatch on every element.

        Instead of `io.StringIO`, output chunks are appended to `out: list[str]` and
        joined once at the end; this is both faster and allows O(1) in-place patching
        (`out[headerIdx] = ...`) when a block element optimistically starts an inline
        run and later encounters a block child.
        """
        out: list[str] = ["<!doctype html>"]
        write = out.append

        opaqueEls = self.opaqueEls
        blockEls = self.blockEls

        cacheKey = (opaqueEls, blockEls)
        if cacheKey in _TAG_INFO_CACHE:
            tagInfo = _TAG_INFO_CACHE[cacheKey]
        else:
            tagInfo = {
                etree.Comment: _ODD_INFO,
                etree.ProcessingInstruction: _ODD_INFO,
                etree.Entity: _ODD_INFO,
            }
            _TAG_INFO_CACHE[cacheKey] = tagInfo
        classCache: dict[str, str] = {}

        def _getTagInfo(rawTag: t.Any) -> TagInfoT:
            """
            Populates `tagInfo[rawTag]` on demand. A spec typically visits ~36,000 elements
            but only ~55 unique tag names, so caching the classification and bare `<tag>`/`</tag>`
            strings per tag eliminates thousands of `isElement`, `unfuckName`, `isBlockElement`,
            and `needsEndTag` calls. Non-string tags (LXML Comment/PI/Entity constructors) map
            to `_ODD_INFO` (`kind = -1`) so odd nodes are filtered in the same lookup.
            """
            if not isinstance(rawTag, str):
                tagInfo[rawTag] = _ODD_INFO
                return _ODD_INFO
            tag = rawTag
            if "{" in tag:
                tag = tag.partition("}")[2]
            if tag == "clippath":
                tag = "clipPath"
            if tag in _VOID_ELS:
                kind = 1
            elif tag in _RAW_ELS:
                kind = 4
            elif tag == "title":
                kind = 5
            elif tag in opaqueEls:
                kind = 3
            elif tag in ("bs-inline", "bs-block"):
                kind = 2
            else:
                kind = 0
            isBlock = rawTag not in _INLINE_ELS and ("-" not in rawTag or rawTag in blockEls)
            openTag = "" if kind == 2 else f"<{tag}>"
            if kind == 2 or rawTag in _ALWAYS_OMIT_END_TAG_ELS:
                closeTag: str | None = ""
            elif rawTag in ("dt", "dd"):
                closeTag = None
            else:
                closeTag = f"</{tag}>"
            res = (tag, kind, isBlock, openTag, closeTag)
            tagInfo[rawTag] = res
            return res

        def _formatClass(v: str) -> str:
            """
            Formats and caches a `class` attribute value (`' class="..."'`).
            Specs reuse the same ~40-60 class combinations thousands of times (~99% hit rate),
            so caching avoids repeated `split()`, `sorted()`, and escaping.
            `.replace()` calls are guarded with `in` (`CONTAINS_OP` bytecode) to avoid
            C method call overhead in the ~99% case where no characters need escaping.
            """
            if v == "":
                res = " class"
            else:
                s = " ".join(sorted(x for x in v.split(" ") if x)) if " " in v else v
                if "&" in s:
                    s = s.replace("&", "&amp;")
                if "'" in s:
                    s = s.replace("'", "&apos;")
                if '"' in s:
                    s = s.replace('"', "&quot;")
                res = f' class="{s}"'
            classCache[v] = res
            return res

        def _formatSingleAttr(k: str, v: str) -> str:
            """Formats a single non-`bs-` attribute for the 2-attribute fast path in `_startTag`."""
            if k == "class":
                try:
                    return classCache[v]
                except KeyError:
                    return _formatClass(v)
            if "{" in k:
                k = k.partition("}")[2]
                if k.startswith("bs-"):
                    return ""
            if k == "viewbox":
                k = "viewBox"
            elif k == "clippath":
                k = "clipPath"
            if v == "":
                return " " + k
            if "&" in v:
                v = v.replace("&", "&amp;")
            if "'" in v:
                v = v.replace("'", "&apos;")
            if '"' in v:
                v = v.replace('"', "&quot;")
            return f' {k}="{v}"'

        def _startTag(tag: str, openTag: str, items: t.Any) -> str:
            """
            Serializes an element's start tag when `el.items()` is non-empty.

            - `items` is always `list[tuple[str, str]]` at runtime, but `types-lxml` types
              `el.items()` as `Sequence[tuple[str | bytes, str | bytes]]`. Typing `items` as
              `t.Any` avoids ~19k runtime `t.cast()` calls while allowing `.sort()` and `str` ops.
            - `match items:` with 1- and 2-item patterns uses `MATCH_SEQUENCE`/`GET_LEN` bytecode
              (no `len()` call) to handle ~76% of elements without `list.sort()` or loop overhead.
            - `k == "bs-line-number" or (k[0] == "b" and k.startswith("bs-"))` short-circuits
              the most common internal attribute by string equality and avoids calling
              `.startswith()` on attributes that don't start with `"b"`.
            """
            match items:
                case [item0]:
                    k, v = item0
                    if k == "bs-line-number" or (k[0] == "b" and k.startswith("bs-")):
                        return openTag
                    if k == "class":
                        try:
                            clsStr = classCache[v]
                        except KeyError:
                            clsStr = _formatClass(v)
                        return f"<{tag}{clsStr}>"
                    if "{" in k:
                        k = k.partition("}")[2]
                        if k.startswith("bs-"):
                            return openTag
                    if k == "viewbox":
                        k = "viewBox"
                    elif k == "clippath":
                        k = "clipPath"
                    if v == "":
                        return f"<{tag} {k}>"
                    if "&" in v:
                        v = v.replace("&", "&amp;")
                    if "'" in v:
                        v = v.replace("'", "&apos;")
                    if '"' in v:
                        v = v.replace('"', "&quot;")
                    return f'<{tag} {k}="{v}">'
                case [item0, item1]:
                    k0, v0 = item0
                    k1, v1 = item1
                    if k0 == "bs-line-number" or (k0[0] == "b" and k0.startswith("bs-")):
                        if k1 == "bs-line-number" or (k1[0] == "b" and k1.startswith("bs-")):
                            return openTag
                        s1 = _formatSingleAttr(k1, v1)
                        return f"<{tag}{s1}>" if s1 else openTag
                    if k1 == "bs-line-number" or (k1[0] == "b" and k1.startswith("bs-")):
                        s0 = _formatSingleAttr(k0, v0)
                        return f"<{tag}{s0}>" if s0 else openTag
                    s0 = _formatSingleAttr(k0, v0)
                    s1 = _formatSingleAttr(k1, v1)
                    return f"<{tag}{s0}{s1}>" if k0 < k1 else f"<{tag}{s1}{s0}>"
                case _:
                    pass

            items.sort()
            res = "<" + tag
            for k, v in items:
                if k == "bs-line-number" or (k[0] == "b" and k.startswith("bs-")):
                    continue
                if k == "class":
                    try:
                        clsStr = classCache[v]
                    except KeyError:
                        clsStr = _formatClass(v)
                    res += clsStr
                    continue
                if "{" in k:
                    k = k.partition("}")[2]
                    if k.startswith("bs-"):
                        continue
                if k == "viewbox":
                    k = "viewBox"
                elif k == "clippath":
                    k = "clipPath"
                if v == "":
                    res += " " + k
                else:
                    if "&" in v:
                        v = v.replace("&", "&amp;")
                    if "'" in v:
                        v = v.replace("'", "&apos;")
                    if '"' in v:
                        v = v.replace('"', "&quot;")
                    res += f' {k}="{v}"'
            return res + ">"

        def _writeRaw(tag: str, openTag: str, el: t.ElementT, indent_str: str) -> None:
            """
            Serializes raw CDATA elements (`xmp`, `script`, `style`, and `<title>` with
            `bs-title-contents`). Streams `el.text` and `child.tail` directly from `el`
            instead of calling `dom.childNodes(el, mergeText=True)` to avoid list allocations.
            """
            items = el.items()
            start = _startTag(tag, openTag, items) if items else openTag
            if tag == "script" and el.get("src") is not None:
                write(f"{indent_str}{start}</script>")
                return
            if tag == "title":
                write(f"{indent_str}{start}{el.get('bs-title-contents', '')}</title>")
                return
            write(start)
            if text := el.text:
                write(text)
            for child in el:
                ctag = child.tag
                try:
                    cinfo = tagInfo[ctag]
                except KeyError:
                    cinfo = _getTagInfo(ctag)
                if cinfo[1] != -1:
                    msg = f"Somehow a CDATA element got an element child:\n{dom.outerHTML(el)}"
                    raise Exception(msg)
                if tail := child.tail:
                    write(tail)
            write(f"</{tag}>")

        def _writeInline(el: t.ElementT, indent_str: str, info: TagInfoT) -> None:
            """
            Serializes both inline elements (`indent_str == ""`) and opaque `<pre>`-like
            elements (`indent_str == " " * indent`), since their traversal is identical
            apart from passing `indent_str` to any descendant void/raw elements.

            Streams `el.text`, `child`, and `child.tail` directly without calling
            `dom.childNodes(el, mergeText=True)` (because HTML escaping is distributive
            over string concatenation), and inlines leaf children (`ckind == 0 and len(child) == 0`)
            to save recursive calls and combine output into a single `write()`.
            """
            tag, kind, _, openTag, _ = info

            if kind in (0, 3):
                items = el.items()
                start = _startTag(tag, openTag, items) if items else openTag
                text = el.text
                if text:
                    if "&" in text:
                        text = text.replace("&", "&amp;")
                    if "<" in text:
                        text = text.replace("<", "&lt;")
                    write(start + text)
                else:
                    write(start)
                for child in el:
                    ctag = child.tag
                    try:
                        cinfo = tagInfo[ctag]
                    except KeyError:
                        cinfo = _getTagInfo(ctag)
                    ckind = cinfo[1]
                    if ckind == 0 and len(child) == 0:
                        citems = child.items()
                        cstart = _startTag(cinfo[0], cinfo[3], citems) if citems else cinfo[3]
                        cend = cinfo[4] or f"</{cinfo[0]}>"
                        if ctext := child.text:
                            if "&" in ctext:
                                ctext = ctext.replace("&", "&amp;")
                            if "<" in ctext:
                                ctext = ctext.replace("<", "&lt;")
                            if tail := child.tail:
                                if "&" in tail:
                                    tail = tail.replace("&", "&amp;")
                                if "<" in tail:
                                    tail = tail.replace("<", "&lt;")
                                write(f"{cstart}{ctext}{cend}{tail}")
                            else:
                                write(f"{cstart}{ctext}{cend}")
                        elif tail := child.tail:
                            if "&" in tail:
                                tail = tail.replace("&", "&amp;")
                            if "<" in tail:
                                tail = tail.replace("<", "&lt;")
                            write(f"{cstart}{cend}{tail}")
                        else:
                            write(cstart + cend)
                    else:
                        if ckind != -1:
                            _writeInline(child, indent_str, cinfo)
                        if tail := child.tail:
                            if "&" in tail:
                                tail = tail.replace("&", "&amp;")
                            if "<" in tail:
                                tail = tail.replace("<", "&lt;")
                            write(tail)
                write(f"</{tag}>")
            elif kind == 1:
                items = el.items()
                start = _startTag(tag, openTag, items) if items else openTag
                write(indent_str + start if indent_str else start)
            elif kind == 2:
                if text := el.text:
                    if "&" in text:
                        text = text.replace("&", "&amp;")
                    if "<" in text:
                        text = text.replace("<", "&lt;")
                    write(text)
                for child in el:
                    ctag = child.tag
                    try:
                        cinfo = tagInfo[ctag]
                    except KeyError:
                        cinfo = _getTagInfo(ctag)
                    if cinfo[1] != -1:
                        _writeInline(child, indent_str, cinfo)
                    if tail := child.tail:
                        if "&" in tail:
                            tail = tail.replace("&", "&amp;")
                        if "<" in tail:
                            tail = tail.replace("<", "&lt;")
                        write(tail)
            elif kind == 4 or (kind == 5 and el.get("bs-title-contents")):
                _writeRaw(tag, openTag, el, indent_str)
            else:
                items = el.items()
                start = _startTag(tag, openTag, items) if items else openTag
                if text := el.text:
                    if "&" in text:
                        text = text.replace("&", "&amp;")
                    if "<" in text:
                        text = text.replace("<", "&lt;")
                    write(start + text)
                else:
                    write(start)
                for child in el:
                    ctag = child.tag
                    try:
                        cinfo = tagInfo[ctag]
                    except KeyError:
                        cinfo = _getTagInfo(ctag)
                    if cinfo[1] != -1:
                        _writeInline(child, indent_str, cinfo)
                    if tail := child.tail:
                        if "&" in tail:
                            tail = tail.replace("&", "&amp;")
                        if "<" in tail:
                            tail = tail.replace("<", "&lt;")
                        write(tail)
                write(f"</{tag}>")

        def _writeBlock(el: t.ElementT, indent: int, info: TagInfoT) -> str:
            """
            Single-pass streaming serializer for block elements.

            Replaces the previous multi-pass approach (`dom.childNodes(clear=True, mergeText=True)`,
            `isBlockElement` scan, `groupIntoBlocks`, `justWS`, and `pairwise`) which iterated
            children 3-5 times, allocated temporary lists, and destroyed the LXML tree.

            Key speed tricks:
            - Deferred `header`: We hold `header` (`indent_str + startTag`) until the first child
              or end of `el`. If `el` has no children (~37% of blocks), we emit
              `f"{header}{pendingText}{closeTag}"` in a single `write()` without calling `len(el)`.
            - Optimistic inline streaming with in-place patching: When the first child is inline,
              we immediately write `header` (recording `headerIdx = len(out)`) and stream inline
              children directly to `out`. In the rare case (~3% of blocks) where a block child
              appears later in the same element, that initial inline run becomes an anonymous
              block that needed a newline+indent after `header`, so we simply patch
              `out[headerIdx] = header + nl_next` in-place with zero rollback.
            - Inlined leaf inline children: ~90% of inline children (`<a>`, `<code>`, `<span>`,
              `<dfn>`, `<var>`) have `ckind == 0 and len(c) == 0`. Handling them inline avoids
              ~8,000 `_writeInline` calls per spec. (We intentionally do NOT check `len(c) == 0`
              on block children because LXML's `len(el)` walks the child linked list in O(N) time,
              which is expensive on large container blocks like `<body>` or `<section>`.)
            - Conditional `<dt>`/`<dd>` end tags without `pairwise` lookahead: When a child block
              is `<dt>` or `<dd>` (`closeTag is None`), `_writeBlock` returns its closing tag
              string as `childPendingClose` instead of writing it. The parent only writes
              `childPendingClose` if a subsequent non-`<dt>`/`<dd>` block or non-whitespace
              inline run follows.
            - Uses `pendingText.isspace()` instead of `pendingText.strip() == ""` to avoid
              allocating a stripped copy of every non-whitespace string.
            """
            tag, kind, _, openTag, closeTag = info
            indent_str = _INDENTS[indent] if indent < 128 else " " * indent

            if kind == 1:
                items = el.items()
                start = _startTag(tag, openTag, items) if items else openTag
                write(indent_str + start)
                return ""
            if kind == 3:
                _writeInline(el, indent_str, info)
                return ""
            if kind == 4 or (kind == 5 and el.get("bs-title-contents")):
                _writeRaw(tag, openTag, el, indent_str)
                return ""

            if kind != 2:
                items = el.items()
                header = indent_str + (_startTag(tag, openTag, items) if items else openTag)
            else:
                header = indent_str

            pendingText: str | None = el.text or None
            hasBlocks = False
            inInlineRun = False
            headerIdx = -1
            childPendingClose = ""

            for c in el:
                ctag = c.tag
                try:
                    cinfo = tagInfo[ctag]
                except KeyError:
                    cinfo = _getTagInfo(ctag)
                ckind = cinfo[1]
                if ckind == -1:
                    # Odd node (e.g. HTML comment): ignore the node itself, but merge its `.tail`
                    # text just like `dom.childNodes(mergeText=True)` would.
                    if tail := c.tail:
                        if inInlineRun:
                            if "&" in tail:
                                tail = tail.replace("&", "&amp;")
                            if "<" in tail:
                                tail = tail.replace("<", "&lt;")
                            write(tail)
                        elif pendingText is not None:
                            pendingText += tail
                        else:
                            pendingText = tail
                    continue
                if not cinfo[2]:
                    # Inline child (`cinfo[2]` is `isBlock == False`)
                    if not inInlineRun:
                        if hasBlocks:
                            if childPendingClose:
                                write(childPendingClose)
                                childPendingClose = ""
                            nl_next = _NL_INDENTS[indent + 1] if indent + 1 < 128 else "\n" + " " * (indent + 1)
                            if pendingText is not None:
                                if "&" in pendingText:
                                    pendingText = pendingText.replace("&", "&amp;")
                                if "<" in pendingText:
                                    pendingText = pendingText.replace("<", "&lt;")
                                write(nl_next + pendingText)
                                pendingText = None
                            else:
                                write(nl_next)
                        else:
                            headerIdx = len(out)
                            write(header)
                            if pendingText is not None:
                                if "&" in pendingText:
                                    pendingText = pendingText.replace("&", "&amp;")
                                if "<" in pendingText:
                                    pendingText = pendingText.replace("<", "&lt;")
                                write(pendingText)
                                pendingText = None
                        inInlineRun = True
                    if ckind == 0 and len(c) == 0:
                        citems = c.items()
                        cstart = _startTag(cinfo[0], cinfo[3], citems) if citems else cinfo[3]
                        cclose = cinfo[4]
                        if ctext := c.text:
                            if "&" in ctext:
                                ctext = ctext.replace("&", "&amp;")
                            if "<" in ctext:
                                ctext = ctext.replace("<", "&lt;")
                            if tail := c.tail:
                                if "&" in tail:
                                    tail = tail.replace("&", "&amp;")
                                if "<" in tail:
                                    tail = tail.replace("<", "&lt;")
                                write(f"{cstart}{ctext}{cclose}{tail}")
                            else:
                                write(f"{cstart}{ctext}{cclose}")
                        elif tail := c.tail:
                            if "&" in tail:
                                tail = tail.replace("&", "&amp;")
                            if "<" in tail:
                                tail = tail.replace("<", "&lt;")
                            write(f"{cstart}{cclose}{tail}")
                        else:
                            write(f"{cstart}{cclose}")
                    else:
                        _writeInline(c, "", cinfo)
                        if tail := c.tail:
                            if "&" in tail:
                                tail = tail.replace("&", "&amp;")
                            if "<" in tail:
                                tail = tail.replace("<", "&lt;")
                            write(tail)
                else:
                    # Block child (`cinfo[2]` is `isBlock == True`)
                    if inInlineRun:
                        if not hasBlocks:
                            # This element started with inline content and now hit a block child;
                            # retroactively indent that initial inline run as an anonymous block.
                            nl_next = _NL_INDENTS[indent + 1] if indent + 1 < 128 else "\n" + " " * (indent + 1)
                            out[headerIdx] = header + nl_next
                        inInlineRun = False
                    elif not hasBlocks:
                        if pendingText is not None and not pendingText.isspace():
                            nl_next = _NL_INDENTS[indent + 1] if indent + 1 < 128 else "\n" + " " * (indent + 1)
                            if "&" in pendingText:
                                pendingText = pendingText.replace("&", "&amp;")
                            if "<" in pendingText:
                                pendingText = pendingText.replace("<", "&lt;")
                            write(f"{header}{nl_next}{pendingText}\n")
                        else:
                            write(header + "\n")
                        pendingText = None
                        hasBlocks = True
                        childPendingClose = _writeBlock(c, indent + 1, cinfo)
                        pendingText = c.tail or None
                        continue
                    elif pendingText is not None:
                        if not pendingText.isspace():
                            if childPendingClose:
                                write(childPendingClose)
                                childPendingClose = ""
                            nl_next = _NL_INDENTS[indent + 1] if indent + 1 < 128 else "\n" + " " * (indent + 1)
                            if "&" in pendingText:
                                pendingText = pendingText.replace("&", "&amp;")
                            if "<" in pendingText:
                                pendingText = pendingText.replace("<", "&lt;")
                            write(nl_next + pendingText)
                        pendingText = None
                    if childPendingClose:
                        if ctag not in ("dt", "dd"):
                            write(childPendingClose)
                        childPendingClose = ""
                    hasBlocks = True
                    write("\n")
                    childPendingClose = _writeBlock(c, indent + 1, cinfo)
                    pendingText = c.tail or None

            if not hasBlocks:
                if inInlineRun:
                    if closeTag is not None:
                        if closeTag:
                            write(closeTag)
                        return ""
                    return f"</{tag}>"
                if pendingText is not None and not pendingText.isspace():
                    if "&" in pendingText:
                        pendingText = pendingText.replace("&", "&amp;")
                    if "<" in pendingText:
                        pendingText = pendingText.replace("<", "&lt;")
                    if closeTag is not None:
                        write(f"{header}{pendingText}{closeTag}")
                        return ""
                    write(header + pendingText)
                    return f"</{tag}>"
                if closeTag is not None:
                    write(header + closeTag if closeTag else header)
                    return ""
                write(header)
                return f"</{tag}>"

            if not inInlineRun and pendingText is not None and not pendingText.isspace():
                if childPendingClose:
                    write(childPendingClose)
                nl_next = _NL_INDENTS[indent + 1] if indent + 1 < 128 else "\n" + " " * (indent + 1)
                if "&" in pendingText:
                    pendingText = pendingText.replace("&", "&amp;")
                if "<" in pendingText:
                    pendingText = pendingText.replace("<", "&lt;")
                write(nl_next + pendingText)

            nl_indent = _NL_INDENTS[indent] if indent < 128 else "\n" + indent_str
            if closeTag is not None:
                if closeTag:
                    write(nl_indent + closeTag)
                elif kind == 2:
                    write(nl_indent)
                return ""
            return f"{nl_indent}</{tag}>"

        try:
            rinfo = tagInfo[root.tag]
        except KeyError:
            rinfo = _getTagInfo(root.tag)
        _writeBlock(root, 0, rinfo)
        return "".join(out)

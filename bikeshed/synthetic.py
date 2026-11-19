# Generates deterministic, self-contained synthetic Bikeshed source documents
# of approximately a requested byte size for performance profiling and
# benchmarking (`bikeshed profile --synthetic`). Each generated document
# cycles through chapters covering CSS properties/descriptors/railroad grammars,
# WebIDL, algorithms, markup/HTTP definitions, CDDL, Markdown, syntax
# highlighting, WPT blocks, Can I Use panels, conditionals, and dense
# cross-references while compiling cleanly offline.

from __future__ import annotations

import json
import re

from . import retrieve

DEFAULT_SYNTHETIC_SIZE = "200kb"

SIZE_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([a-zA-Z]*)\s*$")

UNIT_MULTIPLIERS: dict[str, int] = {
    "": 1024,  # Bare numbers default to KB
    "b": 1,
    "byte": 1,
    "bytes": 1,
    "k": 1024,
    "kb": 1024,
    "kib": 1024,
    "m": 1024 * 1024,
    "mb": 1024 * 1024,
    "mib": 1024 * 1024,
    "g": 1024 * 1024 * 1024,
    "gb": 1024 * 1024 * 1024,
    "gib": 1024 * 1024 * 1024,
}

CANONICAL_UNIT_LABELS: dict[str, str] = {
    "": "kb",
    "b": "b",
    "byte": "b",
    "bytes": "b",
    "k": "kb",
    "kb": "kb",
    "kib": "kb",
    "m": "mb",
    "mb": "mb",
    "mib": "mb",
    "g": "gb",
    "gb": "gb",
    "gib": "gb",
}

PREFERRED_CANIUSE_FEATURES = [
    "flexbox",
    "css-grid",
    "css-variables",
    "css-cascade-layers",
    "fetch",
    "promises",
    "webworkers",
    "abortcontroller",
    "intersectionobserver",
    "resizeobserver",
    "shadowdomv1",
    "custom-elementsv1",
    "css-container-queries",
    "css-nesting",
    "css-subgrid",
    "css-has",
]

FALLBACK_WPT_TESTS = [
    "https://wpt.live/dom/nodes/Node-appendChild.html",
    "https://wpt.live/css/css-values/calc-numbers.html",
    "https://wpt.live/fetch/api/basic/request-headers.any.html",
    "https://wpt.live/html/semantics/embedded-content/the-img-element/img.complete.html",
]


def parseSize(sizeStr: str) -> int:
    """Parse a human-readable size string (e.g. '500kb', '2MB', '100') into bytes; bare numbers are KB."""
    match = SIZE_RE.match(sizeStr)
    if not match:
        msg = (
            f"Invalid synthetic size '{sizeStr}'. "
            + "Expected a positive number with optional unit (e.g. 500kb, 2MB, 100k, 50000b, or bare number in KB)."
        )
        raise ValueError(msg)

    value = float(match.group(1))
    unit = match.group(2).lower()
    if unit not in UNIT_MULTIPLIERS:
        msg = (
            f"Unknown size unit '{match.group(2)}' in '{sizeStr}'. "
            + "Supported units: b, k/kb/kib, m/mb/mib, g/gb/gib (or omit unit for KB)."
        )
        raise ValueError(msg)

    numBytes = round(value * UNIT_MULTIPLIERS[unit])
    if numBytes <= 0:
        msg = f"Synthetic size must be positive; got '{sizeStr}'."
        raise ValueError(msg)

    return numBytes


def formatSize(numBytes: int) -> str:
    """Format a byte count as a human-readable B/KB/MB string."""
    if numBytes >= 1024 * 1024:
        return f"{numBytes / (1024 * 1024):.2f} MB"
    if numBytes >= 1024:
        return f"{numBytes / 1024:.1f} KB"
    return f"{numBytes} B"


def defaultFilename(sizeStr: str) -> str:
    """Return the default 'synth-<size>.bs' filename for a size string."""
    match = SIZE_RE.match(sizeStr)
    if not match:
        return f"synth-{sizeStr.strip()}.bs"
    amount = match.group(1)
    unit = CANONICAL_UNIT_LABELS.get(match.group(2).lower(), match.group(2).lower())
    return f"synth-{amount}{unit}.bs"


def sampleWptTests(dataFile: retrieve.DataFileRequester, limitPerType: int = 8) -> list[str]:
    """Deterministically sample real WPT test paths from local spec-data."""
    buckets: dict[str, list[str]] = {
        "testharness": [],
        "reftest": [],
        "crashtest": [],
    }
    try:
        with dataFile.fetch("wpt-tests.txt", okayToFail=True) as fh:
            for line in fh:
                parts = line.strip().split(" ", 1)
                if len(parts) != 2:
                    continue
                testType, path = parts
                bucket = buckets.get(testType)
                if bucket is not None and len(bucket) < limitPerType:
                    bucket.append(path)
                    if all(len(b) >= limitPerType for b in buckets.values()):
                        break
    except OSError:
        pass

    result: list[str] = []
    for i in range(limitPerType):
        for testType in ("testharness", "reftest", "crashtest"):
            if i < len(buckets[testType]):
                result.append(buckets[testType][i])

    return result or list(FALLBACK_WPT_TESTS)


def sampleCanIUseFeatures(dataFile: retrieve.DataFileRequester) -> list[str]:
    """Deterministically select valid Can I Use feature IDs from local spec-data."""
    try:
        raw = dataFile.fetch("caniuse", "data.json", str=True, okayToFail=True)
        if not raw:
            return []
        parsed = json.loads(raw)
        features = parsed.get("features", {})
        if not isinstance(features, dict):
            return []
        valid = [feat for feat in PREFERRED_CANIUSE_FEATURES if feat in features]
        if valid:
            return valid
        return sorted(str(k) for k in list(features.keys())[:12])
    except (OSError, ValueError):
        return []


class SyntheticSpecBuilder:
    """Assembles a synthetic Bikeshed source document by cycling through feature-rich chapter archetypes."""

    def __init__(self, dataFile: retrieve.DataFileRequester) -> None:
        """Initialize builder state and sample local WPT and Can I Use data."""
        self.wptTests = sampleWptTests(dataFile)
        self.canIUseFeatures = sampleCanIUseFeatures(dataFile)
        self.emittedCss: list[int] = []
        self.emittedGrammar: list[int] = []
        self.emittedIdl: list[int] = []
        self.emittedAlgo: list[int] = []
        self.emittedMarkup: list[int] = []
        self.emittedCddl: list[int] = []

    def preamble(self, compact: bool = False) -> str:
        """Return the metadata block, datablock declarations, and introduction section."""
        canIUseMeta = "Include Can I Use Panels: yes\n" if self.canIUseFeatures else ""
        if compact:
            return (
                "<pre class='metadata'>\n"
                + "Title: Synthetic Performance Benchmark Specification\n"
                + "Shortname: synthetic-perf-test\n"
                + "Level: 1\n"
                + "Status: ED\n"
                + "Work Status: exploring\n"
                + "Group: csswg\n"
                + "URL: https://drafts.csswg.org/synthetic-perf-test/\n"
                + "Repository: example/synthetic-perf-test\n"
                + "Editor: Ada Lovelace, Example Org, https://example.com/ada\n"
                + "Date: 2026-01-01\n"
                + "Indent: 4\n"
                + "Abstract: A compact synthetic specification for Bikeshed performance profiling.\n"
                + "Markup Shorthands: algorithm yes, biblio yes, cddl yes, css yes, dfn yes, http yes, idl yes, "
                + "macros-in-autolinks yes, markdown-block yes, markdown-blockquotes yes, markdown-inline yes, "
                + "markdown-escapes yes, markup yes\n"
                + "Complain About: accidental-2119 yes, missing-example-ids yes, mixed-indents yes\n"
                + canIUseMeta
                + "Use Dfn Panels: yes\n"
                + "WPT Display: inline\n"
                + "Inline Github Issues: no\n"
                + "Dark Mode: yes\n"
                + "Text Macro: SPEC-CODENAME SyntheticPerf\n"
                + "Required IDs: #intro, #privacy, #security, #conformance\n"
                + "</pre>\n\n"
                + "# Introduction # {#intro}\n\n"
                + "The [SPEC-CODENAME] specification defines a <dfn export>synthetic context</dfn>, "
                + "a <dfn export>processing pipeline</dfn>, a "
                + "<dfn export lt='render node|render nodes'>render node</dfn>, and an "
                + "<dfn noexport>internal scheduler</dfn> "
                + "for benchmarking Bikeshed [[!RFC2119]] [[!INFRA]].\n\n"
                + "A conforming user agent must initialize the [=synthetic context=], update [=render nodes=], "
                + "and drive the [=processing pipeline=] via the [=internal scheduler=].\n\n"
            )

        return (
            "<pre class='metadata'>\n"
            + "Title: Synthetic Performance Benchmark Specification\n"
            + "Shortname: synthetic-perf-test\n"
            + "Level: 1\n"
            + "Status: ED\n"
            + "Work Status: exploring\n"
            + "Group: csswg\n"
            + "URL: https://drafts.csswg.org/synthetic-perf-test/\n"
            + "Repository: example/synthetic-perf-test\n"
            + "Editor: Ada Lovelace, Example Org, https://example.com/ada\n"
            + "Editor: Grace Hopper, Example Org, https://example.com/grace\n"
            + "Former Editor: Charles Babbage, Analytical Inc.\n"
            + "Date: 2026-01-01\n"
            + "Indent: 4\n"
            + "Abstract: A synthetically generated specification exercising a wide suite of Bikeshed features\n"
            + "    for performance profiling and regression testing.\n"
            + "Abstract: Exercises CSS property and descriptor definitions, WebIDL interfaces, CDDL schemas,\n"
            + "    algorithms, Markdown blocks and inline syntax, syntax highlighting, railroad diagrams,\n"
            + "    WPT blocks, Can I Use panels, conditionals, and dense cross-referencing.\n"
            + "Markup Shorthands: algorithm yes, biblio yes, cddl yes, css yes, dfn yes, http yes, idl yes, "
            + "macros-in-autolinks yes, markdown-block yes, markdown-blockquotes yes, markdown-inline yes, "
            + "markdown-escapes yes, markup yes\n"
            + "Complain About: accidental-2119 yes, missing-example-ids yes, mixed-indents yes\n"
            + canIUseMeta
            + "Use Dfn Panels: yes\n"
            + "WPT Display: inline\n"
            + "Inline Github Issues: no\n"
            + "Dark Mode: yes\n"
            + "Force Crossorigin: yes\n"
            + "Remove Multiple Links: yes\n"
            + "Text Macro: SPEC-CODENAME SyntheticPerf\n"
            + "Text Macro: API-VERSION 2.0\n"
            + "At Risk: Experimental features marked in individual synthetic modules\n"
            + "Required IDs: #intro, #privacy, #security, #conformance\n"
            + "</pre>\n\n"
            + "<style>\n"
            + ".synth-table td, .synth-table th { padding: 0.35em 0.6em; }\n"
            + ".synth-badge { font-weight: 600; font-family: monospace; }\n"
            + "</style>\n\n"
            + "<pre class='biblio'>\n"
            + "{\n"
            + '    "SYNTH-CORE": {\n'
            + '        "authors": ["Ada Lovelace", "Grace Hopper"],\n'
            + '        "href": "https://example.com/specs/synth-core/",\n'
            + '        "title": "Synthetic Core Architecture",\n'
            + '        "status": "ED",\n'
            + '        "publisher": "Example Standards Group",\n'
            + '        "date": "2026-01-01"\n'
            + "    },\n"
            + '    "SYNTH-EXT": {\n'
            + '        "authors": ["Charles Babbage"],\n'
            + '        "href": "https://example.com/specs/synth-ext/",\n'
            + '        "title": "Synthetic Extensions Primer",\n'
            + '        "status": "NOTE",\n'
            + '        "publisher": "Example Standards Group",\n'
            + '        "date": "2025-11-15"\n'
            + "    }\n"
            + "}\n"
            + "</pre>\n\n"
            + "<pre class='anchors'>\n"
            + "urlPrefix: https://example.com/synth-ext/;\n"
            + "    type: dfn;\n"
            + "        text: external synth context; url: #external-synth-context\n"
            + "    type: interface;\n"
            + "        text: ExternalSynthHost; url: #externalsynthhost\n"
            + "    type: property;\n"
            + "        text: external-synth-mode; url: #propdef-external-synth-mode\n"
            + "    type: abstract-op;\n"
            + "        text: ExternalSynthHook; url: #abstract-opdef-externalsynthhook\n"
            + "</pre>\n\n"
            + "<pre class='link-defaults'>\n"
            + "spec:infra; type:dfn; text:list\n"
            + "spec:infra; type:dfn; text:map\n"
            + "spec:infra; type:dfn; text:ordered set\n"
            + "spec:infra; type:dfn; text:struct\n"
            + "spec:infra; type:dfn; text:string\n"
            + "spec:html; type:dfn; text:flow content\n"
            + "spec:html; type:element; text:div\n"
            + "spec:html; type:element; text:span\n"
            + "spec:html; type:element; text:script\n"
            + "spec:css-values-4; type:type; text:length\n"
            + "spec:css-values-4; type:type; text:length-percentage\n"
            + "spec:css-values-4; type:type; text:percentage\n"
            + "spec:css-values-4; type:type; text:number\n"
            + "spec:css-color-4; type:type; text:color\n"
            + "spec:css-display-4; type:property; text:display\n"
            + "spec:css-color-4; type:property; text:color\n"
            + "spec:fetch; type:http-header; text:X-Content-Type-Options\n"
            + "</pre>\n\n"
            + "<pre class='ignored-specs'>\n"
            + "spec: css21\n"
            + "</pre>\n\n"
            + "<!-- Core overview comment for [SPEC-CODENAME] v[API-VERSION] -->\n\n"
            + "Introduction {#intro}\n"
            + "=====================\n\n"
            + "The [SPEC-CODENAME] (version [API-VERSION]) document specifies a "
            + "<dfn export>synthetic context</dfn>, a <dfn export>processing pipeline</dfn>, "
            + "a <dfn export lt='render node|render nodes'>render node</dfn>, and an "
            + "<dfn noexport local-lt='scheduler'>internal scheduler</dfn> that coordinate "
            + "across styling, scripting, markup, and wire serialization layers "
            + "[[!RFC2119]] [[!INFRA]] [[!SYNTH-CORE]] [[HTML]] [[DOM]] [[WEBIDL]] "
            + "[[CSS-VALUES-4]] [[FETCH]] [[URL]] [[ECMASCRIPT]].\n\n"
            + "Informative background is provided in [[SYNTH-EXT]]. "
            + "Implementations integrating with an [=external synth context=] and {{ExternalSynthHost}} "
            + "must honor 'external-synth-mode' and invoke [$ExternalSynthHook$] when bootstrapping "
            + "the <l>[=synthetic context=]</l>. The author's configuration doesn't bypass validation--\n"
            + "instead, every [=render node=] flows through the [=processing pipeline=] and "
            + "the [=internal scheduler=] (referred to locally as the [=scheduler=]).\n\n"
            + "Literal shorthand escapes remain plain text: \\[=not-a-link=], \\{{NotAnInterface}}, "
            + "\\'not-a-prop', \\<<not-a-type>>, \\*not italic\\*, and \\`not code\\`.\n\n"
            + "<div include-if='ED'>\n"
            + "This Editor's Draft block is conditionally included because the status is `ED`.\n"
            + "</div>\n\n"
            + "<div include-if='CR'>\n"
            + "This Candidate Recommendation notice is conditionally excluded during ED builds.\n"
            + "</div>\n\n"
            + "<if-wrapper include-if='text macro: SPEC-CODENAME'>\n"
            + "Conditional `if-wrapper` content matches the `SPEC-CODENAME` text macro "
            + "<span exclude-if='REC'>for non-REC builds</span><span include-if='REC'>only in REC</span>.\n"
            + "</if-wrapper>\n\n"
        )

    def canIUseAttr(self, idx: int) -> str:
        """Return a caniuse attribute snippet for module idx, or empty string if unavailable."""
        if not self.canIUseFeatures:
            return ""
        feat = self.canIUseFeatures[idx % len(self.canIUseFeatures)]
        return f" caniuse='{feat}'"

    def cssChapter(self, idx: int) -> str:
        """Generate a chapter exercising CSS propdefs, grammars, selectors, Can I Use, and CSS highlighting."""
        self.emittedCss.append(idx)
        canIUse = self.canIUseAttr(idx)
        prevRef = ""
        if idx > 0 and self.emittedCss[:-1]:
            prevIdx = self.emittedCss[-2]
            prevRef = (
                f" It composes with 'synth-layout-{prevIdx}', ''synth-layout-{prevIdx}/compact'', "
                + f"and <<synth-token-{prevIdx}>> defined in [[#css-module-{prevIdx}]]."
            )

        return (
            f"# Styling Module {idx} # {{#css-module-{idx}}}\n\n"
            + "This section defines CSS properties, shorthands, grammar productions, and selectors "
            + f"for [=synthetic context=] styling unit {idx}.{prevRef}\n\n"
            + "<pre class='propdef'>\n"
            + f"Name: synth-layout-{idx}\n"
            + f"Value: auto | none | [ <<length-percentage>> || <<synth-token-{idx}>> ]{{1,4}} && [ <'color'> ]? | <<synth-scale-{idx}>>#\n"
            + "Initial: auto\n"
            + "Applies to: all elements\n"
            + "Inherited: no\n"
            + "Percentages: relative to the containing block width\n"
            + "Computed value: specified keyword or computed list\n"
            + "Animation type: discrete\n"
            + "</pre>\n\n"
            + "<pre class='propdef'>\n"
            + f"Name: synth-align-{idx}\n"
            + "Value: start | center | end | <<number [0,100]>>+\n"
            + "Initial: start\n"
            + "Applies to: all elements\n"
            + "Inherited: yes\n"
            + "Percentages: n/a\n"
            + "Computed value: as specified\n"
            + "Animation type: by computed value type\n"
            + "</pre>\n\n"
            + "<pre class='propdef shorthand'>\n"
            + f"Name: synth-box-{idx}\n"
            + f"Value: <'synth-layout-{idx}'> || <'synth-align-{idx}'>\n"
            + "</pre>\n\n"
            + "<pre class='propdef partial'>\n"
            + f"Name: synth-layout-{idx}\n"
            + "New values: compact | expanded <<length>>?\n"
            + "</pre>\n\n"
            + f"<dl dfn-type='value' dfn-for='synth-layout-{idx}'>\n"
            + "    : <dfn>auto</dfn>\n"
            + "    :: Computes the layout automatically from the surrounding 'display' and [=render nodes=].\n"
            + "    : <dfn>none</dfn>\n"
            + f"    :: Disables module {idx} synthetic layout participation.\n"
            + f"    : <dfn{canIUse}>compact</dfn>\n"
            + "    :: Packs [=render nodes=] tightly using <<length>> and <<percentage>> metrics.\n"
            + "    : <dfn>expanded</dfn>\n"
            + "    :: Expands tracks with a <<color>> accent and 'color' fallback.\n"
            + "</dl>\n\n"
            + f"The <dfn export type><<synth-token-{idx}>></dfn> production accepts either a keyword "
            + f"or the <dfn export function>synth-calc-{idx}()</dfn> functional notation, while "
            + f"<dfn export type><<synth-scale-{idx}>></dfn> accepts a ranged <<number [0,100]>>. "
            + f"Authors can target generated sub-boxes via the <dfn export selector>::synth-part-{idx}</dfn> "
            + f"pseudo-element when 'synth-layout-{idx}' is ''synth-layout-{idx}/compact'' or "
            + f"''synth-layout-{idx}/expanded'', or via the 'synth-box-{idx}' shorthand and "
            + f"''synth-calc-{idx}()''.\n\n"
            + f"<div class='example' id='example-css-{idx}' heading=\"Styling with 'synth-layout-{idx}'\">\n"
            + f"    Applying ''synth-layout-{idx}/compact'' alongside ''::synth-part-{idx}'':\n\n"
            + "    <pre highlight='css' line-numbers line-highlight='2,4-5'>\n"
            + f"    .panel-{idx} {{\n"
            + f"        synth-layout-{idx}: compact;\n"
            + f"        synth-align-{idx}: center;\n"
            + "        color: rebeccapurple;\n"
            + "        display: grid;\n"
            + "    }\n"
            + f"    .panel-{idx}::synth-part-{idx} {{\n"
            + f"        synth-box-{idx}: auto start;\n"
            + "    }\n"
            + "    </pre>\n"
            + "</div>\n\n"
            + "<div class='note' heading='Cascade Interaction'>\n"
            + f"    Setting 'synth-box-{idx}' resets both 'synth-layout-{idx}' and 'synth-align-{idx}' "
            + "to their initial keywords when omitted from the declaration.\n"
            + "</div>\n\n"
        )

    def grammarChapter(self, idx: int) -> str:
        """Generate a chapter exercising CSS at-rules, descdefs, railroad diagrams, simpledefs, and blockquotes."""
        self.emittedGrammar.append(idx)
        cssLink = f" and 'synth-layout-{self.emittedCss[-1]}'" if self.emittedCss else ""
        return (
            f"# Rule and Grammar Module {idx} # {{#grammar-module-{idx}}}\n\n"
            + f"The <dfn export at-rule>@synth-rule-{idx}</dfn> at-rule registers reusable descriptors "
            + f"for the [=processing pipeline=]{cssLink}.\n\n"
            + "<pre class='descdef'>\n"
            + f"Name: synth-src-{idx}\n"
            + f"For: @synth-rule-{idx}\n"
            + "Value: <<string>> | <<length>>+\n"
            + "Initial: none\n"
            + "</pre>\n\n"
            + "<pre class='descdef'>\n"
            + f"Name: synth-weight-{idx}\n"
            + f"For: @synth-rule-{idx}\n"
            + "Value: normal | bold | <<number [1,1000]>>\n"
            + "Initial: normal\n"
            + "</pre>\n\n"
            + f"The syntax of ''@synth-rule-{idx}'' with descriptors '@synth-rule-{idx}/synth-src-{idx}' "
            + f"and '@synth-rule-{idx}/synth-weight-{idx}' follows this railroad grammar:\n\n"
            + "<pre class='railroad'>\n"
            + "Sequence:\n"
            + f"    Terminal: @synth-rule-{idx}\n"
            + "    NonTerminal: ident\n"
            + "    Terminal: {\n"
            + "    OneOrMore:\n"
            + "        Choice: 0\n"
            + "            Sequence:\n"
            + f"                Terminal: synth-src-{idx}:\n"
            + "                NonTerminal: value\n"
            + "            Sequence:\n"
            + f"                Terminal: synth-weight-{idx}:\n"
            + "                Optional:\n"
            + "                    NonTerminal: number\n"
            + "            Skip:\n"
            + "        Comment: ;\n"
            + "    Terminal: }\n"
            + "</pre>\n\n"
            + "<pre class='simpledef'>\n"
            + f"Rule name: ''@synth-rule-{idx}''\n"
            + "Scope: document-wide [=synthetic context=]\n"
            + "Validation: syntax checked during parse\n"
            + "Validation: descriptors resolved before layout\n"
            + "</pre>\n\n"
            + f"> Descriptors inside ''@synth-rule-{idx}'' follow **strict** *forward-compatible* "
            + "parsing rules with `fallback` tokens and [introduction anchors](#intro).\n"
            + ">\n"
            + f">> Nested quote: invalid declarations for '@synth-rule-{idx}/synth-weight-{idx}' "
            + "are dropped without discarding sibling descriptors.\n\n"
            + f"<p class='advisement'>User agents must reject malformed ''@synth-rule-{idx}'' "
            + "blocks before mutating [=render nodes=].</p>\n\n"
            + f"<p class='issue'>Clarify interaction between '@synth-rule-{idx}/synth-src-{idx}' "
            + "and dynamic stylesheet updates in [=synthetic context=].</p>\n\n"
        )

    def idlChapter(self, idx: int) -> str:
        """Generate a chapter exercising WebIDL blocks, domintro, argumentdefs, and JS highlighting."""
        self.emittedIdl.append(idx)
        prevIdl = ""
        if len(self.emittedIdl) >= 2:
            prevIdx = self.emittedIdl[-2]
            prevIdl = (
                f" It interoperates with {{{{SynthController{prevIdx}}}}} "
                + f"and {{{{SynthUtils{prevIdx}/formatTag(raw)}}}}."
            )
        return (
            f"# Scripting API Module {idx} # {{#idl-module-{idx}}}\n\n"
            + f"Module {idx} exposes WebIDL interfaces, dictionaries, enums, mixins, callbacks, "
            + f"and namespaces backed by {{{{EventTarget}}}} and {{{{Promise}}}}.{prevIdl}\n\n"
            + "<pre class='idl'>\n"
            + f'enum SynthMode{idx} {{ "eager", "lazy", "balanced" }};\n\n'
            + f"callback SynthCallback{idx} = undefined (DOMString token, unsigned long count);\n\n"
            + f"dictionary SynthOptions{idx} {{\n"
            + f'    SynthMode{idx} mode = "balanced";\n'
            + "    boolean active = true;\n"
            + "    required USVString label;\n"
            + "    sequence&lt;DOMString> tags;\n"
            + "};\n\n"
            + f"interface mixin SynthObservable{idx} {{\n"
            + "    readonly attribute unsigned long generation;\n"
            + "};\n\n"
            + "[Exposed=(Window,Worker)]\n"
            + f"interface SynthController{idx} : EventTarget {{\n"
            + f"    constructor(optional SynthOptions{idx} options = {{}});\n"
            + f"    attribute SynthMode{idx} mode;\n"
            + "    readonly attribute DOMString identifier;\n"
            + f"    Promise&lt;boolean> process(USVString input, optional SynthOptions{idx} options = {{}}, optional SynthCallback{idx}? callback = null);\n"
            + "    undefined reset();\n"
            + "};\n\n"
            + f"SynthController{idx} includes SynthObservable{idx};\n\n"
            + f"partial interface SynthController{idx} {{\n"
            + "    readonly attribute boolean ready;\n"
            + "};\n\n"
            + "[Exposed=Window]\n"
            + f"namespace SynthUtils{idx} {{\n"
            + "    DOMString formatTag(DOMString raw);\n"
            + "};\n"
            + "</pre>\n\n"
            + "<dl class='domintro'>\n"
            + f"    : `controller = new SynthController{idx}(options)`\n"
            + f"    :: Creates a new {{{{SynthController{idx}}}}} bound to the current [=synthetic context=].\n"
            + "    : `await controller.process(input, options)`\n"
            + f"    :: Runs the {{{{SynthController{idx}/process()}}}} operation and resolves with a boolean flag.\n"
            + "    : `controller.mode`\n"
            + f"    :: Reflects the active {{{{SynthController{idx}/mode}}}} enum value.\n"
            + "</dl>\n\n"
            + f"<div algorithm='SynthController{idx} process'>\n"
            + f"    <pre class='argumentdef' for='SynthController{idx}/process()'>\n"
            + "    |input|: The {{USVString}} payload to normalize.\n"
            + f"    |options|: A {{{{SynthOptions{idx}}}}} configuration dictionary.\n"
            + f"    |callback|: An optional {{{{SynthCallback{idx}}}}} progress observer.\n"
            + "    </pre>\n\n"
            + f"    The <dfn export method for='SynthController{idx}'>process(|input|, |options|, |callback|)</dfn> "
            + "method steps are:\n\n"
            + "    1. Let |trimmed| be |input| trimmed of whitespace.\n"
            + f'    2. Let |mode| be |options|["{{{{SynthOptions{idx}/mode}}}}"].\n'
            + f'    3. If |options|["{{{{SynthOptions{idx}/active}}}}"] is false, return a promise resolved with false.\n'
            + '    4. Let |tags| be an empty [=list=] populated from |options|["tags"].\n'
            + "    5. If |callback| is not null, invoke |callback| with |trimmed| and the size of |tags|.\n"
            + "    6. Queue a task on the [=internal scheduler=] for |mode| and resolve with true.\n"
            + "</div>\n\n"
            + f"The <dfn export constructor for='SynthController{idx}'>SynthController{idx}(options)</dfn> "
            + f"constructor initializes <dfn export attribute for='SynthController{idx}'>mode</dfn>, "
            + f"<dfn export attribute for='SynthController{idx}'>identifier</dfn>, "
            + f"<dfn export attribute for='SynthController{idx}'>ready</dfn>, and "
            + f"<dfn export attribute for='SynthObservable{idx}'>generation</dfn>. "
            + f"Calling <dfn export method for='SynthController{idx}'>reset()</dfn> restores defaults, "
            + f"while <dfn export method for='SynthUtils{idx}'>formatTag(raw)</dfn> normalizes a {{{{DOMString}}}}. "
            + f"Dictionary members <dfn export dict-member for='SynthOptions{idx}'>mode</dfn>, "
            + f"<dfn export dict-member for='SynthOptions{idx}'>active</dfn>, "
            + f"<dfn export dict-member for='SynthOptions{idx}'>label</dfn>, and "
            + f"<dfn export dict-member for='SynthOptions{idx}'>tags</dfn> accept "
            + f"{{{{SynthMode{idx}}}}} values <dfn export enum-value for='SynthMode{idx}'>\"eager\"</dfn>, "
            + f"<dfn export enum-value for='SynthMode{idx}'>\"lazy\"</dfn>, and "
            + f"<dfn export enum-value for='SynthMode{idx}'>\"balanced\"</dfn> "
            + f'(for example, {{{{SynthMode{idx}/"eager"}}}} or {{{{SynthOptions{idx}/label}}}}).\n\n'
            + f"<div class='example' id='example-idl-{idx}' heading='Using SynthController{idx}'>\n"
            + "    <pre highlight='js' line-numbers line-start='10' line-highlight='12-14'>\n"
            + f"    const ctrl = new SynthController{idx}({{\n"
            + f'        label: "unit-{idx}",\n'
            + '        mode: "eager",\n'
            + '        tags: ["alpha", "beta"],\n'
            + "    });\n"
            + f'    const ok = await ctrl.process(SynthUtils{idx}.formatTag("payload-{idx}"));\n'
            + "    if (ok && ctrl.ready) {\n"
            + "        ctrl.reset();\n"
            + "    }\n"
            + "    </pre>\n"
            + "</div>\n\n"
        )

    def algoChapter(self, idx: int) -> str:
        """Generate a chapter exercising algorithm containers, var hygiene, nested lists, and assertions."""
        self.emittedAlgo.append(idx)
        prevCall = ""
        if len(self.emittedAlgo) >= 2:
            prevIdx = self.emittedAlgo[-2]
            prevCall = f"    5. Delegate follow-up work to [$NormalizeSynthPayload{prevIdx}$] with |result|.\n"

        return (
            f"# Processing Algorithms {idx} # {{#algo-module-{idx}}}\n\n"
            + f"<h3 algorithm id='algo-dispatch-{idx}'>Dispatch Synthetic Task {idx}</h3>\n\n"
            + f"To run <dfn export abstract-op>DispatchSynthTask{idx}</dfn> given a [=synthetic context=] "
            + "|context| and a [=string=] |payload|, perform the following steps:\n\n"
            + "1. Assert: |context| is initialized and |payload| is non-empty.\n"
            + "2. Let |queue| be a new [=list=] associated with |context|.\n"
            + "3. Let |table| be a new [=map=] mapping keys to [=ordered set=] buckets.\n"
            + "4. For each |entry| of |queue|:\n"
            + "    1. Let |key| be the normalized identifier of |entry|.\n"
            + "    2. If |table|[|key|] does not exist:\n"
            + "        * Create a new [=struct=] describing |entry|.\n"
            + "        * Set |table|[|key|] to a new [=ordered set=] containing |entry|.\n"
            + "    3. Otherwise:\n"
            + "        * Append |entry| to |table|[|key|].\n"
            + "        * Notify the [=internal scheduler=] about |key|.\n"
            + "5. Let |result| be a summary [=string=] built from |payload| and |table|.\n"
            + "6. Record <var ignore>diagnosticTag</var> if tracing is active and return |result|.\n\n"
            + "<div algorithm>\n"
            + f"    To <dfn export abstract-op>NormalizeSynthPayload{idx}</dfn> given a [=string=] |raw|:\n\n"
            + "    1. Let |trimmed| be |raw| stripped of leading and trailing ASCII whitespace.\n"
            + "    2. Let |context| be the active [=synthetic context=].\n"
            + f"    3. Let |result| be the return value of [$DispatchSynthTask{idx}$] with |context| and |trimmed|.\n"
            + "    4. Return |result| after updating the [=processing pipeline=].\n"
            + prevCall
            + "</div>\n\n"
            + f"<div algorithm='validate synthetic state {idx}'>\n"
            + f"    To verify invariant state for module {idx} given a [=list=] |items|:\n\n"
            + "    1. Let |seen| be an empty [=ordered set=].\n"
            + "    2. For each |item| of |items|:\n"
            + "        1. If |seen| contains |item|, continue.\n"
            + "        2. Append |item| to |seen|.\n"
            + "    3. Return the size of |seen|.\n"
            + "</div>\n\n"
            + f"<p class='assertion'>Calling [$NormalizeSynthPayload{idx}$] twice on identical input "
            + "must yield equivalent [=render nodes=].</p>\n\n"
            + "Key terms for this stage:\n\n"
            + f": <dfn noexport>pipeline ticket {idx}</dfn>\n"
            + f":: An opaque handle tracked by [$DispatchSynthTask{idx}$] and [=processing pipeline=].\n"
            + f": <dfn noexport>pipeline barrier {idx}</dfn>\n"
            + f":: A synchronization point joining each [=pipeline ticket {idx}=] before commit.\n\n"
            + f"Every [=pipeline barrier {idx}=] waits for all active [=pipeline ticket {idx}=] entries.\n\n"
            + "---\n\n"
        )

    def markupChapter(self, idx: int) -> str:
        """Generate a chapter exercising elementdefs, markup/HTTP autolinks, tables, figures, and HTML highlighting."""
        self.emittedMarkup.append(idx)
        domIface = f"SynthController{self.emittedIdl[-1]}" if self.emittedIdl else "Element"
        return (
            f"# Markup and Transport Module {idx} # {{#markup-module-{idx}}}\n\n"
            + "This module defines custom markup elements, attributes, and HTTP headers "
            + "for [=synthetic context=] integration.\n\n"
            + "<pre class='elementdef'>\n"
            + f"Name: synth-widget-{idx}\n"
            + "Categories: flow content\n"
            + "Contexts: Where [=flow content=] is expected.\n"
            + "Content Model: Transparent, containing <{div}> and <{span}> descendants.\n"
            + "Attributes: state, priority\n"
            + f"Attribute Groups: synth-common-{idx} attributes\n"
            + f"DOM Interfaces: {domIface}\n"
            + "</pre>\n\n"
            + f"<dl dfn-type='element-attr' dfn-for='synth-widget-{idx}'>\n"
            + "    : <dfn export>state</dfn>\n"
            + f"    :: Controls lifecycle state: <dfn export attr-value for='synth-widget-{idx}/state'>idle</dfn> "
            + f"or <dfn export attr-value for='synth-widget-{idx}/state'>busy</dfn>.\n"
            + "    : <dfn export>priority</dfn>\n"
            + "    :: Hints scheduling order for the [=internal scheduler=].\n"
            + "</dl>\n\n"
            + f"The <dfn export>synth-common-{idx} attributes</dfn> group contains:\n\n"
            + f"<ul dfn-type='element-attr' dfn-for='synth-common-{idx} attributes'>\n"
            + f"    * <dfn export>synth-role-{idx}</dfn>\n"
            + f"    * <dfn export>synth-level-{idx}</dfn>\n"
            + "</ul>\n\n"
            + f"Servers can send the <dfn export http-header>Synth-Policy-{idx}</dfn> HTTP header alongside "
            + f"[:X-Content-Type-Options:] when serving documents containing <{{synth-widget-{idx}}}> elements with "
            + f"<{{synth-widget-{idx}/state}}> set to <{{synth-widget-{idx}/state/idle}}> or "
            + f"<{{synth-widget-{idx}/state/busy}}>. Script tags (<{{script}}>) observe [:Synth-Policy-{idx}:] "
            + f"and <{{synth-widget-{idx}/priority}}>.\n\n"
            + "<figure>\n"
            + "    <table class='data synth-table'>\n"
            + f"        <caption>Module {idx} State Matrix</caption>\n"
            + "        <thead>\n"
            + "            <tr><th>Attribute</th><th>Token</th><th colspan='2'>Behavior &amp; Notes</th></tr>\n"
            + "        </thead>\n"
            + "        <tbody>\n"
            + "            <tr>\n"
            + f"                <td><{{synth-widget-{idx}/state}}></td>\n"
            + f"                <td><{{synth-widget-{idx}/state/idle}}></td>\n"
            + "                <td>Deferred</td>\n"
            + "                <td>Waits for [=internal scheduler=] &mdash; low overhead</td>\n"
            + "            </tr>\n"
            + "            <tr>\n"
            + f"                <td><{{synth-widget-{idx}/state}}></td>\n"
            + f"                <td><{{synth-widget-{idx}/state/busy}}></td>\n"
            + "                <td>Immediate</td>\n"
            + "                <td>Flushes [=processing pipeline=] &#x2192; active commit</td>\n"
            + "            </tr>\n"
            + "        </tbody>\n"
            + "    </table>\n"
            + f"    <img src='https://example.com/synth-diagram-{idx}.svg' width='480' height='240' "
            + f"alt='Synthetic widget {idx} lifecycle diagram'>\n"
            + f"    <figcaption>State transitions for <{{synth-widget-{idx}}}>.</figcaption>\n"
            + "</figure>\n\n"
            + f"<div class='example' id='example-html-{idx}' heading='Declarative Markup {idx}'>\n"
            + "    <xmp highlight='html'>\n"
            + '    <div class="host">\n'
            + f'        <synth-widget-{idx} state="idle" priority="high" synth-role="region">\n'
            + f"            <span>Synthetic payload {idx}</span>\n"
            + f"        </synth-widget-{idx}>\n"
            + "    </div>\n"
            + "    </xmp>\n"
            + "</div>\n\n"
        )

    def cddlChapter(self, idx: int) -> str:
        """Generate a chapter exercising CDDL schemas, CDDL autolinks, and JSON/Python highlighting."""
        self.emittedCddl.append(idx)
        return (
            f"# Wire Protocol Schema {idx} # {{#cddl-module-{idx}}}\n\n"
            + f"The <dfn export cddl-type>synth-frame-{idx}</dfn> CDDL map defines the wire envelope "
            + f"with members <dfn export cddl-key for='synth-frame-{idx}'>kind</dfn> and "
            + f"<dfn export cddl-key for='synth-frame-{idx}'>payload</dfn>. "
            + f"The <dfn export cddl-type>synth-kind-{idx}</dfn> choice includes "
            + f"<dfn export cddl-value for='synth-kind-{idx}'>\"data\"</dfn> and "
            + f"<dfn export cddl-value for='synth-kind-{idx}'>\"ack\"</dfn>.\n\n"
            + "<xmp class='cddl'>\n"
            + f"synth-frame-{idx} = {{\n"
            + f"    kind: synth-kind-{idx},\n"
            + "    payload: bstr / tstr,\n"
            + f"    ? meta: synth-meta-{idx},\n"
            + f"    ? retries: synth-retry-{idx},\n"
            + "    * tstr => any,\n"
            + "}\n\n"
            + f'synth-kind-{idx} = "data" / "ack"\n'
            + f'synth-kind-{idx} /= "ping"\n\n'
            + f"synth-meta-{idx} = (\n"
            + "    sequence: uint,\n"
            + "    timestamp: float,\n"
            + "    urgent: bool,\n"
            + ")\n\n"
            + f"synth-retry-{idx} = 0..16 ; bounded retry budget\n"
            + f"synth-batch-{idx} = [+ synth-frame-{idx}]\n"
            + "</xmp>\n\n"
            + f"Implementations serializing {{^synth-frame-{idx}^}} populate {{^synth-frame-{idx}/kind^}} "
            + f'with {{^synth-kind-{idx}/"data"^}} or {{^synth-kind-{idx}/"ack"^}} and attach '
            + f"{{^synth-frame-{idx}/payload^}}.\n\n"
            + f"<div class='example' id='example-cddl-{idx}' heading='Wire Payload {idx}'>\n"
            + "    <pre highlight='json' line-numbers>\n"
            + "    {\n"
            + '        "kind": "data",\n'
            + f'        "payload": "frame-{idx}",\n'
            + f'        "sequence": {idx + 1},\n'
            + '        "urgent": false\n'
            + "    }\n"
            + "    </pre>\n\n"
            + "    <pre highlight='python'>\n"
            + f"    def encode_frame_{idx}(payload: str) -> dict[str, object]:\n"
            + f'        return {{"kind": "data", "payload": payload, "seq": {idx}}}\n'
            + "    </pre>\n"
            + "</div>\n\n"
        )

    def integrationChapter(self, idx: int) -> str:
        """Generate a chapter with cross-module links, inline highlighting, tracking vectors, and WPT blocks."""
        wptA = self.wptTests[(idx * 3) % len(self.wptTests)]
        wptB = self.wptTests[(idx * 3 + 1) % len(self.wptTests)]
        wptC = self.wptTests[(idx * 3 + 2) % len(self.wptTests)]

        crossRefs: list[str] = []
        if self.emittedCss:
            c = self.emittedCss[-1]
            crossRefs.append(
                f"CSS property 'synth-layout-{c}' (value ''synth-layout-{c}/compact''), "
                + f"shorthand 'synth-box-{c}', and production <<synth-token-{c}>> (see [[#css-module-{c}]])",
            )
        if self.emittedGrammar:
            g = self.emittedGrammar[-1]
            crossRefs.append(
                f"at-rule ''@synth-rule-{g}'' and descriptor '@synth-rule-{g}/synth-src-{g}' "
                + f"(see [[#grammar-module-{g}]])",
            )
        if self.emittedIdl:
            d = self.emittedIdl[-1]
            crossRefs.append(
                f"interface {{{{SynthController{d}}}}}, method {{{{SynthController{d}/process()}}}}, "
                + f"and member {{{{SynthOptions{d}/active}}}} (see [[#idl-module-{d}]])",
            )
        if self.emittedAlgo:
            a = self.emittedAlgo[-1]
            crossRefs.append(
                f"abstract operations [$DispatchSynthTask{a}$] and [$NormalizeSynthPayload{a}$] "
                + f"(see [[#algo-module-{a}]])",
            )
        if self.emittedMarkup:
            mk = self.emittedMarkup[-1]
            crossRefs.append(
                f"element <{{synth-widget-{mk}}}>, attribute <{{synth-widget-{mk}/state}}>, "
                + f"and header [:Synth-Policy-{mk}:] (see [[#markup-module-{mk}]])",
            )
        if self.emittedCddl:
            cd = self.emittedCddl[-1]
            crossRefs.append(
                f"CDDL envelope {{^synth-frame-{cd}^}} and member {{^synth-frame-{cd}/kind^}} "
                + f"(see [[#cddl-module-{cd}]])",
            )

        summaryBullets = "\n".join(f"* {ref}." for ref in crossRefs) if crossRefs else "* Core [=synthetic context=]."

        return (
            f"# Integration and Testing {idx} # {{#integration-module-{idx}}}\n\n"
            + f"## Processing Model ## {{#integration-processing-{idx}}}\n\n"
            + f"Integration pass {idx} coordinates [=synthetic context=], [=processing pipeline=], "
            + "and [=render nodes=] across subsystems. Repeated references to [=synthetic context=] "
            + "and [=processing pipeline=] in the same paragraph exercise multiple-link deduplication.\n\n"
            + summaryBullets
            + "\n\n"
            + f"## Examples ## {{#integration-examples-{idx}}}\n\n"
            + f"Inline highlighted snippets such as <code highlight='js'>const v{idx} = {idx} * 2;</code> "
            + "and <code highlight='css'>display: flex; color: canvasText;</code> work inside prose.\n\n"
            + f"## Performance Notes ## {{#integration-perf-{idx}}}\n\n"
            + "<p tracking-vector>Exposing fine-grained timing counters from module "
            + f"{idx} can increase cross-origin fingerprinting surface if not coarsened.</p>\n\n"
            + f"<wpt title='Core tests for integration module {idx}'>\n"
            + f"{wptA}\n"
            + f"{wptB}\n"
            + "</wpt>\n"
            + "<wpt>\n"
            + f"{wptC}\n"
            + "</wpt>\n\n"
        )

    def fillerParagraph(self, fillerIdx: int) -> str:
        """Generate a short cross-referenced conformance paragraph to fine-tune the final document size."""
        refs = [
            "[=synthetic context=]",
            "[=processing pipeline=]",
            "[=internal scheduler=]",
            "[=render nodes=]",
        ]
        if self.emittedCss:
            c = self.emittedCss[fillerIdx % len(self.emittedCss)]
            refs.append(f"'synth-layout-{c}'")
        if self.emittedIdl:
            d = self.emittedIdl[fillerIdx % len(self.emittedIdl)]
            refs.append(f"{{{{SynthController{d}}}}}")
        if self.emittedAlgo:
            a = self.emittedAlgo[fillerIdx % len(self.emittedAlgo)]
            refs.append(f"[$DispatchSynthTask{a}$]")
        if self.emittedMarkup:
            mk = self.emittedMarkup[fillerIdx % len(self.emittedMarkup)]
            refs.append(f"<{{synth-widget-{mk}}}>")
        if self.emittedCddl:
            cd = self.emittedCddl[fillerIdx % len(self.emittedCddl)]
            refs.append(f"{{^synth-frame-{cd}^}}")

        joined = ", ".join(refs)
        return (
            f"Supplemental conformance clause {fillerIdx}: conforming implementations must preserve "
            + f"invariants across {joined}, maintaining *deterministic* **ordering** with "
            + f"`clause-{fillerIdx}` tokens and [[#intro]] references.\n\n"
        )

    def epilogue(self) -> str:
        """Return the Privacy, Security, and Conformance closing sections."""
        return (
            "# Privacy Considerations # {#privacy}\n\n"
            + "<p tracking-vector>Synthetic telemetry exposed by [=synthetic context=] "
            + "and [=processing pipeline=] can leak device capability signals unless bounded.</p>\n\n"
            + "# Security Considerations # {#security}\n\n"
            + "<p class='advisement'>Implementations must isolate [=synthetic context=] state "
            + "across origins to prevent cross-site information disclosure.</p>\n\n"
            + "# Conformance # {#conformance}\n\n"
            + "Document conventions follow [[!RFC2119]] and [[!INFRA]]. "
            + "All normative requirements in this specification apply to conforming user agents.\n"
        )

    def build(self, targetBytes: int) -> str:
        """Build the complete synthetic spec source string sized approximately to targetBytes."""
        compact = targetBytes < 6144
        parts: list[str] = [self.preamble(compact=compact)]
        epilogueText = self.epilogue()
        epilogueBytes = len(epilogueText.encode("utf-8"))
        currentBytes = len(parts[0].encode("utf-8"))

        generators = (
            self.cssChapter,
            self.grammarChapter,
            self.idlChapter,
            self.algoChapter,
            self.markupChapter,
            self.cddlChapter,
            self.integrationChapter,
        )
        counters = [0] * len(generators)
        step = 0

        # Reserve space for epilogue and generate chapters until approaching targetBytes.
        while currentBytes + epilogueBytes < targetBytes:
            remaining = targetBytes - currentBytes - epilogueBytes
            arch = step % len(generators)
            chunk = generators[arch](counters[arch])
            chunkBytes = len(chunk.encode("utf-8"))

            # If adding a full chapter would overshoot significantly and we already have
            # at least one chapter (or compact mode), switch to fine-grained filler paragraphs.
            if chunkBytes > remaining * 1.35 and (step > 0 or compact):
                self.rollbackArchetype(arch)
                break

            parts.append(chunk)
            currentBytes += chunkBytes
            counters[arch] += 1
            step += 1

        # Top up remaining budget with fine-grained conformance paragraphs for tight size accuracy.
        fillerIdx = 0
        if currentBytes + epilogueBytes < targetBytes:
            header = "# Supplemental Conformance Notes # {#supplemental-conformance}\n\n"
            headerBytes = len(header.encode("utf-8"))
            if currentBytes + epilogueBytes + headerBytes < targetBytes:
                parts.append(header)
                currentBytes += headerBytes
                while currentBytes + epilogueBytes < targetBytes:
                    para = self.fillerParagraph(fillerIdx)
                    paraBytes = len(para.encode("utf-8"))
                    if currentBytes + epilogueBytes + paraBytes - targetBytes > paraBytes // 2 and fillerIdx > 0:
                        break
                    parts.append(para)
                    currentBytes += paraBytes
                    fillerIdx += 1

        parts.append(epilogueText)
        return "".join(parts)

    def rollbackArchetype(self, arch: int) -> None:
        """Pop the last recorded module index when a generated chapter is discarded for size."""
        lists = (
            self.emittedCss,
            self.emittedGrammar,
            self.emittedIdl,
            self.emittedAlgo,
            self.emittedMarkup,
            self.emittedCddl,
            None,
        )
        targetList = lists[arch]
        if targetList is not None and targetList:
            targetList.pop()


def generateSyntheticSpec(
    targetBytes: int,
    *,
    fileRequester: retrieve.DataFileRequester | None = None,
) -> str:
    """Generate a deterministic, self-contained synthetic Bikeshed spec of approximately targetBytes."""
    if targetBytes <= 0:
        msg = f"targetBytes must be positive; got {targetBytes}."
        raise ValueError(msg)
    dataFile = fileRequester or retrieve.defaultRequester
    builder = SyntheticSpecBuilder(dataFile)
    return builder.build(targetBytes)

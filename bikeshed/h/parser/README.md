# Bikeshed HTML / Markdown / Shorthand Parser (`bikeshed/h/parser`)

This package implements Bikeshed's unified single-pass parser, turning raw spec source text (block-level Markdown, inline Markdown, HTML, Bikeshed autolinks/shorthands, and text macros) into `ParserNode`s and then into an LXML DOM tree.

## Module Overview

- [`main.py`](main.py) — Top-level public entrypoints (`initialDocumentParse`, `nodesFromHtml`, `parseText`, `parseTitle`, `parseLines`, `strFromNodes`, `linesFromNodes`, `debugNodes`).
- [`blocks.py`](blocks.py) — Block-level Markdown parser (`parseBlockStream`, `parseBlocks`, `parseList`, `parseBlockquote`, `parseBlockBsMacro`, `parseParagraph`) and `IndentChecker`.
- [`parser.py`](parser.py) — Core inline stream driver (`parseInlineNodes`, `_parseRawHtmlNodes`, `nodesFromStream`, `parseAnything`, `generateResults`, `generateExperimentalNodes`), top-level syntax dispatchers (`parseNode`, `parseAngleStart`, `parseLToEnd`, `parseBsMacro`), and `closeOpenElements`.
- [`html.py`](html.py) — HTML lexical and tag-level parsing: tags, attributes, Bikeshed attribute shortcut canonicalization, character references, whitespace, comments, doctypes, raw-text elements (`<script>`, `<style>`, `<xmp>`, `<title>`, datablock `<pre>`), `<bs-macro>` balanced body scanning, datablocks, and metadata blocks.
- [`autolinks.py`](autolinks.py) — Non-CSS Bikeshed autolinks and shorthands (`[=dfn=]`, `[$abstract$]`, `[:Header:]`, `{{idl}}`, `{^cddl^}`, `<{element}>`, `|var|`, `[[biblio]]` / `[[#section]]`, `<#123>` / `<org/repo#123>`), plus shared `LinkData`, `parseLinkInfo`, and `parseLinkText`.
- [`css.py`](css.py) — CSS autolink shorthands (`<<production>>`, `''maybe''` declarations/values, `'propdesc'`) and `.prod` production grammar symbol links (`parseCSSProductionGrammar()`, `parseCSSProductionGrammarInText()`).
- [`markdown.py`](markdown.py) — Inline Markdown constructs and fenced code blocks (CommonMark `*`/`**` emphasis via `parseEmphasisRun()` and `resolveEmphasis()`, backtick code spans, fenced code blocks, `[text](dest "title")` links, backslash escapes).
- [`macros.py`](macros.py) — `[MACRO]` / `[MACRO?]` and `<bs-macro>` lookup and expansion in node, block, attribute-list, and plain-text contexts.
- [`nodes.py`](nodes.py) — `ParserNode` AST types (`RawText`, `EmphDelim`, `SafeText`, `StartTag`, `EndTag`, `SelfClosedTag`, `Comment`, `Doctype`, `RawElement`, `SafeElement`), HTML/attribute escaping, and `TagStack`.
- [`stream.py`](stream.py) — `ParseConfig` and `Stream` (character buffer, O(log N) line/column mapping, `subStream`, and open-element delegation).
- [`treebuilder.py`](treebuilder.py) — LXML SAX `TreeBuilder` (`buildDocument`, `buildFragment`, `consumeNodes`).
- [`preds.py`](preds.py) — Character classification predicates, SVG/MathML tag table, and HTML named character reference table.
- [`result.py`](result.py) — Lightweight `(value, next_index, is_error)` result tuple helpers (`Ok`, `Err`, `isOk`, `isErr`).

### Module Dependency Order

The parser modules form an acyclic dependency graph (recursive inline sub-parsers accept `generateResults` / `generateExperimentalNodes` / `nodesFromStream` callbacks rather than importing `parser.py`):

```text
result, preds
  └─> nodes <──(TYPE_CHECKING)──> stream
        └─> macros
              └─> html
                    ├─> markdown
                    └─> autolinks
                          └─> css
                                └─> parser (also imports html, macros, markdown, autolinks)
                                      └─> blocks
                                            └─> main
```

---

## Parsing Flow

### 1. Entry & Setup (`Spec.py`, `main.py`, `stream.py`)

1. `Spec.assembleDocument()` extracts metadata first (`initMetadata()` → `extractMetadata()`), creates an optional `IndentChecker`, and invokes **`initialDocumentParse()`** with the extracted `metadataSpans`.
2. **`ParseConfig.fromSpec()`** builds the configuration snapshot (enabled shorthand/Markdown flags, macros, indent width, block/opaque element sets).
3. **`Stream(...)`** wraps the input text, pre-indexes newline offsets (`_lineBreaks` for O(log N) `line()`/`col()`/`loc()` lookups), and initializes a **`TagStack`** (`s.openEls`) for tracking open elements and opacity.
4. Fragment callers (`h.parseHTML()`, `includes.py`, `boilerplate.py`, `datablocks.py`, metadata helpers) enter through **`nodesFromHtml()`**, **`parseText()`**, **`parseTitle()`**, or **`parseLines()`** instead, optionally enabling `blockMarkdown=True` or `rawHtml=True`.

### 2. Block-Level Pass (`blocks.py`)

When `config.markdownBlock` is enabled, `initialDocumentParse()` runs **`parseBlockStream()` → `parseBlocks()`** (when disabled, it skips directly to inline **`nodesFromStream()`**).

`parseBlocks()` scans the stream line by line while tracking indentation frames (`minIndent`, `ListStop`), paragraph eligibility (`canStartParagraph`), and optional `IndentChecker.checkLine()`:

1. **Opaque element passthrough**: If `s.inOpaqueElement()` is true (e.g. inside an unclosed `<pre>`, `<xmp>`, or `bs-opaque` element), block Markdown is skipped and the line goes straight to **`parseInlineNodes(..., stopAtNewline=True)`**.
2. **Blank lines & standalone comments/doctypes**: Blank lines either terminate an active list (`blankEndsList()`) or set `canStartParagraph = True`. Standalone `<!-- ... -->` and `<!doctype ...>` lines are skipped (`trySkipCommentOrDoctypeAt()`).
3. **Raw Markdown block openers** (`matchRawBlockStart()`):
   - `#` ATX heading → `parseInlineNodes()` for heading content → **`buildSingleLineHeading()`**.
   - `***` / `---` horizontal rule → `SelfClosedTag("hr")`.
   - `*` / `1.` / `:` / `::` list item → **`parseList()`**, which inspects `s.openEls` (`matchHtmlListParent()`) to merge directly into an enclosing matching HTML `<ul>`/`<ol>`/`<dl>` (or `<dl> > <div>`) when present, otherwise opens a synthetic container pushed onto `s.openEls` as a `TagStackSyntheticEntry`, emits `<li>`/`<dt>`/`<dd>` (also supporting interleaved HTML list items via `parseHtmlListItem()`), and recurses into **`parseBlocks()`** with `minIndent = baseIndent + 1`, `minTagDepth = len(s.openEls.tags)`, `firstLineTrimmed=True`, and a chained `ListStop`.
   - `>` blockquote → **`parseBlockquote()`**, which collects consecutive `>` lines (plus CommonMark §5.1 lazy continuations via `bqLineAllowsLazyContinuation()` / `matchFenceAt()`), strips prefixes while recording per-line `colOffsets`, and recurses into **`parseBlocks()`** on a child `Stream` sharing `s.openEls`.
4. **Block-level `<bs-macro>`** (`parseBlockBsMacro()`): Expands `<bs-macro name="...">fallback</bs-macro>` (always requiring a closing tag) in block Markdown mode via `parseBlocks()` sharing `s.openEls` (supporting HTML/Markdown list merging and direct-child checks, with optional fallback content parsed only when the macro is absent/empty).
5. **Everything else (HTML, paragraphs, Setext headings)**:
   - Parses one logical line via **`parseInlineNodes(..., stopAtNewline=True)`**.
   - Empty results (stripped `<pre class=metadata>` blocks or empty optional macros) behave like blank lines; block-level HTML tags (`not isInlineStart()`) are emitted directly.
   - Inline text checks **`peekSetextUnderline()`** (`===` / `---` → **`buildMultiLineHeading()`**); otherwise, if `canStartParagraph` is true, enters **`parseParagraph()`**.
   - **`parseParagraph()`** handles admonition prefixes (`Note:`, `Issue:`, `Assert:`, `Advisement:`) and consumes continuation lines via **`parseInlineNodes(..., stopAtNewline=True)`** until a blank line, list exit, raw block opener, or block HTML line (handing any already-parsed non-paragraph line back as a `PendingLine` so `parseBlocks()` does not re-parse it).

### 3. Inline Parsing Loop (`parser.py`, `nodes.py`)

Both `parseBlocks()` (with `stopAtNewline=True`) and `nodesFromStream()` (whole stream) call **`parseInlineNodes()`** (which delegates immediately to **`_parseRawHtmlNodes()`** when `config.rawHtml` is true).

`parseInlineNodes()` jumps between `ACTUAL_NODE_START_CHARS` (`& < > \` ' ~ [ { | \ — -`):

- Contiguous plain text is accumulated via `textStart`, dedented after newlines when `minIndent > 0` (`_stripIndentAfterNewlines()`), curlified (`RawText.curlifyApostrophes()`), and merged into adjacent `RawText` nodes whenever their emitted newlines match their source line span.
- At each candidate start character, it invokes **`parseNode()`**:
  - **`s.observeResult()`** updates `s.openEls` (`TagStack.update()` in `nodes.py`) for every emitted node, maintaining O(1) opacity/tag counters (`_opaqueCount`, `_tagCounts`), checking required ancestor contexts (`verifyTagContext()`), and applying HTML auto-closing rules (`autoCloseStart()` / `autoCloseEnd()`).
  - Macro expansions (identified because their nodes belong to a child `Stream`) are forwarded to `onMacroNodes` (`IndentChecker.checkMacroNodes()`).

### 4. Syntax Dispatch from `parseNode()`

`parseNode()` dispatches based on the leading 1–3 characters, `ParseConfig` flags, and `inOpaque` / `inA` / `inDfn` state:

- **`--` / `—` at EOL**: Em-dash + zero-width space (`emdashRe`).
- **`&`**: **`html.parseCharRef()`** — HTML named/numeric character references and `&bs...;` Bikeshed escapes.
- **`<`**: **`parseAngleStart()`**:
  - `<!` → `html.parseDoctype()` / `html.parseComment()`.
  - `</` → `html.parseEndTag()`.
  - `<tag...` → **`html.parseStartTag()`** (`parseTagName()` → `parseAttributeList()` → `canonicalizeShortcuts()`; also delegates `<org/` to `autolinks.parseRepositoryLink()`).
    - Special elements consume their bodies immediately: `<l>` → **`parseLToEnd()`** (dispatches any autolink + `</l>`), `<bs-macro>` → **`parseBsMacro()`** (reads balanced body via `html.parseBsMacroToEnd()`, resolves macro or fallback via `macros.resolveBsMacro()`, and parses via `s.blockParser` when `markdownBlock` is enabled), `<title>` → `html.parseTitleToEnd()`, `<pre/xmp class=metadata>` → `html.parseMetadataBlockToEnd()` (stripped from output), datablock `<pre>` → `html.parseDatablockPreToEnd()`, and `<script>`/`<style>`/`<xmp>` → `html.parseScriptToEnd()`/`parseStyleToEnd()`/`parseXmpToEnd()` (with optional `bs-macros` expansion via `macros.replaceMacrosInText()`).
  - Fallback `<#123>` → `autolinks.parseRepositoryLink()`; `<<` and `<{` fall through to CSS/markup shorthands below; any other unrecognized `<` is emitted as escaped `SafeText`.
- **`` ` `` / `~`**: **`markdown.parseFencedCodeBlock()`** and **`markdown.parseCodeSpan()`**.
- **`''` / `'` / `<<` / `.prod` grammar symbols**: **`css.parseCSSMaybe()`** (`parseMaybeDecl()` / `parseMaybeValue()`), **`css.parseCSSPropdesc()`**, **`css.parseCSSProduction()`**, and (when `css` is enabled inside `<pre class=prod>`, `<xmp class=prod>`, ```` ```prod ````, or `propdef`/`descdef` `Value` cells via `ParseConfig.inProd`) **`css.parseCSSProductionGrammar()`** / **`css.parseCSSProductionGrammarInText()`**.
- **`[=` / `[$` / `[:` / `{{` / `{^` / `<{` / `|` / `[[`**: **`autolinks.parseAutolink*()`** and **`parseShorthandVariable()`** — target data is parsed with `parseLinkInfo()`, and optional `|custom text` is parsed with `parseLinkText()`.
- **`[text](url)` / `*` / `\`**: **`markdown.parseMarkdownLink()`**, **`markdown.parseEmphasisRun()`** (emits `EmphDelim` runs resolved per HTML element scope by **`markdown.resolveEmphasis()`** at the end of `parseBlockStream()` / `parseInlineNodes()`), and **`markdown.isMarkdownEscape()`** / `htmlifyMarkdownEscapes()`.
- **`[MACRO]`**: **`macros.parseMacroToNodes()`** — resolves the macro into a child `Stream` and recurses via `nodesFromStream()` (similarly, `html.parseAttributeList()` calls `macros.parseMacroToAttrs()`, and `html.parseTitleToEnd()` calls `macros.parseMacroToText()`).

#### Recursive Inline Sub-Parsing

Four constructs can contain arbitrary nested inline markup:

- `autolinks.parseLinkText()` (explicit `|linktext` in autolinks and `''prop: val''` declarations) iterates **`generateResults()`** → **`parseAnything()`** → **`parseNode()`**, scoped on `TagStack` via `observeShorthandOpen()` / `observeShorthandClose()`.
- `css.parseMaybeValue()` and `markdown.parseMarkdownLink()` perform speculative lookahead via **`generateExperimentalNodes()`** (`generateResults(..., experimental=True)`), committing parsed nodes to `TagStack` only once the closing delimiter (`''` or `](`) is found.
- `macros.parseMacroToNodes()` recurses via **`nodesFromStream()`** on a `subStream` (depth-limited to 10 to guard against recursive macros).

### 5. Closing Open Elements & Tree Building (`parser.py`, `treebuilder.py`)

1. At the end of `initialDocumentParse()`, **`closeOpenElements()`** pops any tags still on `s.openEls` (silently closing a trailing `<p>`, logging errors for anything else) and appends synthetic `EndTag` nodes.
2. Back in `Spec.assembleDocument()`, `boilerplate.addHeaderFooter()` prepends and appends parsed header/footer `ParserNode`s to `self.nodes`.
3. **`buildDocument(self.nodes)`** (or **`buildFragment()`** for subtrees) creates a **`TreeBuilder`**, runs **`consumeNodes()`** to stream each `ParserNode` into `lxml.sax.ElementTreeContentHandler` (via `prepareAttrs()`, `unescapeHtml()`, and `startTag()`/`endTag()`/`characters()` with HTML `<head>`/`<body>` placement and auto-closing), and **`TreeBuilder.finish()`** merges deferred `<html>`/`<head>`/`<body>` attributes and returns `(document, head, body)`.

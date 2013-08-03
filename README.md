css-preprocessor
================

This project is a pre-processor for the source documents the CSSWG produces their specs from.
We write our specs in HTML, but rely on a preprocessor for a lot of niceties, 
like automatically generating a bibliography and table of contents,
or automatically linking terms to their definitions.
Specs also come with a lot of boilerplate repeated on every document,
which we omit from our source document.

A short overview of my preprocessor's features:

* [automatic linking](docs/definitions-autolinks.md) of terms to their definitions based on text, so you can simple write `Use <a>some term</a> to...` and have it automatically link to the `<dfn>some term</dfn>` elsewhere in the document, or in another spec entirely!
* [automatic id generation](docs/markup.md) for headings and definitions, based on their text.
* [textual shortcuts for autolinks](docs/definition-autolinks.md): [[FOO]] for bibliography entries, &lt;&lt;foo>> for grammar productions, 'foo' for property names, and ''foo'' for values.
* [boilerplate generation](docs/boilerplate.md), both wholesale and piecemeal.
* [markdown-style paragraphs](docs/markup.md).
* a [compact syntax](docs/markup.md) for writing property-definition tables.
* [automatic whitespace-prefix stripping](docs/markup.md) from `<pre>` contents, so the contents can be indented properly in your HTML.

Examples of all of the functionality described here can be found by looking at the source of the [CSS Variables source document](http://dev.w3.org/csswg/css-variables/Overview.src.html)

Documentation Sections
----------------------

* [Quick Start Guide](docs/quick-start.md) - gets you from an empty file to a full spec in no time.
* [Metadata](docs/metadata.md) - describes the format of the required metadata block in your spec.
* [Definitions, Autolinks, and Bibliography](docs/definitions-autolinks.md) - describes how to create definitions, autolinks, and bibliography entries.
* [Markup](docs/markup.md) - describes several of the markup niceties and shortcuts over plain HTML that the processor recognizes.
* [Boilerplate](docs/boilerplate.md) - describes the use and generation of a spec's boilerplate sections. You probably don't need to read this.
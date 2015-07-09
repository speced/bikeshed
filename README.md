Bikeshed, a spec preprocessor
=============================

<img src="https://rawgit.com/tabatkins/bikeshed/master/docs/icon.svg" width=100 height=100 align=left>

Bikeshed is a pre-processor for spec documents,
turning a source document
(containing only the actual spec content, plus several shorthands for linking to terms and other things)
into a final spec document,
with appropriate boilerplate, bibliography, indexes, etc all filled in.
It's currently used on nearly all specs in the CSSWG,
as well as various specs in the FXTF, SVGWG, WebAppSecurity, WHATWG, and elsewhere!

[![Build Status](https://travis-ci.org/tabatkins/bikeshed.svg?branch=master)](https://travis-ci.org/tabatkins/bikeshed)
[![Gitter](https://img.shields.io/badge/Gitter-Join%20Chat%20↣-blue.svg)](https://gitter.im/tabatkins/bikeshed?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge)

The processor can be easily installed and run locally (requiring no network access unless you're updating),
or accessed as a CGI without any installation at all: <https://api.csswg.org/bikeshed/>

A short overview of some of Bikeshed's features:

* [automatic linking](docs/definitions-autolinks.md) of terms to their definitions based on text, so you can simple write `Use <a>some term</a> to...` and have it automatically link to the `<dfn>some term</dfn>` elsewhere in the document, or in another spec entirely!
* [automatic id generation](docs/markup.md) for headings and definitions, based on their text.
* [textual shortcuts for autolinks](docs/definitions-autolinks.md): [[FOO]] for bibliography entries, &lt;&lt;foo>> for grammar productions, 'foo' for CSS property names, {{foo}} for IDL terms, and more.
* [boilerplate generation](docs/boilerplate.md), both wholesale and piecemeal.
* [partial support for markdown](docs/markup.md) (more is coming, as is compliance with [CommonMark](http://commonmark.org)).
* a [compact syntax](docs/markup.md) for writing property-definition tables.
* [automatic whitespace-prefix stripping](docs/markup.md) from `<pre>` contents, so the contents can be indented properly in your HTML.
* [automatic IDL processing and syntax-checking](docs/idl.md) for `<pre class=idl>` contents, so you don't have to mark up every single significant term yourself.
* [automatic generation of railroad diagrams](docs/railroad-diagrams.md) from `<pre class='railroad'>` contents.

Note About Fatal Errors
-----------------------

Bikeshed generates "fatal errors" for lots of things that it wants you to fix,
but generally recovers gracefully from them anyway.
If you're getting a fatal error,
but don't have time to fix it and just need a spec **right now**,
you can force Bikeshed to generate anyway with the `-f` flag, like: `bikeshed -f spec`.

This is also sometimes useful when converting a spec to Bikeshed for the first time,
so you can see all the errors at once and fix them in whatever order is easiest,
rather than having to deal with them one-by-one with no idea when they'll end.
(You may also want to silence the warnings in this case,
to reduce visual noise until you've gotten it at least building successfully.
Use `bikeshed -qf spec`.)

Documentation Sections
----------------------

* [Installing Bikeshed](docs/install.md) - gets you from "reading this page" to "running Bikeshed" in as few steps as possible.
* [Quick Start Guide](docs/quick-start.md) - gets you from an empty file to a full spec in no time.
* [Metadata](docs/metadata.md) - describes the format of the required metadata block in your spec.
* [Definitions, Autolinks, and Bibliography](docs/definitions-autolinks.md) - describes how to create definitions, autolinks, and bibliography entries.
* [Markup](docs/markup.md) - describes several of the markup niceties and shortcuts over plain HTML that the processor recognizes.
* [Global Names](docs/global-names.md) - describes the concept and syntax of global names, which are used by several features to uniquely identify and refer to defined terms.
* [IDL](docs/idl.md) - describes Bikeshed's automatic IDL processing.
* [Railroad Diagrams](docs/railroad-diagrams.md) - describes the railroad-diagram feature, and its syntax.
* [Boilerplate](docs/boilerplate.md) - describes the use and generation of a spec's boilerplate sections. You probably don't need to read this.
* [Source-File Processing](docs/source.md) - describes the functions Bikeshed has for processing your *source file itself*.
* [Anatomy of a Dfn](docs/dfn-contract.md) - describes the way Bikeshed formats `<dfn>` elements for processing by scrapers, so interoperating tools can do the same.

Bikeshed File Extension
-----------------------

The preferred file extensions for Bikeshed source files is `bs`, like `index.bs`.
Bikeshed will automatically recognize `*.bs` files in the folder it's run in,
and assume that you want an output file of the same name with a `.html` extension.
The repository also contains a syntax highlighting script for Bikeshed source files.

(Bikeshed also recognizes files with `*.src.html` for backwards compatibility with older CSS specs,
though most such specs have switched their source file extensions to `.bs` now.
Using `.src.html` in most text editors will display the file with HTML source formatting,
which isn't generally what you want.)

License
-------

This document and all associated files in the github project are licensed under [CC0](http://creativecommons.org/publicdomain/zero/1.0/) ![](http://licensebuttons.net/p/zero/1.0/80x15.png).
This means you can reuse, remix, or otherwise appropriate this project for your own use **without restriction**.
(The actual legal meaning can be found at the above link.)
Don't ask me for permission to use any part of this project, **just use it**.
I would appreciate attribution, but that is not required by the license.

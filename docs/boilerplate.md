Boilerplate Generation
======================

The processor automatically generates nearly all of a spec's boilerplate,
the text that is repeated nearly identically across all specs.

Generally, you won't need to understand what's going on here in order to use the processor - it'll just automatically do the right thing.

Groups
------

Much of the boilerplate is determined based on the "Group" metadata.
This defaults to "csswg", as Bikeshed is written primarily by a CSS spec writer and is intended to replace the CSSWG's previous spec preprocessor,
but it can be set to anything.

Several groups are already accommodated with appropriate inclusion files:
* "csswg", as mentioned.
* "fxtf", for the FX Task Force
* "svg", for the SVG Working Group

You can put whatever value you want into the "Group" value, though.
Unrecognized values will just use the default boilerplate files.
If you want to add specialized boilerplate files for your group,
check out the File-Based Includes section, later in this document,
and write your own files.


Text Macros
-----------

Several text "macros" are defined by the spec's metadata,
and can be used anywhere in the spec to substitute in the spec they stand for by using the syntax `[FOO]`.
Note that this is similar to the syntax for bibliography references, but it has only a single set of `[]` characters.
The following macros are defined:

* [TITLE] gives the spec's full title, as extracted from either the `<h1>` or the spec metadata.
* [SHORTNAME] gives the document's shortname, like "css-cascade".
* [VSHORTNAME] gives the "versioned" shortname, like "css-cascade-3".
* [STATUS] gives the spec's status.
* [LONGSTATUS] gives a long form of the spec's status, so "ED" becomes "Editor's Draft", for example.
* [STATUSTEXT] gives an additional status text snippet.
* [LATEST] gives the link to the undated /TR link, if it exists.
* [VERSION] gives the link to the ED, if the spec is an ED, and otherwise constructs a dated /TR link from today's date.
* [ABSTRACT] gives the document's abstract.
* [ABSTRACTATTR] gives the document's abstract, correctly escaped to be an attribute value.
* [YEAR] gives the current year.
* [DATE] gives a human-readable date.
* [CDATE] gives a compact date in the format "YYYYMMDD".
* [ISODATE] gives a compact date in iso format "YYYY-MM-DD".
* [DEADLINE] gives a human-readable version of the deadline data, if one was specified.

As these are substituted at the text level, not the higher HTML level, you can use them *anywhere*, including in attribute values.


Boilerplate Sections
--------------------

The location of the boilerplate sections are indicated by elements with `data-fill-with=''` attributes.
If the elements contain anything, they're emptied before being filled with the appropriate boilerplate.
The valid `data-fill-with=''` values are:

* "table-of-contents" for the ToC
* "spec-metadata" for the `<dl>` of spec data that's in the header of all of our specs
* "abstract" for the spec's abstract
* "status" for the status section
* "normative-references" for the normative bibliography refs
* "informative-references" for the informative bibliography refs
* "index" for the index of terms (all the `<dfn>` elements in the spec)
* "property-index" for the table summarizing all properties defined in the spec
* "logo" for the W3C logo
* "copyright" for the W3C copyright statement
* "warning" for the relevant spec warning, if one was indicated in the metadata.


Table of Contents
-----------------

The headings in the spec are automatically numbered,
and a table of contents automatically generated.

Any heading `<h2>` to `<h6>`
(that is, skipping only the document-titling `<h1>`)
is automatically numbered by having a `<span class='secno'>...</span>`
prepended to its contents.
You can avoid this behavior for a heading and all of its subsequent subheadings
by adding `class='no-num'` to the heading.

Similarly, a ToC is generated to match.
Headings and their subheadings can be omitted from the ToC
by adding `class='no-toc'` to them.

The processor assumes that your headings are numbered correctly.
It does not yet pay attention to the HTML outline algorithm,
so using a bunch of `<h1>s` nested in `<section>s` will have very wrong effects.

Headings also automatically gain a self-link pointing to themselves,
to enable people to easily link to sections without having to return to the ToC.


File-based Includes
-------------------

Several of the data-fill-with values
(those that are static, rather than generated from in-document data)
actually come from sets of .include files in the include/ directory.

The base files are simply named "foo.include",
where "foo" is the name of the data-fill-with value.
They can be specialized, however,
to particular working groups,
and to particular document statuses.

Adding a "-group" to the filename, like "header-csswg.include",
specializes it for that group (specified in the spec's metadata).
Adding a "-STATUS" to the filename specializes it for the status (same).
These can be used together, with the group coming first, like "status-csswg-CR.include".

The processor will first look for the "foo-group-STATUS.include" file,
failing over to "foo-group.include",
then "foo-STATUS.include",
and finally "foo.include".


"Rerun" capability
------------------

Bert's preprocessor had the useful meta-feature
where most of it's features would continue to work if you lost the original source document
and just started editting the output document instead.
This preprocessor has maintained this feature as much as it could,
with only a few caveats:

1. Boilerplate is inserted if and only if your spec doesn't start with a doctype.
   Otherwise, it assumes that you're rolling your own boilerplate,
   which means that if your source document auto-genned its boilerplate,
   the output document won't double-generate.
   However, the `data-fill-with` attribute sticks around in the output,
   ensuring that those sections will be replaced with up-to-date text every time.

2. If a `<pre>` isn't nested deeply in your document (short whitespace prefix),
   but the contents are deeply nested (long whitespace prefix),
   it's possible that a second run-through would strip more whitespace in error.
   If you always indent with tabs, this is automatically avoided,
   as tabs `<pre>` contents (after removing the prefix) are auto-converted into two spaces
   (because tabs are enormous by default in HTML - 8 spaces wide!),
   and so the leftover leading whitespace will never match the `<pre>` tag's prefix.

3. The textual macros of the form [FOO] disappear entirely from the generated document,
   and will need to be replaced manually.
   It would be easy to make these work if they only showed up in content,
   but the fact that there are valid use-cases for putting them in attributes makes it harder to keep around in-band information about replacing them.

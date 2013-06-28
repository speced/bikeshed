css-preprocessor
================

This project is a pre-processor for the source documents the CSSWG produces their specs from.
We write our specs in HTML, but rely on a preprocessor for a lot of niceties, 
like automatically generating a bibliography and table of contents,
or automatically linking terms to their definitions.
Specs also come with a lot of boilerplate repeated on every document,
which we omit from our source document.

A short overview of my preprocessor's features:

* automatic linking of terms to their definitions based on text, so you can simple write `Use <a>some term</a> to...` and have it automatically link to the `<dfn>some term</dfn>` elsewhere in the document.  (Only same-document for now, but soon cross-document links will work!)
* automatic id generation for headings and definitions, based on their text.
* textual shortcuts for autolinks: [[FOO]] for bibliography entries, &lt;&lt;foo>> for grammar productions, 'foo' for property names, and ''foo'' for values.
* boilerplate generation, both wholesale and piecemeal.
* markdown-style paragraphs.
* a compact syntax for writing property-definition tables.
* automatic whitespace-prefix stripping from `<pre>` contents, so the contents can be indented properly in your HTML.

Examples of all of the functionality described here can be found by looking at the source of the [CSS Variables source document](http://dev.w3.org/csswg/css-variables/Overview.src.html)

Quick-Start Guide
---------------

Starting from an empty file, do the following:

1. Add an `<h1>` with the spec's title as the very first line.
2. Add a `<pre class='metadata'>` block, with at least the following keys (each line in the format "[key]:[value]"):
	1. "Status" - the shortcode for the spec's status (ED, WD, UD, etc.)
	2. "ED" - link to the Editor's Draft
	3. "Shortname" - the spec's shortname, like "css-flexbox".
	4. "Level" - an integer for the spec's level.  If you're unsure, just put "1".
	5. "Editor" - an editor's personal information, in the format "[name], [company], [email or contact url]".
	6. "Abstract" - a short (one or two sentences) description of what the spec is for.
3. You *should* add an `<h2>Introduction</h2>` section.
4. Write the rest of the spec!

The processor expects that your headings are all `<h2>` or higher (`<h1>` is reserved for the spec title).
You don't need to use `<p>` tags in most cases -
plain paragraphs are automatically inferred by linebreaks,
and starting one with "Note:" makes it add `class="note"`.

To use autolinks, just define things with `<dfn>`,
then link to them with `<a>` (no `href` attribute).
It matches up the contained text by default,
which can be overridden by using `title` on either the `<dfn>` or `<a>`.
There are more types of autolinks - check the docs below for details.

`<pre>` whitespace stripping
----------------------------
Using a `<pre>` element in HTML is unsatisfying, 
because it forces you to break your indentation strategy, 
pulling the content back to the margin edge
(or else employing silly hacks with comments and explicit newlines).
The preprocessor fixes this.

Whenever a `<pre>` element is encountered,
the processor records how much whitespace precedes it,
and then strips that much whitespace from all the content lines.

Additionally, if the closing `</pre>` is on its own line,
the processor automatically pulls it up onto the end of the previous line,
so there's no final blank line in the content.

In other words, you can now write:

~~~~html
<div class='example'>
	<p>
		An example:

	<pre>
	&lt;ul>
		&lt;li>one
		&lt;li>two
	&lt;</ul>
	</pre>
</div>
~~~~

The preprocessor will automatically convert it into:

~~~~html
<div class='example'>
	<p>
		An example:

	<pre>
&lt;ul>
	&lt;li>one
	&lt;li>two
&lt;</ul></pre>
</div>
~~~~


Propdef table expansion
-----------------------

Propdef tables are rather large, even when correctly formatted.
Instead, you can write a propdef table as a data block, like:

~~~~html
	<xmp class='propdef'>
	Name: var-*
	Values: [ <value> | <CDO> | <CDC> ]
	Initial: (nothing, see prose)
	Applies To: all elements
	Inherited: yes
	Computed Value: specified value with variables substituted (but see prose for "invalid variables")
	Media: all
	</xmp>
~~~~

Using `<pre>` or `<xmp>` are both valid - choose `<pre>` normally, or `<xmp>` if you want to include unescaped HTML special characters.
The important bit is the class='propdef' on the element.

The data block is parsed as a series of lines, 
with each line composed of one of the propdef headings, a colon, then the value.

The property name will automatically be wrapped in a `<dfn>` element.
Within the Values line, things that look like grammar nonterminals (anything like `<foo>`) will be automatically escaped and wrapped in `<var>` elements.


Markdown-style Paragraphs
-------------------------

Because I'm used to Markdown,
the preprocessor handles Markdown-style paragraphs.
That is, any block of text that either starts with an inline element or no element at all,
and is preceded by a blank line,
will have a `<p>` tag automatically inserted before it.

Any Markdown-style paragraphs starting with "Note: " or "Note, "
will instead get a `<p class='note'>`.


Automatic Linking
-----------------
Every heading or `<dfn>` element automatically defines an autolink target.
(Add `class=no-ref` to avoid this.)
If the target doesn't have an `id` attribute,
one is auto-generated for it out of the element's text content
by stripping out everything but alphanumerics, dashes, and underscores.

If the text content looks like a function (ends in "()"), "-function" is appended to the id.
If the text content looks like a grammar production (starts with "<", ends with ">"), "-production" is appended to the id.
These corrections help reduce id collisions between function/productions and normal terms.

If there is a collision, the processer attempts to fix it by trying to append the digits 0-9 to the id.
If for some reason you have so many collisions that 0-9 doesn't work, it'll fail noisily.

Every `<a>` element *without* an `href` attribute defines an autolink,
as does any `<a>` with a `data-autolink` attribute on it identifying a valid autolink type.
Autolinking is accomplished by matching up the text content of the autolink target and the autolink.
You can override this behavior on either by providing a `title` attribute, which is used instead.
On autolink targets, multiple match targets can be provided by using a pipe character (|) to separate each.

If the text of an autolink doesn't match any target,
the processor tries a few simple manipulations to accommodate common English variations:
* if the text ends with an "s", "es", "'s", or "'", tries to match without it
* if the text ends with an "ies", tries to match with that replaced by "y"

The valid autolink types are:
* "link", which matches against any heading or `<dfn>` element.
* "maybe", which is identical to link, but doesn't complain if it fails. (This exists because the ''foo'' syntax is overloaded in the older preprocessor from Bert to also indicate any stretch of inline CSS code.  Due to the way the preprocessor worked, it would accidentally autolink sometimes, and our specs now depend on this.)
* "property", which only matches against property definitions (`<dfn>` elements in a propdef table).
* "biblio", which only matches against bibliography names (the `<dt>` elements in the biblio section of the spec).

The various textual shortcuts all turn into an `<a>` with an appropriate `data-autolink` attribute - [[FOO]] becomes "biblio", 'foo' becomes "property", &lt;&lt;foo>> becomes "link", and ''foo'' becomes "maybe".


Bibliography and References
---------------------------

Currently, referencing an external document can only be done through the bibliography syntax,
triggered by an `<a data-autolink="biblio">` element (or the shorthand [[FOO]] syntax).
When this syntax is used, the processor verifies that the link is valid by checking its biblio file,
then generates an appropriate line in the biblio section of the spec,
and links to it.

The repo comes with a "biblio.refer" file which is used by default.
If it's missing, the bibliography file is retrieved from the internet
(behind a W3C member-only page, so you'll need W3C credentials to retrieve it)
and stored in the same directory as the preprocess.py file.
You can force it to look in a different location by passing the --biblio flag.

Currently, the biblio file must be in REFER format.
The default biblio file is already in this format,
so you shouldn't have to do anything.

Any occurence of "[[NAME]]" or "[[!NAME]]" will be assumed to be a bibliographic reference.
The text is automatically converted into a link,
pointing to the auto-generated References section.
The former syntax is for informative references,
the latter is for normative ones.

The References section is generated automatically,
and filled with full bibliographic lines for all the documents referenced by your spec.


Metadata and Boilerplate Generation
-----------------------------------

Our module template contains several screenfuls of boilerplate even when entirely empty of content.
The preprocessor adds that automatically, so your spec source will have less noise in it.
It does so by extracting a few pieces of metadata from the document.

To trigger the full-spec boilerplate generation,
just start your sepc with an `<h1>` containing the spec's title.
Then, somewhere in the spec
(it's recommended that it be put right after the title),
a data block (`<pre>` or `<xmp>`) with class='metadata' must exist,
containing several pieces of metadata.
The format is the same as propdef tables: each line is one piece of data, containing key, colon, value.

The following keys are required:

* "Status" is the spec's status, as one of the standard abbreviations ("WD", "ED", "CR", etc.)
* "ED" must contain a link that points to the editor's draft.
* "Shortname" must contain the spec's shortname, like "css-lists" or "css-backgrounds".
* "Level" must contain the spec's level as an integer.
* "Editor" must contain an editor's information.
	This has a special format:
	it must contain the editor's name,
	followed by the editor's affiliation,
	followed by either an email address or a link to their contact page,
	all comma-separated.
	(There is not currently any way to put a comma *in* one of these values.)
	Multiple "Editor" lines can be used to supply multiple editors.
* "Abstract" must contain an abstract for the spec, a 1-2 sentence description of what the spec is about.

The following keys are optional, and may be omitted:
	
* "TR" must contain a link that points to the latest version on /TR.
* "Warning" must contain either "Obsolete" or "Not Ready", which triggers the appropriate warning message in the boilerplate.
* "Previous Version" must contain a link that points to a previous (dated) version on /TR.
* "At Risk" must contain an at-risk feature.  Multiple lines can be provided.  Each will be formatted as a list item in the Status section.
* "Group" must contain the name of the group the spec is being generated for.  This is used by the boilerplate generation to select the correct file.  It defaults to "csswg".
* "Ignored Properties" and "Ignored Terms" accept a comma-separated list of properties and terms, respectively, and ignore their absence if they can't link up.  Use these to quiet spurious preprocessor warnings caused by you inventing terms or specifying something as a term before its target exists.
* "Date" must contain a date in YYYY-MM-DD format, which is used instead of today's date for all the date-related stuff in the spec.
* "Deadline" is also a YYYY-MM-DD date, which is used for things like the LCWD Status section, to indicate deadlines.
* "Test Suite" must contain a link to the test suite nightly cover page (like <http://test.csswg.org/suites/css3-flexbox/nightly-unstable>)

Anything else put in the metadata block will be extracted and later put into the `<dl>` in the spec's header, 
using the keys and values you specify.
If you need multiple values for a particular key (such as multiple "Previous Editor" lines), 
just repeat the key on multiple lines.

Any HTML used in a value in a metadata block will be put directly into the document unescaped, so feel free to insert links and the like in values.

An example metadata block:

~~~~html
<pre class='metadata'>
Status: ED
TR: http://www.w3.org/TR/css-variables/
ED: http://dev.w3.org/csswg/css-variables/
Shortname: Variables
Level: 1
Editor: Tab Atkins Jr., Google, http://xanthir.com/contact
Editor: Luke Macpherson, Google, macpherson@google.com
Editor: Daniel Glazman, Disruptive Innovations, daniel.glazman@disruptive-innovations.com
Abstract: This module introduces cascading variables as a new primitive value type that is accepted by all CSS properties, and custom properties for defining them.
</pre>
~~~~

Alternately, you can write your own boilerplate and just opt into individual pieces being auto-generated.
To do this, start your spec with anything other than an `<h1>` element
(I recommend just putting the HTML doctype `<!doctype html>` as the first line).
Then, to get the processor to generate some part of the boilerplate,
add an element with a `data-fill-with` attribute specifying the type of thing it should be filled with.
The current values are:

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

As well, there are a few textual macros that can be invoked to fill in various small bits of information,
written as [FOO].
Most of them take their data straight from the document's metadata block.
These are replaced early, before the source text has been parsed into a document,
so they can occur anywhere, including attribute values.
The current values are:

* [TITLE] gives the spec's full title, as extracted from either the `<h1>` or the spec metadata.
* [SHORTNAME] is replaced with the document's shortname.
* [STATUS] gives the spec's status.
* [LONGSTATUS] gives a long form of the spec's status, so "ED" becomes "Editor's Draft", for example.
* [LATEST] gives the link to the undated /TR link, if it exists.
* [VERSION] gives the link to the ED, if the spec is an ED, and otherwise constructs a dated /TR link from today's date.
* [ABSTRACT] gives the document's abstract.
* [YEAR] gives the current year.
* [DATE] gives a human-readable date.
* [CDATE] gives a compact date in the format "YYYYMMDD".
* [ISODATE] gives a compact date in iso format "YYYY-MM-DD".

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
specializes it for that group.
Adding a "-STATUS" to the filename specializes it for the status.
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

1. Boilerplate is inserted if and only if the first line of your source is an `<h1>`.
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
css-preprocessor
================

This file documents the pre-preprocessor I made to help minimize the markup of specs in the CSSWG.
It currently sits in front of [Bert's existing preprocessor](https://www.w3.org/Style/Group/css3-src/bin/README.html), 
so everything that could be done previously still works.
It introduces several new features, though.

Examples of all of the functionality described here can be found by looking at the source of the [CSS Variables source document](http://dev.w3.org/csswg/css-variables/Overview.src.html)

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


Metadata and Boilerplate Generation
-----------------------------------

Our module template contains several screenfuls of boilerplate even when entirely empty of content.
The preprocessor adds that automatically, so your spec source will have less noise in it.
It does so by extracting a few pieces of metadata from the document.

The first line of the spec should be an `<h1>` containing the spec's title.
Then, somewhere in the spec
(it's recommended that it be put right after the title),
a data block (`<pre>` or `<xmp>`) with class='metadata' must exist,
containing several pieces of metadata.
The format is the same as propdef tables: each line is one piece of data, containing key, colon, value.

The relevant keys are:

* "Status" must be the spec's status, as one of the standard abbreviations ("WD", "ED", "CR", etc.)
* "ED" must contain a link that points to the editor's draft.
* "TR" may contain a link that points to the latest version on /TR.
* "Editor" must contain an editor's information.
	This has a special format:
	it must contain the editor's name,
	followed by the editor's affiliation,
	followed by either an email address or a link to their contact page,
	all comma-separated.
	(There is not currently any way to put a comma *in* one of these values.)
	Multiple "Editor" lines can be used to supply multiple editors.
* "Abstract" must contain an abstract for the spec, a 1-2 sentence description of what the spec is about.

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
Editor: Tab Atkins Jr., Google, http://xanthir.com/contact
Editor: Luke Macpherson, Google, macpherson@google.com
Editor: Daniel Glazman (Disruptive Innovations) daniel.glazman@disruptive-innovations.com
Abstract: This module introduces cascading variables as a new primitive value type that is accepted by all CSS properties, and custom properties for defining them.
</pre>
~~~~

Some pieces of the boilerplate are generated specially, after the rest,
and have a special syntax to indicate that -
an element with a specially chosen id,
followed by an empty `<div>`.
Here are the current special ids currently recognized:

* The Table of Contents is indicated by `id=contents`.
* The Normative and Informative References sections are indicated, respectively, by `id=normative` and `id=informative`.


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


Automatic Linking
-----------------

The preprocessor will now automatically link terms to their definitions within a single document.

Every heading or `<dfn>` element automatically defines an autolink target.
(Add `class=no-ref` to avoid this.)
If the target doesn't have an `id` attribute,
one is auto-generated for it out of the element's text content
by stripping out everything but alphanumerics, dashes, and underscores.

If the text content looks like a function (ends in "()"), "-function" is appended to the id.
If the text content looks like a grammar production (start with "<", ends with ">"), "-production" is appended to the id.
These corrections help reduce id collisions between function/productions and normal terms.

If there is a collision, the processer attempts to fix it by trying to append the digits 0-9 to the id.
If for some reason you have so many collisions that 0-9 doesn't work, it'll fail noisily.

Every `<a>` element *without* an `href` attribute defines an autolink.
Autolinking is accomplished by matching up the text content of the autolink target and the autolink.
You can override this behavior on either by providing a `title` attribute, which is used instead.
On autolink targets, multiple match targets can be provided by using a pipe character (|) to separate each.

If the text of an autolink doesn't match any target,
the processor tries a few simple manipulations to accommodate common English variations:
* if the text ends with an "s" or "'s", tries to match without it
* if the text ends with an "ies", tries to match with that replaced by "y"


Bibliography and References
---------------------------

External document references have a special syntax,
copying the syntax used in Bert's preprocessor,
which are driven by a bibliography file.

By default, the bibliography file is retrieved from the internet
(behind a W3C member-only page, so you'll need W3C credentials to retrieve it)
and stored in the same directory as the preprocess.py file.
You can force it to look in a different location by passing the --biblio flag.
You can regenerate the cached file by deleting the cache and running the script again.

Currently, the biblio file must be in REFER format.
The default biblio file retrieved from the internet is already in this format,
so you shouldn't have to do anything.

Any occurence of "[[NAME]]" or "[[!NAME]]" will be assumed to be a bibliographic reference.
Similar to autolinks, the text is automatically converted into a link,
pointing to the auto-generated References section.
The former syntax is for informative references,
the latter is for normative ones.

The References section is generated automatically,
and filled with full bibliographic lines for all the documents referenced by your spec.


Further Preprocessing
---------------------

After the fixups described above, 
the preprocessor automatically passes the result through Bert's preprocessor as well,
so anything provided by that processor,
like automatic in-document cross-refs, TOC generation, and the like.
I plan to eventually subsume that into this processor as well,
but for now just chaining it is sufficient.

As is CSSWG tradition,
the preprocessor assumes that the source file is called "Overview.src.html",
and the desired output file is called "Overview.html".
I'll add some controls for this later.


Additional Notes
----------------

Like Bert's preprocessor,
this processor should be capable of running over an already-processed document as a no-op.
A few assumptions are made to aid with this:

1. Boilerplate is inserted if and only if the first line of your source is an `<h1>`.
   Otherwise, it assumes that you're rolling your own boilerplate.

2. If a `<pre>` isn't nested deeply in your document (short whitespace prefix),
   but the contents are deeply nested (long whitespace prefix),
   it's possible that a second run-through would strip more whitespace in error.
   If you always indent with tabs, this is automatically avoided,
   as tabs `<pre>` contents (after removing the prefix) are auto-converted into two spaces
   (because tabs are enormous by default in HTML - 8 spaces wide!),
   and so the leftover leading whitespace will never match the `<pre>` tag's prefix.

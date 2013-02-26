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

~~~~
<div class='example'>
	<p>
		An example:

	<pre>
	&lt;ul>
		&lt;li>one
		&lt;li>two
	&lt;</ul>
	</pre>
~~~~

The preprocessor will automatically convert it into:

~~~~
<div class='example'>
	<p>
		An example:

	<pre>
&lt;ul>
	&lt;li>one
	&lt;li>two
&lt;</ul></pre>
~~~~


Propdef table expansion
-----------------------

Propdef tables are rather large, even when correctly formatted.
Instead, you can write a propdef table as a data block, like:

~~~~
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
	This has a special format: the name comes first,
	followed by the editor's affiliation in parentheses,
	followed by either an email address or a link to their contact page.
	Multiple "Editor" lines can be used to supply multiple editors.
* "Abstract" must contain an abstract for the spec, a 1-2 sentence description of what the spec is about.

Anything else put in the metadata block will be extracted and later put into the `<dl>` in the spec's header, 
using the keys and values you specify.
If you need multiple values for a particular key (such as multiple "Previous Editor" lines), 
just repeat the key on multiple lines.

Any HTML used in a value in a metadata block will be put directly into the document unescaped, so feel free to insert links and the like in values.

An example metadata block:

~~~~
<pre class='metadata'>
Status: ED
TR: http://www.w3.org/TR/css-variables/
ED: http://dev.w3.org/csswg/css-variables/
Editor: Tab Atkins Jr. (Google, Inc.) http://xanthir.com/contact
Editor: Luke Macpherson (Google, Inc.) macpherson@google.com
Editor: Daniel Glazman (Disruptive Innovations) daniel.glazman@disruptive-innovations.com
Abstract: This module introduces cascading variables as a new primitive value type that is accepted by all CSS properties, and custom properties for defining them.
</pre>
~~~~


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
   as tabs in the whitespace prefix of `<pre>` contents are auto-converted into two spaces
   (because tabs are enormous by default in HTML - 8 spaces wide!),
   and so the leftover prefix will never match the `<pre>` tag's prefix.
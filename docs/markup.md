Markup Shortcuts
================

The processor allows you to omit or shorten several verbose/annoying parts of HTML,
reducing the amount of format noise in the spec source,
making it easier to read and write.

Markdown-style Paragraphs
-------------------------

The processor recognizes Markdown-style paragraphs,
allowing you to omit nearly all `<p>` elements from your source.

Any block of text preceded by a blank line and starting with either naked text or an inline HTML element will be recognized as a paragraph and have the appropriate markup inserted automatically.

Additionally, starting a paragraph with "Note: " or "Note, " will add a `class='note'` to the paragraph,
which triggers special formatting in the CSS stylesheet.
Starting one with "Issue: " will add a `class='issue'` to the paragraph.


Typography Fixes
----------------

Bikeshed will automatically handle a few typographic niceties for you, ones that it can reliably detect:

* Possessive apostophes, and most contraction apostrophes, are automatically turned into curly right single quotes (`’`).
* Ending a line with `--` will turn it into an em dash (`—`) and pull the following line upwards so there's no space between the surrounding words and the dash.


Autolink Shortcuts
------------------

There are several shortcuts for writing autolinks of particular types, so you don't have to write the `<a>` element yourself:

* `<i>` elements are treated as autolinks as well, for legacy reasons.
* `'foo'` (apostophes/straight quotes) is an autolink to a property or descriptor named "foo"
* `''foo''` (double apostrophes) is an autolink to any of the CSS definition types except property and descriptor
* `<<foo>>` is an autolink to a type/production named "&lt;foo>"
* `<<'foo'>>` is an autolink to the the property or descriptor named "foo" (used in grammars, where you need `<foo>` for non-terminals)
* `<<foo()>>` is an autolink to the function named "foo" (same)
* `<<@foo>>` is an autolink to the at-rule named "@foo" (same)
* `[[foo]]` is an autolink to a bibliography entry named "foo", and auto-generates an informative reference in the biblio section.
    Add a leading exclamation point to the value, like `[[!foo]]` for a normative reference.

If using the `''foo''` shortcut,
you can specify the `for=''` attribute in the shortcut as well
by writing the for value first, then a slash, then the value.
For example, `''width/auto''` specifically refers to the `auto` value for the `width` property,
which is much shorter than writing out `<a value for=width>auto</a>`.

Remember that if you need to write out the `<a>` tag explicitly,
you can add the type as a boolean attribute.


`<pre>` whitespace stripping
----------------------------
Using a `<pre>` element in HTML is unsatisfying,
because it forces you to break your indentation strategy,
pulling the content back to the margin edge
(or else employing silly hacks with comments and explicit newlines).
The preprocessor fixes this.

Whenever a `<pre>` element is encountered,
the processor records how much whitespace precedes the first line,
and then strips that much whitespace from it and all following lines.

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
Instead, you can write the table in a simple text format similar to the spec's metadata block,
and let the processor automatically generate a `<table>` from it:

~~~~html
	<pre class='propdef'>
	Name: var-*
	Values: [ <value> | <CDO> | <CDC> ]
	Initial: (nothing, see prose)
	Applies To: all elements
	Inherited: yes
	Computed Value: specified value with variables substituted (but see prose for "invalid variables")
	Media: all
	</pre>
~~~~

The data block is parsed as a series of lines,
with each line composed of one of the propdef headings, a colon, then the value.

The property name will automatically be wrapped in a `<dfn>` element.
Within the Values line, things that look like grammar nonterminals (anything like `<foo>`) will be automatically escaped and wrapped in `<var>` elements.

This also works for descdef tables, describing the syntax of descriptors.
When writing a descdef table, you should additionally add a "For" line containing the name of the at-rule the descriptor is for.

If you're defining a *partial* propdef or descdef
(for example, just defining a few new values for an existing property),
you can indicate this by adding a "partial" class to the `<pre>`.
(This will prevent Bikeshed from complaining about lots of missing propdef/descdef lines.)


Automatic ID Generation
-----------------------

If any heading, issue, or `<dfn>` element doesn't have an `id=''` attribute,
one will be automatically generated by the processor,
to ensure it's usable as a link target.

Heading IDs are generated directly from the text contents of the element,
cleaning up the characters to be a valid id.
This often isn't the best for complex heading texts,
so it's not recommended to rely on this.
(Bikeshed will warn you that it's generating IDs, and suggest you supply one manually.)

Issues (elements with `class='issue'`) will generate IDs of the form "issue-###",
where "###" is substring of a hash of the issue's contents.
This means that an issue's ID will be stable against changes elsewhere in the document,
including adding or removing issues above it in the source,
but will change if you change the contents of the issue.

Definition IDs are also generated directly from the text contents of the element.
Most definitions additionally get a prefix, such as "propdef-",
to avoid clashes with other definitions.

If an automatically-generated ID would collide with any other ID,
it's automatically de-duped by appending a number to the end.
This isn't very pretty,
so if you want to avoid it,
supply an ID yourself.


Automatic Self-Link Generation
------------------------------

Giving IDs to important things in your document,
like headings and definitions,
is great, but of little use if people don't know they can link to them.
Bikeshed will automatically generate a "self-link"
in the margin next to certain linkable elements
which just links to the element,
so people can click on the link and then just copy the URL from their address bar
to get a link straight to what they care about.

Self-links are currently auto-generated for headings, definitions, and issues,
and notes, examples, `<li>`s, and `<dt>`s that have been given IDs.

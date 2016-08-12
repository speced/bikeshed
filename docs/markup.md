Markup Shortcuts
================

Bikeshed's source format is *roughly* HTML,
but it allows you to omit or shorten several verbose/annoying parts of the language,
reducing the amount of format noise in the spec source,
making it easier to read and write.

Markdown
--------

Bikeshed currently recognizes a subset of Markdown:

* paragraphs
* lists
* headings
* horizontal rules
* fenced code blocks
* *emphasis* and **strong** span elements
* inline links, with optional title

It also recognizes **definition lists**, with the following format:

```
Here's the dl syntax:

: key
:: val
: key 1
: key 2
:: more vals
```

For all three list formats,
on the rare occasions you need to add a class or attribute to the list,
you can wrap it in the appropriate list container, like:

```
<ol class=foo>
	1. first
	2. second
</ol>
```

Bikeshed will use the container you provided,
rather than generating a fresh one like it does by default.

It supports adding IDs to headings,
via the Markdown Extra syntax:

```
Header 1 {#header1}
========

### Header 2 ### {#header2}
```

Additionally, starting a paragraph with "Note: " or "Note, " will add a `class='note'` to the paragraph,
which triggers special formatting in the CSS stylesheet.
Starting one with "Issue: " will add a `class='issue'` to the paragraph.
Starting one with "Advisement: " will add a `<strong class=advisement>` around the contents of the paragraph.
Starting one with "Assertion: " will add a `class=assertion` to the paragraph.

More of Markdown will be supported in the future,
as is adherence to the CommonMark specification.


Typography Fixes
----------------

Bikeshed will automatically handle a few typographic niceties for you, ones that it can reliably detect:

* Possessive apostophes, and most contraction apostrophes, are automatically turned into curly right single quotes (`’`).
* Ending a line with `--` will turn it into an em dash (`—`) and pull the following line upwards so there's no space between the surrounding words and the dash.


Autolink Shortcuts
------------------

There are several shortcuts for writing autolinks of particular types, so you don't have to write the `<a>` element yourself:

* `'foo'` (apostophes/straight quotes) is an autolink to a property or descriptor named "foo"
* `''foo''` (double apostrophes) is an autolink to any of the CSS definition types except property and descriptor
* `<<foo>>` is an autolink to a type/production named "&lt;foo>"
* `<<'foo'>>` is an autolink to the the property or descriptor named "foo" (used in grammars, where you need `<foo>` for non-terminals)
* `<<foo()>>` is an autolink to the function named "foo" (same)
* `<<@foo>>` is an autolink to the at-rule named "@foo" (same)
* `{{Foo}}` is an autolink to an IDL term named "Foo". (Accepts interfaces, attributes, methods, etc)
* `<{Foo}>` is an autolink to an element named "Foo".
* `|foo|` is a variable reference (`<var>`). (Vars created this way will shortly be checked for typos, so look out for new warnings/errors soon.)
* `[[foo]]` is an autolink to a bibliography entry named "foo", and auto-generates an informative reference in the biblio section.
    Add a leading exclamation point to the value, like `[[!foo]]` for a normative reference.
* `[[#foo]]` is an autolink to the heading in the same document with that ID. This generates appropriate reference text in its place, like "§5.3 Baseline Self-Alignment"
* `<i>` elements can be enabled as autolinks as well, using `Use <i> Autolinks: yes` metadata. (The CSSWG has this enabled by default.)

If using the `''foo''`,
`<<'descriptor'>>`,
or `{{Foo}}` shortcuts,
you can specify the `for=''` attribute in the shortcut as well
by writing the for value first, then a slash, then the value.
For example, `''width/auto''` specifically refers to the `auto` value for the `width` property,
which is much shorter than writing out `<a value for=width>auto</a>`.
For the `{{foo}}` shortcut,
you can also specify exactly which type of IDL link it is,
in case of ambiguity,
by appending a `!` and the type,
like `{{family!argument}}`,
which is equivalent to `<a argument><code>family</code></a>`

Remember that if you need to write out the `<a>` tag explicitly,
you can add the type as a boolean attribute.


`<var>` and Algorithms
----------------------

The `<var>` element (or its shorthand equivalent, `|foo|`) is often used to mark up "arguments" to a prose algorithm.
Bikeshed explicitly recognizes this,
and has several features related to this.

**Algorithms** can be explicitly indicated in your markup
by putting the `algorithm="to foo a bar"` attribute on a container element
or a heading.
All vars within an algorithm are "scoped" to that algorithm.

Generally, vars are used at least twice in an algorithm:
once to define them,
and at least once to actually use them for something.
If you use a var only once,
there's a good chance it's actually a typo.
Bikeshed will emit a warning if it finds any vars used only once in an algorithm.
If this singular usage is correct,
you can instruct Bikeshed to ignore the error by listing it in the `Ignored Vars` metadata.


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
		&lt;/ul>
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
&lt;/ul></pre>
</div>
~~~~


Syntax Highlighting
-------------------

You can also syntax-highlight code blocks.
Just add either a `highlight="foo"` attribute
or a `lang-foo` class to the element,
and the element will automatically be syntax-highlighted according to the "foo" language rules.

The syntax highlighter uses Pygments, which supports a large set of languages.
See <http://pygments.org/docs/lexers/> for the full list.
(Use one of the "short names" of the language for the "foo" value.)

Note: If you use "html", `<script>` and `<style>` elements are automatically highlighted with JS and CSS rules.


Property/descriptor/element definition table expansion
------------------------------------------------------

Propdef tables are rather large, even when correctly formatted.
Instead, you can write the table in a simple text format similar to the spec's metadata block,
and let the processor automatically generate a `<table>` from it:

~~~~html
	<pre class='propdef'>
	Name: flex-basis
	Value: content | <<'width'>>
	Initial: auto
	Applies to: <a>flex items</a>
	Inherited: no
	Computed value: as specified, with lengths made absolute
	Percentages: relative to the <a>flex container's</a> inner <a>main size</a>
	Media: visual
	Animation type: length
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

The format of an elementdef table is a little different.  It can contain the following lines:

* **Name** - the element name(s)
* **Categories** - what "categories" the element is classified in, such as "flow content" or "graphics element".
	These must be defined terms, as Bikeshed will attempt to link them.
* **Contexts** - what contexts the element can be used in
* **Content Model** - what kind of elements and other nodes can validly appear inside the element
* **Attributes** - what attributes are defined for the element.
	These must be defined (as `element-attr` definitions), as Bikeshed will attempt to link to them.
* **Attribute Groups** - optional. If some attributes commonly appear on lots of elements, you can classify them into groups and list them here.
	The group name must be defined as a `dfn` type definition,
	with the attributes in the group defined as `element-attr` definitions with a `for` value of the group name.
	Bikeshed will expand the group into a `<details>` element for you and automatically link the attributes.
* **DOM Interfaces** - list the IDL interfaces that correspond to the elements defined in the block.
	These must be defined (as `interface` definitions), as Bikeshed will attempt to link to them.


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

If a heading changed significantly,
so that you want to change the ID,
but you want links to the old heading ID to still work,
put the old ID in an `oldids=''` attribute on the heading element.
If there are multiple, comma-separate them.

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

Bikeshed recognizes a fake element named `<assert>` for marking "assertions" that tests can refer to.
In the generated output, this is converted to a `<span>` with a unique ID generated from its contents,
like issues (described above).
This ensures that you have a unique ID that won't change arbitrarily,
but *will* change **when the contents of the assertion change**,
making it easier to tell when a test might no longer be testing the assertion it points to
(because it's no longer pointing to a valid target at all!).


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

Remote Issues
-------------

As defined earlier, you can start a paragraph with `Issue: ` to cause Bikeshed to automatically format it as an inline issue paragraph.
You can also refer to remote issues, which are tracked in some other issue tracker.
To do so, instead start your paragraph with `Issue(###): `,
where the `###` is some identifying value for the issue.

If the identifying value is of the form `user/repo#number`,
Bikeshed assumes you are referring to GitHub repository,
and points the issue at the corresponding issue.

If you have **Repository** set up to point to a GitHub repository
(or it was auto-detected as such,
because you're working on the spec from within one),
then a numeric identifying value is assumed to be an issue number for your repository.

Otherwise, you need to tell Bikeshed how to convert the identifying value into a remote issue link.
Specify a format string in the **Issue Tracker Template** metadata,
with a `{0}` in the place where the identifying value should go.
Bikeshed will then point the issue at the generated url.


Including Other Files
---------------------

Sometimes a spec is too large to easily work with in one file.
Sometimes there's lots of repetitive markup that only changes in a few standard ways.
For whatever reason,
Bikeshed has the ability to include additional files directly into your spec
with a `<pre class=include>` block:

```
<pre class=include>
path: relative/to/spec
</pre>
```

The included document is parsed just like if it were written in locally,
except that metadata blocks aren't processed.
(For various reasons, they have to be parsed before *any* other processing occurs).
This means that the include file can use markdown,
data blocks of various kinds (`<pre class=anchors>`, `<pre class=railroad-diagram>`, etc),
and both provide definitions for the outer document
and refer to ones defined by the outer document.

If you're including a block of repetitive markup multiple times,
and want to vary how it's displayed,
you can pass additional "local" text macros in the block,
which are valid only inside the included file:

```
<pre class=include>
path: template.md
macros:
	foo: bar
	baz: qux qux qux
</pre>
```

With the above code, you can use `[FOO]` and `[BAZ]` macros inside the include file,
and they'll be substituted with "bar" and "qux qux qux", respectively.
(Remember that you can mark text macros as optional by appending a `?`, like `[FOO?]`,
in which case they'll be replaced with the empty string if Bikeshed can't find a definition.)

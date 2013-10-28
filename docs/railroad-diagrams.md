RailRoad Diagrams
=================

A **railroad diagram** is a particular way of visually representing a structure roughly equivalent to regular expressions, or simple grammars.  They tend to be more readable and easier to grok than their equivalents written in terse regexps, and smaller than their equivalents written in explicit parsers.

Here's an example of a railroad diagram, this one describing the syntax of valid IDENT tokens in CSS:

<img width=729 height=110 src='https://rawgithub.com/tabatkins/bikeshed/master/docs/rr1.svg'>

Bikeshed supports the automatic generation of railroad diagrams from a simplified DSL.  To use, simply embed a diagram description in a `<pre class='railroad'>` element - it'll get replaced by an appropriate `<svg>` element.

The Diagram Language
--------------------

Diagrams are described by a custom DSL that resembles function calls in most languages like Python or JS.  (Actually, it's raw Python, but there's no reason to use anything beyond the DSL specified here.)

A railroad diagram consists of a number of nested elements, each of which may contain multiple children.  Each element is specified as a function call, with the element's name as the function name, and the element's children as it's arguments, like:

```js
Diagram(
	'/*',
	ZeroOrMore(
		NonTerminal('anything but * followed by /')),
	'*/')
```

This draws the following diagram:

<img width=497 height=81 src='data:image/svg+xml,<svg class="railroad-diagram" height="81" viewBox="0 0 497 81" width="497">
<g transform="translate(.5 .5)">
<path d="M 20 31 v 20 m 10 -20 v 20 m -10 -10 h 20.5">
</path><path d="M40 41h10">
</path><g>
<path d="M50 41h0">
</path><path d="M86 41h0">
</path><rect height="22" rx="10" ry="10" width="36" x="50" y="30">
</rect><text x="68" y="45">
/*</text></g><path d="M86 41h10">
</path><g>
<path d="M96 41h0">
</path><path d="M400 41h0">
</path><path d="M96 41a10 10 0 0 0 10 -10v0a10 10 0 0 1 10 -10">
</path><g>
<path d="M116 21h264">
</path></g><path d="M380 21a10 10 0 0 1 10 10v0a10 10 0 0 0 10 10">
</path><path d="M96 41h20">
</path><g>
<path d="M116 41h0">
</path><path d="M380 41h0">
</path><path d="M116 41h10">
</path><g>
<path d="M126 41h0">
</path><path d="M370 41h0">
</path><rect height="22" width="244" x="126" y="30">
</rect><text x="248" y="45">
anything but * followed by /</text></g><path d="M370 41h10">
</path><path d="M126 41a10 10 0 0 0 -10 10v0a10 10 0 0 0 10 10">
</path><g>
<path d="M126 61h244">
</path></g><path d="M370 61a10 10 0 0 0 10 -10v0a10 10 0 0 0 -10 -10">
</path></g><path d="M380 41h20">
</path></g><path d="M400 41h10">
</path><g>
<path d="M410 41h0">
</path><path d="M446 41h0">
</path><rect height="22" rx="10" ry="10" width="36" x="410" y="30">
</rect><text x="428" y="45">
*/</text></g><path d="M446 41h10">
</path><path d="M 456 41 h 20 m -10 -10 v 20 m 10 -20 v 20">
</path></g></svg>'>

The top-level element must always be a Diagram, and you must not use a Diagram anywhere else (it's not meaningful, and will do weird things).  Inside of a Diagram, any of the other elements may be used.  Elements are split into two groups: containers and text.

The containers wrap other elements, and modify their semantics:

* **Sequence** - used for sequences of elements which must all be selected in order.  Like concatenation in regexes.
* **Choice** - used for a choice between elements.  Like the `|` character in regexes.  The first argument to `Choice()` must be the index of the "default" choice.  If there is no reasonable default, it's fine to just provide 0.
* **Optional** - used for an element that's optional.  Like the `?` character in regexes.  This takes only a single child, and optionally a boolean after it: `true` indicates that the "default" choice is to skip this element.
* **OneOrMore** - used for an element that can be chosen one or more times.  Like the `+` character in regexes.  This takes only a single child, and optionally an element that must be provided between repetitions.  For example, a comma-separated list of tokens may be written as `OneOrMore(NT('token'), ',')`.
* **ZeroOrMore** - same as OneOrMore, but allows the element to be chosen zero times as well (skipped entirely).  Like the `*` character in regexes.

The text elements only contain text, not other elements:

* **Terminal** - represents a "terminal" in the grammar, something that can't be expanded any more.  Generally represents literal text.
* **NonTerminal** - represents a "non-terminal" in the grammar, something that can be expanded further.
* **Comment** - represents a comment in the railroad diagram, to aid in reading or provide additional information.  This is often used as the repetition value of a OneOrMore or ZeroOrMore to provide information about the repetitions, like how many are allowed.
* **Skip** - represents nothing, an empty option.  This is rarely necessary to use explicitly, as containers like Optional use it automatically, but it's occasionally necessary.

Most of the elements can be written in a shorter form, as well, to make the railroad diagram code more compact and easier to write:

* Sequence may be shortened to **And**.
* Choice may be shortened to **Or**.
* Optional may be shortened to **Opt**.
* OneOrMOre may be shortened to **Plus**.
* ZeroOrMore may be shortened to **Star**.
* Terminal may be shortened to **T**, or just a plain string.
* NonTerminal may be shortened to **NT**.
* Comment may be shortened to **C**.
* Skip may be shortened to **S**.


Pitfalls
--------

The diagram DSL is actually just raw Python, and so some rules of Python apply. For example, certain characters in strings must be escaped.  If you don't want to think about the rules, and aren't using any character escapes, you can precede a string with the letter "r", like `r"This isn't a newline: \n"`, to indicate it's a "raw" string and shouldn't try to process any escapes.

Don't worry about indentation, however.  As the contents of a railroad block are just a single `Diagram()` call, indentation isn't important.

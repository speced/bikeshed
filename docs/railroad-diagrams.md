RailRoad Diagrams
=================

A **railroad diagram** is a particular way of visually representing a structure roughly equivalent to regular expressions, or simple grammars.  They tend to be more readable and easier to grok than their equivalents written in terse regexps, and smaller than their equivalents written in explicit parsers.

Here's an example of a railroad diagram, this one describing the syntax of valid IDENT tokens in CSS:

<img width=729 height=110 src='https://rawgithub.com/tabatkins/bikeshed/master/docs/rr1.svg'>

Bikeshed supports the automatic generation of railroad diagrams from a simplified DSL.  To use, simply embed a diagram description in a `<pre class='railroad'>` element - it'll get replaced by an appropriate `<svg>` element.

The Diagram Language
--------------------

Diagrams are described by a custom DSL that somewhat resembles Python.

A railroad diagram consists of a number of nested elements, each of which may contain multiple children.  Each element is specified as a command followed by a colon, possibly followed by additional data (the prelude), and the element's children indented on following lines, like:

```js
T: /*
ZeroOrMore:
	N: anything but * followed by /
T: */
```

This draws the following diagram:

<img width=497 height=81 src='https://rawgithub.com/tabatkins/bikeshed/master/docs/rr2.svg'>

The top-level elements are assumed to be a sequence of elements in the diagram.
Inside of a diagram, any of the elements may be used.
Elements are split into two groups: containers and text.

The containers hold other elements, and modify their semantics:

* **Sequence** - used for sequences of elements which must all be selected in order.  Like concatenation in regexes. Takes 1 or more children.
* **Choice** - used for a choice between elements.  Like the `|` character in regexes.  Takes 1 or more children.  Optionally, the "default" index may be provided in the prelude (defaulting to 0).
* **Optional(child, skip?)** - used for an element that's optional.  Like the `?` character in regexes.  Takes 1 child.  Optionally, the word `skip` may be provided in the prelude to indicate that this term is skipped by default.
* **OneOrMore(child, repeat?)** - used for an element that can be chosen one or more times.  Like the `+` character in regexes.
Takes 1 or 2 children: the first child is the element being repeated, and the optional second child is an element repeated between repetitions.
* **ZeroOrMore(child, repeat?, skip?)** - same as OneOrMore, but allows the element to be chosen zero times as well (skipped entirely).  Like the `*` character in regexes.

The text elements only contain text, not other elements.  Their values are given in their preludes.

* **Terminal(text)** - represents a "terminal" in the grammar, something that can't be expanded any more.  Generally represents literal text.
* **NonTerminal(text)** - represents a "non-terminal" in the grammar, something that can be expanded further.
* **Comment(text)** - represents a comment in the railroad diagram, to aid in reading or provide additional information.  This is often used as the repetition value of a OneOrMore or ZeroOrMore to provide information about the repetitions, like how many are allowed.
* **Skip()** - represents nothing, an empty option.  This is rarely necessary to use explicitly, as containers like Optional use it automatically, but it's occasionally useful when writing out a Choice element where one option is to do nothing.

All of the elements can be written in a shorter form as well, to make the railroad diagram code more compact and easier to write:

* Sequence may be shortened to **And** or **Seq**.
* Choice may be shortened to **Or**.
* Optional may be shortened to **Opt**.
* OneOrMOre may be shortened to **Plus**.
* ZeroOrMore may be shortened to **Star**.
* Terminal may be shortened to **T**.
* NonTerminal may be shortened to **N**.
* Comment may be shortened to **C**.
* Skip may be shortened to **S**.

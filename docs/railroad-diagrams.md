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

```plain
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

* **Sequence** (**And**, **Seq**) - used for sequences of elements which must all be selected in order.  Like concatenation in regexes. Takes 1 or more children.
* **Choice** (**Or**) - used for a choice between elements.  Like the `|` character in regexes.  Takes 1 or more children.  Optionally, the "default" index may be provided in the prelude (defaulting to 0).
* **Optional** (**Opt**)- used for an element that's optional.  Like the `?` character in regexes.  Takes 1 child.  Optionally, the word `skip` may be provided in the prelude to indicate that this term is skipped by default.
* **OneOrMore** (**Plus**)- used for an element that can be chosen one or more times.  Like the `+` character in regexes.
	Takes 1 or 2 children: the first child is the element being repeated, and the optional second child is an element repeated between repetitions.
* **ZeroOrMore** (**Star**) - same as OneOrMore, but allows the element to be chosen zero times as well (skipped entirely).  Like the `*` character in regexes.
	Like **Optional**, the keyword `skip` may be provided in the prelude to indicate that the "default option" is to skip it (repeat 0 times).

The text elements only contain text, not other elements.  Their values are given in their preludes.

* **Terminal** (**T**) - represents a "terminal" in the grammar, something that can't be expanded any more.  Generally represents literal text.
* **NonTerminal (**N**)** - represents a "non-terminal" in the grammar, something that can be expanded further.
* **Comment** (**C**) - represents a comment in the railroad diagram, to aid in reading or provide additional information.  This is often used as the repetition value of a OneOrMore or ZeroOrMore to provide information about the repetitions, like how many are allowed.
* **Skip** (**S**) - represents nothing, an empty option.  This is rarely necessary to use explicitly, as containers like Optional use it automatically, but it's occasionally useful when writing out a Choice element where one option is to do nothing.

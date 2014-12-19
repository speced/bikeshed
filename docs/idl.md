IDL Processing
==============

Bikeshed can automatically process IDL blocks,
marking up all relevant terms for you without any intervention,
setting up definitions and autolinks as appropriate.

To activate this behavior,
simply place the IDL in the `<pre class='idl'>` element.
Bikeshed will consume the text content of the element
(ignoring any markup you may currently have)
and replace it with marked-up text containing `<dfn>` and `<a>` elements.

In the process of doing this, Bikeshed will also syntax-check your IDL,
and report fatal errors for any mistakes.
Bikeshed's IDL parser, courtesy of Peter Linss, is intended to be forward-compatible with IDL changes,
gracefully emitting unknown constructs unchanged and recovering as well as it can.
If anything isn't recognized when it should be,
or the parser fails in a major, non-graceful way,
please report it as an issue.

Putting Definitions Elsewhere
-----------------------------

Quite often, you may want to have the actual definition of an IDL term
(the thing that Bikeshed actually links to)
somewhere in your prose near the full definition,
rather than being in the IDL block.

Bikeshed will automatically produce an `<a>` in your IDL,
rather than a `<dfn>`,
if it can find a pre-existing definition of that IDL term,
including local definitions in the current spec.
However, you have to mark up the definition correctly to get this to work,
or else Bikeshed will fail to recognize there's an external definition
and will mark up the IDL with a `<dfn>` as well.

In particular, method and attribute definitions need to have their `for` value set to the interface they're a part of
(and similar with dictionary members).
Methods have some further complexity -
they should have their definition text set to contain the names of all their arguments.

For example, take the following example IDL:

```
interface Foo {
	void bar(DOMString baz, optional long qux);
};
```

To have Bikeshed recognize a definition for the `bar()` method placed elsewhere,
it must look something like `<dfn method for=Foo title="bar(baz, qux)">bar(DOMString baz, optional long qux)</dfn>`.

Additionally, it *should* define alternate linking texts for omittable arguments,
like `<dfn method for=Foo title="bar(baz, qux)|bar(baz)">bar(DOMString baz, optional long qux)</dfn>`.
This way any valid call signature can be used to autolink.
Note that arguments are omittable if they're marked with `optional`, or are variadic (like `long... qux`), or have a default value.
Nullable arguments (like `long? qux`) are not omittable.
(If you are fine with the `<dfn>` being in the IDL block,
Bikeshed will do all of this for you.)

Unless all arguments can be omitted, the definition text *should not* have an alternative with empty args.
For convenience, however, Bikeshed will allow *autolinks* with empty argument lists to work,
as long as it can resolve the link unambiguously.
For example, `{{Foo/bar()}}` will autolink to the method defined above,
despite it not being a valid call signature,
as long as there isn't an overload of `bar()` that it might also apply to.

(The above applies to all functionish types: method, constructor, stringifier, etc.)

Marking up argument definitions is similar.
To mark up the `baz` argument of the above method, for example,
do `<dfn argument for="Foo/bar(baz, qux)">baz</dfn>`.
You *should* use the full call signature of the method.

Linking to Stringifiers
-----------------------

Linking to a stringifier is a little complicated,
because WebIDL allows *four* different syntaxes for it.

The `stringifier` keyword itself is always linkable;
it's a "dfn" type definition with `for=MyInterface`
and linking text "stringification behavior".
Like any other IDL construct,
you can instead define the term yourself in the same way,
and the IDL will link to your definition instead,
like `<dfn dfn for=MyInterface>stringification behavior</dfn>`.
This is generally what you *should* use to link to the stringifier,
as it'll maintain the links even if you change which syntax form you use.

If you use the "stringifier attribute" form,
like `stringifier attribute DOMString href;`,
you can also just link/dfn the attribute as normal.

If you use the "stringifier method" form,
like `stringifier DOMString foo(long bar);`,
you can also just link/dfn the method as normal,
like `<dfn stringifier for=MyInterface>foo(bar)</dfn>.
(Note that it's a "stringifier" type definition,
not "method".)

If you use the "*anonymous* stringifer method" form,
like `stringifier DOMString(long bar)`,
you can still technically link/dfn it as a stringifier method.
It doesn't have a name, so we invent one -
it's called `__stringifier__()`, a la Python's magic methods.
(Note the *two* underscores on each side.)
You should *almost* never need to do this;
the only reason to need to specify the method name
(rather than just linking to the keyword, as described above)
is if you're linking/dfning an argument to the method,
and need to specify a `for` value for it.



Forcing Definitions
-------------------

Bikeshed decides whether a significant term should be a link or a definition
based on whether a definition for the term already exists or not.
This means, unfortunately, that you can't redefine an already-existing term,
at least not via the IDL block,
even if you intend to obsolete the prior definition.

This behavior can be tweaked if necessary.
Simply add a `force` attribute to the `<pre>`,
containing a list of [global names](global-names.md).
The corresponding terms in that IDL block will be forced into becoming definitions,
even if a definition for them already exists elsewhere.

Turning Off Processing
----------------------

If for whatever reason you don't want your IDL block to be processed by Bikeshed,
simple use another element, or another class.
If you really want to use `<pre class=idl>`,
you can add a `data-no-idl` attribute to the element.
Bikeshed will leave these elements alone.

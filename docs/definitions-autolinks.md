Definitions
===========

Defining a term is as easy as wrapping a `<dfn>` element around it.
Most of the time, this is all you'll need to do -
the definition automatically gains an id,
and is usually automatically exposed as an autolink target for local and cross-spec autolinks.

**Autolinking** is a special mechanism in the processor to let you link terms to their definitions without having to explicitly provide a url.
Instead, the text of the link is matched against the text of the definitions,
and if a match is found,
the link's `href` is set up to connect the two.

Changing the Linking Text
-------------------------

Sometimes, the text of the definition isn't exactly what you want it to be linked by,
or you may want it to be linkable with more than one phrase.
For example, an algorithm named "Check if three characters would start an identifier"
may also want to be linkable from the phrase "starts with an identifier".
To alter the linking text, simply add a `title` attribute to the definition;
the title text is used instead of the text content.
You can separate multiple linking phrases by separating them with the pipe "|" character.

Defining Extra-Short "Local" Linking Texts
------------------------------------------

Sometimes you want to use an extra-short version of a term for within a spec,
but don't want to confuse things by exporting it globally.
To achieve this, add a `local-title` attribute with the terms you want to be only usable within the spec;
the syntax is identical to that of the `title` attribute, described above.

Using local linking text does not disturb the normal linking-text process;
that still takes from either the element text or the `title` attribute,
as normal.

Definition Types
----------------

All definitions have a definition type.
This allows for "namespacing" of the linking text,
so you can define, for example, both a property and a term with the same linking text, such as "direction" or "color".

There are several types for CSS values:

* property
* descriptor (the things inside at-rules like @font-face)
* value (any value that goes inside of a property, at-rule, etc.)
* type (an abstract type, like `<length>` or `<image>`)
* at-rule
* function (like counter() or linear-gradient())
* selector

There are additional types for WebIDL definitions:

* interface
* constructor
* method
* argument
* attribute
* callback
* dictionary
* dict-member
* exception
* except-field
* exception-code
* enum
* const
* typedef
* stringifier
* serializer
* iterator

And for HTML/SVG/etc element definitions:

* element
* element-attr

A special type just for definitions of operators used in grammar definitions,
like `||` and similar:

* grammar

And finally, a catch-all category for general terms and phrases, and anything that doesn't fall into one of the above categories:

* dfn

The processor will attempt to infer your definition type from the context and text content of the definition:

* Is it inside a propdef, descdef, or elementdef block?  Then it's a **property**, **descriptor**, or **element**.
* Is it inside an idl block (`<pre class='idl'>`)?  Then it's an **one of the IDL types, inferred by parsing the IDL**.
* Does it start with an `@`?  Then it's an **at-rule**.
* Is it surrounded by `<>`?  Then it's a **type**.
* Does it start with a `:`?  Then it's a **selector**.
* Does it end with `()`?  Then it's a **function**.
* Is it surrounded by double single quotes in the source, like `''foo''`?  Then it's a **value**.
* Otherwise, it's a **dfn**.

Note that this auto-detection is a **last-resort** operation.
There are methods (defined below) to explicitly indicate what type a definition is,
and those win over the auto-detection.

If your value doesn't fit one of these categories,
you'll have to tag it manually.
Just add the type as a boolean attribute to the definition, like

~~~~html
  attribute DOMString <dfn attribute>name</dfn>;
~~~~

Alternately, if you've got several definitions of the same type that share some container element (such as a `<pre>` or `<dl>`),
just add a `dfn-type="type-goes-here"` attribute to the container.
Anything which isn't explicitly tagged otherwise will take that type by default.

(There are more methods to determine definition type, but they're only meant for legacy content, and so are not documented here.)

Specifying What a Definition is For
-----------------------------------

Some types of definitions are defined relative to a higher construct,
such as values for a particularly property,
or attributes of a particular IDL interface.
This is useful, as it means these names don't have to be globally unique,
but that means your autolinks may have a hard time telling which name you intend to link to.

To fix this, the processor enforces that some types of definitions *must* define what they are for.
This is specified with a `for=''` attribute on the definition.

Specifically:

* "attribute", "constructor", "method", and "const" definitions must define what interface they're relative to.
* "argument" definitions must define what method or constructor they're relative to.
* "dict-member" definitions must define what dictionary they're relative to.
* "except-field" and "exception-code" definitions must define what exception they're relative to.
* "descriptor" definitions must define what at-rule they're relative to.
    (This happens automatically if you add a "For" line to the descdef table.)
* "value" definitions must define what property, descriptor, at-rule, type, selector, or function they're relative to.
    If a value definition is relative to a descriptor, the value must be of the form "@foo/bar", where "@foo" is the at-rule the "bar" descriptor is relative to.

Just like with the definition type, you can instead declare what several definitions are for by putting an attribute on a container.
In this case, just add `dfn-for=''` to the container.
This is especially useful for property/descriptor values, as they're usually defined in a `<dl>`,
or IDL definitions, as you can just put a `dfn-for`	on the `<pre class='idl'>`.

Exporting Definitions
---------------------

Most definitions are automatically "exported",
which means they're made available for other specs to autolink to.
The only exception is "dfn" type definitions, which aren't exported by default.

To force a link to be exported, add an `export` boolean attribute to it.
To force a link *not* to be exported, add a `noexport` boolean attribute instead.
Like the other attributes, you can instead add this to a container to have it be a default for the definitions inside.

Providing Custom Definitions
----------------------------

If you want to link to dfns in specs that aren't yet part of the autolinking database,
you can provide your own definition data that Bikeshed can use.
Within a `<pre class='anchors'>` element,
define the anchors you need in [InfoTree format](infotree.md),
with the following keys:

* **text** - the linking text for the definition. (Exactly 1 required.)
* **type** - the definition's type (dfn, interface, etc)  (Exactly 1 required.)
* **urlPrefix** and/or **url** - define the anchor's url, as described below.  (At least one of `urlPrefix` or `url` must be specified. 0+ `urlPrefix` entries allowed, 0 or 1 `url` entries allowed.)

To generate the url for the anchor,
first all of the `urlPrefix` entires are concatenated.
If a `url` is provided,
it's appended to the prefixes;
otherwise, the `text` is url-ified and appended.
(Lowercased, spaces converted to dashes, non-alphanumeric characters dropped.)
If neither `urlPrefix` nor `url` had a "#" character in them,
one is inserted between them.

Example:

```html
<pre class="anchors">
urlPrefix: https://encoding.spec.whatwg.org/; type: dfn
  text: ascii whitespace
  text: decoder
url: http://www.unicode.org/reports/tr46/#ToASCII; type: dfn; text: toascii
</pre>

<a>ascii whitespace</a> links now!
```

Alternately, this data can be provided in a file named `anchors.bsdata`,
in the same folder as the spec source.


Autolinking
===========

The processor supports "autolinks" for easy linking to terms without having to fiddle around with urls.
Instead, just match up the text of the link to the text of the definition!

In its most basic form, autolinks are just `<a>` elements without `href=''` attributes.
The processor takes this as a signal that it should attempt to automatically determine the link target.
It compares the text content of the link to the text content of all the definitions in the page or in the cross-ref data,
and if it finds a match,
automatically sets the `href` appropriately to point at the relevant definition.

Like definitions, you can override the linking text by setting a `title=''` attribute.
Unlike definitions, you can't separate multiple linking phrases by the bar "|" character,
as that doesn't make sense for links.

Setting an empty title attribute turns off autolinking entirely,
if for whatever reason you need to do so.

There are several additional shortcuts for writing an autolink:
* `'foo'` (apostophes/straight quotes) is an autolink to a property or descriptor named "foo"
* `''foo''` (double apostrophes) is an autolink to any of the CSS definition types except property and descriptor
* `<<foo>>` is an autolink to a type/production named "&lt;foo>"
* `<<'foo'>>` is an autolink to the the property or descriptor named "foo" (used in grammars, where you need `<foo>` for non-terminals)
* `<<foo()>>` is an autolink to the function named "foo" (same)
* `<<@foo>>` is an autolink to the at-rule named "@foo" (same)
* `{{foo}}` is an autolink to one of the IDL types for the term "foo".
* `[[foo]]` is an autolink to a bibliography entry named "foo", and auto-generates an informative reference in the biblio section.
    Add a leading exclamation point to the value, like `[[!foo]]` for a normative reference.
* `[[#foo]]` is an autolink to a heading in the same document with the given ID.  (See [Section Links](#section-links) for more detail.)
* `<{element}>` is an autolink to the element named "element".
* `<{element/attribute}>` is an autolink to the attribute named "attribute" for the element "element".

For any of the above shorthands that can have a "for" value, you can indicate this inline by preceding the linking text with the "for" value and separating it with a slash. For example, to disambiguate that you want the "foo" value from the "prop1" property (rather than "prop2", which also has a "foo" value), you can write:

```
''prop1/foo''
```

The "for" value will not be shown in the processed document; it's extracted and stashed in metadata for the link instead.

Similarly, any of the above types except biblio links can have their type specified explicitly, by *appending* the type and separating it with a double bang, like the following to indicate that you want the *attribute* named "bar", rather than the dictionary member of the same name:

```
{{bar!!attribute}}
```

Again, the type value won't be shown in the processed document.

These two techniques can, of course, be combined.

Link Types
----------

Links have the same types as definitions, with a few additional "union" types that are used by the shortcut forms.
While you shouldn't specify them explicitly,
they'll show up in error messages sometimes,
so here's a list of them:

* "propdesc" - used by the `'foo'` shorthand.  A union of "property" and "descriptor".
* "functionish" - used by the `''foo''` shorthand for things that look like functions.  A union of "function" and "method".
* "maybe" - used by the rest of the `''foo''` shorthand values.  A union of "dfn" and all the CSS types except "property" and "descriptor".
    For legacy reasons, this link type has the additional magic that it doesn't flag an error if it can't find any matches,
    because it's also used to annotate inline CSS code fragments.

Additionally, there's an "idl" link type which *is* intended to be used by authors.
It's a union of all the WebIDL types,
and exists because the WebIDL types are somewhat verbose,
so simply putting "idl" as the type on an IDL-heavy container can eliminate the need to individually specify types most of the time.

When you actually run the processor, you may get errors about there being too many possible references to choose from.
The processor will continue to run anyway, but its default choice might be the wrong definition.
There are three things you might have to do to fix these:

1. Specify the type explicitly, if the link isn't being processed as the correct type.
    Like definitions, this can be done by just adding the type as a boolean attribute on the link,
    or by adding a `link-for=''` attribute to a container.
    If the link is using shorthand syntax, you can use the `!!type` suffix to specify the type.

2. If the link type corresponds to one of the definition types that needs `for` to be specified,
    you may need to specify `for` on the link as well to narrow down which definition you're referring to.
    For example, many properties define an "auto" value;
    to link to the "auto" value of the 'width' property in particular,
    specify `<a value for=width>auto</a>`,
    or the shorthand syntax `''width/auto''.
    To refer to a value of a descriptor,
    you *can* be completely explicit and specify the at-rule as well,
    like `<a value for='@counter-style/system'>numeric</a>`,
    but you're allowed to omit the at-rule if there are no other properties or descriptors with the same name,
    like `''system/numeric''`.
    This might trigger errors in the future if a conflicting property or definition gets added later,
    but it keeps your links shorter for now.

    Again, you can specify a `link-for=''` attribute on a container to default it for all the autolinks inside the container.

3. If multiple specs define the same property, you may need to declare which spec you're referring to.
    (The processor is smart enough to automatically figure out which one you probably want in many cases.)
    Just add a `spec=''` attribute with the spec's shortname to either the link or a container.
    This can also be specified in the spec's [metadata](metadata.md) with "Link Defaults",
    which applies document-wide.
    (There is no shorthand syntax for specifying this; if you need to add this to a shorthand autolink, you must first convert it into an explicitly `<a>` element.)

As a final note, the autolinking algorithm will link differently based on whether the spec being processed is an "unofficial" or "official" draft.
If "unofficial" (ED, UD, etc.), it'll prefer to link to other EDs, and will only link to TRs if no ED version of that spec exists.
(If a definition only exists in the "official" draft but not the editor's draft,
that almost certainly means it's been deleted since the official draft was last published,
and thus shouldn't be linked to.)
On the other hand, "official" (WD, CR, etc.) specs will preferentially link to other official specs.
A future version of the processor will likely enforce the W3C's linking policy more strongly:
preventing CRs from linking to EDs at all,
preventing RECs from linking to anything below CR,
etc.

If you need to override the processor's choice for which status to link to for a particular link,
provide a `status=''` attribute containing either "ED" or "TR" on the link or a container.

Linking to Unexported Definitions
---------------------------------

Most definition types are automatically exported and made available for cross-linking,
but "dfn" type definitions aren't,
because specs often define terms for their own internal use that aren't meant to be used outside the spec
(and in particular, aren't named in a way so as to avoid collisions).

If a spec contains a "dfn" type definition that you want to link to,
but it's not marked for export
(either intentionally, or because it was accidentally missed and fixing the spec would be time-consuming),
using the `spec=''` attribute (defined above) will override the lack of an export declaration,
and go ahead and link to it anyway.


Section Links
-------------

Sometimes you want to link to a section of a document,
rather than a specific definition.
Bikeshed has section links to handle this case more easily:

```html
[[#heading-id]]
```

renders as:

```html
<a href="#heading-id">§6.1 The Example Section</a>
```

Note that this is quite different from normal autolinks;
rather than matching on text and letting Bikeshed fill in the href,
you match on href and let Bikeshed fill in the text.
This is because section titles change much more often than definition texts,
so using text-based matching is fragile;
on the other hand,
their IDs tend to be stable,
as they're often linked to.
Also, the section titles are often long and annoying to type,
and they move around,
so numbering isn't stable.

Note how Section Links have a similar syntax to Bibliography Links;
these will soonish merge,
allowing you to link to sections in other documents
(at least, when Bikeshed has section information for them).


Bibliography
============

Bibliographical references form a special class of autolinks.
They're typically added *only* via the shorthands
`[[FOO]]` for informative references
and `[[!FOO]]` for normative references.

Some biblio entries come with multiple sets of urls;
at present, Bikeshed tracks a single "current" url and a single "dated" url.
In the W3C, for example, this maps to Editors Drafts and things in /TR space.
You can specify which url to use by specifying "current" or "dated" within the biblio shorthand,
like `[[FOO current]]`,
or specify the default url to choose for all your biblio refs with the ["Default Biblio Status" metadata](metadata.md).

If, for whatever reason, you need to craft a bibliography link manually,
add `data-link-type=biblio`, `data-biblio-type=[normative | informative]`, and `data-biblio-status=[current | dated]` attributes to the link.

Unlike regular autolinks,
which link to `<dfn>` elements,
biblio autolinks cause the spec to generate entries in its "References" section,
and then link to that instead.
The biblio database is also entirely separate from the normal definitions database,
and can be found at <http://dev.w3.org/csswg/biblio.ref>.
A version of this file is included in the processor's repository,
and the data doesn't change often,
so it should be sufficient.

The bibliography database is completely separate from the autolinking database,
and comes from multiple sources.
The default data comes from the [SpecRef project](https://github.com/tobie/specref)
and [the CSSWG's own biblio file](http://dev.w3.org/csswg/biblio.ref)
(preferring SpecRef's information when the same name appears in both).

You can also add your own bibliography data,
following the SpecRef JSON format:

```json
{
    "foo-bar": {
        "authors": [
            "Tab Atkins",
            "Dirk Schultze"
        ],
        "href": "http://www.w3.org/TR/foo-bar/",
        "title": "Foo Bar Level 1",
        "status": "CR",
        "publisher": "W3C",
        "deliveredBy": [
            "http://www.w3.org/html/wg/"
        ]
    }
}
```

Only the "title" field is strictly necessary;
the rest can be omitted if desired.

This JSON should either be inline, in a `<pre class=biblio>` block,
or in a `biblio.json` file in the same folder as the spec file.

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

Conjugating/Pluralizing/etc the Linking Text
--------------------------------------------

Bikeshed can automatically handle a wide range of English conjugations and pluralizations.
For example, if you define the term "snap",
you can link to it with "snapping" or "snapped"
without having to manually add those variations to your `<dfn>` manually.

As such, it's best to define your term in the "base" form,
singular and present tense.
Use `lt='...'` if necessary to set up the correct "base" linking text,
if your visible text needs to be in a conjugated form due to the surrounding text.

These variations only work for the *last* word in a phrase.
If you have a longer phrase where it's a middle word that conjugates differently,
you do still have to manually handle that,
either by defining multiple linking texts on the `<dfn>`,
or by manually specifying the linking text on the `<a>`.

Changing the Linking Text
-------------------------

Sometimes, the text of the definition isn't exactly what you want it to be linked by,
or you may want it to be linkable with more than one phrase.
For example, an algorithm named "Check if three characters would start an identifier"
may also want to be linkable from the phrase "starts with an identifier".
To alter the linking text, simply add an `lt` attribute (for "Linking Text") to the definition;
the linking text is used instead of the text content.
You can separate multiple linking phrases by separating them with the pipe "|" character.

Defining Extra-Short "Local" Linking Texts
------------------------------------------

Sometimes you want to use an extra-short version of a term for within a spec,
but don't want to confuse things by exporting it globally.
To achieve this, add a `local-lt` attribute with the terms you want to be only usable within the spec;
the syntax is identical to that of the `lt` attribute, described above.

Using local linking text does not disturb the normal linking-text process;
that still takes from either the element text or the `lt` attribute,
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
* type (an abstract type for CSS grammars, like `<length>` or `<image>`)
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
* enum
* enum-value
* exception (for new DOMException names)
* const
* typedef
* stringifier
* serializer
* iterator
* maplike
* setlike
* extended-attribute (things like `[EnforceRange]`)

And for HTML/SVG/etc element definitions:

* element
* element-state (a spec concept, like `<input>` being in the "password state")
* element-attr
* attr-value

A special type for URL schemes, like "http" or "blob":

* scheme

A special type for HTTP headers:

* http-header

A special type just for definitions of operators used in grammar definitions,
like `||` and similar:

* grammar

And finally, some categories for "English" terms:

* abstract-op (for "English-language algorithms")
* dfn (for general terms and phrases, and a catch-all for anything else)

The processor will attempt to infer your definition type from the context and text content of the definition:

* Is it inside a propdef, descdef, or elementdef block?  Then it's a **property**, **descriptor**, or **element**.
* Is it inside an idl block (`<pre class='idl'>`)?  Then it's an **one of the IDL types, inferred by parsing the IDL**.
* Does it start with an `@`?  Then it's an **at-rule**.
* Is it surrounded by `<>`?  Then it's a **type**.
* Does it start with a `:`?  Then it's a **selector**.
* Does it end with `()`?  Then it's a **function**.
* Is it surrounded by double single quotes in the source, like `''foo''`?  Then it's a **value**.
* Otherwise, it's a **dfn**.

(This auto-detection is obviously skewed towards CSS types; Bikeshed started as a CSS spec preprocessor, and the CSS types are easier to auto-detect syntactically than anything else.)

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

* "attribute", "constructor", "method", "const", "event", "serializer", "stringifier", and "iterator" definitions must define what interface they're relative to.
* "argument" definitions must define what method or constructor they're relative to.
* "dict-member" definitions must define what dictionary they're relative to.
* "except-field" and "exception-code" definitions must define what exception they're relative to.
* "enum-value" definitions must define what enum they're relative to
* "element-attr" and "element-state" definitions must define what element they're relative to.
* "attr-value" definitions must define what element and attribute they're relative to.
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
* **for** - what the definition is for.  (Any number allowed, including 0.)
* **spec** - Which spec the definition comes from. (optional)

To generate the url for the anchor,
first all of the `urlPrefix` entries are concatenated.
If a `url` is provided,
it's appended to the prefixes;
otherwise, the `text` is url-ified and appended.
(Lowercased, spaces converted to dashes, non-alphanumeric characters dropped.)
If neither `urlPrefix` nor `url` had a "#" character in them,
one is inserted between them.

The `spec` attribute is used only for index generation, and has no effect on URL generation.

Example:

```html
<pre class="anchors">
urlPrefix: https://encoding.spec.whatwg.org/; type: dfn; spec: ENCODING
  text: ascii whitespace
  text: decoder
url: http://www.unicode.org/reports/tr46/#ToASCII; type: dfn; text: toascii
</pre>

<a>ascii whitespace</a> links now!
```

Alternately, this data can be provided in a file named `anchors.bsdata`,
in the same folder as the spec source, but this prevents you from using
[the web service](https://api.csswg.org/bikeshed/).


Autolinking
===========

The processor supports "autolinks" for easy linking to terms without having to fiddle around with urls.
Instead, just match up the text of the link to the text of the definition!

In its most basic form, autolinks are just `<a>` elements without `href=''` attributes.
The processor takes this as a signal that it should attempt to automatically determine the link target.
It compares the text content of the link to the text content of all the definitions in the page or in the cross-ref data,
and if it finds a match,
automatically sets the `href` appropriately to point at the relevant definition.

Like definitions, you can override the linking text by setting a `lt=''` attribute.
Unlike definitions, you can't separate multiple linking phrases by the bar "|" character,
as that doesn't make sense for links.

Setting an empty lt attribute turns off autolinking entirely,
if for whatever reason you need to do so.

There are several additional shortcuts for writing an autolink.

The Dfn variety (controlled by `Markup Shorthands: dfn yes`):

* `[=foo=]` is an autolink to the "dfn" type definition "foo".

The CSS varieties (controlled by `Markup Shorthands: css yes`):

* `'foo'` (apostophes/straight quotes) is an autolink to a property or descriptor named "foo". If there is both a property and a descriptor of a given name, this defaults to linking to the property if used in its bare (`'foo'`) form.
* `''foo''` (double apostrophes) is an autolink to any of the CSS definition types except property and descriptor
* `<<foo>>` is an autolink to a type/production named "&lt;foo>"
* `<<'foo'>>` is an autolink to the the property or descriptor named "foo" (used in grammars, where you need `<foo>` for non-terminals).
* `<<foo()>>` is an autolink to the function named "foo" (used in grammars)
* `<<@foo>>` is an autolink to the at-rule named "@foo" (used in grammars)

The IDL variety (controlled by `Markup Shorthands: idl yes`):

* `{{foo}}` or `{{foo()}}` is an autolink to one of the IDL types (interface, method, dictionary, etc) for the term "foo".

The markup (HTML/etc) varieties (controlled by `Markup Shorthands: markup yes`):

* `<{element}>` is an autolink to the element named "element".
* `<{element/attribute}>` is an autolink to the attribute or element-state named "attribute" for the element "element".

The bibliography/spec varieties (controlled by `Markup Shorthands: biblio yes`):

* `[[foo]]` is an autolink to a bibliography entry named "foo", and auto-generates an informative reference in the biblio section.
    Add a leading exclamation point to the value, like `[[!foo]]`, for a normative reference.
    If both a "current" and "dated" bibliography entry exists for that entry,
    Bikeshed will prefer the "current" one by default
    (but this can be controlled by the `Default Biblio Status` metadata).
    To explicitly link to one or the other, specify it after the name,
    like `[[foo current]]`.
* `[[#foo]]` is an autolink to a heading in the same document with the given ID.  (See [Section Links](#section-links) for more detail.)
* `[[foo#bar]]` is an autolink to the heading with ID "bar" in the spec whose leveled shortname is "foo". (This only works for specs known to Bikeshed's autolinking database, which is distinct from its bibliography database.)  If linking into a multi-page spec and the desired ID shows up on multiple pages, write it like `[[spec/page#id]]`, where `page` is the filename (without extension) of the page being linked to. Or to link just to the page itself, rather than any particular heading, write `[[spec/page]]`.

---

Any of the above shorthands (besides the biblio varieties) can, if they're specifying a link type that can have a for='' value, specify that explicitly by prepending the for='' value and separating it with a `/`, like the following to indicate that you want the "bar" attribute of the "Foo" interface (rather than of some other interface):

```
{{Foo/bar}}
```

If the for='' value is itself of a type that can have a for='' value, you can prepend more specifiers if necessary, like `''@foo/bar/baz''` to refer to the "baz" value for the "bar" descriptor of the "@foo" at-rule.

If you need to explicitly refer to the definition instance *without* a for='' value
(which would be written as `<a for="/">foo</a>` in normal markup),
just use the slash with nothing preceding it,
like `[=/foo=]`

Any of the above shorthands (besides the biblio varieties) that encompass multiple types can have their type specified explicitly, by *appending* the type and separating it with a `!!`, like the following to indicate that you want the *IDL attribute* named "bar", rather than the dictionary member of the same name:

```
{{bar!!attribute}}
```

Any of the above shorthands (**including** the biblio varieties) can override their default display text (the term you're autolinking) with some other explicitly specified text, by appending the new text and separating it with a `|`, like the following to indicate you want to link to the "do foo" term but display "when foo is done":

```
[=do foo|when foo is done=]
```

If both specifying the type and overriding the display text, put the type-specifier first *then* the desired display text, like:

```
{{bar!!attribute|the bar attribute}}
```





Link Types
----------

Links have the same types as definitions, with a few additional "union" types that are used by the shortcut forms.
While you shouldn't specify them explicitly,
they'll show up in error messages sometimes,
so here's a list of them:

* "propdesc" - used by the `'foo'` shorthand.  A union of "property" and "descriptor".
* "functionish" - used by the `''foo()''` shorthand for things that look like functions.  A union of "function", "method", "constructor", and "stringifier".
* "maybe" - used by the rest of the `''foo''` shorthand values.  A union of "dfn" and all the CSS types except "property" and "descriptor".
    For legacy reasons, this link type has the additional magic that it doesn't flag an error if it can't find any matches,
    because it's also used to annotate inline CSS code fragments.
* "idl" - used by the `{{foo}}` shorthand. A union of all the IDL types.
* "idl-name" - used by the IDL auto-parser. A union of all the IDL types that can declare IDL argument types, like "interface", "enum", or "dictionary".
* "element-sub" - used by the `<{foo/bar}>` shorthand. A union of "element-attr" and "element-state".

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
    or the shorthand syntax `''width/auto''`.
    To refer to a value of a descriptor,
    you *can* be completely explicit and specify the at-rule as well,
    like `<a value for='@counter-style/system'>numeric</a>`,
    but you're allowed to omit the at-rule if there are no other properties or descriptors with the same name,
    like `''system/numeric''`.
    This might trigger errors in the future if a conflicting property or definition gets added later,
    but it keeps your links shorter for now.

    Again, you can specify a `link-for=''` attribute on a container to default it for all the autolinks inside the container.
    Alternately, you can specify `link-for-hint=''` on a container,
    which'll use the hint as the for value *if possible*
    (if doing so wouldn't eliminate all the possible links).
    This is useful if some container has a bunch of links for a given property, say,
    but *some* of the links are to other things entirely;
    using `link-for` means you have to manually specify the other links aren't for anything,
    but `link-for-hint` is more "do what I mean".

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


Configuring Linking Defaults
----------------------------

When there are multiple definitions for a given term
and Bikeshed can't automatically tell which one you want,
it'll emit a warning asking you to specify more explicitly.
You can do this per-link,
but you typically want to make the same choice every time the term is autolinked;
this can be done by adding Link Defaults metadata.

You can either add a Link Defaults metadata line to your `<pre class=metadata>`,
as specified in [metadata](metadata.md),
or add a `<pre class='link-defaults'>` block,
written in the [InfoTree](infotree.md) format.
For the latter,
each piece of info must have a `spec`, `type`, and `text` line,
and optionally a `for` line if necessary to further disambiguate.

Sometimes this is too fine-grained,
and you'd actually like to completely ignore a given spec when autolinking,
always preferring to link to something else.
To do this, add a `<pre class='ignored-specs'>` block,
written in the [InfoTree](infotree.md) format.
Each piece of info must have a `spec` line,
and optionally a `replacedBy` line,
both naming specs.
If the info has just a `spec` line, that spec is ignored totally by default;
linking to it requires you to manually specify a `spec=''` attribute on the autolink.
If the info has a `replacedBy` line,
then whenever an autolink has a choice between the two specs,
it'll delete the `spec` value from consideration,
leaving only the `replacedBy` value
(plus any other specs that might be providing a definition).


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

You can also use **cross-spec** section links,
as long as the spec is either in Bikeshed's linking database,
or the biblio database.
The syntax is a mixture of a biblio reference and a section link:

```html
[[css-flexbox-1#auto-margins]]
[[CSS-access-19990804#Features]]
```

which renders as:

```html
<a href="https://drafts.csswg.org/css-flexbox-1/#auto-margins">CSS Flexbox 1 §8.1 Aligning with auto margins</a>
<a href="http://www.w3.org/1999/08/NOTE-CSS-access-19990804#Features">Accessibility Features of CSS §Features</a>
```

If Bikeshed knows about the spec,
it link-checks you,
and fills in the section number and heading in the generated text.
If the spec is only in the bibliography database,
Bikeshed just assumes that the link target exists
and uses it directly in the text,
because it has no way to tell what the section is named.

If the spec is multipage, like SVG,
and Bikeshed knows about it,
*most* of the time you don't need to do anything different -
Bikeshed will find the correct page for the heading you're linking to.
On the rare occasions that the same heading id exists in multiple pages of the same spec, tho,
specify the page like `[[svg/intro#toc]]`
(which indicates the #toc heading on the intro.html page).
If the desired heading is on the top-level page,
use an empty page name, like `[[html/#living-standard]]`.
In any case, Bikeshed will throw an error,
and tell you what names it knows about so you can easily correct your link.



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

This JSON should be inline, in a `<pre class=biblio>` block.  It can
also be in a `biblio.json` file in the same folder as the spec file,
but this is incompatible with
[the web service](https://api.csswg.org/bikeshed/).

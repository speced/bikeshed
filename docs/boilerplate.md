Boilerplate Generation
======================

The processor automatically generates nearly all of a spec's boilerplate,
the text that is repeated nearly identically across all specs.

Generally, you won't need to understand what's going on here in order to use the processor - it'll just automatically do the right thing.

For help in creating *new* boilerplate files for your organization, see [Creating New Boilerplate Files](creating-boilerplate.md).

Groups
------

Much of the boilerplate is determined based on the "Group" metadata.
If unspecified, it defaults to a generic set of boilerplate that is generally appropriate for most things,
without making reference to any particular standards body or the like.
However, to obtain correct boilerplate for a given standards body,
"Group" can be used.

Several groups are already accommodated with appropriate inclusion files:

* "csswg", as mentioned.
* “dap”, for the Device APIs Working Group
* "fxtf", for the FX Task Force
* "svg", for the SVG Working Group
* "webappsec", for the WebApps Security Working Group
* "whatwg", for the WHATWG

You can put whatever value you want into the "Group" value, though.
Unrecognized values will just use the default boilerplate files.
If you want to add specialized boilerplate files for your group,
check out the File-Based Includes section, later in this document,
and write your own files.


Text Macros
-----------

Several text "macros" are defined by the spec's metadata,
and can be used anywhere in the spec to substitute in the spec they stand for by using the syntax `[FOO]`.
Note that this is similar to the syntax for bibliography references, but it has only a single set of `[]` characters.
The following macros are defined:

* [TITLE] gives the spec's full title, as extracted from either the `<h1>` or the spec metadata.
* [H1] gives the desired document heading, in case the in-page title is supposed to be different from the `<title>` element value.
* [SHORTNAME] gives the document's shortname, like "css-cascade".
* [VSHORTNAME] gives the "versioned" shortname, like "css-cascade-3".
* [STATUS] gives the spec's status.
* [LONGSTATUS] gives a long form of the spec's status, so "ED" becomes "Editor's Draft", for example.
* [STATUSTEXT] gives an additional status text snippet.
* [LATEST] gives the link to the undated /TR link, if it exists.
* [VERSION] gives the link to the ED, if the spec is an ED, and otherwise constructs a dated /TR link from today's date.
* [ABSTRACT] gives the document's abstract.
* [ABSTRACTATTR] gives the document's abstract, correctly escaped to be an attribute value.
* [YEAR] gives the current year.
* [DATE] gives a human-readable date.
* [CDATE] gives a compact date in the format "YYYYMMDD".
* [ISODATE] gives a compact date in iso format "YYYY-MM-DD".
* [DEADLINE] gives a human-readable version of the deadline data, if one was specified.
* [LOGO] gives the url of the spec's logo
* [REPOSITORY] gives the name of the VCS repository the spec is located in; this is currently only filled when the spec source is in a GitHub repository. (Patches welcome for more repo-extraction code!)

As these are substituted at the text level, not the higher HTML level, you can use them *anywhere*, including in attribute values.


Boilerplate Sections
--------------------

The location of the boilerplate sections are indicated by elements with `data-fill-with=''` attributes.
If the elements contain anything, they're emptied before being filled with the appropriate boilerplate.
The valid `data-fill-with=''` values are:

* "table-of-contents" for the ToC
* "spec-metadata" for the `<dl>` of spec data that's in the header of all of our specs
* "abstract" for the spec's abstract
* "status" for the status section
* "logo" for the W3C logo
* "copyright" for the W3C copyright statement
* "warning" for the relevant spec warning, if one was indicated in the metadata.
* "references" for the bibliography refs
* "index" for the index of terms (all the `<dfn>` elements in the spec)
* "property-index" for the table summarizing all properties defined in the spec
* "issues-index"

Additionally, "header" and "footer" boilerplate files are used to put content at the start and end of your document.
Most or all of the above boilerplate sections should actually show up here, in the header and footer,
rather than being manually specified in your source file.

### Default Boilerplate ###

Some sections listed above are generated *by default*;
if you don't put an explicitly `data-fill-with` container in your document,
they'll generate anyway (if they have anything to fill themselves with),
appending themselves to the end of the `<body>`.
These sections are:

* all of the indexes: "index", "property-index", and "issues-index"
* "references"

Again, these will only auto-generate if there is something for them to do;
if your spec doesn't define any CSS properties, for example,
the "property-index" boilerplate won't generate.
If you want to suppress their generation even when they do have something to do,
use the `Boilerplate` metadata, like:

```
<pre class="metadata">
Boilerplate: omit property-index
</pre>
```

### Overriding Boilerplate ###

Sometimes a file-based boilerplate (see below) that is appropriate for most of the specs in your group
isn't quite right for your specific spec.
Any boilerplate, file-based or Bikeshed-generated,
can be overriden by custom text of your choosing.
Just add an element to your source document with the content you'd like to show up in place of the offending boilerplate,
and add a `boilerplate="foo"` attribute to the container,
specifying which boilerplate section is being replaced.

Bikeshed will automatically remove that element from you document,
and instead inject its contents in place of the boilerplate that it would normally provide.


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

Headings also automatically gain a self-link pointing to themselves,
to enable people to easily link to sections without having to return to the ToC.


File-based Includes
-------------------

Several of the data-fill-with values
(those that are static, rather than generated from in-document data)
actually come from sets of .include files in the include/ directory.

The base files are simply named "foo.include",
where "foo" is the name of the data-fill-with value.
They can be specialized, however,
to particular working groups,
and to particular document statuses.

Adding a "-group" to the filename, like "header-csswg.include",
specializes it for that group (specified in the spec's metadata).
Adding a "-STATUS" to the filename specializes it for the status (same).
These can be used together, with the group coming first, like "status-csswg-CR.include".

The processor will first look for the "foo-group-STATUS.include" file,
failing over to "foo-group.include",
then "foo-STATUS.include",
and finally "foo.include".

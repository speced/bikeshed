Metadata
========

Crucial to the processor's ability to automatically generate most of a spec's boilerplate is a small metadata section,
typically located at the top of a file.

A metadata block is just a `<pre class='metadata'>` element, like so:

~~~~html
<pre class='metadata'>
Status: ED
TR: http://www.w3.org/TR/css-variables/
ED: http://dev.w3.org/csswg/css-variables/
Shortname: css-variables
Level: 1
Editor: Tab Atkins Jr., Google, http://xanthir.com/contact
Editor: Daniel Glazman, Disruptive Innovations, daniel.glazman@disruptive-innovations.com
Abstract: This module introduces cascading variables as a new primitive value type that is accepted by all CSS properties,
	and custom properties for defining them.
</pre>
~~~~

The syntax of a metadata block is very simple - it's a line-based format, with each line consisting of a key and a value, separated by a colon.
Or if you're adding multiple lines with the same key, you can just start the subsequent lines with whitespace to have it reuse the last-seen key.

Several keys are required information, and will cause the processor to flag an error if you omit them:

* **Title** is the spec's full title.  This can alternately be specified by adding an `<h1>` element as the first line of the spec.
* **Status** is the spec's status, as one of the standard abbreviations ("WD", "ED", "CR", etc.)
* **ED** must contain a link that points to the editor's draft.
* **Shortname** must contain the spec's shortname, like "css-lists" or "css-backgrounds".
* **Level** must contain the spec's level as an integer.
* **Editor** must contain an editor's information.
	This has a special format:
	it must contain the editor's name,
	optionally followed by the editor's affiliation
	(composed of a company name, optionally followed by a link to the company homepage),
	optionally followed by an email address and/or a link to their contact page,
	all comma-separated.
	(To put a comma *in* one of these values, use an HTML character reference: `&#44;`.)
	For example: `Editor: Tab Atkins Jr., Google http://google.com, http://xanthir.com/contact/`

	Multiple "Editor" lines can be used to supply multiple editors.
* **Abstract** must contain an abstract for the spec, a 1-2 sentence description of what the spec is about.
    Multiple Abstract lines can be used, representing multiple lines of content, as if you'd written those multiple lines directly into the document.

There are several additional optional keys:

* **TR** must contain a link that points to the latest version on /TR.
* **Former Editor** must contain a former editor's information, in the same format as "Editor".
* **Warning** must contain either "Obsolete", "Not Ready", "New Version XXX", "Replaced by XXX", "Commit deadb33f http://example.com/url/to/deadb33f replaced by XXX", or "Branch XXX http://example.com/url/to/XXX replaced by YYY" which triggers the appropriate warning message in the boilerplate.
* **Previous Version** must contain a link that points to a previous (dated) version on /TR.  You can specify this key more than once for multiple entries.
* **At Risk** must contain an at-risk feature.  You can specify this key more than once for multiple entries.
* **Group** must contain the name of the group the spec is being generated for.  This is used by the boilerplate generation to select the correct file.  It defaults to "csswg".
* **Status Text** allows adding an additional customized sentence that can be used in the document status section.
* **Ignored Terms** accepts a comma-separated list of terms and won't attempt to link them.  Use these to quiet spurious preprocessor warnings caused by you inventing terms (for example, the Variables spec invents custom properties like 'var-foo'), or as a temporary patch when the spec you want to link to doesn't set up its definitions correctly.
* **Link Defaults** lets you specify a default spec for particular autolinks to link to.  The value is a comma-separated list of entries, where each entry is a versioned spec shortname, followed by a link type, followed by a "/"-separated list of link phrases.
* **Date** must contain a date in YYYY-MM-DD format, which is used instead of today's date for all the date-related stuff in the spec.
* **Deadline** is also a YYYY-MM-DD date, which is used for things like the LCWD Status section, to indicate deadlines.
* **Test Suite** must contain a link to the test suite nightly cover page (like <http://test.csswg.org/suites/css3-flexbox/nightly-unstable>).
* **Mailing List** must contain an email address to be used for mailing lists.
* **Mailing List Archives** must contain a link to the list archives.
* **Issue Tracking** indicates what and where you track issues. It must contain a comma-separated list of locations, each of which consists of the name of the location followed by the url.  (If you use any inline issues, Bikeshed will automatically indicate that as well.)
* **Use `<i>` Autolinks** turns on legacy support for using `<i>` elements as "dfn" autolinks.  It takes a bool-ish value: "yes/no", "y/n", "true/false", or "on/off".  (This only exists for legacy purposes; do not use in new documents. Instead, just use the `<a>` element like you're supposed to.)
* **No Editor** lets you omit the `Editor` metadata without an error. It takes a bool-ish value.  This shouldn't generally be used; even if your organization doesn't privilege editors in any way, putting the organization itself in the `Editor` field meets the intent while still producing useful information for readers of the spec.
* **Default Biblio Status** takes the values "current" or "dated", and selects which URL you want to default to for bibliography entries that have both "current" and "dated" URLs. (You can also specify this per-biblio entry.)
* **Markup Shorthands** lets you specify which categories of markup shorthands you want to use; for example, you can turn off CSS shorthands and reclaim use of single quotes in your spec.  You can still link to things with explicit markup even if the shorthand is turned off.  Its value is a comma-separated list of markup categories and bool-ish values.  The currently-recognized categories are "css", "idl", "biblio" (including section links), and "markup".

You can also provide custom keys with whatever values you want,
by prefixing the key with `!`,
like `!Issue Tracking: in spec`.
Any custom keys are collected together and formatted as entries in the spec's boilerplate header `<dl>`.
Specifying a custom key multiple times will put all the values as `<dd>`s under a single `<dt>` for the key.

Default Metadata
----------------

To specify default metadata for all specs generated for a given group and/or spec status,
add an appropriate "default.include" file to the `include/` folder.
This file must be a JSON file,
with the keys and values all strings matching the above descriptions.

Here's an example file:

~~~~js
{
	"Mailing List": "www-style@w3.org",
	"Mailing List Archives": "http://lists.w3.org/Archives/Public/www-style/"
}
~~~~

Overriding Metadata From The Command Line
-----------------------------------------

If you want to generate multiple versions of a spec from the same source
(such as a primary spec, plus some snapshots),
you can override the metadata from the command line to generate the alternate forms.

For any metadata key defined above,
just pass it as a `--md-foo=bar` command-line argument.
For example, to override the **Status** metadata,
run `bikeshed spec --md-status=ED`.

(If the metadata name has spaces in it, use dashes to separate the words instead.)

### Known Issues

1. You can't override the `Use <i> Autolinks` status, because you can't input the `<>` characters. I don't intend to fix this, as you shouldn't be specifying this in the first place.
2. You can't supply custom metadata keys (ones with a `!` prefix). If you want to do this, let me know, and I'll work on it.
3. Passing values with spaces in them is tricky.  This is [an issue with the argparse library](http://bugs.python.org/issue22909).  The only way around it is to specify both of the positional arguments (the input and output filenames), then put the offending argument after them.

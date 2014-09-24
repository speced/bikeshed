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
* **Warning** must contain either "Obsolete", "Not Ready", "New Version XXX", or "Replaced by XXX", which triggers the appropriate warning message in the boilerplate.
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

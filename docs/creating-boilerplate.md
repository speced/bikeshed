Creating New Boilerplate Files For Your Organization
====================================================

Bikeshed's default boilerplate generates a functional and reasonably attractive spec,
but if your group has specific style requirements,
you can produce your own boilerplate files.
This section is a basic guide to developing these files.

Header and Footer
-----------------

The most important part of the boilerplate is the `header.include` and `footer.include` file.
These define the parts of the spec HTML that precede and follow your actual spec content,
so the source file can contain only the actual spec text,
and all specs in the same organization can look similar.

Here is a basic example `header.include` file:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
  <title>[TITLE]</title>
  <style>
  ...
  </style>
</head>
<body class="h-entry">
<div class="head">
  <p data-fill-with="logo"></p>
  <h1 id="title" class="p-name no-ref">[TITLE]</h1>
  <h2 id="subtitle" class="no-num no-toc no-ref">[LONGSTATUS],
    <span class="dt-updated"><span class="value-title" title="[CDATE]">[DATE]</span></h2>
  <div data-fill-with="spec-metadata"></div>
  <div data-fill-with="warning"></div>
  <p class='copyright' data-fill-with='copyright'></p>
  <hr title="Separator for header">
</div>

<h2 class='no-num no-toc no-ref' id='abstract'>Abstract</h2>
<div class="p-summary" data-fill-with="abstract"></div>
<div data-fill-with="at-risk"></div>

<h2 class="no-num no-toc no-ref" id="contents">Table of Contents</h2>
<div data-fill-with="table-of-contents"></div>
```

This uses several of Bikeshed's boilerplating features:

* Text replacement, via the `[FOO]` macros.
	These macros are prepopulated by Bikeshed,
	either from metadata in the spec (like `[TITLE]`) or from environment data (like `[DATE]`).
	The full list of text macros can be found at [Boilerplate§Text Macros](boilerplate.md#text-macros)

* Boilerplate pieces, via empty container elements with `data-fill-with` attributes.
	The list of Bikeshed-provided `data-fill-with` values can be found at [Boilerplate§Boilerplate Section](boilerplate.md#boilerplate-sections).
	At minimum, you want to include the `abstract`, `table-of-contents`, and `spec-metadata` sections here;
	they're all most useful at the top of the document.

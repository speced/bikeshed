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

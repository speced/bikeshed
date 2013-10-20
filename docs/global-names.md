Global Names
============

Several features in Bikeshed use **global names** to uniquely identify defined terms.
(Several legacy features that need to identify defined terms don't, but they'll be fixed as time goes on.)

A global name is a guaranteed-unique identifier for every defined term.
It consists of the term itself and its type,
and if necessary to disambiguate, the value and type of what it's for.
For example, CSS properties are unique by themselves -
within the namespace of "properties",
their names are unique.
However, descriptors aren't guaranteed to be unique;
it's possible for multiple at-rules to have descriptors of the same name,
so the information about the at-rule is contained in the global name.

Global names are written as a series of terms,
starting with the highest-level uniquifier and ending with the targeted term itself,
separated by slashes.
Each term is accompanied by its type, wrapped in `<>` characters.
For example, to refer to the `auto` value of the `width` property,
its global name is `"width<property>/auto<value>"`.

Simplified Global Names
-----------------------

Not all information needs to be provided in a global name used just to *reference* a term,
if there's not currently any ambiguity.
You may leave off terms from the front,
or leave off type information from any term.
Global names are matched optimistically,
assuming that the missing values will match correctly.
For example, `"width/auto"` will match with `"width<property>/auto<value>"`,
as will a simple `"auto"`.
Specifying a full global name is never a bad idea, however,
to avoid accidental matches with unintended terms
that may not be immediately obvious.
For example, `"auto"` matches `"width<property>/auto<value>"`,
but it also matches `"Foo<interface>/auto<attribute>"`.

Multiple Global Names
---------------------

If multiple global names are required,
simply separate them with spaces.

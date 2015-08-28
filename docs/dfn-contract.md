Anatomy of a Dfn
================

Bikeshed's most important feature is its powerful cross-spec autolinking.
This is possible due to each definition being annotated with a rich set of metadata,
which is then exposed via custom `data-*` attributes
and picked up by specialized scrapers (such as Shepherd)
that then compile a definition database that Bikeshed relies on.

If you're writing a spec processor or related tool
and would like to interoperate with the Bikeshed ecosystem,
here's the full definition data model and how to properly expose it.

1. The defining element MUST be a `<dfn>` or `<h1-6>`.  No other element is recognized as defining a term.
2. The element MUST have an `id` attribute.
3. The linking text defaults to the **text content** of the `<dfn>`/heading.
	If the desired text content isn't suitable for linking text,
	or you wish to provide multiple linking texts,
	a `data-lt` attribute containing one or more pipe-separated linking texts will override the text content.
4. `data-dfn-type` MUST be provided, and set to [one of the accepted values](definitions-autolinks.md#definition-types).
5. Either `data-export` or `data-noexport` MAY be provided (both boolean attributes).  If neither is provided, "dfn" type definitions default to noexport, while all others default to export.  Unexported definitions aren't linkable by default.
6. [Several types](definitions-autolinks.md#specifying-what-a-definition-is-for) of definitions are namespaced to another construct; for example, attribute names are namespaced to an interface.  These definitions MUST contain a `data-dfn-for` attribute, containing a comma-separated list of one or more definitions they're namespaced to.

If you have written a web spec and it conforms to this definition syntax,
contact the project maintainer and ask them to register your spec in Shepherd,
so its definitions will be available to everyone else.

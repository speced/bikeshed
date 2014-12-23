Bikeshed’s "InfoTree" Format
============================

Bikeshed's custom text formats attempt to be fairly regular;
most of them involve specifying key/value pairs,
and are line-based.
For example, Bikeshed's metadata format is one key/value pair per line,
with a colon between the key and the value.

The InfoTree format,
used by several things in Bikeshed,
is similar.
It's used when you need to specify data consistenting of multiple key/value pairs,
where it's common that multiple entries share some of that data.
The InfoTree format makes this easy to read, write, and maintain.

Specifying Information on a Single Line
---------------------------------------

The simplest way to provide a piece of information is by putting all the key/value pairs on a single line.
In the InfoTree format, this is done by putting a colon between the key and value,
and separating the pairs with semicolons.
For example, here is an example of two "anchor" entries:

```
urlPrefix: https://encoding.spec.whatwg.org/; type: dfn; text: ascii whitespace
urlPrefix: https://encoding.spec.whatwg.org/; type: dfn; text: utf-8
```

This specifies two entries, each with three keys: urlPrefix, type, and text.

Nesting Information to Share Pieces
-----------------------------------

When multiple pieces of information share some key/value pairs,
you can use nesting to indicate this,
so you don't have to repeat yourself.
Here's the same two entries as before,
but using nesting to share their common information:

```
urlPrefix: https://encoding.spec.whatwg.org/; type: dfn
	text: ascii whitespace
	text: utf-8
```

Just like the previous, this defines two entries, each with three key/value pairs
Now it's clearer, though, that the two entries share their `urlPrefix` and `type` data,
and you only have to maintain the common data in one place.

Additional Details
------------------

The order that keys are specified in is irrelevant.
Feel free to rearrange them for readability or more effective nesting.

You can specify the same key multiple times;
the values will be collected into an array for later processing.
(Each user of InfoTree will define whether multiple values for a key is valid or not, and what it means.)
The order that the values appear in *is* preserved,
as it might be important.
(For example, in the anchor format, multiple urlPrefix values are concatenated together, to help specify urls in multipage specs.)

Additional semicolons are silently ignored;
in other words, empty entries get dropped, so you can put a final semicolon at the end of the line or not, as you prefer.

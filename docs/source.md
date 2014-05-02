Source-File Processing
======================

Sometimes it's the *source* file you want to preprocess,
if there is some feature you want literally in your source
that is hard or annoying to type in yourself.
Bikeshed has some options for doing this as well.

All of these commands are accessed from the `source` sub-command,
like `bikeshed source`.
You can run individual commands by specifying their relevant flag
(see `bikeshed source -h` for a list),
or run all of them by not passing any flags.

Big Text
--------

When editing a large spec,
it's easy to get lost in its length,
and have to spend some time scrolling back and forth to find particular sections.

The Sublime Text editor has a special feature,
the minimap,
which shows an extremely-zoomed out version of your document while you scroll,
so you can recognize where you are in the file by the shape of your code.
This can be made even easier by putting extra-large "ASCII art" text in your source
to label major sections,
so they show up visibly in the minimap as section markers.

Bikeshed can auto-generate this "ASCII art" text for you
with its `--big-text` command.
Just add an HTML comment to your document on its own line that looks like:

```
<!-- Big Text: your text here -->
```

If you run `bikeshed source --big-text`,
Bikeshed will replace it with a comment that looks like:

```
<!--
██    ██  ███████  ██     ██ ████████        ████████ ████████ ██     ██ ████████       ██     ██ ████████ ████████  ████████
 ██  ██  ██     ██ ██     ██ ██     ██          ██    ██        ██   ██     ██          ██     ██ ██       ██     ██ ██
  ████   ██     ██ ██     ██ ██     ██          ██    ██         ██ ██      ██          ██     ██ ██       ██     ██ ██
   ██    ██     ██ ██     ██ ████████           ██    ██████      ███       ██          █████████ ██████   ████████  ██████
   ██    ██     ██ ██     ██ ██   ██            ██    ██         ██ ██      ██          ██     ██ ██       ██   ██   ██
   ██    ██     ██ ██     ██ ██    ██           ██    ██        ██   ██     ██          ██     ██ ██       ██    ██  ██
   ██     ███████   ███████  ██     ██          ██    ████████ ██     ██    ██          ██     ██ ████████ ██     ██ ████████
-->
```

Which is clearly visible from Sublime's minimap!

# Contributions welcome

We love contributions from our users. As bikeshed is all about precise, clear specifications, there is no fix too small. If you would like to update or improve the documentation, we ask that you follow these quick rules:

1. **Use [Semantic Linefeeds](http://rhodesmill.org/brandon/2012/one-sentence-per-line/)** to put one sentence or clause per line.

    Do this:

    ```
    Indent tells Bikeshed how many spaces you prefer to use to indent your source code,⏎
    so it can properly parse your Markdown and data-blocks.⏎
    It takes a single integer,⏎
    and defaults to 4 if unspecified.⏎
    (Of course, using tabs avoids this entirely,⏎
    as one tab is always one indent.)
    ```

    Don't do this:

    ```
    Indent tells Bikeshed how many spaces you prefer to use to indent your source code, so it can properly parse your Markdown and data-blocks. It takes a single integer, and defaults to 4 if unspecified. (Of course, using tabs avoids this entirely, as one tab is always one indent.)
    ```

1. **Include an updated `index.html`** in your Pull Request.

    The quickest way is to use [the Bikeshed API](https://api.csswg.org/bikeshed/) to pre-process your `index.bs` file.

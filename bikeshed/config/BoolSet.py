import collections


class BoolSet(collections.MutableMapping):
    """
    Implements a "boolean set",
    where keys can be explicitly set to True or False,
    but interacted with like a normal set
    (similar to Counter, but with bools).
    Can also set whether the default should consider unset values to be True or False by default.
    """

    def __init__(self, values=None, default=False):
        self._internal = {}
        if isinstance(values, collections.Mapping):
            for k, v in values.items():
                self._internal[k] = bool(v)
        elif isinstance(values, collections.Iterable):
            for k in values:
                self._internal[k] = True
        self.default = bool(default)

    def __missing__(self, key):
        return self.default

    def __contains__(self, key):
        if key in self._internal:
            return self._internal[key]
        else:
            return self.default

    def __getitem__(self, key):
        return key in self

    def __setitem__(self, key, val):
        self._internal[key] = bool(val)

    def __delitem__(self, key):
        del self._internal[key]

    def __iter__(self):
        return iter(self._internal)

    def __len__(self):
        return len(self._internal)

    def __repr__(self):
        if self.default is False:
            trueVals = [k for k, v in self._internal.items() if v is True]
            vrepr = "[" + ", ".join(repr(x) for x in trueVals) + "]"
        else:
            falseVals = [k for k, v in self._internal.items() if v is False]
            vrepr = "{" + ", ".join(repr(x) + ":False" for x in falseVals) + "}"
        return f"BoolSet({vrepr}, default={self.default})"

from __future__ import annotations

from .. import t


class StringEnum:
    """
    Simple Enum class.

    Takes strings, returns an object that acts set-like (you can say `"foo" in someEnum`),
    but also hangs the strings off of the object as attributes (you can say `someEnum.foo`)
    or as a dictionary (`someEnum["foo"]`).
    """

    def __init__(self, *vals: str) -> None:
        self._vals = {}
        for val in vals:
            self._vals[val] = val
            setattr(self, val, val)

    def __iter__(self) -> t.Iterator[str]:
        return iter(list(self._vals.values()))

    def __len__(self) -> int:
        return len(self._vals)

    def __contains__(self, val: str) -> bool:
        return val in self._vals

    def __getitem__(self, val: str) -> str:
        return self._vals[val]

    def __getattr__(self, name: str) -> str:
        """will only get called for undefined attributes"""
        msg = f"No member '{name}' contained in StringEnum."
        raise IndexError(msg)

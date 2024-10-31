from __future__ import annotations

import dataclasses

from .. import t

if t.TYPE_CHECKING:
    # Need to use function form due to "for" key
    # being invalid as a property name
    class RefDataT(t.TypedDict, total=False):
        type: t.Required[str]
        spec: t.Required[str | None]
        shortname: t.Required[str | None]
        level: t.Required[str | None]
        status: t.Required[str]
        url: t.Required[str]
        export: t.Required[bool]
        normative: t.Required[bool]
        for_: t.Required[list[str]]
        el: t.ElementT | None


@dataclasses.dataclass
class RefWrapper:
    # Refs don't contain their own name, so I don't have to copy as much when there are multiple linkTexts
    # This wraps that, producing an object that looks like it has a text property.
    # It also makes all the ref dict keys look like object attributes.

    text: str
    displayText: str
    _ref: RefDataT

    @property
    def type(self) -> str:
        return self._ref["type"].strip()

    @property
    def spec(self) -> str:
        if self._ref["spec"] is None:
            return ""
        return self._ref["spec"].strip()

    @property
    def shortname(self) -> str:
        if self._ref["shortname"] is None:
            return ""
        return self._ref["shortname"].strip()

    @property
    def level(self) -> str:
        if self._ref["level"] is None:
            return ""
        return self._ref["level"].strip()

    @property
    def status(self) -> str:
        if self._ref["status"] is None:
            return ""
        return self._ref["status"].strip()

    @property
    def url(self) -> str:
        if self._ref["url"] is None:
            return ""
        return self._ref["url"].strip()

    @property
    def export(self) -> bool:
        return self._ref["export"]

    @property
    def normative(self) -> bool:
        return self._ref["normative"]

    @property
    def for_(self) -> list[str]:
        return [x.strip() for x in self._ref["for_"]]

    @property
    def el(self) -> t.ElementT | None:
        return self._ref.get("el", None)

    def __json__(self) -> t.JSONT:
        return {
            "text": self.text,
            "displayText": self.displayText,
            "type": self.type,
            "spec": self.spec,
            "shortname": self.shortname,
            "level": self.level,
            "status": self.status,
            "url": self.url,
            "export": self.export,
            "normative": self.normative,
            "for_": self.for_,
        }

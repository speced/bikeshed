from __future__ import annotations

from .. import t


class Ref:
    __slots__ = [
        "displayText",
        "el",
        "export",
        "for_",
        "level",
        "normative",
        "shortname",
        "spec",
        "status",
        "text",
        "type",
        "uniquifier",
        "url",
    ]

    def __init__(
        self,
        text: str,
        displayText: str | None = None,
        *,
        type: str,
        spec: str | None = None,
        shortname: str | None = None,
        level: str | None = None,
        status: str | None = None,
        url: str | None = None,
        export: bool = True,
        normative: bool = True,
        for_: list[str] | None = None,
        el: t.ElementT | None = None,
        uniquifier: str | None = None,
    ) -> None:
        """Initialize a Ref, performing eager string trimming and normalization on attributes."""
        self.text = text
        self.displayText = text if displayText is None else displayText
        self.type = type.strip()
        self.spec = "" if spec is None else spec.strip()
        self.shortname = "" if shortname is None else shortname.strip()
        self.level = "" if level is None else level.strip()
        self.status = "" if status is None else status.strip()
        self.url = "" if url is None else url.strip()
        self.export = bool(export)
        self.normative = bool(normative)
        self.for_ = [x.strip() for x in for_] if for_ else []
        self.el = el
        self.uniquifier = uniquifier

    def refKey(self) -> str:
        """Return the unique key for this ref, falling back to its URL."""
        return self.uniquifier or self.url

    def __eq__(self, other: t.Any) -> bool:
        if not isinstance(other, Ref):
            return NotImplemented
        return (
            self.type == other.type
            and self.spec == other.spec
            and self.shortname == other.shortname
            and self.level == other.level
            and self.status == other.status
            and self.url == other.url
            and self.export == other.export
            and self.normative == other.normative
            and self.for_ == other.for_
            and self.el == other.el
            and self.uniquifier == other.uniquifier
        )

    def __hash__(self) -> int:
        return hash(
            (
                self.type,
                self.spec,
                self.shortname,
                self.level,
                self.status,
                self.url,
                self.export,
                self.normative,
                tuple(self.for_),
                self.el,
                self.uniquifier,
            ),
        )

    def __repr__(self) -> str:
        return f"Ref(text={self.text!r}, type={self.type!r}, spec={self.spec!r}, url={self.url!r})"

    def __json__(self) -> dict[str, bool | str | list[str]]:
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

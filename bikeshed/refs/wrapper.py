import copy
import dataclasses

from . import utils
from .. import t


@dataclasses.dataclass
class RefWrapper:
    # Refs don't contain their own name, so I don't have to copy as much when there are multiple linkTexts
    # This wraps that, producing an object that looks like it has a text property.
    # It also makes all the ref dict keys look like object attributes.

    text: str
    _ref: t.JSONT

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
        return [x.strip() for x in self._ref["for"]]

    @property
    def el(self) -> t.ElementT | None:
        return self._ref.get("el", None)

    """
        "type": linesIter.next(),
        "spec": linesIter.next(),
        "shortname": linesIter.next(),
        "level": linesIter.next(),
        "status": linesIter.next(),
        "url": linesIter.next(),
        "export": linesIter.next() != "\n",
        "normative": linesIter.next() != "\n",
        "for": [],
        (optionall) "el": manuallyProvided,
    """

    def __json__(self) -> t.JSONT:
        refCopy = copy.copy(self._ref)
        refCopy["text"] = self.text
        return utils.stripLineBreaks(refCopy)

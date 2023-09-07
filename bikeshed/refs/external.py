from __future__ import annotations

import dataclasses as dc

from .. import t


@dc.dataclass
class ExternalRefsManager:
    specs: dict[str, ExternalRefsSpec] = dc.field(default_factory=dict)

    def addRef(self, specName: str, ref: t.RefWrapper, for_: str | None) -> None:
        if specName not in self.specs:
            self.specs[specName] = ExternalRefsSpec()
        self.specs[specName].addRef(ref, for_)

    def hasRefs(self) -> bool:
        return any(spec.refs for spec in self.specs.values())

    def addBiblio(self, specName: str, biblio: t.BiblioEntry) -> None:
        if specName not in self.specs:
            self.specs[specName] = ExternalRefsSpec()
        self.specs[specName].biblio = biblio

    def sorted(self) -> t.Iterable[tuple[str, ExternalRefsSpec]]:
        return sorted(
            self.specs.items(),
            key=lambda x: x[0].upper(),
        )


@dc.dataclass
class ExternalRefsSpec:
    refs: dict[str, ExternalRefsGroup] = dc.field(default_factory=dict)
    biblio: t.BiblioEntry | None = None

    def addRef(self, ref: t.RefWrapper, for_: str | None) -> None:
        if ref.text not in self.refs:
            self.refs[ref.text] = ExternalRefsGroup()
        self.refs[ref.text].valuesByFor[for_] = ref

    def sorted(self) -> t.Iterable[tuple[str, ExternalRefsGroup]]:
        return sorted(self.refs.items(), key=lambda x: x[0])


@dc.dataclass
class ExternalRefsGroup:
    valuesByFor: dict[str | None, t.RefWrapper] = dc.field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.valuesByFor)

    def single(self) -> t.RefWrapper:
        if len(self.valuesByFor) == 1:
            return next(iter(self.valuesByFor.values()))
        else:
            msg = f"There are {len(self.valuesByFor)} values, not just 1."
            raise IndexError(msg)

    def sorted(self) -> t.Generator[tuple[str | None, t.RefWrapper], None, None]:
        if None in self.valuesByFor:
            yield None, self.valuesByFor[None]
        for forVal in sorted(x for x in self.valuesByFor if x is not None):
            yield forVal, self.valuesByFor[forVal]

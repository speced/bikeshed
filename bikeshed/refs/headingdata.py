from __future__ import annotations

from .. import h, t
from .. import messages as m

# Heading data for a spec is a dict.
# Each key is either an id, like "#id",
# or a page name + id, like "/page#id".
# The value is either a list of "/page#id" keys
# (when an #id appears in several pages in the spec),
# or a {"current": ..., "snapshot":...} dict,
# which can have either or both of these keys.
# Each of these latter dicts' values
# are a dict[str, str] of heading data like
# {
#   "number": "7.1",
#   "spec": "CSS Overflow 4",
#   "text": "Fragment styling",
#   "url": "https://drafts.csswg.org/css-overflow-4/#fragment-styling"
# }


class SpecHeadings:
    def __init__(self, spec: str, data: dict[str, list[str] | dict[str, dict[str, str]]]) -> None:
        self.spec = spec
        self.data = data

    def get(self, id: str, status: str, el: t.ElementT | None = None) -> dict[str, str] | None:
        currentHeading: dict[str, str] | None
        snapshotHeading: dict[str, str] | None
        if id in self.data:
            heading = self.data[id]
            if isinstance(heading, dict):
                currentHeading = heading.get("current")
                snapshotHeading = heading.get("snapshot")
            if isinstance(heading, list):
                clashingIds = heading
                # Multipage spec, list is "/page#id" keys
                # that (potentially) collide for that heading ID
                if len(clashingIds) == 1:
                    # only one heading of this name, no worries
                    x = self.data[clashingIds[0]]
                    assert isinstance(x, dict)
                    currentHeading = x.get("current")
                    snapshotHeading = x.get("snapshot")
                else:
                    # multiple headings of this id, user needs to disambiguate
                    m.die(
                        f"Multiple headings with id '{id}' for spec '{self.spec}'. Please specify:\n"
                        + "\n".join(f"  [[{self.spec + x}]]" for x in clashingIds),
                        el=el,
                    )
                    return None
        else:
            m.die(
                f"Couldn't find section '{id}' in spec '{self.spec}':\n{h.outerHTML(el)}",
                el=el,
            )
            return None
        if status == "current":
            return currentHeading or snapshotHeading
        else:
            return snapshotHeading or currentHeading

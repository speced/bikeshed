from __future__ import annotations

import dataclasses as dc

from .. import t

"""
Simple design for now.

1. Identify the container that'll contain all the subpages content.
    (Either an explicit `[bs-pages-root]` element, or <main>, or <body>.)
2. Iterate the children, grouping them into subpages.
3. The first content, before I run into a subpage, will be left on the "main" page.
4. When I see a heading with the right attribute, form a new subpage for it.
    Pages contain all content until the next page starts,
    including more headings/sections of the same or lower levels.
5. Pages can start on subsections of the previous page.
    If so, the next *higher* heading *must* start a new page.
6. Pages other than the "main" will use a different template, and can specify exactly *which* template to use.
7. I'll generate some additional controls to get the page's limited ToC, current page, previous/next pages, etc.
"""


@dc.dataclass
class SubPage:
    name: str
    level: int
    incitingElement: t.ElementT
    nodes: list[t.NodeT] = dc.field(default_factory=list)
    ids: set[str] = dc.field(default_factory=set)


@dc.dataclass
class PageSplitConfig:
    autoLevel: int | None = None
    rootPageName: str = "index.html"

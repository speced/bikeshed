from __future__ import annotations

from collections import OrderedDict

from . import h, t

if t.TYPE_CHECKING:
    from . import refs as r  # pylint: disable=unused-import


def addDfnPanels(doc: t.SpecT, dfns: list[t.ElementT]) -> None:
    # Constructs "dfn panels" which show all the local references to a term
    atLeastOnePanel = False
    # Gather all the <a href>s together
    allRefs: OrderedDict[str, list[t.ElementT]] = OrderedDict()
    for a in h.findAll("a", doc):
        href = a.get("href")
        if href is None:
            continue
        if not href.startswith("#"):
            continue
        allRefs.setdefault(href[1:], []).append(a)
    for dfn in dfns:
        id = dfn.get("id")
        if not id:
            # Something went wrong, bail.
            continue
        refs: OrderedDict[str, list[t.ElementT]] = OrderedDict()
        for link in allRefs.get(id, []):
            section = h.sectionName(doc, link)
            if section is not None:
                refs.setdefault(section, []).append(link)
        if not refs:
            # Just insert a self-link instead
            # unless it already has a self-link, of course
            if h.find(".self-link", dfn) is None:
                h.appendChild(dfn, h.E.a({"href": "#" + h.escapeUrlFrag(id), "class": "self-link"}))
            continue
        h.addClass(doc, dfn, "dfn-paneled")
        atLeastOnePanel = True
        panel = h.E.aside(
            {"class": "dfn-panel", "data-for": id},
            h.E.b(h.E.a({"href": "#" + h.escapeUrlFrag(id)}, "#" + id)),
            h.E.b("Referenced in:"),
        )
        ul = h.appendChild(panel, h.E.ul())
        for text, els in refs.items():
            li = h.appendChild(ul, h.E.li())
            for i, el in enumerate(els):
                refID = el.get("id")
                if refID is None:
                    refID = f"ref-for-{id}"
                    el.set("id", h.safeID(doc, refID))
                if i == 0:
                    h.appendChild(
                        li,
                        h.E.a(
                            {
                                "href": "#" + h.escapeUrlFrag(refID),
                                "data-silently-dedup": "",
                            },
                            text,
                        ),
                    )
                else:
                    h.appendChild(
                        li,
                        " ",
                        h.E.a(
                            {
                                "href": "#" + h.escapeUrlFrag(refID),
                                "data-silently-dedup": "",
                            },
                            "(" + str(i + 1) + ")",
                        ),
                    )
        h.appendChild(doc.body, panel)
    if atLeastOnePanel:
        doc.extraScripts["script-dfn-panel"] = dfnPanelScript
        doc.extraStyles["style-dfn-panel"] = dfnPanelStyle


def addExternalDfnPanel(termEl: t.ElementT, ref: r.RefWrapper, doc: t.SpecT) -> None:
    # Constructs "dfn panels" which show all the local references to an external term

    # Calculate and cache the doc's links,
    # so I'm not iterating the doc for links constantly.
    if not doc.cachedLinksFromHref:
        for a in h.findAll("a", doc):
            href = a.get("href")
            if href is None:
                continue
            if href.startswith("#"):
                continue
            doc.cachedLinksFromHref.setdefault(href, []).append(a)

    # Group the relevant links according to the section they're in.
    linksBySection: OrderedDict[str, list[t.ElementT]] = OrderedDict()
    for link in doc.cachedLinksFromHref[ref.url]:
        section = h.sectionName(doc, link) or "Unnumbered Section"
        linksBySection.setdefault(section, []).append(link)
    if linksBySection:
        h.addClass(doc, termEl, "dfn-paneled")
        _, _, refID = ref.url.partition("#")
        termID = f"term-for-{refID}"
        termEl.set("id", termID)
        termEl.set("data-silently-dedup", "")
        panel = h.E.aside(
            {"class": "dfn-panel", "data-for": termID},
            h.E.a({"href": ref.url}, ref.url),
            h.E.b("Referenced in:"),
        )
        ul = h.appendChild(panel, h.E.ul())
        for text, els in linksBySection.items():
            li = h.appendChild(ul, h.E.li())
            for i, el in enumerate(els):
                linkID = el.get("id")
                if linkID is None:
                    linkID = f"termref-for-{refID}"
                    el.set("id", h.safeID(doc, linkID))
                    el.set("data-silently-dedup", "")
                if i == 0:
                    h.appendChild(
                        li,
                        h.E.a(
                            {
                                "href": "#" + h.escapeUrlFrag(linkID),
                                "data-silently-dedup": "",
                            },
                            text,
                        ),
                    )
                else:
                    h.appendChild(
                        li,
                        " ",
                        h.E.a(
                            {
                                "href": "#" + h.escapeUrlFrag(linkID),
                                "data-silently-dedup": "",
                            },
                            "(" + str(i + 1) + ")",
                        ),
                    )
        h.appendChild(doc.body, panel)


def addExternalDfnPanelStyles(doc: t.SpecT) -> None:
    doc.extraScripts["script-dfn-panel"] = dfnPanelScript
    doc.extraStyles["style-dfn-panel"] = dfnPanelStyle
    doc.extraStyles["style-darkmode"] += dfnPanelDarkmodeStyle


dfnPanelScript = """
document.body.addEventListener("click", function(e) {
    var queryAll = function(sel) { return [].slice.call(document.querySelectorAll(sel)); }
    // Find the dfn element or panel, if any, that was clicked on.
    var el = e.target;
    var target;
    var hitALink = false;
    while(el.parentElement) {
        if(el.tagName == "A") {
            // Clicking on a link in a <dfn> shouldn't summon the panel
            hitALink = true;
        }
        if(el.classList.contains("dfn-paneled")) {
            target = "dfn";
            break;
        }
        if(el.classList.contains("dfn-panel")) {
            target = "dfn-panel";
            break;
        }
        el = el.parentElement;
    }
    if(target != "dfn-panel") {
        // Turn off any currently "on" or "activated" panels.
        queryAll(".dfn-panel.on, .dfn-panel.activated").forEach(function(el){
            el.classList.remove("on");
            el.classList.remove("activated");
        });
    }
    if(target == "dfn" && !hitALink) {
        // open the panel
        var dfnPanel = document.querySelector(".dfn-panel[data-for='" + el.id + "']");
        if(dfnPanel) {
            dfnPanel.classList.add("on");
            var rect = el.getBoundingClientRect();
            dfnPanel.style.left = window.scrollX + rect.right + 5 + "px";
            dfnPanel.style.top = window.scrollY + rect.top + "px";
            var panelRect = dfnPanel.getBoundingClientRect();
            var panelWidth = panelRect.right - panelRect.left;
            if(panelRect.right > document.body.scrollWidth && (rect.left - (panelWidth + 5)) > 0) {
                // Reposition, because the panel is overflowing
                dfnPanel.style.left = window.scrollX + rect.left - (panelWidth + 5) + "px";
            }
        } else {
            console.log("Couldn't find .dfn-panel[data-for='" + el.id + "']");
        }
    } else if(target == "dfn-panel") {
        // Switch it to "activated" state, which pins it.
        el.classList.add("activated");
        el.style.left = null;
        el.style.top = null;
    }

});
"""

dfnPanelStyle = """
:root {
    --dfnpanel-bg: #ddd;
    --dfnpanel-text: var(--text);
}
.dfn-panel {
    position: absolute;
    z-index: 35;
    height: auto;
    width: -webkit-fit-content;
    width: fit-content;
    max-width: 300px;
    max-height: 500px;
    overflow: auto;
    padding: 0.5em 0.75em;
    font: small Helvetica Neue, sans-serif, Droid Sans Fallback;
    background: var(--dfnpanel-bg);
    color: var(--dfnpanel-text);
    border: outset 0.2em;
}
.dfn-panel:not(.on) { display: none; }
.dfn-panel * { margin: 0; padding: 0; text-indent: 0; }
.dfn-panel > b { display: block; }
.dfn-panel a { color: var(--dfnpanel-text); }
.dfn-panel a:not(:hover) { text-decoration: none !important; border-bottom: none !important; }
.dfn-panel > b + b { margin-top: 0.25em; }
.dfn-panel ul { padding: 0; }
.dfn-panel li { list-style: inside; }
.dfn-panel.activated {
    display: inline-block;
    position: fixed;
    left: .5em;
    bottom: 2em;
    margin: 0 auto;
    max-width: calc(100vw - 1.5em - .4em - .5em);
    max-height: 30vh;
}

.dfn-paneled { cursor: pointer; }
"""

dfnPanelDarkmodeStyle = """
@media (prefers-color-scheme: dark) {
    :root {
        --dfnpanel-bg: #222;
        --dfnpanel-text: var(--text);
    }
}"""

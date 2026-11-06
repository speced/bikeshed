from __future__ import annotations

from collections import Counter, defaultdict

from . import h, t
from . import messages as m


def addImplicitAlgorithms(doc: t.SpecT) -> None:
    # If a container has an empty `algorithm` attribute,
    # but it contains only a single `<dfn>`,
    # assume that the dfn is a description of the algorithm.
    for el in h.findAll("[data-algorithm='']:not(h1):not(h2):not(h3):not(h4):not(h5):not(h6)", doc):
        dfns = h.findAll("dfn", el)
        if len(dfns) == 1:
            dfnName = h.firstLinkTextFromElement(dfns[0]) or ""
            el.set("data-algorithm", dfnName)
            dfnFor = dfns[0].get("data-dfn-for")
            if dfnFor:
                el.set("data-algorithm-for", dfnFor)
        elif len(dfns) == 0:
            m.die(
                "Algorithm container has no name, and there is no <dfn> to infer one from. Please set the algorithm='name here' attribute.",
                el=el,
            )
        else:
            m.die(
                "Algorithm container has no name, and there are too many <dfn>s to choose which to infer a name from. Please set the algorithm='name here' attribute.",
                el=el,
            )


def checkVarHygiene(doc: t.SpecT) -> None:
    def isAlgo(el: t.ElementT) -> bool:
        return el.get("data-algorithm") is not None

    def nearestAlgo(el: t.ElementT) -> t.ElementT | None:
        # Find the nearest "algorithm" container,
        # either an ancestor with [algorithm] or the nearest heading with same.
        if isAlgo(el):
            return el
        ancestor = h.closestAncestor(el, isAlgo)
        if ancestor is not None:
            return ancestor
        for heading in h.relevantHeadings(el):
            if isAlgo(heading):
                return heading
            break
        return None

    def algoName(el: t.ElementT) -> str | None:
        # Finds a uniquified algorithm name from an algo container
        algo = nearestAlgo(el)
        if algo is None:
            return None
        algoName = algo.get("data-algorithm")
        algoFor = algo.get("data-algorithm-for")
        return f"'{algoName}'" + (f" for {algoFor}" if algoFor else "")

    # Look for vars that only show up once. These are probably typos.
    varCounts: defaultdict[tuple[str, str | None], list[t.ElementT]] = defaultdict(list)
    atLeastOneAlgo = False
    for el in h.findAll("var:not([data-var-ignore])", doc):
        var = h.foldWhitespace(h.textContent(el)).strip()
        algo = algoName(el)
        varCounts[(var, algo)].append(el)
        if algo:
            atLeastOneAlgo = True
    for (var, algo), els in varCounts.items():
        if len(els) > 1:
            continue
        if var.lower() in doc.md.ignoredVars:
            continue
        if algo:
            varName = f"'{var}' (in algorithm {algo})"
        else:
            varName = f"'{var}' (in global scope)"
        m.warn(
            f"The var {varName} is only used once.\nIf this is not a typo, please add an ignore='' attribute to the <var>.",
            el=els[0],
        )

    if atLeastOneAlgo:
        addVarClickHighlighting(doc)

    # Look for algorithms that show up twice; these are errors.
    for algo, count in Counter(algoName(el) for el in h.findAll("[data-algorithm]", doc)).items():
        if count > 1:
            m.die(f"Multiple declarations of the {algo} algorithm.")
            return


def addVarClickHighlighting(doc: t.SpecT) -> None:
    if doc.md.slimBuildArtifact:
        return
    doc.extraJC.addVarClickHighlighting()

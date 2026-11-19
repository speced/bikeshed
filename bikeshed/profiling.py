# Performance profiling and reporting for Bikeshed (`bikeshed profile`).
# Runs spec builds, synthetic benchmark specs, test runs, or arbitrary CLI
# commands under cProfile and PhaseTimer, then analyzes call stacks and
# caller/callee relationships to produce terminal bottleneck reports, JSON
# exports, interactive SVG flamegraphs, standalone HTML dashboards, and raw
# pstats files.
#
# This file was Gemini-generated.

from __future__ import annotations

import contextlib
import cProfile
import dataclasses
import html
import json
import os
import pstats
import re
import sys
import time

from . import InputSource, constants, metadata, synthetic, t, test
from . import messages as m
from .Spec import PhaseRecord, PhaseTimer, Spec, defaultOutputFilename

if t.TYPE_CHECKING:
    import argparse


class FunctionKey(t.NamedTuple):
    """Unique identifier for a profiled function (file path, line number, and function name)."""

    filename: str
    line: int
    funcName: str


@dataclasses.dataclass
class CallerInfo:
    """Aggregated call statistics for a single caller invoking a profiled function."""

    key: FunctionKey
    name: str
    location: str
    category: str
    ncalls: int
    cumtime: float
    percentOfCallee: float


@dataclasses.dataclass
class CalleeInfo:
    """Aggregated call statistics for a single callee invoked by a profiled function."""

    key: FunctionKey
    name: str
    location: str
    category: str
    ncalls: int
    cumtime: float
    percentOfCaller: float


@dataclasses.dataclass
class FunctionStat:
    """Timing metrics, call counts, classification, and call-graph edges for a profiled function."""

    key: FunctionKey
    name: str
    filename: str
    line: int
    location: str
    category: str  # "bikeshed", "dependency", "stdlib", "built-in"
    ncalls: int
    pcalls: int  # primitive calls
    tottime: float
    cumtime: float
    tottimePercent: float
    cumtimePercent: float
    percallTot: float
    percallCum: float
    callers: list[CallerInfo] = dataclasses.field(default_factory=list)
    callees: list[CalleeInfo] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class CallTreeNode:
    """Node in a hierarchical call tree used for flamegraphs and JSON export."""

    name: str
    location: str
    category: str
    cumtime: float
    tottime: float
    ncalls: int
    percent: float
    children: list[CallTreeNode] = dataclasses.field(default_factory=list)

    def toDict(self) -> dict[str, t.Any]:
        """Serialize this call tree node and its descendants into a JSON-compatible dictionary."""
        return {
            "name": self.name,
            "location": self.location,
            "category": self.category,
            "cumtime": self.cumtime,
            "tottime": self.tottime,
            "ncalls": self.ncalls,
            "percent": self.percent,
            "children": [c.toDict() for c in self.children],
        }


@dataclasses.dataclass
class ProfileAnalysis:
    """Complete analyzed results of a profiling run, including phases, function stats, and call tree."""

    targetName: str
    totalWallTime: float
    totalCpuTime: float
    totalCalls: int
    primitiveCalls: int
    phases: list[PhaseRecord]
    functions: dict[FunctionKey, FunctionStat]
    bikeshedFunctions: list[FunctionStat]
    topOverallFunctions: list[FunctionStat]
    stats: pstats.Stats
    callTree: CallTreeNode | None = None


def getBikeshedRoot() -> str:
    """Return the absolute path to the Bikeshed package directory."""
    return os.path.dirname(os.path.abspath(__file__))


def categorizeFunction(filename: str, bikeshedRoot: str) -> tuple[str, str]:
    """Classify a source filename into (category, displayLocation)."""
    if filename.startswith("<") or filename == "~":
        return "built-in", filename

    normPath = os.path.normpath(filename)
    if normPath.startswith(bikeshedRoot):
        rel = os.path.relpath(normPath, bikeshedRoot)
        return "bikeshed", rel

    if "site-packages" in normPath or "dist-packages" in normPath:
        parts = normPath.replace("\\", "/").split("/")
        if "site-packages" in parts:
            idx = parts.index("site-packages")
            rel = "/".join(parts[idx + 1 :])
            return "dependency", rel
        if "dist-packages" in parts:
            idx = parts.index("dist-packages")
            rel = "/".join(parts[idx + 1 :])
            return "dependency", rel
        return "dependency", os.path.basename(normPath)

    # Standard library or local python
    if "/lib/python" in normPath or "\\lib\\python" in normPath:
        parts = re.split(r"[/\\]lib[/\\]python\d+\.\d+[/\\]?", normPath)
        if len(parts) > 1:
            return "stdlib", parts[-1]
        return "stdlib", os.path.basename(normPath)

    return "stdlib", os.path.basename(normPath)


def formatDuration(seconds: float) -> str:
    """Format a duration in seconds as a fixed-width string in s, ms, or µs."""
    if seconds >= 1.0:
        return f"{seconds:6.2f}s"
    if seconds >= 0.001:
        return f"{seconds * 1000:6.1f}ms"
    return f"{seconds * 1000000:6.0f}µs"


def formatBar(fraction: float, width: int = 12, asciiOnly: bool = False) -> str:
    """Render a proportional horizontal progress bar using Unicode blocks or ASCII."""
    clamped = max(0.0, min(1.0, fraction))
    if asciiOnly:
        barLen = round(clamped * width)
        return "[" + "=" * barLen + " " * (width - barLen) + "]"
    blocks = [" ", "▏", "▎", "▍", "▌", "▋", "▊", "▉", "█"]
    totalEighths = round(clamped * width * 8)
    fullBlocks = totalEighths // 8
    remainder = totalEighths % 8
    res = "█" * fullBlocks
    if fullBlocks < width and remainder > 0:
        res += blocks[remainder]
        fullBlocks += 1
    res += " " * (width - fullBlocks)
    return res


def analyzeProfile(
    pr: cProfile.Profile,
    wallTime: float,
    phases: list[PhaseRecord],
    targetName: str,
    *,
    rootFilter: str | None = None,
    leafFilter: str | None = None,
) -> ProfileAnalysis:
    """Convert raw cProfile stats and phase timings into a structured ProfileAnalysis."""
    ps = pstats.Stats(pr)
    psAny = t.cast("t.Any", ps)
    bikeshedRoot = getBikeshedRoot()

    totalCpuTime = float(psAny.total_tt)
    totalCalls = int(psAny.total_calls)
    primitiveCalls = int(psAny.prim_calls)

    effectiveTotalTime = max(wallTime, totalCpuTime, 0.000001)

    rawStats = dict(psAny.stats)

    # First pass: categorize and build initial FunctionStat objects
    fnStats: dict[FunctionKey, FunctionStat] = {}
    for rawKey, (cc, nc, tt, ct, _) in rawStats.items():
        key = FunctionKey(*rawKey)
        category, loc = categorizeFunction(key.filename, bikeshedRoot)
        displayLoc = f"{loc}:{key.line}" if key.line > 0 else loc
        totPct = (tt / effectiveTotalTime) * 100.0
        cumPct = (ct / effectiveTotalTime) * 100.0
        percallTot = tt / max(1, nc)
        percallCum = ct / max(1, nc)
        fnStats[key] = FunctionStat(
            key=key,
            name=key.funcName,
            filename=key.filename,
            line=key.line,
            location=displayLoc,
            category=category,
            ncalls=cc,
            pcalls=nc,
            tottime=tt,
            cumtime=ct,
            tottimePercent=totPct,
            cumtimePercent=cumPct,
            percallTot=percallTot,
            percallCum=percallCum,
        )

    # Second pass: compute callers and callees
    for rawCalleeKey, (_, _, _, calleeCt, callersDict) in rawStats.items():
        calleeKey = FunctionKey(*rawCalleeKey)
        calleeStat = fnStats[calleeKey]
        for rawCallerKey, callerInfo in callersDict.items():
            callerKey = FunctionKey(*rawCallerKey)
            if callerKey not in fnStats:
                continue
            callerStat = fnStats[callerKey]
            callerCc, _, _, callerCumtime = callerInfo
            pctOfCallee = (callerCumtime / max(calleeCt, 0.000001)) * 100.0
            pctOfCaller = (callerCumtime / max(callerStat.cumtime, 0.000001)) * 100.0

            calleeStat.callers.append(
                CallerInfo(
                    key=callerKey,
                    name=callerStat.name,
                    location=callerStat.location,
                    category=callerStat.category,
                    ncalls=callerCc,
                    cumtime=callerCumtime,
                    percentOfCallee=pctOfCallee,
                ),
            )

            callerStat.callees.append(
                CalleeInfo(
                    key=calleeKey,
                    name=calleeStat.name,
                    location=calleeStat.location,
                    category=calleeStat.category,
                    ncalls=callerCc,
                    cumtime=callerCumtime,
                    percentOfCaller=pctOfCaller,
                ),
            )

    # Sort callers and callees by cumtime descending
    for stat in fnStats.values():
        stat.callers.sort(key=lambda c: c.cumtime, reverse=True)
        stat.callees.sort(key=lambda c: c.cumtime, reverse=True)

    # Build sorted lists
    bikeshedList = [s for s in fnStats.values() if s.category == "bikeshed"]
    bikeshedList.sort(key=lambda s: s.cumtime, reverse=True)

    allList = list(fnStats.values())
    allList.sort(key=lambda s: s.cumtime, reverse=True)

    # Build Call Tree
    callTree = buildCallTree(
        fnStats=fnStats,
        totalTime=effectiveTotalTime,
        rootFilter=rootFilter,
        leafFilter=leafFilter,
    )

    return ProfileAnalysis(
        targetName=targetName,
        totalWallTime=wallTime,
        totalCpuTime=totalCpuTime,
        totalCalls=totalCalls,
        primitiveCalls=primitiveCalls,
        phases=phases,
        functions=fnStats,
        bikeshedFunctions=bikeshedList,
        topOverallFunctions=allList,
        stats=ps,
        callTree=callTree,
    )


def buildCallTree(
    fnStats: dict[FunctionKey, FunctionStat],
    totalTime: float,
    rootFilter: str | None = None,
    leafFilter: str | None = None,
) -> CallTreeNode:
    """Build a pruned hierarchical call tree from function statistics, optionally filtered by root or leaf."""
    minTimeThreshold = totalTime * 0.002  # ignore branches < 0.2% of total

    # Find root candidates
    roots: list[FunctionKey] = []
    if rootFilter:
        for k, stat in fnStats.items():
            if rootFilter in stat.name or rootFilter in stat.location:
                roots.append(k)
    else:
        # Candidate roots: functions with no callers or no callers in fnStats
        for k, stat in fnStats.items():
            if not stat.callers and stat.cumtime >= minTimeThreshold:
                roots.append(k)

    if not roots:
        # Fallback to the top function by cumtime
        top = max(fnStats.values(), key=lambda s: s.cumtime)
        roots = [top.key]

    def expandNode(
        key: FunctionKey,
        currentCumtime: float,
        ancestors: frozenset[FunctionKey],
        depth: int,
    ) -> CallTreeNode:
        """Recursively expand a function node and its significant callees while guarding against cycles."""
        stat = fnStats[key]
        pct = (currentCumtime / max(totalTime, 0.000001)) * 100.0
        node = CallTreeNode(
            name=stat.name,
            location=stat.location,
            category=stat.category,
            cumtime=currentCumtime,
            tottime=stat.tottime,
            ncalls=stat.ncalls,
            percent=pct,
        )

        if depth > 35:
            return node

        newAncestors = ancestors | {key}
        for callee in stat.callees:
            if callee.cumtime < minTimeThreshold:
                continue
            if callee.key in ancestors:
                # Cycle / recursion detected
                calleeStat = fnStats.get(callee.key)
                if calleeStat:
                    node.children.append(
                        CallTreeNode(
                            name=f"{calleeStat.name} (recursive)",
                            location=calleeStat.location,
                            category=calleeStat.category,
                            cumtime=callee.cumtime,
                            tottime=calleeStat.tottime,
                            ncalls=callee.ncalls,
                            percent=(callee.cumtime / max(totalTime, 0.000001)) * 100.0,
                        ),
                    )
            else:
                childNode = expandNode(callee.key, callee.cumtime, newAncestors, depth + 1)
                node.children.append(childNode)

        return node

    rootChildren: list[CallTreeNode] = []
    for r in roots:
        stat = fnStats[r]
        rootChildren.append(expandNode(r, stat.cumtime, frozenset(), 0))

    # Apply leaf filter if requested
    if leafFilter:

        def pruneLeaves(n: CallTreeNode) -> CallTreeNode | None:
            """Keep only call tree branches leading to nodes matching leafFilter."""
            matches = leafFilter in n.name or leafFilter in n.location
            newChildren = []
            for c in n.children:
                pruned = pruneLeaves(c)
                if pruned:
                    newChildren.append(pruned)
            if matches or newChildren:
                n.children = newChildren
                return n
            return None

        filteredChildren = []
        for rc in rootChildren:
            pruned = pruneLeaves(rc)
            if pruned:
                filteredChildren.append(pruned)
        rootChildren = filteredChildren

    topNode = CallTreeNode(
        name="total",
        location="bikeshed",
        category="bikeshed",
        cumtime=totalTime,
        tottime=0.0,
        ncalls=1,
        percent=100.0,
        children=rootChildren,
    )
    return topNode


def printTerminalReport(
    analysis: ProfileAnalysis,
    *,
    sortBy: str = "cumtime",
    limit: int = 20,
    showAll: bool = False,
    callersFunc: str | None = None,
    calleesFunc: str | None = None,
) -> None:
    """Print a formatted terminal summary of pipeline phases, bottleneck functions, and caller/callee details."""
    asciiOnly = m.state.asciiOnly
    dividerChar = "=" if asciiOnly else "━"
    subDivider = "-" if asciiOnly else "─"

    m.say(dividerChar * 80)
    m.say(f"  BIKESHED PERFORMANCE PROFILE: {analysis.targetName}")
    durInfo = (
        f"  Total Wall Time: {formatDuration(analysis.totalWallTime)}  |  "
        + f"CPU Time: {formatDuration(analysis.totalCpuTime)}  |  "
        + f"Total Calls: {analysis.totalCalls:,}"
    )
    m.say(durInfo)
    m.say(dividerChar * 80)

    # 1. Pipeline Phases
    if analysis.phases:
        m.say("")
        m.say(
            f"── Pipeline Phases ({len(analysis.phases)} recorded) "
            + (subDivider * (54 - len(str(len(analysis.phases))))),
        )
        header = f"  {'Phase':<42} {'Duration':>10} {'% Total':>9}  {'Proportion':<12}"
        m.say(header)
        m.say("  " + (subDivider * 76))

        totalTime = max(analysis.totalWallTime, sum(p.elapsed for p in analysis.phases), 0.000001)
        # Filter phases that took at least 0.5ms or 0.2%
        visiblePhases = [p for p in analysis.phases if p.elapsed >= 0.0005 or (p.elapsed / totalTime) >= 0.002]
        # Sort by duration descending
        visiblePhases.sort(key=lambda p: p.elapsed, reverse=True)

        for p in visiblePhases:
            pct = (p.elapsed / totalTime) * 100.0
            pBar = formatBar(p.elapsed / totalTime, width=12, asciiOnly=asciiOnly)
            durStr = formatDuration(p.elapsed)
            nameStr = p.name if len(p.name) <= 42 else (p.name[:39] + "...")
            m.say(f"  {nameStr:<42} {durStr:>10} {pct:>8.1f}%  {pBar}")

    # 2. Top Functions
    fnList = analysis.topOverallFunctions if showAll else analysis.bikeshedFunctions
    titleKind = "All Functions" if showAll else "Bikeshed Code"

    if sortBy == "tottime":
        sortedFns = sorted(fnList, key=lambda s: s.tottime, reverse=True)
    elif sortBy == "calls":
        sortedFns = sorted(fnList, key=lambda s: s.ncalls, reverse=True)
    elif sortBy == "name":
        sortedFns = sorted(fnList, key=lambda s: s.name.lower())
    else:  # cumtime
        sortedFns = sorted(fnList, key=lambda s: s.cumtime, reverse=True)

    m.say("")
    m.say(
        f"── Top {titleKind} Bottlenecks (Sorted by {sortBy}) " + (subDivider * (45 - len(titleKind) - len(sortBy))),
    )
    header = f"  {'Function':<28} {'Location':<24} {'Calls':>7} {'Self':>9} {'%Tot':>6} {'Cumul':>9} {'%Cum':>6} {'PerCall':>8}"
    m.say(header)
    m.say("  " + (subDivider * 98))

    for s in sortedFns[:limit]:
        fname = s.name if len(s.name) <= 28 else (s.name[:25] + "...")
        floc = s.location if len(s.location) <= 24 else ("..." + s.location[-21:])
        callsStr = f"{s.ncalls:,}" if s.ncalls < 1000000 else f"{s.ncalls/1000000:.1f}M"
        totStr = formatDuration(s.tottime)
        cumStr = formatDuration(s.cumtime)
        perCallStr = formatDuration(s.percallCum)
        row = (
            f"  {fname:<28} {floc:<24} {callsStr:>7} {totStr:>9} {s.tottimePercent:>5.1f}% "
            + f"{cumStr:>9} {s.cumtimePercent:>5.1f}% {perCallStr:>8}"
        )
        m.say(row)

    # 3. If Bikeshed functions were shown, also show top overall non-bikeshed bottlenecks if any
    if not showAll:
        nonBikeshed = [s for s in analysis.topOverallFunctions if s.category != "bikeshed" and s.cumtime >= 0.005]
        if nonBikeshed:
            m.say("")
            m.say("── Top External & Runtime Bottlenecks " + (subDivider * 42))
            m.say(f"  {'Function':<28} {'Category':<12} {'Location':<20} {'Calls':>7} {'Cumul':>9} {'%Cum':>6}")
            m.say("  " + (subDivider * 86))
            for s in nonBikeshed[:8]:
                fname = s.name if len(s.name) <= 28 else (s.name[:25] + "...")
                floc = s.location if len(s.location) <= 20 else ("..." + s.location[-17:])
                callsStr = f"{s.ncalls:,}" if s.ncalls < 1000000 else f"{s.ncalls/1000000:.1f}M"
                cumStr = formatDuration(s.cumtime)
                m.say(
                    f"  {fname:<28} {s.category:<12} {floc:<20} {callsStr:>7} {cumStr:>9} {s.cumtimePercent:>5.1f}%",
                )

    # 4. Caller details for top bottlenecks or requested function
    targetsForCallers: list[FunctionStat] = []
    if callersFunc is not None:
        if callersFunc == "":
            targetsForCallers = sortedFns[:5]
        else:
            targetsForCallers = [
                s
                for s in analysis.functions.values()
                if callersFunc.lower() in s.name.lower() or callersFunc in s.location
            ][:5]
    else:
        # Default: show callers for the top 3 slowest functions with callers
        targetsForCallers = [s for s in sortedFns if s.callers][:3]

    if targetsForCallers:
        m.say("")
        m.say("── Callers of Key Bottlenecks " + (subDivider * 50))
        for stat in targetsForCallers:
            cumStr = formatDuration(stat.cumtime)
            m.say(f"  • {stat.location} ({stat.name}) [cumtime: {cumStr}, calls: {stat.ncalls:,}]")
            for caller in stat.callers[:4]:
                callerCum = formatDuration(caller.cumtime)
                pct = caller.percentOfCallee
                m.say(
                    f"      ↳ {caller.ncalls:,} calls ({callerCum}, {pct:4.1f}%) from {caller.location} ({caller.name})",
                )

    # 5. Callees details if requested
    if calleesFunc is not None:
        targetsForCallees = (
            sortedFns[:3]
            if calleesFunc == ""
            else [
                s
                for s in analysis.functions.values()
                if calleesFunc.lower() in s.name.lower() or calleesFunc in s.location
            ][:5]
        )
        if targetsForCallees:
            m.say("")
            m.say("── Callees of Functions " + (subDivider * 55))
            for stat in targetsForCallees:
                cumStr = formatDuration(stat.cumtime)
                m.say(f"  • {stat.location} ({stat.name}) [cumtime: {cumStr}] calls:")
                for callee in stat.callees[:6]:
                    calleeCum = formatDuration(callee.cumtime)
                    pct = callee.percentOfCaller
                    m.say(
                        f"      ⮡ {callee.ncalls:,} calls ({calleeCum}, {pct:4.1f}%) to {callee.location} ({callee.name})",
                    )

    # Footer tips
    m.say("")
    m.say("Profile hints:")
    m.say("  • Generate interactive HTML dashboard: bikeshed profile <spec> --html report.html")
    m.say("  • Generate interactive SVG flamegraph: bikeshed profile <spec> --svg flame.svg")
    m.say("  • Export machine-readable JSON:        bikeshed profile <spec> --json [report.json]")
    m.say("  • Inspect function callers/callees:   bikeshed profile <spec> --callers [func] / --callees [func]")
    m.say("  • Profile a synthetic benchmark spec:  bikeshed profile --synthetic [size] [--save-synthetic [out.bs]]")


def exportJson(analysis: ProfileAnalysis) -> dict[str, t.Any]:
    """Convert a ProfileAnalysis into a JSON-serializable dictionary of phases, bottlenecks, and call tree."""
    totalTime = max(analysis.totalWallTime, 0.000001)

    phasesData = [
        {
            "name": p.name,
            "group": p.group,
            "duration": p.elapsed,
            "percent": round((p.elapsed / totalTime) * 100.0, 2),
        }
        for p in analysis.phases
    ]

    def serializeFn(s: FunctionStat) -> dict[str, t.Any]:
        """Serialize a FunctionStat and its top callers and callees into a dictionary."""
        return {
            "name": s.name,
            "location": s.location,
            "filename": s.filename,
            "line": s.line,
            "category": s.category,
            "calls": s.ncalls,
            "primitive_calls": s.pcalls,
            "tottime": round(s.tottime, 6),
            "cumtime": round(s.cumtime, 6),
            "tottime_percent": round(s.tottimePercent, 2),
            "cumtime_percent": round(s.cumtimePercent, 2),
            "percall_tot": round(s.percallTot, 6),
            "percall_cum": round(s.percallCum, 6),
            "callers": [
                {
                    "name": c.name,
                    "location": c.location,
                    "category": c.category,
                    "calls": c.ncalls,
                    "cumtime": round(c.cumtime, 6),
                    "percent_of_callee": round(c.percentOfCallee, 1),
                }
                for c in s.callers[:10]
            ],
            "callees": [
                {
                    "name": c.name,
                    "location": c.location,
                    "category": c.category,
                    "calls": c.ncalls,
                    "cumtime": round(c.cumtime, 6),
                    "percent_of_caller": round(c.percentOfCaller, 1),
                }
                for c in s.callees[:10]
            ],
        }

    return {
        "target": analysis.targetName,
        "total_wall_time": round(analysis.totalWallTime, 6),
        "total_cpu_time": round(analysis.totalCpuTime, 6),
        "total_calls": analysis.totalCalls,
        "primitive_calls": analysis.primitiveCalls,
        "phases": phasesData,
        "bikeshed_bottlenecks": [serializeFn(s) for s in analysis.bikeshedFunctions[:50]],
        "top_overall": [serializeFn(s) for s in analysis.topOverallFunctions[:50]],
        "call_tree": analysis.callTree.toDict() if analysis.callTree else None,
    }


def generateSvgFlamegraph(
    analysis: ProfileAnalysis,
    width: int = 1200,
    rowHeight: int = 20,
) -> str:
    """Generate a self-contained, interactive SVG flamegraph from the analysis call tree."""
    tree = analysis.callTree
    if not tree or not tree.children:
        # Generate minimal SVG indicating no data
        return f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="100"><text x="20" y="50" font-family="sans-serif">No profiling frames recorded.</text></svg>'

    # Layout flamegraph frames
    # Frames grow upwards from bottom
    # Colors:
    #   bikeshed: warm sunset hues (#e67e22, #d35400, #e74c3c, #f39c12)
    #   dependency: purple / blue (#8e44ad, #2980b9, #5c6bc0)
    #   stdlib: slate / cyan (#0097a7, #0288d1, #455a64)
    #   built-in: neutral gray (#78909c)

    # Flatten nodes with coordinates (depth, xFrac, wFrac)
    nodesLayout: list[dict[str, t.Any]] = []
    maxDepth = 0

    def layoutNode(node: CallTreeNode, depth: int, xFrac: float, wFrac: float) -> None:
        """Compute normalized layout coordinates for a call tree node and its descendants."""
        nonlocal maxDepth
        maxDepth = max(maxDepth, depth)

        nodesLayout.append(
            {
                "node": node,
                "depth": depth,
                "xFrac": xFrac,
                "wFrac": wFrac,
            },
        )

        currX = xFrac
        sumChildTime = sum(c.cumtime for c in node.children)
        for child in node.children:
            # allocate child width proportionally
            childW = (child.cumtime / max(node.cumtime, sumChildTime, 0.000001)) * wFrac
            if childW < 0.0005:  # skip subpixel frames
                continue
            layoutNode(child, depth + 1, currX, childW)
            currX += childW

    layoutNode(tree, 0, 0.0, 1.0)

    headerHeight = 60
    chartHeight = (maxDepth + 2) * rowHeight
    totalHeight = headerHeight + chartHeight

    def pickColor(category: str, name: str) -> str:
        """Pick a deterministic fill color for a flamegraph frame by category and name."""
        # Stable hash for variation
        hVal = abs(hash(name)) % 5
        if category == "bikeshed":
            colors = ["#e67e22", "#d35400", "#e74c3c", "#f39c12", "#c0392b"]
            return colors[hVal]
        if category == "dependency":
            colors = ["#8e44ad", "#9b59b6", "#5c6bc0", "#3f51b5", "#673ab7"]
            return colors[hVal]
        if category == "stdlib":
            colors = ["#0097a7", "#00838f", "#0288d1", "#0277bd", "#00695c"]
            return colors[hVal]
        # built-in
        colors = ["#78909c", "#607d8b", "#90a4ae", "#546e7a", "#b0bec5"]
        return colors[hVal]

    elements: list[str] = []
    # Build frames
    for item in nodesLayout:
        node: CallTreeNode = item["node"]
        depth: int = item["depth"]
        xFrac: float = item["xFrac"]
        wFrac: float = item["wFrac"]

        y = totalHeight - ((depth + 1) * rowHeight) - 10
        fill = pickColor(node.category, node.name)
        durStr = formatDuration(node.cumtime)
        tip = f"{node.name} | {node.location} | {durStr} ({node.percent:.1f}%) | {node.ncalls:,} calls"
        safeName = html.escape(node.name)
        safeTip = html.escape(tip)

        txt = safeName if (wFrac * width) >= 40 else ""
        elem = (
            f'<g class="frame" data-name="{safeName}" data-tip="{safeTip}" '
            + f'data-xf="{xFrac:.6f}" data-wf="{wFrac:.6f}" data-depth="{depth}">'
            + f'<rect x="{xFrac * width:.2f}" y="{y}" width="{max(0.5, wFrac * width):.2f}" '
            + f'height="{rowHeight - 1}" fill="{fill}" rx="2" ry="2"/>'
            + f'<text x="{xFrac * width + 4:.2f}" y="{y + rowHeight - 6}" font-size="11" '
            + 'font-family="monospace" fill="#ffffff" clip-path="url(#cp)">'
            + f"{txt}</text></g>"
        )
        elements.append(elem)

    framesXml = "\n".join(elements)

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {totalHeight}" width="100%" height="100%" style="background:#1e1e1e; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
  <style>
    .frame {{ cursor: pointer; transition: opacity 0.15s ease; }}
    .frame:hover rect {{ filter: brightness(1.25); stroke: #ffffff; stroke-width: 1; }}
    .frame.highlight rect {{ fill: #ffeb3b !important; stroke: #ff9800; stroke-width: 2; }}
    text {{ pointer-events: none; text-shadow: 0 1px 2px rgba(0,0,0,0.8); user-select: none; }}
    #tooltip {{ position: absolute; pointer-events: none; background: rgba(15,15,15,0.92); color: #fff; padding: 6px 12px; border-radius: 4px; font-size: 12px; font-family: monospace; border: 1px solid #444; z-index: 1000; display: none; }}
    .btn {{ cursor: pointer; fill: #333; rx: 4; ry: 4; }}
    .btn:hover {{ fill: #444; }}
    .btn-text {{ fill: #eee; font-size: 12px; user-select: none; }}
  </style>

  <rect width="{width}" height="{totalHeight}" fill="#181824"/>

  <!-- Header -->
  <text x="20" y="30" font-size="16" font-weight="bold" fill="#ffffff">Bikeshed Flamegraph: {html.escape(analysis.targetName)}</text>
  <text x="20" y="48" font-size="12" fill="#aaaaaa">Total: {formatDuration(analysis.totalWallTime)} | CPU: {formatDuration(analysis.totalCpuTime)} | Calls: {analysis.totalCalls:,} (Click frame to zoom, click top to reset)</text>

  <!-- Legend -->
  <g transform="translate({width - 420}, 20)">
    <rect x="0" y="0" width="12" height="12" fill="#e67e22" rx="2"/>
    <text x="18" y="10" font-size="11" fill="#ddd">Bikeshed</text>
    <rect x="90" y="0" width="12" height="12" fill="#8e44ad" rx="2"/>
    <text x="108" y="10" font-size="11" fill="#ddd">Dependency</text>
    <rect x="200" y="0" width="12" height="12" fill="#0097a7" rx="2"/>
    <text x="218" y="10" font-size="11" fill="#ddd">Stdlib</text>
    <rect x="270" y="0" width="12" height="12" fill="#78909c" rx="2"/>
    <text x="288" y="10" font-size="11" fill="#ddd">Built-in</text>
  </g>

  <!-- Reset Button -->
  <g id="reset-btn" transform="translate({width - 80}, 20)">
    <rect width="60" height="22" class="btn"/>
    <text x="12" y="15" class="btn-text">Reset</text>
  </g>

  <!-- Frames -->
  <g id="frames-group">
    {framesXml}
  </g>

  <!-- Status / Info text bar -->
  <text id="status-bar" x="20" y="{totalHeight - 4}" font-size="11" fill="#888888">Hover over a box for details; click to zoom in; click Reset to zoom out.</text>

  <script><![CDATA[
    (function() {{
      const svg = document.querySelector('svg');
      const width = {width};
      const totalHeight = {totalHeight};
      const rowHeight = {rowHeight};
      const frames = Array.from(document.querySelectorAll('.frame'));
      const statusBar = document.getElementById('status-bar');
      const resetBtn = document.getElementById('reset-btn');

      let zoomX = 0.0;
      let zoomW = 1.0;

      function updateZoom(newX, newW) {{
        zoomX = newX;
        zoomW = newW;
        frames.forEach(g => {{
          const xf = parseFloat(g.getAttribute('data-xf'));
          const wf = parseFloat(g.getAttribute('data-wf'));
          const depth = parseInt(g.getAttribute('data-depth'));
          const name = g.getAttribute('data-name');
          const rect = g.querySelector('rect');
          const text = g.querySelector('text');

          const newXf = (xf - zoomX) / zoomW;
          const newWf = wf / zoomW;

          if (newXf + newWf < -0.001 || newXf > 1.001) {{
            g.style.display = 'none';
          }} else {{
            g.style.display = '';
            const px = Math.max(0, newXf * width);
            const pw = Math.max(0.5, newWf * width);
            rect.setAttribute('x', px.toFixed(2));
            rect.setAttribute('width', pw.toFixed(2));
            text.setAttribute('x', (px + 4).toFixed(2));
            text.textContent = pw >= 40 ? name : '';
          }}
        }});
      }}

      frames.forEach(g => {{
        g.addEventListener('click', e => {{
          e.stopPropagation();
          const xf = parseFloat(g.getAttribute('data-xf'));
          const wf = parseFloat(g.getAttribute('data-wf'));
          updateZoom(xf, wf);
          statusBar.textContent = 'Zoomed into: ' + g.getAttribute('data-tip');
        }});
        g.addEventListener('mouseenter', () => {{
          statusBar.textContent = g.getAttribute('data-tip');
        }});
        g.addEventListener('mouseleave', () => {{
          statusBar.textContent = 'Hover over a box for details; click to zoom in; click Reset to zoom out.';
        }});
      }});

      if (resetBtn) {{
        resetBtn.addEventListener('click', () => {{
          updateZoom(0.0, 1.0);
          statusBar.textContent = 'Zoom reset to full view.';
        }});
      }}
    }})();
  ]]></script>
</svg>"""
    return svg


def generateHtmlReport(
    analysis: ProfileAnalysis,
) -> str:
    """Generate a standalone interactive HTML dashboard with flamegraph, phases, and function explorer."""
    svgFlamegraph = generateSvgFlamegraph(analysis)
    jsonData = json.dumps(exportJson(analysis))

    targetName = html.escape(analysis.targetName)
    wallTimeStr = formatDuration(analysis.totalWallTime)
    cpuTimeStr = formatDuration(analysis.totalCpuTime)
    callsStr = f"{analysis.totalCalls:,}"

    # Build phase items
    totalTime = max(analysis.totalWallTime, 0.000001)
    phasesHtml = []
    for p in analysis.phases:
        pct = (p.elapsed / totalTime) * 100.0
        durStr = formatDuration(p.elapsed)
        row = (
            f'<tr><td>{html.escape(p.name)}</td><td>{html.escape(p.group or "-")}</td>'
            + f'<td style="text-align:right;">{durStr}</td>'
            + f'<td style="text-align:right;">{pct:.1f}%</td>'
            + f'<td><div class="progress-bar"><div class="progress-fill" style="width:{pct:.1f}%;"></div></div></td></tr>'
        )
        phasesHtml.append(row)
    phasesRows = "\n".join(phasesHtml) if phasesHtml else "<tr><td colspan='5'>No phases recorded</td></tr>"

    htmlContent = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Bikeshed Profile: {targetName}</title>
  <style>
    :root {{
      --bg: #12121e;
      --card-bg: #1a1a2e;
      --card-border: #282846;
      --text: #e0e0ea;
      --text-muted: #8c8ca0;
      --primary: #4e8cff;
      --primary-hover: #6ea1ff;
      --accent-bikeshed: #e67e22;
      --accent-dep: #9b59b6;
      --accent-stdlib: #0097a7;
      --accent-builtin: #78909c;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.5;
      padding: 24px;
    }}
    header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 24px;
      padding-bottom: 16px;
      border-bottom: 1px solid var(--card-border);
    }}
    h1 {{ font-size: 24px; font-weight: 700; color: #fff; }}
    .subtitle {{ color: var(--text-muted); font-size: 14px; margin-top: 4px; }}
    .stat-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 16px;
      margin-bottom: 24px;
    }}
    .stat-card {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 8px;
      padding: 16px;
    }}
    .stat-title {{ font-size: 12px; color: var(--text-muted); text-transform: uppercase; font-weight: 600; letter-spacing: 0.5px; }}
    .stat-value {{ font-size: 26px; font-weight: 700; color: #fff; margin-top: 6px; }}
    .section {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 8px;
      padding: 20px;
      margin-bottom: 24px;
    }}
    .section-title {{
      font-size: 18px;
      font-weight: 600;
      color: #fff;
      margin-bottom: 16px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid var(--card-border); }}
    th {{ color: var(--text-muted); font-weight: 600; text-transform: uppercase; font-size: 11px; cursor: pointer; user-select: none; }}
    th:hover {{ color: #fff; }}
    tr:hover td {{ background: rgba(255,255,255,0.02); }}
    .progress-bar {{ background: rgba(255,255,255,0.08); height: 8px; border-radius: 4px; overflow: hidden; width: 120px; }}
    .progress-fill {{ background: var(--primary); height: 100%; border-radius: 4px; }}
    .badge {{
      display: inline-block;
      padding: 2px 8px;
      border-radius: 4px;
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
    }}
    .badge-bikeshed {{ background: rgba(230, 126, 34, 0.2); color: #f39c12; }}
    .badge-dependency {{ background: rgba(155, 89, 182, 0.2); color: #9b59b6; }}
    .badge-stdlib {{ background: rgba(0, 151, 167, 0.2); color: #00bcd4; }}
    .badge-builtin {{ background: rgba(120, 144, 156, 0.2); color: #90a4ae; }}
    .search-box {{
      padding: 8px 14px;
      border-radius: 6px;
      border: 1px solid var(--card-border);
      background: var(--bg);
      color: var(--text);
      font-size: 13px;
      width: 280px;
    }}
    .search-box:focus {{ outline: none; border-color: var(--primary); }}
    .tab-group {{ display: flex; gap: 8px; margin-bottom: 16px; }}
    .tab-btn {{
      background: var(--bg);
      border: 1px solid var(--card-border);
      color: var(--text-muted);
      padding: 6px 14px;
      border-radius: 6px;
      cursor: pointer;
      font-size: 12px;
      font-weight: 600;
    }}
    .tab-btn.active {{
      background: var(--primary);
      color: #fff;
      border-color: var(--primary);
    }}
    .tab-btn:hover:not(.active) {{ color: #fff; }}
    .flamegraph-container {{
      border: 1px solid var(--card-border);
      border-radius: 6px;
      overflow: hidden;
      margin-top: 12px;
    }}
    .drawer {{
      background: rgba(0,0,0,0.25);
      border-left: 3px solid var(--primary);
      padding: 12px 16px;
      margin: 8px 0;
      border-radius: 4px;
      font-size: 12px;
    }}
    .drawer h4 {{ color: #fff; margin-bottom: 6px; font-size: 13px; }}
    .drawer table {{ font-size: 12px; }}
    .jump-link {{ color: var(--primary); cursor: pointer; text-decoration: underline; }}
    .jump-link:hover {{ color: var(--primary-hover); }}
  </style>
</head>
<body>

  <header>
    <div>
      <h1>Bikeshed Performance Profile</h1>
      <div class="subtitle">Target: <strong>{targetName}</strong></div>
    </div>
    <div>
      <button class="tab-btn" onclick="downloadJSON()">Export JSON</button>
    </div>
  </header>

  <div class="stat-grid">
    <div class="stat-card">
      <div class="stat-title">Total Wall Time</div>
      <div class="stat-value">{wallTimeStr}</div>
    </div>
    <div class="stat-card">
      <div class="stat-title">Total CPU Time</div>
      <div class="stat-value">{cpuTimeStr}</div>
    </div>
    <div class="stat-card">
      <div class="stat-title">Function Calls</div>
      <div class="stat-value">{callsStr}</div>
    </div>
    <div class="stat-card">
      <div class="stat-title">Top Bikeshed Bottleneck</div>
      <div class="stat-value" style="font-size: 18px; color: #f39c12;">
        {html.escape(analysis.bikeshedFunctions[0].name if analysis.bikeshedFunctions else "N/A")}
      </div>
    </div>
  </div>

  <!-- Flamegraph Section -->
  <div class="section">
    <div class="section-title">
      <span>Interactive Flamegraph</span>
      <span style="font-size: 12px; color: var(--text-muted); font-weight: normal;">Click any rectangle to zoom into that call stack; click Reset in the SVG to zoom out.</span>
    </div>
    <div class="flamegraph-container">
      {svgFlamegraph}
    </div>
  </div>

  <!-- Pipeline Phases Section -->
  <div class="section">
    <div class="section-title">Pipeline Phases Breakdown</div>
    <table>
      <thead>
        <tr>
          <th>Phase</th>
          <th>Group</th>
          <th style="text-align:right;">Duration</th>
          <th style="text-align:right;">% Total</th>
          <th>Proportion</th>
        </tr>
      </thead>
      <tbody>
        {phasesRows}
      </tbody>
    </table>
  </div>

  <!-- Function Bottlenecks Explorer Section -->
  <div class="section">
    <div class="section-title">
      <span>Function Hotspots & Call Explorer</span>
      <input type="text" id="fn-search" class="search-box" placeholder="Filter functions or files..." oninput="filterTable()">
    </div>

    <div class="tab-group">
      <button class="tab-btn active" id="tab-bs" onclick="setCategory('bikeshed')">Bikeshed Code</button>
      <button class="tab-btn" id="tab-all" onclick="setCategory('all')">All Functions</button>
      <button class="tab-btn" id="tab-dep" onclick="setCategory('dependency')">Dependencies</button>
      <button class="tab-btn" id="tab-std" onclick="setCategory('stdlib')">Standard Library</button>
    </div>

    <table id="fn-table">
      <thead>
        <tr>
          <th onclick="sortTable('name')">Function</th>
          <th onclick="sortTable('category')">Category</th>
          <th onclick="sortTable('location')">Location</th>
          <th onclick="sortTable('calls')" style="text-align:right;">Calls</th>
          <th onclick="sortTable('tottime')" style="text-align:right;">Self Time</th>
          <th onclick="sortTable('tottime_percent')" style="text-align:right;">% Self</th>
          <th onclick="sortTable('cumtime')" style="text-align:right;">Cumul Time</th>
          <th onclick="sortTable('cumtime_percent')" style="text-align:right;">% Cumul</th>
          <th onclick="sortTable('percall_cum')" style="text-align:right;">Per Call</th>
        </tr>
      </thead>
      <tbody id="fn-tbody">
      </tbody>
    </table>
  </div>

  <script>
    const profileData = {jsonData};
    let currentCategory = 'bikeshed';
    let sortColumn = 'cumtime';
    let sortAsc = false;
    let selectedRowIndex = null;

    function formatDur(sec) {{
      if (sec >= 1.0) return sec.toFixed(2) + 's';
      if (sec >= 0.001) return (sec * 1000).toFixed(1) + 'ms';
      return (sec * 1000000).toFixed(0) + 'µs';
    }}

    function setCategory(cat) {{
      currentCategory = cat;
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      const activeBtn = document.getElementById('tab-' + (cat === 'bikeshed' ? 'bs' : cat === 'dependency' ? 'dep' : cat === 'stdlib' ? 'std' : 'all'));
      if (activeBtn) activeBtn.classList.add('active');
      renderTable();
    }}

    function sortTable(col) {{
      if (sortColumn === col) {{
        sortAsc = !sortAsc;
      }} else {{
        sortColumn = col;
        sortAsc = (col === 'name' || col === 'location' || col === 'category');
      }}
      renderTable();
    }}

    function filterTable() {{
      renderTable();
    }}

    function renderTable() {{
      const query = document.getElementById('fn-search').value.toLowerCase();
      let list = profileData.top_overall;
      if (currentCategory === 'bikeshed') {{
        list = profileData.bikeshed_bottlenecks;
      }} else if (currentCategory !== 'all') {{
        list = list.filter(fn => fn.category === currentCategory);
      }}

      if (query) {{
        list = list.filter(fn => fn.name.toLowerCase().includes(query) || fn.location.toLowerCase().includes(query));
      }}

      list.sort((a, b) => {{
        let v1 = a[sortColumn];
        let v2 = b[sortColumn];
        if (typeof v1 === 'string') return sortAsc ? v1.localeCompare(v2) : v2.localeCompare(v1);
        return sortAsc ? (v1 - v2) : (v2 - v1);
      }});

      const tbody = document.getElementById('fn-tbody');
      tbody.innerHTML = '';

      list.slice(0, 100).forEach((fn, idx) => {{
        const tr = document.createElement('tr');
        tr.style.cursor = 'pointer';
        tr.onclick = () => toggleDetails(idx, fn, tr);

        const badgeClass = 'badge-' + (fn.category || 'stdlib');
        tr.innerHTML = `
          <td><strong>${{fn.name}}</strong></td>
          <td><span class="badge ${{badgeClass}}">${{fn.category}}</span></td>
          <td style="color:var(--text-muted); font-family:monospace;">${{fn.location}}</td>
          <td style="text-align:right;">${{fn.calls.toLocaleString()}}</td>
          <td style="text-align:right;">${{formatDur(fn.tottime)}}</td>
          <td style="text-align:right;">${{fn.tottime_percent.toFixed(1)}}%</td>
          <td style="text-align:right; font-weight:600;">${{formatDur(fn.cumtime)}}</td>
          <td style="text-align:right; font-weight:600;">${{fn.cumtime_percent.toFixed(1)}}%</td>
          <td style="text-align:right; color:var(--text-muted);">${{formatDur(fn.percall_cum)}}</td>
        `;
        tbody.appendChild(tr);
      }});
    }}

    function toggleDetails(idx, fn, tr) {{
      const next = tr.nextElementSibling;
      if (next && next.classList.contains('details-row')) {{
        next.remove();
        return;
      }}
      document.querySelectorAll('.details-row').forEach(r => r.remove());

      const detailsTr = document.createElement('tr');
      detailsTr.className = 'details-row';
      const td = document.createElement('td');
      td.colSpan = 9;

      let callersHtml = '<em>No callers recorded</em>';
      if (fn.callers && fn.callers.length > 0) {{
        callersHtml = '<table><thead><tr><th>Caller</th><th>Calls</th><th>Cumul Time</th><th>% of Callee</th></tr></thead><tbody>';
        fn.callers.forEach(c => {{
          callersHtml += `<tr>
            <td><span class="jump-link" onclick="searchFor('${{c.name}}')">${{c.name}}</span> <span style="color:var(--text-muted); font-size:11px;">(${{c.location}})</span></td>
            <td>${{c.calls.toLocaleString()}}</td>
            <td>${{formatDur(c.cumtime)}}</td>
            <td>${{c.percent_of_callee.toFixed(1)}}%</td>
          </tr>`;
        }});
        callersHtml += '</tbody></table>';
      }}

      let calleesHtml = '<em>No callees recorded</em>';
      if (fn.callees && fn.callees.length > 0) {{
        calleesHtml = '<table><thead><tr><th>Callee</th><th>Calls</th><th>Cumul Time</th><th>% of Caller</th></tr></thead><tbody>';
        fn.callees.forEach(c => {{
          calleesHtml += `<tr>
            <td><span class="jump-link" onclick="searchFor('${{c.name}}')">${{c.name}}</span> <span style="color:var(--text-muted); font-size:11px;">(${{c.location}})</span></td>
            <td>${{c.calls.toLocaleString()}}</td>
            <td>${{formatDur(c.cumtime)}}</td>
            <td>${{c.percent_of_caller.toFixed(1)}}%</td>
          </tr>`;
        }});
        calleesHtml += '</tbody></table>';
      }}

      td.innerHTML = `
        <div class="drawer">
          <div style="display:grid; grid-template-columns: 1fr 1fr; gap: 20px;">
            <div>
              <h4>Called by (Callers):</h4>
              ${{callersHtml}}
            </div>
            <div>
              <h4>Calls (Callees):</h4>
              ${{calleesHtml}}
            </div>
          </div>
        </div>
      `;
      detailsTr.appendChild(td);
      tr.parentNode.insertBefore(detailsTr, tr.nextSibling);
    }}

    function searchFor(name) {{
      document.getElementById('fn-search').value = name;
      setCategory('all');
    }}

    function downloadJSON() {{
      const blob = new Blob([JSON.stringify(profileData, null, 2)], {{ type: 'application/json' }});
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'profile_' + (profileData.target.replace(/[^a-zA-Z0-9]/g, '_')) + '.json';
      a.click();
      URL.revokeObjectURL(url);
    }}

    // Initial render
    renderTable();
  </script>
</body>
</html>"""
    return htmlContent


def profileSpec(
    options: argparse.Namespace,
    extras: list[str],
    *,
    inputSource: InputSource.InputSource | None = None,
    targetName: str | None = None,
    defaultOutfile: str | None = None,
    saveOutput: bool = False,
) -> ProfileAnalysis:
    """Profile compiling a Bikeshed specification from a file path or explicit InputSource."""
    infile = getattr(options, "infile", None)
    timer = PhaseTimer(enabled=True)

    pr = cProfile.Profile()
    startWall = time.perf_counter()

    pr.enable()
    doc = Spec(
        inputFilename=infile if inputSource is None else None,
        inputSource=inputSource,
        debug=getattr(options, "debug", False),
        debugPrint=getattr(options, "debugPrint", None),
        token=getattr(options, "ghToken", None),
        lineNumbers=getattr(options, "lineNumbers", False),
        timer=timer,
    )
    if not doc.valid:
        pr.disable()
        m.die("Spec is in an invalid state; exitting.")
        sys.exit(1)

    doc.mdCommandLine = metadata.fromCommandLine(extras)
    errorLevel = getattr(options, "errorLevel", None) or "nothing"
    doc.mdCommandLine.addData("Die On", errorLevel)
    if getattr(options, "errorTiming", None):
        doc.mdCommandLine.addData("Die When", options.errorTiming)
    if getattr(options, "byos", False):
        doc.mdCommandLine.addData("Group", "byos")

    doc.preprocess()

    # Finish & serialize
    outfile = getattr(options, "outfile", None)
    shouldSaveOutput = saveOutput or getattr(options, "saveOutput", False) or bool(outfile)

    if shouldSaveOutput:
        doc.finish(outputFilename=outfile or defaultOutfile)
    else:
        # Dry run finish: serialize without writing file
        doc.serialize()

    pr.disable()
    elapsedWall = time.perf_counter() - startWall

    resolvedTarget = targetName or infile or (doc.inputSource.sourceName if doc.inputSource else "index.bs")

    analysis = analyzeProfile(
        pr=pr,
        wallTime=elapsedWall,
        phases=timer.phases,
        targetName=resolvedTarget,
        rootFilter=getattr(options, "root", None),
        leafFilter=getattr(options, "leaf", None),
    )
    return analysis


def profileSynthetic(
    sizeStr: str,
    options: argparse.Namespace,
    extras: list[str],
) -> ProfileAnalysis:
    """Generate a synthetic benchmark spec of sizeStr, optionally save it and its HTML, and profile it."""
    try:
        targetBytes = synthetic.parseSize(sizeStr)
    except ValueError as e:
        m.die(str(e))
        sys.exit(1)

    content = synthetic.generateSyntheticSpec(targetBytes)
    actualBytes = len(content.encode("utf-8"))
    lineCount = content.count("\n")

    saveSynthetic = getattr(options, "saveSynthetic", None)
    if saveSynthetic == "":
        saveSynthetic = synthetic.defaultFilename(sizeStr)
    if saveSynthetic is not None:
        try:
            with open(saveSynthetic, "w", encoding="utf-8") as fh:
                fh.write(content)
        except OSError as e:
            m.die(f"Couldn't save synthetic spec to '{saveSynthetic}':\n{e}")
            sys.exit(1)
        if getattr(options, "jsonFile", None) != "-":
            m.say(
                f"Saved synthetic spec ({synthetic.formatSize(actualBytes)}, {lineCount:,} lines) to {saveSynthetic}",
            )

    source = InputSource.StringInputSource(content, sourceName=saveSynthetic or "<synthetic>")
    targetName = f"synthetic ({synthetic.formatSize(actualBytes)}, {lineCount:,} lines)"
    defaultOutfile: str | None = None
    if saveSynthetic is not None:
        defaultOutfile = defaultOutputFilename(saveSynthetic)
    elif getattr(options, "saveOutput", False):
        defaultOutfile = "synthetic.html"

    analysis = profileSpec(
        options,
        extras,
        inputSource=source,
        targetName=targetName,
        defaultOutfile=defaultOutfile,
        saveOutput=saveSynthetic is not None,
    )

    resolvedOutfile = getattr(options, "outfile", None) or defaultOutfile
    if (
        saveSynthetic is not None
        and resolvedOutfile is not None
        and resolvedOutfile != "-"
        and not constants.dryRun
        and getattr(options, "jsonFile", None) != "-"
    ):
        m.say(f"Saved synthetic output HTML to {resolvedOutfile}")

    return analysis


def profileTest(options: argparse.Namespace) -> ProfileAnalysis:
    """Profile running Bikeshed's test suite with the configured test filters."""
    filters = test.TestFilter.fromOptions(options)
    timer = PhaseTimer(enabled=True)

    pr = cProfile.Profile()
    startWall = time.perf_counter()

    pr.enable()
    test.run(filters)
    pr.disable()

    elapsedWall = time.perf_counter() - startWall

    analysis = analyzeProfile(
        pr=pr,
        wallTime=elapsedWall,
        phases=timer.phases,
        targetName=f"test (filters={filters})",
        rootFilter=getattr(options, "root", None),
        leafFilter=getattr(options, "leaf", None),
    )
    return analysis


def profileCommand(commandStr: str, options: argparse.Namespace, cliMain: t.Callable[[], None]) -> ProfileAnalysis:
    """Run an arbitrary Bikeshed CLI command string under the profiler."""
    origArgv = sys.argv[:]
    timer = PhaseTimer(enabled=True)
    pr = cProfile.Profile()
    startWall = time.perf_counter()

    try:
        sys.argv = ["bikeshed", *commandStr.split()]
        pr.enable()
        cliMain()
    except SystemExit:
        pass
    finally:
        pr.disable()
        sys.argv = origArgv

    elapsedWall = time.perf_counter() - startWall

    analysis = analyzeProfile(
        pr=pr,
        wallTime=elapsedWall,
        phases=timer.phases,
        targetName=f"command: {commandStr}",
        rootFilter=getattr(options, "root", None),
        leafFilter=getattr(options, "leaf", None),
    )
    return analysis


def handleProfileCli(options: argparse.Namespace, extras: list[str], cliMain: t.Callable[[], None]) -> None:
    """Dispatch `bikeshed profile` CLI options to run profiling and emit requested reports."""
    syntheticSize = getattr(options, "syntheticSize", None)
    saveSynthetic = getattr(options, "saveSynthetic", None)
    isTestMode = bool(
        getattr(options, "profileTest", False)
        or getattr(options, "testFiles", None)
        or getattr(options, "testFolders", None),
    )
    isCommandMode = bool(getattr(options, "command", None))

    if saveSynthetic is not None and syntheticSize is None:
        m.die("--save-synthetic can only be used together with --synthetic.")
        sys.exit(1)

    if syntheticSize is not None:
        if isCommandMode or isTestMode:
            m.die("--synthetic cannot be combined with --test, --file, --folder, or --command.")
            sys.exit(1)
        if getattr(options, "infile", None):
            m.die("Cannot specify an input file together with --synthetic.")
            sys.exit(1)
        analysis = profileSynthetic(syntheticSize, options, extras)
    elif isCommandMode:
        analysis = profileCommand(options.command, options, cliMain)
    elif isTestMode:
        # Profiling tests
        # Adapt test options
        options.manualOnly = None
        options.folders = getattr(options, "testFolders", None)
        options.files = getattr(options, "testFiles", None)
        options.rebase = False
        analysis = profileTest(options)
    else:
        # Default: profile spec
        analysis = profileSpec(options, extras)

    # Save raw pstats if requested
    pstatsFile = getattr(options, "pstatsFile", None)
    if pstatsFile:
        analysis.stats.dump_stats(pstatsFile)
        m.say(f"Saved raw pstats to {pstatsFile}")

    # Generate and save SVG flamegraph if requested
    svgFile = getattr(options, "svgFile", None)
    if svgFile:
        svgContent = generateSvgFlamegraph(
            analysis,
        )
        with open(svgFile, "w", encoding="utf-8") as f:
            f.write(svgContent)
        m.say(f"Saved interactive SVG flamegraph to {svgFile}")

    # Generate and save HTML report if requested
    htmlFile = getattr(options, "htmlFile", None)
    if htmlFile:
        htmlContent = generateHtmlReport(analysis)
        with open(htmlFile, "w", encoding="utf-8") as f:
            f.write(htmlContent)
        m.say(f"Saved interactive HTML profile report to {htmlFile}")

    # JSON export
    jsonFile = getattr(options, "jsonFile", None)
    if jsonFile:
        jsonObj = exportJson(analysis)
        jsonStr = json.dumps(jsonObj, indent=2)
        if jsonFile == "-":
            with contextlib.suppress(BrokenPipeError):
                print(jsonStr)  # noqa: T201
            return
        with open(jsonFile, "w", encoding="utf-8") as f:
            f.write(jsonStr)
        m.say(f"Saved profile JSON to {jsonFile}")
        return

    # Print terminal report
    if not m.state.silent and m.state.printOn != "nothing":
        printTerminalReport(
            analysis=analysis,
            sortBy=getattr(options, "sortBy", "cumtime"),
            limit=getattr(options, "limit", 20),
            showAll=getattr(options, "showAll", False),
            callersFunc=getattr(options, "callersFunc", None),
            calleesFunc=getattr(options, "calleesFunc", None),
        )

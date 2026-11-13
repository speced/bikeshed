from __future__ import annotations

import contextlib
import cProfile
import dataclasses
import html
import io
import json
import os
import pstats
import re
import sys
import time
from typing import Any

from . import constants, t
from . import messages as m

if t.TYPE_CHECKING:
    import argparse

    from .Spec import Spec

FunctionKey = tuple[str, int, str]  # (filename, line, func_name)


@dataclasses.dataclass
class PhaseRecord:
    name: str
    elapsed: float
    group: str = ""


class PhaseTimer:
    def __init__(self, enabled: bool = False) -> None:
        self.enabled = enabled
        self.phases: list[PhaseRecord] = []

    @contextlib.contextmanager
    def phase(self, name: str, group: str = "") -> t.Generator[None, None, None]:
        if not self.enabled:
            yield
            return
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed = time.perf_counter() - start
            self.phases.append(PhaseRecord(name=name, elapsed=elapsed, group=group))

    def total_time(self) -> float:
        return sum(p.elapsed for p in self.phases)


@dataclasses.dataclass
class CallerInfo:
    key: FunctionKey
    name: str
    location: str
    category: str
    ncalls: int
    cumtime: float
    percent_of_callee: float


@dataclasses.dataclass
class CalleeInfo:
    key: FunctionKey
    name: str
    location: str
    category: str
    ncalls: int
    cumtime: float
    percent_of_caller: float


@dataclasses.dataclass
class FunctionStat:
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
    tottime_percent: float
    cumtime_percent: float
    percall_tot: float
    percall_cum: float
    callers: list[CallerInfo] = dataclasses.field(default_factory=list)
    callees: list[CalleeInfo] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class CallTreeNode:
    name: str
    location: str
    category: str
    cumtime: float
    tottime: float
    ncalls: int
    percent: float
    children: list[CallTreeNode] = dataclasses.field(default_factory=list)

    def to_dict(self) -> dict[str, t.Any]:
        return {
            "name": self.name,
            "location": self.location,
            "category": self.category,
            "cumtime": self.cumtime,
            "tottime": self.tottime,
            "ncalls": self.ncalls,
            "percent": self.percent,
            "children": [c.to_dict() for c in self.children],
        }


@dataclasses.dataclass
class ProfileAnalysis:
    target_name: str
    total_wall_time: float
    total_cpu_time: float
    total_calls: int
    primitive_calls: int
    phases: list[PhaseRecord]
    functions: dict[FunctionKey, FunctionStat]
    bikeshed_functions: list[FunctionStat]
    top_overall_functions: list[FunctionStat]
    stats: pstats.Stats
    call_tree: CallTreeNode | None = None


def get_bikeshed_root() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def categorize_function(filename: str, bikeshed_root: str) -> tuple[str, str]:
    """Returns (category, display_location)."""
    if filename.startswith("<") or filename == "~":
        return "built-in", filename

    norm_path = os.path.normpath(filename)
    if norm_path.startswith(bikeshed_root):
        rel = os.path.relpath(norm_path, bikeshed_root)
        return "bikeshed", rel

    if "site-packages" in norm_path or "dist-packages" in norm_path:
        parts = norm_path.replace("\\", "/").split("/")
        if "site-packages" in parts:
            idx = parts.index("site-packages")
            rel = "/".join(parts[idx + 1 :])
            return "dependency", rel
        if "dist-packages" in parts:
            idx = parts.index("dist-packages")
            rel = "/".join(parts[idx + 1 :])
            return "dependency", rel
        return "dependency", os.path.basename(norm_path)

    # Standard library or local python
    if "/lib/python" in norm_path or "\\lib\\python" in norm_path:
        parts = re.split(r"[/\\]lib[/\\]python\d+\.\d+[/\\]?", norm_path)
        if len(parts) > 1:
            return "stdlib", parts[-1]
        return "stdlib", os.path.basename(norm_path)

    return "stdlib", os.path.basename(norm_path)


def format_duration(seconds: float) -> str:
    if seconds >= 1.0:
        return f"{seconds:6.2f}s"
    if seconds >= 0.001:
        return f"{seconds * 1000:6.1f}ms"
    return f"{seconds * 1000000:6.0f}µs"


def format_bar(fraction: float, width: int = 12, ascii_only: bool = False) -> str:
    clamped = max(0.0, min(1.0, fraction))
    if ascii_only:
        bar_len = round(clamped * width)
        return "[" + "=" * bar_len + " " * (width - bar_len) + "]"
    blocks = [" ", "▏", "▎", "▍", "▌", "▋", "▊", "▉", "█"]
    total_eighths = round(clamped * width * 8)
    full_blocks = total_eighths // 8
    remainder = total_eighths % 8
    res = "█" * full_blocks
    if full_blocks < width and remainder > 0:
        res += blocks[remainder]
        full_blocks += 1
    res += " " * (width - full_blocks)
    return res


def analyze_profile(
    pr: cProfile.Profile,
    wall_time: float,
    phases: list[PhaseRecord],
    target_name: str,
    *,
    root_filter: str | None = None,
    leaf_filter: str | None = None,
) -> ProfileAnalysis:
    ps = pstats.Stats(pr)
    ps_any = t.cast(Any, ps)
    bikeshed_root = get_bikeshed_root()

    total_cpu_time = float(ps_any.total_tt)
    total_calls = int(ps_any.total_calls)
    primitive_calls = int(ps_any.prim_calls)

    effective_total_time = max(wall_time, total_cpu_time, 0.000001)

    raw_stats = dict(ps_any.stats)

    # First pass: categorize and build initial FunctionStat objects
    fn_stats: dict[FunctionKey, FunctionStat] = {}
    for key, (cc, nc, tt, ct, _) in raw_stats.items():
        fname, line, func_name = key
        category, loc = categorize_function(fname, bikeshed_root)
        display_loc = f"{loc}:{line}" if line > 0 else loc
        tot_pct = (tt / effective_total_time) * 100.0
        cum_pct = (ct / effective_total_time) * 100.0
        percall_tot = tt / max(1, nc)
        percall_cum = ct / max(1, nc)
        fn_stats[key] = FunctionStat(
            key=key,
            name=func_name,
            filename=fname,
            line=line,
            location=display_loc,
            category=category,
            ncalls=cc,
            pcalls=nc,
            tottime=tt,
            cumtime=ct,
            tottime_percent=tot_pct,
            cumtime_percent=cum_pct,
            percall_tot=percall_tot,
            percall_cum=percall_cum,
        )

    # Second pass: compute callers and callees
    for callee_key, (_, _, _, callee_ct, callers_dict) in raw_stats.items():
        callee_stat = fn_stats[callee_key]
        for caller_key, caller_info in callers_dict.items():
            if caller_key not in fn_stats:
                continue
            caller_stat = fn_stats[caller_key]
            caller_cc, _, _, caller_cumtime = caller_info
            pct_of_callee = (caller_cumtime / max(callee_ct, 0.000001)) * 100.0
            pct_of_caller = (caller_cumtime / max(caller_stat.cumtime, 0.000001)) * 100.0

            callee_stat.callers.append(
                CallerInfo(
                    key=caller_key,
                    name=caller_stat.name,
                    location=caller_stat.location,
                    category=caller_stat.category,
                    ncalls=caller_cc,
                    cumtime=caller_cumtime,
                    percent_of_callee=pct_of_callee,
                ),
            )

            caller_stat.callees.append(
                CalleeInfo(
                    key=callee_key,
                    name=callee_stat.name,
                    location=callee_stat.location,
                    category=callee_stat.category,
                    ncalls=caller_cc,
                    cumtime=caller_cumtime,
                    percent_of_caller=pct_of_caller,
                ),
            )

    # Sort callers and callees by cumtime descending
    for stat in fn_stats.values():
        stat.callers.sort(key=lambda c: c.cumtime, reverse=True)
        stat.callees.sort(key=lambda c: c.cumtime, reverse=True)

    # Build sorted lists
    bikeshed_list = [s for s in fn_stats.values() if s.category == "bikeshed"]
    bikeshed_list.sort(key=lambda s: s.cumtime, reverse=True)

    all_list = list(fn_stats.values())
    all_list.sort(key=lambda s: s.cumtime, reverse=True)

    # Build Call Tree
    call_tree = build_call_tree(
        fn_stats=fn_stats,
        total_time=effective_total_time,
        root_filter=root_filter,
        leaf_filter=leaf_filter,
    )

    return ProfileAnalysis(
        target_name=target_name,
        total_wall_time=wall_time,
        total_cpu_time=total_cpu_time,
        total_calls=total_calls,
        primitive_calls=primitive_calls,
        phases=phases,
        functions=fn_stats,
        bikeshed_functions=bikeshed_list,
        top_overall_functions=all_list,
        stats=ps,
        call_tree=call_tree,
    )


def build_call_tree(
    fn_stats: dict[FunctionKey, FunctionStat],
    total_time: float,
    root_filter: str | None = None,
    leaf_filter: str | None = None,
) -> CallTreeNode:
    min_time_threshold = total_time * 0.002  # ignore branches < 0.2% of total

    # Find root candidates
    roots: list[FunctionKey] = []
    if root_filter:
        for k, stat in fn_stats.items():
            if root_filter in stat.name or root_filter in stat.location:
                roots.append(k)
    else:
        # Candidate roots: functions with no callers or no callers in fn_stats
        for k, stat in fn_stats.items():
            if not stat.callers and stat.cumtime >= min_time_threshold:
                roots.append(k)

    if not roots:
        # Fallback to the top function by cumtime
        top = max(fn_stats.values(), key=lambda s: s.cumtime)
        roots = [top.key]

    def expand_node(
        key: FunctionKey,
        current_cumtime: float,
        ancestors: frozenset[FunctionKey],
        depth: int,
    ) -> CallTreeNode:
        stat = fn_stats[key]
        pct = (current_cumtime / max(total_time, 0.000001)) * 100.0
        node = CallTreeNode(
            name=stat.name,
            location=stat.location,
            category=stat.category,
            cumtime=current_cumtime,
            tottime=stat.tottime,
            ncalls=stat.ncalls,
            percent=pct,
        )

        if depth > 35:
            return node

        new_ancestors = ancestors | {key}
        for callee in stat.callees:
            if callee.cumtime < min_time_threshold:
                continue
            if callee.key in ancestors:
                # Cycle / recursion detected
                callee_stat = fn_stats.get(callee.key)
                if callee_stat:
                    node.children.append(
                        CallTreeNode(
                            name=f"{callee_stat.name} (recursive)",
                            location=callee_stat.location,
                            category=callee_stat.category,
                            cumtime=callee.cumtime,
                            tottime=callee_stat.tottime,
                            ncalls=callee.ncalls,
                            percent=(callee.cumtime / max(total_time, 0.000001)) * 100.0,
                        ),
                    )
            else:
                child_node = expand_node(callee.key, callee.cumtime, new_ancestors, depth + 1)
                node.children.append(child_node)

        return node

    root_children: list[CallTreeNode] = []
    for r in roots:
        stat = fn_stats[r]
        root_children.append(expand_node(r, stat.cumtime, frozenset(), 0))

    # Apply leaf filter if requested
    if leaf_filter:

        def prune_leaves(n: CallTreeNode) -> CallTreeNode | None:
            matches = leaf_filter in n.name or leaf_filter in n.location
            new_children = []
            for c in n.children:
                pruned = prune_leaves(c)
                if pruned:
                    new_children.append(pruned)
            if matches or new_children:
                n.children = new_children
                return n
            return None

        filtered_children = []
        for rc in root_children:
            pruned = prune_leaves(rc)
            if pruned:
                filtered_children.append(pruned)
        root_children = filtered_children

    top_node = CallTreeNode(
        name="total",
        location="bikeshed",
        category="bikeshed",
        cumtime=total_time,
        tottime=0.0,
        ncalls=1,
        percent=100.0,
        children=root_children,
    )
    return top_node


def print_terminal_report(
    analysis: ProfileAnalysis,
    *,
    sort_by: str = "cumtime",
    limit: int = 20,
    show_all: bool = False,
    callers_func: str | None = None,
    callees_func: str | None = None,
) -> None:
    ascii_only = m.state.asciiOnly
    divider_char = "=" if ascii_only else "━"
    sub_divider = "-" if ascii_only else "─"

    m.say(divider_char * 80)
    m.say(f"  BIKESHED PERFORMANCE PROFILE: {analysis.target_name}")
    dur_info = (
        f"  Total Wall Time: {format_duration(analysis.total_wall_time)}  |  "
        + f"CPU Time: {format_duration(analysis.total_cpu_time)}  |  "
        + f"Total Calls: {analysis.total_calls:,}"
    )
    m.say(dur_info)
    m.say(divider_char * 80)

    # 1. Pipeline Phases
    if analysis.phases:
        m.say("")
        m.say(f"── Pipeline Phases ({len(analysis.phases)} recorded) " + (sub_divider * (54 - len(str(len(analysis.phases))))))
        header = f"  {'Phase':<42} {'Duration':>10} {'% Total':>9}  {'Proportion':<12}"
        m.say(header)
        m.say("  " + (sub_divider * 76))

        total_time = max(analysis.total_wall_time, sum(p.elapsed for p in analysis.phases), 0.000001)
        # Filter phases that took at least 0.5ms or 0.2%
        visible_phases = [p for p in analysis.phases if p.elapsed >= 0.0005 or (p.elapsed / total_time) >= 0.002]
        # Sort by duration descending
        visible_phases.sort(key=lambda p: p.elapsed, reverse=True)

        for p in visible_phases:
            pct = (p.elapsed / total_time) * 100.0
            bar = format_bar(p.elapsed / total_time, width=12, ascii_only=ascii_only)
            dur_str = format_duration(p.elapsed)
            name_str = p.name if len(p.name) <= 42 else (p.name[:39] + "...")
            m.say(f"  {name_str:<42} {dur_str:>10} {pct:>8.1f}%  {bar}")

    # 2. Top Functions
    fn_list = analysis.top_overall_functions if show_all else analysis.bikeshed_functions
    title_kind = "All Functions" if show_all else "Bikeshed Code"

    if sort_by == "tottime":
        sorted_fns = sorted(fn_list, key=lambda s: s.tottime, reverse=True)
    elif sort_by == "calls":
        sorted_fns = sorted(fn_list, key=lambda s: s.ncalls, reverse=True)
    elif sort_by == "name":
        sorted_fns = sorted(fn_list, key=lambda s: s.name.lower())
    else:  # cumtime
        sorted_fns = sorted(fn_list, key=lambda s: s.cumtime, reverse=True)

    m.say("")
    m.say(f"── Top {title_kind} Bottlenecks (Sorted by {sort_by}) " + (sub_divider * (45 - len(title_kind) - len(sort_by))))
    header = f"  {'Function':<28} {'Location':<24} {'Calls':>7} {'Self':>9} {'%Tot':>6} {'Cumul':>9} {'%Cum':>6} {'PerCall':>8}"
    m.say(header)
    m.say("  " + (sub_divider * 98))

    for s in sorted_fns[:limit]:
        fname = s.name if len(s.name) <= 28 else (s.name[:25] + "...")
        floc = s.location if len(s.location) <= 24 else ("..." + s.location[-21:])
        calls_str = f"{s.ncalls:,}" if s.ncalls < 1000000 else f"{s.ncalls/1000000:.1f}M"
        tot_str = format_duration(s.tottime)
        cum_str = format_duration(s.cumtime)
        per_call_str = format_duration(s.percall_cum)
        row = (
            f"  {fname:<28} {floc:<24} {calls_str:>7} {tot_str:>9} {s.tottime_percent:>5.1f}% "
            + f"{cum_str:>9} {s.cumtime_percent:>5.1f}% {per_call_str:>8}"
        )
        m.say(row)

    # 3. If Bikeshed functions were shown, also show top 5 overall non-bikeshed bottlenecks if any
    if not show_all:
        non_bikeshed = [s for s in analysis.top_overall_functions if s.category != "bikeshed" and s.cumtime >= 0.005]
        if non_bikeshed:
            m.say("")
            m.say("── Top External & Runtime Bottlenecks " + (sub_divider * 42))
            m.say(f"  {'Function':<28} {'Category':<12} {'Location':<20} {'Calls':>7} {'Cumul':>9} {'%Cum':>6}")
            m.say("  " + (sub_divider * 86))
            for s in non_bikeshed[:8]:
                fname = s.name if len(s.name) <= 28 else (s.name[:25] + "...")
                floc = s.location if len(s.location) <= 20 else ("..." + s.location[-17:])
                calls_str = f"{s.ncalls:,}" if s.ncalls < 1000000 else f"{s.ncalls/1000000:.1f}M"
                cum_str = format_duration(s.cumtime)
                m.say(f"  {fname:<28} {s.category:<12} {floc:<20} {calls_str:>7} {cum_str:>9} {s.cumtime_percent:>5.1f}%")

    # 4. Caller details for top bottlenecks or requested function
    targets_for_callers: list[FunctionStat] = []
    if callers_func is not None:
        if callers_func == "":
            targets_for_callers = sorted_fns[:5]
        else:
            targets_for_callers = [
                s for s in analysis.functions.values() if callers_func.lower() in s.name.lower() or callers_func in s.location
            ][:5]
    else:
        # Default: show callers for the top 3 slowest functions with callers
        targets_for_callers = [s for s in sorted_fns if s.callers][:3]

    if targets_for_callers:
        m.say("")
        m.say("── Callers of Key Bottlenecks " + (sub_divider * 50))
        for stat in targets_for_callers:
            cum_str = format_duration(stat.cumtime)
            m.say(f"  • {stat.location} ({stat.name}) [cumtime: {cum_str}, calls: {stat.ncalls:,}]")
            for caller in stat.callers[:4]:
                caller_cum = format_duration(caller.cumtime)
                pct = caller.percent_of_callee
                m.say(f"      ↳ {caller.ncalls:,} calls ({caller_cum}, {pct:4.1f}%) from {caller.location} ({caller.name})")

    # 5. Callees details if requested
    if callees_func is not None:
        targets_for_callees = (
            sorted_fns[:3]
            if callees_func == ""
            else [
                s for s in analysis.functions.values() if callees_func.lower() in s.name.lower() or callees_func in s.location
            ][:5]
        )
        if targets_for_callees:
            m.say("")
            m.say("── Callees of Functions " + (sub_divider * 55))
            for stat in targets_for_callees:
                cum_str = format_duration(stat.cumtime)
                m.say(f"  • {stat.location} ({stat.name}) [cumtime: {cum_str}] calls:")
                for callee in stat.callees[:6]:
                    callee_cum = format_duration(callee.cumtime)
                    pct = callee.percent_of_caller
                    m.say(f"      ⮡ {callee.ncalls:,} calls ({callee_cum}, {pct:4.1f}%) to {callee.location} ({callee.name})")

    # Footer tips
    m.say("")
    m.say("Profile hints:")
    m.say("  • Generate interactive HTML dashboard: bikeshed profile <spec> --html report.html")
    m.say("  • Generate interactive SVG flamegraph: bikeshed profile <spec> --svg flame.svg")
    m.say("  • Export machine-readable JSON:        bikeshed profile <spec> --json [report.json]")
    m.say("  • Inspect function callers/callees:   bikeshed profile <spec> --callers [func] / --callees [func]")


def export_json(analysis: ProfileAnalysis) -> dict[str, t.Any]:
    total_time = max(analysis.total_wall_time, 0.000001)

    phases_data = [
        {
            "name": p.name,
            "group": p.group,
            "duration": p.elapsed,
            "percent": round((p.elapsed / total_time) * 100.0, 2),
        }
        for p in analysis.phases
    ]

    def serialize_fn(s: FunctionStat) -> dict[str, t.Any]:
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
            "tottime_percent": round(s.tottime_percent, 2),
            "cumtime_percent": round(s.cumtime_percent, 2),
            "percall_tot": round(s.percall_tot, 6),
            "percall_cum": round(s.percall_cum, 6),
            "callers": [
                {
                    "name": c.name,
                    "location": c.location,
                    "category": c.category,
                    "calls": c.ncalls,
                    "cumtime": round(c.cumtime, 6),
                    "percent_of_callee": round(c.percent_of_callee, 1),
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
                    "percent_of_caller": round(c.percent_of_caller, 1),
                }
                for c in s.callees[:10]
            ],
        }

    return {
        "target": analysis.target_name,
        "total_wall_time": round(analysis.total_wall_time, 6),
        "total_cpu_time": round(analysis.total_cpu_time, 6),
        "total_calls": analysis.total_calls,
        "primitive_calls": analysis.primitive_calls,
        "phases": phases_data,
        "bikeshed_bottlenecks": [serialize_fn(s) for s in analysis.bikeshed_functions[:50]],
        "top_overall": [serialize_fn(s) for s in analysis.top_overall_functions[:50]],
        "call_tree": analysis.call_tree.to_dict() if analysis.call_tree else None,
    }


def generate_svg_flamegraph(
    analysis: ProfileAnalysis,
    width: int = 1200,
    row_height: int = 20,
) -> str:
    """Generates a self-contained, interactive SVG flamegraph."""
    tree = analysis.call_tree
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

    # Flatten nodes with coordinates (depth, x_fraction, width_fraction)
    nodes_layout: list[dict[str, t.Any]] = []
    max_depth = 0

    def layout_node(node: CallTreeNode, depth: int, x_frac: float, w_frac: float) -> None:
        nonlocal max_depth
        max_depth = max(max_depth, depth)

        nodes_layout.append(
            {
                "node": node,
                "depth": depth,
                "x_frac": x_frac,
                "w_frac": w_frac,
            },
        )

        curr_x = x_frac
        sum_child_time = sum(c.cumtime for c in node.children)
        for child in node.children:
            # allocate child width proportionally
            child_w = (child.cumtime / max(node.cumtime, sum_child_time, 0.000001)) * w_frac
            if child_w < 0.0005:  # skip subpixel frames
                continue
            layout_node(child, depth + 1, curr_x, child_w)
            curr_x += child_w

    layout_node(tree, 0, 0.0, 1.0)

    header_height = 60
    chart_height = (max_depth + 2) * row_height
    total_height = header_height + chart_height

    def pick_color(category: str, name: str) -> str:
        # Stable hash for variation
        h_val = abs(hash(name)) % 5
        if category == "bikeshed":
            colors = ["#e67e22", "#d35400", "#e74c3c", "#f39c12", "#c0392b"]
            return colors[h_val]
        if category == "dependency":
            colors = ["#8e44ad", "#9b59b6", "#5c6bc0", "#3f51b5", "#673ab7"]
            return colors[h_val]
        if category == "stdlib":
            colors = ["#0097a7", "#00838f", "#0288d1", "#0277bd", "#00695c"]
            return colors[h_val]
        # built-in
        colors = ["#78909c", "#607d8b", "#90a4ae", "#546e7a", "#b0bec5"]
        return colors[h_val]

    elements: list[str] = []
    # Build frames
    for item in nodes_layout:
        node: CallTreeNode = item["node"]
        depth: int = item["depth"]
        x_frac: float = item["x_frac"]
        w_frac: float = item["w_frac"]

        y = total_height - ((depth + 1) * row_height) - 10
        fill = pick_color(node.category, node.name)
        dur_str = format_duration(node.cumtime)
        tip = f"{node.name} | {node.location} | {dur_str} ({node.percent:.1f}%) | {node.ncalls:,} calls"
        safe_name = html.escape(node.name)
        safe_tip = html.escape(tip)

        txt = safe_name if (w_frac * width) >= 40 else ""
        elem = (
            f'<g class="frame" data-name="{safe_name}" data-tip="{safe_tip}" '
            + f'data-xf="{x_frac:.6f}" data-wf="{w_frac:.6f}" data-depth="{depth}">'
            + f'<rect x="{x_frac * width:.2f}" y="{y}" width="{max(0.5, w_frac * width):.2f}" '
            + f'height="{row_height - 1}" fill="{fill}" rx="2" ry="2"/>'
            + f'<text x="{x_frac * width + 4:.2f}" y="{y + row_height - 6}" font-size="11" '
            + 'font-family="monospace" fill="#ffffff" clip-path="url(#cp)">'
            + f"{txt}</text></g>"
        )
        elements.append(elem)

    frames_xml = "\n".join(elements)

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {total_height}" width="100%" height="100%" style="background:#1e1e1e; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
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

  <rect width="{width}" height="{total_height}" fill="#181824"/>

  <!-- Header -->
  <text x="20" y="30" font-size="16" font-weight="bold" fill="#ffffff">Bikeshed Flamegraph: {html.escape(analysis.target_name)}</text>
  <text x="20" y="48" font-size="12" fill="#aaaaaa">Total: {format_duration(analysis.total_wall_time)} | CPU: {format_duration(analysis.total_cpu_time)} | Calls: {analysis.total_calls:,} (Click frame to zoom, click top to reset)</text>

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
    {frames_xml}
  </g>

  <!-- Status / Info text bar -->
  <text id="status-bar" x="20" y="{total_height - 4}" font-size="11" fill="#888888">Hover over a box for details; click to zoom in; click Reset to zoom out.</text>

  <script><![CDATA[
    (function() {{
      const svg = document.querySelector('svg');
      const width = {width};
      const totalHeight = {total_height};
      const rowHeight = {row_height};
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


def generate_html_report(
    analysis: ProfileAnalysis,
    root_filter: str | None = None,
    leaf_filter: str | None = None,
) -> str:
    """Generates an all-in-one standalone HTML profile report."""
    svg_flamegraph = generate_svg_flamegraph(analysis)
    json_data = json.dumps(export_json(analysis))

    target_name = html.escape(analysis.target_name)
    wall_time_str = format_duration(analysis.total_wall_time)
    cpu_time_str = format_duration(analysis.total_cpu_time)
    calls_str = f"{analysis.total_calls:,}"

    # Build phase items
    total_time = max(analysis.total_wall_time, 0.000001)
    phases_html = []
    for p in analysis.phases:
        pct = (p.elapsed / total_time) * 100.0
        dur_str = format_duration(p.elapsed)
        row = (
            f'<tr><td>{html.escape(p.name)}</td><td>{html.escape(p.group or "-")}</td>'
            + f'<td style="text-align:right;">{dur_str}</td>'
            + f'<td style="text-align:right;">{pct:.1f}%</td>'
            + f'<td><div class="progress-bar"><div class="progress-fill" style="width:{pct:.1f}%;"></div></div></td></tr>'
        )
        phases_html.append(row)
    phases_rows = "\n".join(phases_html) if phases_html else "<tr><td colspan='5'>No phases recorded</td></tr>"

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Bikeshed Profile: {target_name}</title>
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
      <div class="subtitle">Target: <strong>{target_name}</strong></div>
    </div>
    <div>
      <button class="tab-btn" onclick="downloadJSON()">Export JSON</button>
    </div>
  </header>

  <div class="stat-grid">
    <div class="stat-card">
      <div class="stat-title">Total Wall Time</div>
      <div class="stat-value">{wall_time_str}</div>
    </div>
    <div class="stat-card">
      <div class="stat-title">Total CPU Time</div>
      <div class="stat-value">{cpu_time_str}</div>
    </div>
    <div class="stat-card">
      <div class="stat-title">Function Calls</div>
      <div class="stat-value">{calls_str}</div>
    </div>
    <div class="stat-card">
      <div class="stat-title">Top Bikeshed Bottleneck</div>
      <div class="stat-value" style="font-size: 18px; color: #f39c12;">
        {html.escape(analysis.bikeshed_functions[0].name if analysis.bikeshed_functions else "N/A")}
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
      {svg_flamegraph}
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
        {phases_rows}
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
    const profileData = {json_data};
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
    return html_content


def profile_spec(
    options: argparse.Namespace,
    extras: list[str],
) -> ProfileAnalysis:
    from . import metadata
    from .Spec import Spec

    infile = getattr(options, "infile", None)
    timer = PhaseTimer(enabled=True)

    pr = cProfile.Profile()
    start_wall = time.perf_counter()

    pr.enable()
    doc = Spec(
        inputFilename=infile,
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
    error_level = getattr(options, "errorLevel", None) or "nothing"
    doc.mdCommandLine.addData("Die On", error_level)
    if getattr(options, "errorTiming", None):
        doc.mdCommandLine.addData("Die When", options.errorTiming)
    if getattr(options, "byos", False):
        doc.mdCommandLine.addData("Group", "byos")

    doc.preprocess()

    # Finish & serialize
    outfile = getattr(options, "outfile", None)
    save_output = getattr(options, "saveOutput", False)
    if outfile and not save_output:
        save_output = True

    if save_output:
        doc.finish(outputFilename=outfile)
    else:
        # Dry run finish: serialize without writing file
        doc.serialize()

    pr.disable()
    elapsed_wall = time.perf_counter() - start_wall

    target_name = infile or (doc.inputSource.sourceName if doc.inputSource else "index.bs")

    analysis = analyze_profile(
        pr=pr,
        wall_time=elapsed_wall,
        phases=timer.phases,
        target_name=target_name,
        root_filter=getattr(options, "root", None),
        leaf_filter=getattr(options, "leaf", None),
    )
    return analysis


def profile_test(options: argparse.Namespace) -> ProfileAnalysis:
    from . import test

    filters = test.TestFilter.fromOptions(options)
    timer = PhaseTimer(enabled=True)

    pr = cProfile.Profile()
    start_wall = time.perf_counter()

    pr.enable()
    test.run(filters)
    pr.disable()

    elapsed_wall = time.perf_counter() - start_wall

    analysis = analyze_profile(
        pr=pr,
        wall_time=elapsed_wall,
        phases=timer.phases,
        target_name=f"test (filters={filters})",
        root_filter=getattr(options, "root", None),
        leaf_filter=getattr(options, "leaf", None),
    )
    return analysis


def profile_command(command_str: str, options: argparse.Namespace) -> ProfileAnalysis:
    """Runs an arbitrary bikeshed command string under the profiler."""
    from .cli import main

    orig_argv = sys.argv[:]
    timer = PhaseTimer(enabled=True)
    pr = cProfile.Profile()
    start_wall = time.perf_counter()

    try:
        sys.argv = ["bikeshed", *command_str.split()]
        pr.enable()
        main()
    except SystemExit:
        pass
    finally:
        pr.disable()
        sys.argv = orig_argv

    elapsed_wall = time.perf_counter() - start_wall

    analysis = analyze_profile(
        pr=pr,
        wall_time=elapsed_wall,
        phases=timer.phases,
        target_name=f"command: {command_str}",
        root_filter=getattr(options, "root", None),
        leaf_filter=getattr(options, "leaf", None),
    )
    return analysis


def handle_profile_cli(options: argparse.Namespace, extras: list[str]) -> None:
    # Check if profiling tests or custom command
    if getattr(options, "command", None):
        analysis = profile_command(options.command, options)
    elif getattr(options, "profileTest", False) or getattr(options, "testFiles", None) or getattr(options, "testFolders", None):
        # Profiling tests
        # Adapt test options
        options.manualOnly = None
        options.folders = getattr(options, "testFolders", None)
        options.files = getattr(options, "testFiles", None)
        options.rebase = False
        analysis = profile_test(options)
    else:
        # Default: profile spec
        analysis = profile_spec(options, extras)

    # Save raw pstats if requested
    pstats_file = getattr(options, "pstatsFile", None)
    if pstats_file:
        analysis.stats.dump_stats(pstats_file)
        m.say(f"Saved raw pstats to {pstats_file}")

    # Generate and save SVG flamegraph if requested
    svg_file = getattr(options, "svgFile", None)
    if svg_file:
        svg_content = generate_svg_flamegraph(
            analysis,
        )
        with open(svg_file, "w", encoding="utf-8") as f:
            f.write(svg_content)
        m.say(f"Saved interactive SVG flamegraph to {svg_file}")

    # Generate and save HTML report if requested
    html_file = getattr(options, "htmlFile", None)
    if html_file:
        html_content = generate_html_report(
            analysis,
            root_filter=getattr(options, "root", None),
            leaf_filter=getattr(options, "leaf", None),
        )
        with open(html_file, "w", encoding="utf-8") as f:
            f.write(html_content)
        m.say(f"Saved interactive HTML profile report to {html_file}")

    # JSON export
    json_file = getattr(options, "jsonFile", None)
    if json_file:
        json_obj = export_json(analysis)
        json_str = json.dumps(json_obj, indent=2)
        if json_file == "-":
            with contextlib.suppress(BrokenPipeError):
                print(json_str)
            return
        with open(json_file, "w", encoding="utf-8") as f:
            f.write(json_str)
        m.say(f"Saved profile JSON to {json_file}")
        return

    # Print terminal report
    if not m.state.silent and m.state.printOn != "nothing":
        print_terminal_report(
            analysis=analysis,
            sort_by=getattr(options, "sortBy", "cumtime"),
            limit=getattr(options, "limit", 20),
            show_all=getattr(options, "showAll", False),
            callers_func=getattr(options, "callersFunc", None),
            callees_func=getattr(options, "calleesFunc", None),
        )

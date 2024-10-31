from __future__ import annotations

import dataclasses
import json
import re
from abc import ABCMeta, abstractmethod
from pathlib import Path

from .. import config, h, t
from .. import messages as m


@dataclasses.dataclass
class JCManager:
    styles: dict[str, Style] = dataclasses.field(default_factory=dict)
    scripts: dict[str, Script] = dataclasses.field(default_factory=dict)

    def getStyles(self, allowList: t.BoolSet) -> list[Style]:
        styles: dict[str, Style] = {}
        for style in self.styles.values():
            if not style.insertable(allowList):
                continue
            styles[style.name] = style
        for script in self.scripts.values():
            if not script.insertable(allowList):
                continue
            if script.style and script.style.insertable(allowList):
                styles[script.style.name] = script.style
        return sorted(styles.values(), key=lambda x: x.name)

    def getScripts(self, allowList: t.BoolSet) -> list[Library | Script]:
        libs: dict[str, Library] = {}
        scripts: dict[str, Script] = {}
        for style in self.styles.values():
            if not style.insertable(allowList):
                continue
            if style.script and style.script.insertable(allowList):
                scripts[style.script.name] = style.script
        for script in self.scripts.values():
            if not script.insertable(allowList):
                continue
            if script.libraries:
                for lib in script.libraries.values():
                    if lib.insertable(allowList):
                        libs[lib.name] = lib
            scripts[script.name] = script
        return sorted(libs.values(), key=lambda x: x.name) + sorted(scripts.values(), key=lambda x: x.name)

    def _addCSS(self, name: str, moduleName: str = "stylescript") -> Style:
        if name not in self.styles:
            self.styles[name] = Style(name, Path(config.scriptPath(f"{moduleName}/{name}.css")))
        return self.styles[name]

    def _addJS(self, name: str, moduleName: str = "stylescript") -> Script:
        if name not in self.scripts:
            self.scripts[name] = Script(name, Path(config.scriptPath(f"{moduleName}/{name}.js")))
        return self.scripts[name]

    def addColors(self) -> None:
        self._addCSS("colors")

    def addMdLists(self) -> None:
        self._addCSS("md-lists")

    def addAutolinks(self) -> None:
        self._addCSS("autolinks")

    def addSelflinks(self) -> None:
        self._addCSS("selflinks")

    def addCounters(self) -> None:
        self._addCSS("counters")

    def addIssues(self) -> None:
        self._addCSS("issues")

    def addMdn(self) -> None:
        style = self._addCSS("mdn-anno", "mdn")
        if not style.script:
            style.script = Script("position-annos", Path(config.scriptPath("stylescript/position-annos.js")))

    def addCiu(self) -> None:
        style = self._addCSS("caniuse-panel", "caniuse")
        if not style.script:
            style.script = Script("position-annos", Path(config.scriptPath("stylescript/position-annos.js")))

    def addDomintro(self) -> None:
        self._addCSS("domintro")

    def addSyntaxHighlighting(self) -> None:
        self._addCSS("syntax-highlighting", "highlight")

    def addLineNumbers(self) -> None:
        self._addCSS("line-numbers", "highlight")

    def addLineHighlighting(self) -> None:
        self._addCSS("line-highlighting", "highlight")

    def addExpires(self) -> None:
        self._addJS("expires")

    def addHidedel(self) -> None:
        self._addCSS("hidedel")

    def addVarClickHighlighting(self) -> None:
        script = self._addJS("var-click-highlighting")
        if not script.style:
            script.style = Style(
                "var-click-highlighting",
                Path(config.scriptPath("stylescript/var-click-highlighting.css")),
            )

    def addRefHints(self) -> t.JSONT:
        script = self._addJS("ref-hints", "refs")
        if not script.style:
            script.style = Style("ref-hints", Path(config.scriptPath("refs/ref-hints.css")))
        if "dom-helper" not in script.libraries:
            script.libraries["dom-helper"] = Library("dom-helper", Path(config.scriptPath("stylescript/dom-helper.js")))
        if not script.data:
            script.data = ("refsData", {})
        return script.data[1]

    def addLinkTitles(self) -> t.JSONT:
        script = self._addJS("link-titles")
        if not script.data:
            script.data = ("linkTitleData", {})
        return script.data[1]

    def addIDLHighlighting(self) -> None:
        self._addCSS("idl-highlighting")

    def addRailroad(self) -> None:
        self._addCSS("railroad")

    def addWptCSS(self) -> None:
        self._addCSS("wpt", "wpt")

    def addWpt(self, paths: list[str] | None) -> None:
        script = self._addJS("wpt", "wpt")
        if not script.style:
            script.style = Style("wpt", Path(config.scriptPath("wpt/wpt.css")))
        if "dom-helper" not in script.libraries:
            script.libraries["dom-helper"] = Library("dom-helper", Path(config.scriptPath("stylescript/dom-helper.js")))
        if not script.data:
            script.data = ("wptData", {"paths": []})
        if paths:
            script.data[1]["paths"] = sorted(set(script.data[1]["paths"] + paths))

    def addDfnPanels(self) -> t.JSONT:
        script = self._addJS("dfn-panel", "dfnpanels")
        if not script.style:
            script.style = Style("dfn-panel", Path(config.scriptPath("dfnpanels/dfn-panel.css")))
        if "dom-helper" not in script.libraries:
            script.libraries["dom-helper"] = Library("dom-helper", Path(config.scriptPath("stylescript/dom-helper.js")))
        if not script.data:
            script.data = ("dfnPanelData", {})
        return script.data[1]


@dataclasses.dataclass
class JCResource(metaclass=ABCMeta):
    name: str

    @abstractmethod
    def insertable(self, allowList: t.BoolSet) -> bool:
        pass

    @abstractmethod
    def toElement(self) -> t.ElementT:
        pass


@dataclasses.dataclass
class Script(JCResource):
    path: Path
    libraries: dict[str, Library] = dataclasses.field(default_factory=dict)
    style: Style | None = None
    data: tuple[str, t.JSONT] | None = None

    def insertable(self, allowList: t.BoolSet) -> bool:
        if f"script-{self.name}" not in allowList:
            return False
        if self.data is None:
            return True
        if self.data[1]:  # noqa: SIM103
            return True
        return False

    def toElement(self) -> t.ElementT:
        text = f'/* Boilerplate: script-{self.name} */\n"use strict";\n{{\n'
        if self.data:
            text += f"let {self.data[0]} = {{\n"
            for key, val in sorted(self.data[1].items()):
                text += f'"{key}": {json.dumps(val, sort_keys=True, separators=(",",":"))},\n'
            text += "};\n\n"
        with self.path.open("r", encoding="utf-8") as fh:
            text += fh.read()
        if not text.endswith("\n"):
            text += "\n"
        text += "}\n"
        return h.E.script(text)


@dataclasses.dataclass
class Library(JCResource):
    path: Path

    def insertable(self, allowList: t.BoolSet) -> bool:
        return True

    def toElement(self) -> t.ElementT:
        with self.path.open("r", encoding="utf-8") as fh:
            text = fh.read()
        return h.E.script(f'/* Boilerplate: script-{self.name} */\n"use strict";\n{text}')


@dataclasses.dataclass
class Style(JCResource):
    textPath: Path
    script: Script | None = None

    def insertable(self, allowList: t.BoolSet) -> bool:
        return f"style-{self.name}" in allowList

    def toElement(self, darkMode: bool = True) -> t.ElementT:
        with self.textPath.open("r", encoding="utf-8") as fh:
            sheet = fh.read()
        if not darkMode:
            sheet = removeInlineDarkStyles(self.name, sheet)
        if not sheet.endswith("\n"):
            sheet += "\n"
        return h.E.style(f"/* Boilerplate: style-{self.name} */\n{sheet}")


darkModeRe = re.compile(
    r"""
    ^@media\s+\(prefers-color-scheme:\s*dark\s*\)\s*{$ # start of block
    .*? # inside the block
    ^}(\n?)
    """,
    re.MULTILINE | re.DOTALL | re.X,
)
darkModeMaybe = re.compile(r"prefers-color-scheme\s*:\s*dark")


def removeInlineDarkStyles(name: str, text: str) -> str:
    # Looks for an @media declaring dark-mode styles,
    # and removes it from the text.
    # Simplistic: requires the @media and the closing }
    # to be against the left margin, and the block's contents
    # to all be indented.

    maybeMatch = re.search(darkModeMaybe, text)
    if not maybeMatch:
        return text
    match = re.search(darkModeRe, text)
    if not match:
        m.warn(
            f"The {name} stylesheet appears to contain darkmode styles, but they aren't being correctly detected. Please report this to the Bikeshed maintainer.",
        )
        return text
    text = re.sub(darkModeRe, "", text)
    # In case there are multiple blocks
    text = removeInlineDarkStyles(name, text)
    return text

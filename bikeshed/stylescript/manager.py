from __future__ import annotations

import dataclasses
import re

from .. import config, h, messages as m, t


@dataclasses.dataclass
class ScriptManager:
    scripts: list[Script] = dataclasses.field(default_factory=list)

    def set(self, name: str, text: str) -> None:
        self.scripts.append(Script(name, text))

    def setFile(self, name: str, localPath: str) -> None:
        with open(config.scriptPath(localPath), "r", encoding="utf-8") as fh:
            self.set(name, fh.read())

    def setDefault(self, name: str, text: str) -> Script:
        if self.has(name):
            return self.get(name)
        script = Script(name, text)
        self.scripts.append(script)
        return script

    def get(self, name: str) -> Script:
        for x in self.scripts:
            if x.name == name:
                return x
        raise KeyError()

    def getAll(self) -> list[Script]:
        return list(sorted(self.scripts, key=lambda x: x.name))

    def has(self, name: str) -> bool:
        for x in self.scripts:
            if x.name == name:
                return True
        return False


@dataclasses.dataclass
class StyleManager:
    styles: list[Style] = dataclasses.field(default_factory=list)

    def set(self, name: str, text: str, dark: str | None = None) -> None:
        self.styles.append(Style(name, text, dark))

    def setFile(self, name: str, localPath: str, darkPath: str | None = None) -> None:
        with open(config.scriptPath(localPath), "r", encoding="utf-8") as fh:
            text = fh.read()
        if darkPath:
            with open(config.scriptPath(darkPath), "r", encoding="utf-8") as fh:
                dark = fh.read()
        else:
            dark = None
        self.set(name, text, dark)

    def setDefault(self, name: str, text: str, dark: str | None = None) -> Style:
        if self.has(name):
            return self.get(name)
        style = Style(name, text, dark)
        self.styles.append(style)
        return style

    def get(self, name: str) -> Style:
        for x in self.styles:
            if x.name == name:
                return x
        raise KeyError()

    def getAll(self) -> list[Style]:
        return list(sorted(self.styles, key=lambda x: x.name))

    def has(self, name: str) -> bool:
        for x in self.styles:
            if x.name == name:
                return True
        return False


@dataclasses.dataclass
class Script:
    name: str
    text: str

    def toElement(self) -> t.ElementT:
        text = self.text
        if not self.text.endswith("\n"):
            text += "\n"
        return h.E.script(f"/* Boilerplate: script-{self.name} */\n{text}")


@dataclasses.dataclass
class Style:
    name: str
    text: str
    dark: str | None

    def toElement(self, darkMode: bool) -> t.ElementT:
        if darkMode:
            sheet = self.text
            if self.dark:
                sheet += "\n" + self.dark
        else:
            # Remove darkmode styles from the stylesheets
            sheet = removeInlineDarkStyles(self.name, self.text)
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
            f"The {name} stylesheet appears to contain darkmode styles, but they aren't being correctly detected. Please report this to the Bikeshed maintainer."
        )
        return text
    text = re.sub(darkModeRe, "", text)
    # In case there are multiple blocks
    text = removeInlineDarkStyles(name, text)
    return text

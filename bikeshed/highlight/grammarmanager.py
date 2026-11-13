from __future__ import annotations

import ast
import json
from pathlib import Path

from .. import config, t
from .. import messages as m

LANGUAGE_ALIASES: dict[str, str] = {
    "docker": "dockerfile",
    "gql": "graphql",
    "js": "javascript",
    "jsx": "javascript",
    "md": "markdown",
    "py": "python",
    "rb": "ruby",
    "sass": "scss",
    "sh": "bash",
    "shell": "bash",
    "ts": "typescript",
    "yml": "yaml",
    "zsh": "bash",
    "c++": "cpp",
    "c#": "csharp",
    "golang": "go",
    "markup": "html",
    "svg": "html",
}

SUPPORTED_THEMES: frozenset[str] = frozenset(
    [
        "cobalt2",
        "dracula",
        "flexoki",
        "github",
        "gruvbox",
        "min",
        "monokai",
        "night-owl",
        "solarized-light",
        "tokyo-night",
        "vesper",
        "vscode-plus",
        "none",
    ],
)


class HighlightGrammarManager:
    def __init__(self, doc: t.SpecT | None = None) -> None:
        self.doc = doc
        self.grammars: dict[str, dict[str, t.Any]] = {}
        self.grammarPaths: dict[str, str] = {}
        self.scopes: dict[str, dict[str, t.Any]] = {}
        self._builtins: set[str] | None = None

    def normalizeLanguage(self, lang: str | None) -> str | None:
        if lang is None:
            return None
        lang = lang.strip().lower()
        if lang == "aspnet":
            return "aspx-cs"
        if lang == "idl":
            return "webidl"
        return LANGUAGE_ALIASES.get(lang, lang)

    @property
    def builtins(self) -> set[str]:
        if self._builtins is None:
            grammars_dir = Path(config.scriptPath("highlight/grammars"))
            if grammars_dir.is_dir():
                self._builtins = {p.stem for p in grammars_dir.glob("*.json")}
            else:
                self._builtins = set()
        return self._builtins

    def hasGrammar(self, lang: str) -> bool:
        normalized = self.normalizeLanguage(lang)
        if not normalized:
            return False
        if normalized in self.grammars:
            return True
        if normalized in self.grammarPaths:
            return True
        if normalized in self.builtins:
            return True
        return False

    def addGrammarPath(self, lang: str, filePath: str) -> None:
        normalized = self.normalizeLanguage(lang)
        if not normalized:
            return
        self.grammarPaths[normalized] = filePath

    def addGrammar(self, lang: str, grammar: dict[str, t.Any]) -> None:
        normalized = self.normalizeLanguage(lang)
        if not normalized:
            return
        self.grammars[normalized] = grammar
        scopeName = grammar.get("scopeName")
        if isinstance(scopeName, str):
            self.scopes[scopeName] = grammar

    def addGrammarFromFile(self, lang: str, filePath: str, el: t.ElementT | None = None) -> None:
        if self.doc is None:
            m.die(f"Cannot load grammar '{lang}' without a document context.", el=el)
            return
        try:
            source = self.doc.inputSource.relative(filePath)
            if source is None:
                m.die(
                    f"Tried to load highlight grammar at '{filePath}', but the current input type can't resolve relative paths.",
                    el=el,
                )
                return
            self.doc.recordDependencies(source)
            input_content = source.read()
            if input_content is None:
                m.die(f"Couldn't read highlight grammar file at '{filePath}'.", el=el)
                return
            grammar = parseGrammarText(input_content.content)
            if not isinstance(grammar, dict):
                m.die(f"Highlight grammar at '{filePath}' must be a JSON object.", el=el)
                return
            self.addGrammar(lang, grammar)
        except Exception as e:
            m.die(f"Error loading highlight grammar from '{filePath}': {e}", el=el)

    def getGrammar(self, langOrScope: str) -> dict[str, t.Any] | None:
        normalized = self.normalizeLanguage(langOrScope)
        if normalized and normalized in self.grammars:
            return self.grammars[normalized]
        if normalized and normalized in self.grammarPaths:
            path = self.grammarPaths.pop(normalized)
            self.addGrammarFromFile(normalized, path)
            if normalized in self.grammars:
                return self.grammars[normalized]
        if langOrScope in self.scopes:
            return self.scopes[langOrScope]
        if normalized and normalized in self.builtins:
            grammar_path = Path(config.scriptPath(f"highlight/grammars/{normalized}.json"))
            try:
                with grammar_path.open("r", encoding="utf-8") as fh:
                    grammar = json.load(fh)
                if isinstance(grammar, dict):
                    self.grammars[normalized] = grammar
                    scopeName = grammar.get("scopeName")
                    if isinstance(scopeName, str):
                        self.scopes[scopeName] = grammar
                    return grammar
            except Exception as e:
                m.die(f"Error loading built-in grammar '{normalized}': {e}")
                return None
        return None

    def getExternalLanguages(self, grammar: dict[str, t.Any]) -> set[str]:
        languages: set[str] = set()

        def visit(item: t.Any) -> None:
            if isinstance(item, list):
                for x in item:
                    visit(x)
            elif isinstance(item, dict):
                inc = item.get("include")
                if isinstance(inc, str) and not inc.startswith("#") and not inc.startswith("$"):
                    scope = inc.split("#")[0]
                    # Check if scope matches source.<lang> or text.<lang>
                    parts = scope.split(".")
                    if len(parts) >= 2 and parts[0] in ("source", "text"):
                        languages.add(parts[1])
                for v in item.values():
                    visit(v)

        visit(grammar)
        return languages

    def getGrammarsForLanguages(self, languages: t.Iterable[str]) -> dict[str, dict[str, t.Any]]:
        result: dict[str, dict[str, t.Any]] = {}
        pending: set[str] = set()
        for lang in languages:
            norm = self.normalizeLanguage(lang)
            if norm:
                pending.add(norm)
        visited: set[str] = set()

        while pending:
            curr = pending.pop()
            if curr in visited:
                continue
            visited.add(curr)
            grammar = self.getGrammar(curr)
            if grammar is None:
                continue
            result[curr] = grammar
            for dep in self.getExternalLanguages(grammar):
                norm_dep = self.normalizeLanguage(dep)
                if norm_dep and norm_dep not in visited:
                    pending.add(norm_dep)

        return result


def parseGrammarText(text: str) -> dict[str, t.Any]:
    text = text.strip()
    try:
        res = json.loads(text)
        if isinstance(res, dict):
            return res
    except json.JSONDecodeError:
        pass

    # Fallback for JS object literal or comments
    # Strip comments and "export default"
    lines = [line for line in text.splitlines() if not line.strip().startswith("//")]
    cleaned = "\n".join(lines).strip()
    if cleaned.startswith("export default"):
        cleaned = cleaned[len("export default") :].strip()
    if cleaned.endswith(";"):
        cleaned = cleaned[:-1].strip()

    try:
        res = json.loads(cleaned)
        if isinstance(res, dict):
            return res
    except json.JSONDecodeError:
        pass

    try:
        # If it looks like a python/json dict with single quotes / true / false
        # We can safely evaluate with ast.literal_eval if true/false/null are mapped
        eval_text = cleaned.replace("true", "True").replace("false", "False").replace("null", "None")
        res = ast.literal_eval(eval_text)
        if isinstance(res, dict):
            return res
    except Exception:
        pass

    msg = "Could not parse grammar content as JSON"
    raise ValueError(msg)

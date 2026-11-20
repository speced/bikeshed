/*
Microlighter
MIT License
Copyright (c) 2026 Dave Rupert
https://github.com/davatron5000/microlighter
*/

const languageAliases = {
  "1c": "bsl",
  "1c-query": "sdbl",
  actionscript: "actionscript-3",
  adoc: "asciidoc",
  ahk1: "ahk",
  as3: "actionscript-3",
  asm: "assembly",
  batch: "bat",
  be: "berry",
  bison: "yacc",
  "c#": "csharp",
  "c++": "cpp",
  cdc: "cadence",
  chpl: "chapel",
  clj: "clojure",
  "closure-templates": "soy",
  cmd: "bat",
  coffeescript: "coffee",
  console: "shellsession",
  cql: "cypher",
  diff: "git-diff",
  docker: "dockerfile",
  elisp: "emacs-lisp",
  erl: "erlang",
  f: "fortran-fixed-form",
  "f#": "fsharp",
  f03: "fortran-free-form",
  f08: "fortran-free-form",
  f18: "fortran-free-form",
  f77: "fortran-fixed-form",
  f90: "fortran-free-form",
  f95: "fortran-free-form",
  flex: "lex",
  for: "fortran-fixed-form",
  fs: "fsharp",
  fsl: "jssm",
  ftl: "fluent",
  gd: "gdscript",
  gjs: "glimmer-js",
  golang: "go",
  gql: "graphql",
  grm: "gold",
  gts: "glimmer-ts",
  hbs: "handlebars",
  hs: "haskell",
  idl: "webidl",
  jade: "pug",
  jl: "julia",
  js: "javascript",
  jsx: "javascript",
  justfile: "just",
  lean4: "lean",
  lisp: "common-lisp",
  makefile: "make",
  markup: "html",
  mbt: "moonbit",
  mbti: "moonbit",
  md: "markdown",
  mediawiki: "wikitext",
  mmd: "mermaid",
  nar: "narrat",
  nf: "nextflow",
  nu: "nushell",
  peggy: "pegjs",
  perl6: "raku",
  protobuf: "proto",
  py: "python",
  ql: "codeql",
  rb: "ruby",
  regex: "regexp",
  "ruby-signature": "rbs",
  sass: "scss",
  scad: "openscad",
  sh: "bash",
  shader: "shaderlab",
  shell: "bash",
  shellscript: "bash",
  spl: "splunk",
  styl: "stylus",
  surql: "surrealql",
  svg: "html",
  talon: "talonscript",
  tres: "gdresource",
  ts: "typescript",
  tscn: "gdresource",
  tsp: "typespec",
  typ: "typst",
  vim: "viml",
  vimscript: "viml",
  vy: "vyper",
  wiki: "wikitext",
  wl: "wolfram",
  yml: "yaml",
  zsh: "bash",
  "文言": "wenyan"
};

const normalizeLanguage = (language, aliases = {}) =>
  aliases[language] || languageAliases[language] || language;

const getExternalLanguages = value => {
  const languages = new Set();
  const visit = item => {
    if (Array.isArray(item)) {
      item.forEach(visit);
    } else if (item && typeof item === "object") {
      if (typeof item.include === "string" && !/^[#$]/.test(item.include)) {
        const scope = item.include.split("#")[0];
        const match = scope.match(/^(?:source|text)\.([a-z0-9_-]+)/);
        if (match) languages.add(match[1]);
      }
      Object.values(item).forEach(visit);
    }
  };
  visit(value);
  return languages;
};

const inlinedGrammars = typeof highlightGrammars !== "undefined" ? highlightGrammars : {};

const getGrammar = language => Promise.resolve(inlinedGrammars[language] || null);

const createGrammarLoader = (importLanguage = getGrammar) => {
  const loadingLanguages = new Map();
  const grammars = {
    languages: {},
    scopes: new Map()
  };

  for (const [lang, grammar] of Object.entries(inlinedGrammars)) {
    if (grammar && grammar.scopeName) {
      grammars.languages[lang] = grammar;
      grammars.scopes.set(grammar.scopeName, grammar);
    }
  }

  const loadGrammar = language => {
    if (!loadingLanguages.has(language)) {
      const grammarModule = importLanguage(language).then(grammar => {
        if (grammar) {
          grammars.languages[language] = grammar;
          grammars.scopes.set(grammar.scopeName, grammar);
        }
        return grammar;
      });
      loadingLanguages.set(language, grammarModule);
    }

    return loadingLanguages.get(language);
  };

  return async languages => {
    const visited = new Set();
    let pending = [...new Set(languages)]
      .filter(language => /^[a-z0-9_-]+$/.test(language));

    while (pending.length) {
      pending.forEach(language => visited.add(language));
      const loaded = (await Promise.all(pending.map(loadGrammar))).filter(Boolean);
      pending = [...new Set(loaded.flatMap(grammar =>
        grammar.dependencies || [...getExternalLanguages(grammar)]
      ))].map(language => normalizeLanguage(language)).filter(language => !visited.has(language));
    }

    return grammars;
  };
};

const getLanguageClass = element => [...element.classList]
  .find(className => className.startsWith("language-") || className.startsWith("lang-"))
  ?.replace(/^(?:language|lang)-/, "");

const getLanguage = codeBlock => {
  const pre = codeBlock.parentElement;
  const language = codeBlock.dataset.language
    || getLanguageClass(codeBlock)
    || pre?.dataset.language
    || (pre ? getLanguageClass(pre) : "")
    || "";

  return language.toLowerCase();
};

const loadGrammars = createGrammarLoader();
const highlights = new Map();
const noMatch = { indices: [[Infinity, Infinity]] };

const themeCategories = new Set([
  "anchor", "animation", "at-rule", "attribute-name", "attribute-value",
  "boolean", "character-entity", "comment", "constant", "decorator",
  "deleted", "doctype", "entity", "function", "important", "inserted",
  "interpolation", "key", "keyword", "link", "numeric", "operator",
  "property", "punctuation", "quote", "raw", "regexp", "section",
  "selector", "storage", "string", "support", "symbol", "tag", "type",
  "variable"
]);

const entityNameAliases = {
  class: "type", struct: "type", interface: "type", enum: "type",
  trait: "type", module: "type", namespace: "type", record: "type",
  alias: "type", method: "function", macro: "function",
  constructor: "function", command: "function", label: "constant",
  "goto-label": "constant", filename: "string", field: "property",
  member: "property"
};

const getScopeCategory = scope => {
  const parts = scope.split(".");
  const [first, second, third] = parts;

  if (first === "markup") {
    if (["quote", "inserted", "deleted", "raw"].includes(second)) return second;
    if (second === "heading") return "section";
    if (second === "code" || second === "inline") return "raw";
    if (second === "underline" || second === "link") return "link";
    if (second === "bold" || second === "italic") return "keyword";
    if (second === "list") return "punctuation";
  }
  if (first === "entity" && second === "name") {
    if (themeCategories.has(third)) return third;
    return entityNameAliases[third] || "type";
  }
  if (first === "entity" && second === "other") {
    if (third === "attribute-name") return "attribute-name";
    if (third === "inherited-class") return "type";
  }
  if (scope.startsWith("constant.character.entity")) return "character-entity";
  if (parts.includes("numeric")) return "numeric";
  if (first === "support") {
    if (second === "function") return "function";
    if (second === "constant") return "constant";
    if (second === "variable") return "variable";
    if (scope.startsWith("support.type.property-name")) return "property";
    return "support";
  }
  if (parts.includes("attribute-value")) return "attribute-value";
  if (scope.startsWith("string.other.link")) return "link";
  if (parts.includes("preprocessor")) return "keyword";

  for (const part of [
    "doctype", "at-rule", "important", "regexp", "boolean",
    "symbol", "operator", "attribute-name"
  ]) {
    if (parts.includes(part)) return part;
  }

  if ([
    "comment", "string", "constant", "storage", "keyword",
    "variable", "punctuation", "entity", "support"
  ].includes(first)) return first;
};

const getCategory = scope => {
  if (!scope) return;
  if (!scope.includes(" ")) return getScopeCategory(scope);
  const tokens = scope.split(/\s+/);
  for (let i = tokens.length - 1; i >= 0; i--) {
    const cat = getScopeCategory(tokens[i]);
    if (cat) return cat;
  }
};

const findNode = (textNodes, offset, isEnd) => {
  let low = 0;
  let high = textNodes.length - 1;
  while (low <= high) {
    const mid = (low + high) >> 1;
    const item = textNodes[mid];
    if (isEnd ? (offset > item.start && offset <= item.end) : (offset >= item.start && offset < item.end)) {
      return [item.node, offset - item.start];
    }
    if (offset <= item.start) {
      high = mid - 1;
    } else {
      low = mid + 1;
    }
  }
  const fallback = isEnd ? textNodes.at(-1) : textNodes[0];
  return [fallback.node, isEnd ? fallback.node.data.length : 0];
};

const addRange = (textNodes, start, end, scope) => {
  const category = getCategory(scope);
  if (!category || start === end) return;

  const [startNode, startOffset] = findNode(textNodes, start, false);
  const [endNode, endOffset] = findNode(textNodes, end, true);

  const range = new Range();
  range.setStart(startNode, startOffset);
  range.setEnd(endNode, endOffset);

  if (!highlights.has(category)) highlights.set(category, new Highlight());
  highlights.get(category).add(range);
};

const escapeRegex = value => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

const expandEnd = (pattern, beginMatch) => pattern.replace(/\\(\d+)/g, (reference, index) => {
  return beginMatch[index] === undefined ? reference : escapeRegex(beginMatch[index]);
});

const getRules = rule => {
  if (!rule) return [];
  if (Array.isArray(rule)) return rule;

  if (rule.match || rule.begin || rule.include) return [rule];
  return rule.patterns || [];
};

const compileRegex = (pattern, flags) => {
  try {
    return new RegExp(pattern, flags);
  } catch {
    return null;
  }
};

const highlightAll = async ({
  root = document,
  selector = "[data-language], pre.highlight, code.highlight, pre > code",
  languageAliases
} = {}) => {
  const elements = [...root.querySelectorAll(selector)];
  const codeBlocks = elements.filter(el => {
    if (el.tagName === "PRE" && el.querySelector(":scope > code")) return false;
    const language = normalizeLanguage(getLanguage(el), languageAliases);
    return language && language !== "none";
  });
  const languages = codeBlocks.map(codeBlock =>
    normalizeLanguage(getLanguage(codeBlock), languageAliases)
  );
  const grammars = await loadGrammars(languages);
  const regexes = new Map();
  let matches = new Map();

  highlights.forEach((ranges, category) => {
    if (CSS.highlights.get(category) === ranges) CSS.highlights.delete(category);
    ranges.clear();
  });

  const exec = (pattern, text, start, end, anchor = 0) => {
    if (/(?:^|[^\\])(?:\\\\)*\\G/.test(pattern)) {
      let entry = regexes.get(pattern);
      if (!entry) {
        const atPat = pattern
          .replace(/((?:^|[^\\])(?:\\\\)*)\(\?(?:<!|!)\\G\)/g, "$1(?!)")
          .replace(/((?:^|[^\\])(?:\\\\)*)\\G/g, "$1");
        const afterPat = pattern.replace(/((?:^|[^\\])(?:\\\\)*)\\G/g, "$1(?!)");
        entry = {
          at: compileRegex(atPat, "dym"),
          after: compileRegex(afterPat, "dgm")
        };
        regexes.set(pattern, entry);
      }
      if (start === anchor && entry.at) {
        entry.at.lastIndex = anchor;
        const m = entry.at.exec(text);
        if (m && m.indices[0][0] < end && m.indices[0][1] <= end) return m;
      }
      if (entry.after) {
        const searchStart = start <= anchor ? anchor + 1 : start;
        if (searchStart < end) {
          entry.after.lastIndex = searchStart;
          const m = entry.after.exec(text);
          if (m && m.indices[0][0] < end && m.indices[0][1] <= end) return m;
        }
      }
      return null;
    }

    let match = matches.get(pattern);

    if (!match || match.indices[0][0] < start) {
      if (!regexes.has(pattern)) regexes.set(pattern, compileRegex(pattern, "dgm"));
      const regex = regexes.get(pattern);
      if (!regex) {
        matches.set(pattern, noMatch);
        return null;
      }
      regex.lastIndex = start;
      match = regex.exec(text) || noMatch;
      matches.set(pattern, match);
    }

    return match.indices[0][0] < end && match.indices[0][1] <= end
      ? match
      : null;
  };

  const resolveInclude = (include, grammar, baseGrammar) => {
    if (include === "$self") return { grammar, rules: grammar.patterns };
    if (include === "$base") return { grammar: baseGrammar, rules: baseGrammar.patterns };

    if (include[0] === "#") {
      return { grammar, rules: getRules(grammar.repository?.[include.slice(1)]) };
    }

    const [scopeName, repositoryName] = include.split("#");
    const includedGrammar = grammars.scopes.get(scopeName);
    if (!includedGrammar) return null;

    return {
      grammar: includedGrammar,
      rules: repositoryName
        ? getRules(includedGrammar.repository?.[repositoryName])
        : includedGrammar.patterns
    };
  };

  const expandRules = (rules, grammar, baseGrammar, activeIncludes = new Set()) => {
    const expanded = [];

    rules.forEach(rule => {
      if (rule.include) {
        const includeKey = `${grammar.scopeName}:${rule.include}`;
        if (activeIncludes.has(includeKey)) return;

        const included = resolveInclude(rule.include, grammar, baseGrammar);
        if (!included) return;

        const nestedIncludes = new Set(activeIncludes);
        nestedIncludes.add(includeKey);
        expanded.push(...expandRules(included.rules, included.grammar, baseGrammar, nestedIncludes));
        return;
      }

      if (rule.match || (rule.begin && rule.end)) {
        expanded.push({ grammar, rule });
      } else if (rule.patterns) {
        expanded.push(...expandRules(rule.patterns, grammar, baseGrammar, activeIncludes));
      }
    });

    return expanded;
  };

  const nextRule = (text, contexts, start, end, anchor) => {
    let winner = null;

    contexts.forEach(context => {
      const pattern = context.rule.match || context.rule.begin;
      const match = exec(pattern, text, start, end, anchor);
      if (!match) return;

      if (!winner || match.indices[0][0] < winner.match.indices[0][0]) {
        winner = { ...context, match };
      }
    });

    return winner;
  };

  const addCaptures = (text, textNodes, match, captures, grammar, baseGrammar, depth) => {
    if (!captures) return;
    Object.entries(captures).forEach(([index, capture]) => {
      const offsets = match.indices[+index];
      if (!offsets) return;
      if (capture.name) addRange(textNodes, ...offsets, capture.name);
      if (capture.patterns && offsets[0] < offsets[1]) {
        scanRegion(text, textNodes, capture.patterns, offsets[0], offsets[1], grammar, baseGrammar, null, depth + 1);
      }
    });
  };

  const scanRegion = (text, textNodes, rules, start, end, grammar, baseGrammar = grammar, closing = null, depth = 0) => {
    if (depth > 64) return { contentEnd: end, end, match: null };
    const contexts = expandRules(rules, grammar, baseGrammar);
    let cursor = start;

    while (cursor < end) {
      const candidate = nextRule(text, contexts, cursor, end, start);
      const endMatch = closing ? exec(closing.pattern, text, cursor, end, start) : null;
      const candidateStart = candidate?.match.indices[0][0] ?? Infinity;
      const endStart = endMatch?.indices[0][0] ?? Infinity;

      if (endMatch && (endStart < candidateStart || (endStart === candidateStart && !closing?.applyEndPatternLast))) {
        return { contentEnd: endStart, end: endMatch.indices[0][1], match: endMatch };
      }

      if (!candidate) return { contentEnd: end, end, match: null };

      const { rule, match, grammar: ruleGrammar } = candidate;
      if (rule.match) {
        if (rule.name) addRange(textNodes, ...match.indices[0], rule.name);
        addCaptures(text, textNodes, match, rule.captures, ruleGrammar, baseGrammar, depth);
        cursor = match.indices[0][1] > cursor ? match.indices[0][1] : cursor + 1;
        continue;
      }

      const nested = scanRegion(
        text,
        textNodes,
        rule.patterns || [],
        match.indices[0][1],
        end,
        ruleGrammar,
        baseGrammar,
        { pattern: expandEnd(rule.end, match), applyEndPatternLast: rule.applyEndPatternLast },
        depth + 1
      );

      if (rule.name) addRange(textNodes, match.indices[0][0], nested.end, rule.name);
      if (rule.contentName) addRange(textNodes, match.indices[0][1], nested.contentEnd, rule.contentName);
      addCaptures(text, textNodes, match, rule.beginCaptures || rule.captures, ruleGrammar, baseGrammar, depth);
      if (nested.match) addCaptures(text, textNodes, nested.match, rule.endCaptures || rule.captures, ruleGrammar, baseGrammar, depth);

      cursor = nested.end > cursor ? nested.end : cursor + 1;
    }

    return { contentEnd: end, end, match: null };
  };

  codeBlocks.forEach((codeBlock, index) => {
    const language = languages[index];
    if (!language || language === "none") return;
    const grammar = grammars.languages[language];
    if (!grammar) return;

    codeBlock.normalize();

    const walker = document.createTreeWalker(codeBlock, NodeFilter.SHOW_TEXT);
    const textNodes = [];
    let text = "";
    let n;
    while ((n = walker.nextNode())) {
      if (n.data.length === 0) continue;
      textNodes.push({
        node: n,
        start: text.length,
        end: text.length + n.data.length,
      });
      text += n.data;
    }

    if (!textNodes.length) return;

    matches = new Map();

    scanRegion(text, textNodes, grammar.patterns, 0, text.length, grammar);
  });

  highlights.forEach((ranges, category) => {
    if (ranges.size) CSS.highlights.set(category, ranges);
  });

  return codeBlocks;
};

document.addEventListener("syntax-highlight", () => highlightAll());
highlightAll();

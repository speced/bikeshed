/*
Microlighter
MIT License
Copyright (c) 2026 Dave Rupert
https://github.com/davatron5000/microlighter
*/

const languageAliases = {
  docker: "dockerfile",
  gql: "graphql",
  idl: "webidl",
  js: "javascript",
  jsx: "javascript",
  md: "markdown",
  py: "python",
  rb: "ruby",
  sass: "scss",
  sh: "bash",
  shell: "bash",
  ts: "typescript",
  yml: "yaml",
  zsh: "bash"
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
  const language = codeBlock.getAttribute("highlight")
    || getLanguageClass(codeBlock)
    || codeBlock.dataset.language
    || pre?.getAttribute("highlight")
    || (pre ? getLanguageClass(pre) : "")
    || pre?.dataset.language
    || "";

  return language.toLowerCase();
};

const loadGrammars = createGrammarLoader();
const highlights = new Map();
const noMatch = { indices: [[Infinity, Infinity]] };

const getCategory = scope => {
  const parts = scope.split(".");
  const [first, second, third] = parts;
  const last = parts.at(-1);

  if (first === "markup" && ["quote", "inserted", "deleted", "raw"].includes(second)) return second;
  if (first === "entity" && second === "name") return third;
  if (scope.startsWith("constant.character.entity")) return "character-entity";
  if (parts.includes("numeric")) return "numeric";
  if (scope.startsWith("support.type.property-name")) return "property";
  if (parts.includes("attribute-value")) return "attribute-value";
  if (scope.startsWith("string.other.link")) return "link";
  if (parts.includes("preprocessor")) return "keyword";

  if ([
    "doctype", "at-rule", "important", "regexp", "boolean",
    "symbol", "operator", "attribute-name"
  ].includes(last)) return last;

  if ([
    "comment", "string", "constant", "storage", "keyword",
    "variable", "punctuation", "entity", "support"
  ].includes(first)) return first;
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

const addCaptures = (textNodes, match, captures = {}) => {
  Object.entries(captures).forEach(([index, capture]) => {
    const offsets = match.indices[+index];
    if (offsets) addRange(textNodes, ...offsets, capture.name);
  });
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

const highlightAll = async ({
  root = document,
  selector = "[highlight], pre.highlight, code.highlight, pre > code",
  languageAliases
} = {}) => {
  const elements = [...root.querySelectorAll(selector)];
  const codeBlocks = elements.filter(el => {
    if (el.tagName === "PRE" && el.querySelector(":scope > code")) return false;
    return getLanguage(el);
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

  const exec = (pattern, text, start, end) => {
    let match = matches.get(pattern);

    if (!match || match.indices[0][0] < start) {
      if (!regexes.has(pattern)) regexes.set(pattern, new RegExp(pattern, "dgm"));
      const regex = regexes.get(pattern);
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

      if (rule.match || (rule.begin && rule.end)) expanded.push({ grammar, rule });
    });

    return expanded;
  };

  const nextRule = (text, contexts, start, end) => {
    let winner = null;

    contexts.forEach(context => {
      const pattern = context.rule.match || context.rule.begin;
      const match = exec(pattern, text, start, end);
      if (!match) return;

      if (!winner || match.indices[0][0] < winner.match.indices[0][0]) {
        winner = { ...context, match };
      }
    });

    return winner;
  };

  const scanRegion = (text, textNodes, rules, start, end, grammar, baseGrammar = grammar, closing = null) => {
    const contexts = expandRules(rules, grammar, baseGrammar);
    let cursor = start;

    while (cursor < end) {
      const candidate = nextRule(text, contexts, cursor, end);
      const endMatch = closing ? exec(closing.pattern, text, cursor, end) : null;
      const candidateStart = candidate?.match.indices[0][0] ?? Infinity;
      const endStart = endMatch?.indices[0][0] ?? Infinity;

      if (endMatch && (endStart < candidateStart || (endStart === candidateStart && !closing?.applyEndPatternLast))) {
        return { contentEnd: endStart, end: endMatch.indices[0][1], match: endMatch };
      }

      if (!candidate) return { contentEnd: end, end, match: null };

      const { rule, match, grammar: ruleGrammar } = candidate;
      if (rule.match) {
        if (rule.name) addRange(textNodes, ...match.indices[0], rule.name);
        addCaptures(textNodes, match, rule.captures);
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
        { pattern: expandEnd(rule.end, match), applyEndPatternLast: rule.applyEndPatternLast }
      );

      if (rule.name) addRange(textNodes, match.indices[0][0], nested.end, rule.name);
      if (rule.contentName) addRange(textNodes, match.indices[0][1], nested.contentEnd, rule.contentName);
      addCaptures(textNodes, match, rule.beginCaptures || rule.captures);
      if (nested.match) addCaptures(textNodes, nested.match, rule.endCaptures || rule.captures);

      cursor = nested.end > cursor ? nested.end : cursor + 1;
    }

    return { contentEnd: end, end, match: null };
  };

  codeBlocks.forEach((codeBlock, index) => {
    const grammar = grammars.languages[languages[index]];
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

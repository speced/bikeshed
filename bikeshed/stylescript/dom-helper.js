function query(sel) { return document.querySelector(sel); }

function queryAll(sel) { return [...document.querySelectorAll(sel)]; }

function iter(obj) {
	if(!obj) return [];
	var it = obj[Symbol.iterator];
	if(it) return it;
	return Object.entries(obj);
}

function mk(tagname, attrs, ...children) {
	const el = document.createElement(tagname);
	for(const [k,v] of iter(attrs)) {
		if(k.slice(0,3) == "_on") {
			const eventName = k.slice(3);
			el.addEventListener(eventName, v);
		} else if(k[0] == "_") {
			// property, not attribute
			el[k.slice(1)] = v;
		} else {
			if(v === false || v == null) {
        continue;
      } else if(v === true) {
        el.setAttribute(k, "");
        continue;
      } else {
  			el.setAttribute(k, v);
      }
		}
	}
	append(el, children);
	return el;
}

/* Create shortcuts for every known HTML element */
[
  "a",
  "abbr",
  "acronym",
  "address",
  "applet",
  "area",
  "article",
  "aside",
  "audio",
  "b",
  "base",
  "basefont",
  "bdo",
  "big",
  "blockquote",
  "body",
  "br",
  "button",
  "canvas",
  "caption",
  "center",
  "cite",
  "code",
  "col",
  "colgroup",
  "datalist",
  "dd",
  "del",
  "details",
  "dfn",
  "dialog",
  "div",
  "dl",
  "dt",
  "em",
  "embed",
  "fieldset",
  "figcaption",
  "figure",
  "font",
  "footer",
  "form",
  "frame",
  "frameset",
  "head",
  "header",
  "h1",
  "h2",
  "h3",
  "h4",
  "h5",
  "h6",
  "hr",
  "html",
  "i",
  "iframe",
  "img",
  "input",
  "ins",
  "kbd",
  "label",
  "legend",
  "li",
  "link",
  "main",
  "map",
  "mark",
  "meta",
  "meter",
  "nav",
  "nobr",
  "noscript",
  "object",
  "ol",
  "optgroup",
  "option",
  "output",
  "p",
  "param",
  "pre",
  "progress",
  "q",
  "s",
  "samp",
  "script",
  "section",
  "select",
  "small",
  "source",
  "span",
  "strike",
  "strong",
  "style",
  "sub",
  "summary",
  "sup",
  "table",
  "tbody",
  "td",
  "template",
  "textarea",
  "tfoot",
  "th",
  "thead",
  "time",
  "title",
  "tr",
  "u",
  "ul",
  "var",
  "video",
  "wbr",
  "xmp",
].forEach(tagname=>{
	mk[tagname] = (...args) => mk(tagname, ...args);
});

function* nodesFromChildList(children) {
	for(const child of children.flat(Infinity)) {
		if(child instanceof Node) {
			yield child;
		} else {
			yield new Text(child);
		}
	}
}
function append(el, ...children) {
	for(const child of nodesFromChildList(children)) {
		if(el instanceof Node) el.appendChild(child);
		else el.push(child);
	}
	return el;
}

function insertAfter(el, ...children) {
	for(const child of nodesFromChildList(children)) {
		el.parentNode.insertBefore(child, el.nextSibling);
	}
	return el;
}

function clearContents(el) {
	el.innerHTML = "";
	return el;
}

function parseHTML(markup) {
	if(markup.toLowerCase().trim().indexOf('<!doctype') === 0) {
		const doc = document.implementation.createHTMLDocument("");
		doc.documentElement.innerHTML = markup;
		return doc;
	} else {
		const el = mk.template({});
		el.innerHTML = markup;
		return el.content;
	}
}
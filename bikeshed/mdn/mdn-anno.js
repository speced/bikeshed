'use strict';
// File copied from https://github.com/whatwg/whatwg.org/blob/main/resources.whatwg.org/standard-mdn-annos.js

// Builds MDN annotation panels on demand from the compact `data-mdn` attribute written by
// the spec generator (wattsi's EncodeMDNAnnotations; Bikeshed's mdnspeclinks.py builds its
// panels eagerly for now). Only the wire format is shared: the browser labels, the
// engine-support strings and the render grouping all live here.
//
// Archived commit snapshots load this file forever, so every format version this script
// has ever understood has to keep working. Evolve the format by adding a branch in
// `hydrate`, never by redefining a version that has already shipped.

const MDN_URL = 'https://developer.mozilla.org/en-US/docs/Web/';
const CANIUSE_URL = 'https://caniuse.com/#feat=';

// Render groups, in the order they appear in a panel, separated by <hr>.
const CURRENT_ENGINES = 0;
const BORROWED_ENGINES = 1;
const RETIRED_ENGINES = 2;
const MOBILE = 3;
const NON_BROWSER = 4;
const GROUP_COUNT = 5;

// Cell slots, in the order they appear in `data-mdn`. APPEND-ONLY: a new browser goes at
// the end and is never inserted, so that old data still lines up and old copies of this
// script can keep ignoring the cells they don't know about. `group` is what decides where
// a row is rendered, so appending to this list doesn't constrain where the row shows up.
const SLOTS = [
  { id: 'firefox', label: 'Firefox', group: CURRENT_ENGINES },
  { id: 'safari', label: 'Safari', group: CURRENT_ENGINES },
  { id: 'chrome', label: 'Chrome', group: CURRENT_ENGINES },
  { id: 'opera', label: 'Opera', group: BORROWED_ENGINES, mirrors: 'Chrome' },
  { id: 'edge_blink', label: 'Edge', group: BORROWED_ENGINES },
  { id: 'edge', label: 'Edge (Legacy)', group: RETIRED_ENGINES },
  { id: 'ie', label: 'IE', group: RETIRED_ENGINES },
  { id: 'firefox_android', label: 'Firefox for Android', group: MOBILE, mirrors: 'Firefox' },
  { id: 'safari_ios', label: 'iOS Safari', group: MOBILE, mirrors: 'Safari' },
  { id: 'chrome_android', label: 'Chrome for Android', group: MOBILE, mirrors: 'Chrome' },
  { id: 'webview_android', label: 'Android WebView', group: MOBILE, mirrors: 'Chrome' },
  { id: 'samsunginternet_android', label: 'Samsung Internet', group: MOBILE, mirrors: 'Chrome' },
  { id: 'opera_android', label: 'Opera Mobile', group: MOBILE, mirrors: 'Chrome' },
  { id: 'nodejs', label: 'Node.js', group: NON_BROWSER },
];

// One mnemonic character per engine-support note.
const LEVELS = {
  '0': { class: 'less-than-two-engines-text', text: 'In no current engines.' },
  '1': { class: 'less-than-two-engines-text', text: 'In only one current engine.' },
  '9': { class: 'all-engines-text', text: 'In all current engines.' },
  's': { class: 'less-than-two-engines-text', text: 'Support in one engine under other name.' },
  'S': { class: 'less-than-two-engines-text', text: 'Support in some engines under other name.' },
  'v': { class: 'less-than-two-engines-text', text: 'Prefixed support in one engine.' },
  'V': { class: 'less-than-two-engines-text', text: 'Prefixed support in some engines.' },
  'p': { class: 'less-than-two-engines-text', text: 'Partial support in one engine.' },
  'P': { class: 'less-than-two-engines-text', text: 'Partial support in some engines.' },
};

// Leading character of a cell, qualifying how the version after it should be read. `flag`
// is whether to mark the version with 🔰 as well as explaining it in a tooltip.
const CAVEATS = {
  '*': { flag: true, title: () => 'Partial implementation.' },
  '^': { flag: true, title: () => 'Requires setting a user preference or runtime flag.' },
  '$': { flag: true, title: () => 'Requires a prefix or alternative name.' },
  // Mirrored support is far too common to flag every occurrence; the tooltip is enough.
  '@': { flag: false, title: (slot) => `Support is mirrored from ${slot.mirrors ?? 'the upstream browser'}.` },
};

const FLAG = '\u{1F530}'; // 🔰, marks a version that comes with a caveat
const EN_DASH = '–';

function element(name, attributes, ...children) {
  const node = document.createElement(name);
  for (const [attribute, value] of Object.entries(attributes)) {
    if (value !== undefined) {
      node.setAttribute(attribute, value);
    }
  }
  node.append(...children);
  return node;
}

function splitOnce(string, separator) {
  const at = string.indexOf(separator);
  return at === -1 ? [string, undefined] : [string.slice(0, at), string.slice(at + 1)];
}

// A version body says both whether the browser supports the feature and since when.
function readVersion(body) {
  if (body === '?') {
    return { state: 'unknown', version: '?' };
  }
  if (body === '-') {
    return { state: 'no', version: 'None' };
  }
  if (body === '!') {
    return { state: 'yes', version: 'Yes' };
  }
  if (body.startsWith('=')) {
    // A version that will never be superseded, so no trailing "+".
    return { state: 'yes', version: body.slice(1) };
  }
  const [added, removed] = body.split('-');
  if (removed !== undefined) {
    return { state: 'no', version: added + EN_DASH + removed };
  }
  return { state: 'yes', version: added + '+' };
}

function readCell(cell, slot) {
  const caveat = CAVEATS[cell[0]];
  const { state, version } = readVersion(caveat ? cell.slice(1) : cell);
  return {
    state,
    version: caveat?.flag ? `${FLAG} ${version}` : version,
    title: caveat?.title(slot),
  };
}

// A browser row is the browser's name in one cell and its version in the next. The logo
// comes from CSS, keyed off the browser id in the row's class.
function browserRow(slot, cell) {
  const { state, version, title } = readCell(cell, slot);
  return element('span', { class: `${slot.id} ${state}` },
    element('span', {}, slot.label),
    element('span', { title }, version));
}

// The caniuse row has a single cell instead, since its logo needs no label beside it.
function caniuseRow(field) {
  const [feature, title] = splitOnce(field, ',');
  const link = element('a', { href: CANIUSE_URL + feature, title }, 'caniuse.com table');
  return element('span', { class: 'caniuse' }, element('span', {}, link));
}

function supportTable(cells, caniuse) {
  const groups = Array.from({ length: GROUP_COUNT }, () => []);
  SLOTS.forEach((slot, slotIndex) => {
    // An empty cell means this browser gets no row at all. Cells beyond SLOTS are
    // browsers added after this copy of the script was written; ignore them.
    if (cells[slotIndex]) {
      groups[slot.group].push(browserRow(slot, cells[slotIndex]));
    }
  });
  if (caniuse !== undefined) {
    groups.push([caniuseRow(caniuse)]);
  }

  const table = element('div', { class: 'support' });
  for (const rows of groups.filter((rows) => rows.length > 0)) {
    if (table.hasChildNodes()) {
      table.append(element('hr', {}));
    }
    table.append(...rows);
  }
  return table;
}

function featurePanel(record) {
  const [slug, level, cells, caniuse] = record.split('|');

  const article = element('a', { href: MDN_URL + slug }, slug.slice(slug.indexOf('/') + 1));
  const panel = element('div', { class: 'feature' }, element('p', {}, article));

  if (level in LEVELS) {
    panel.append(element('p', { class: LEVELS[level].class }, LEVELS[level].text));
  }
  if (cells) {
    panel.append(supportTable(cells.split(','), caniuse));
  }
  return panel;
}

function hydrate(anno) {
  const [version, features] = splitOnce(anno.dataset.mdn, '|');
  delete anno.dataset.mdn; // Only ever hydrate a panel once.

  if (version !== 'v1') {
    console.warn(`Unsupported MDN annotation data version "${version}".`, anno);
    return;
  }
  anno.append(...features.split('~').map(featurePanel));
}

function hydrateIfNeeded(node) {
  if (node instanceof Element && node.matches('.mdn-anno[data-mdn]')) {
    hydrate(node);
  }
}

// A click on the summary arrives before the browser opens the <details>, so hydrating
// from it means the panel never flashes empty. That covers pointers and the keyboard,
// since activating a summary dispatches a click either way.
document.addEventListener('click', (event) => {
  if (event.target instanceof Element) {
    hydrateIfNeeded(event.target.closest('summary')?.parentElement);
  }
}, true);

// And `toggle` is the catch-all for a panel opened some other way, such as find-in-page
// or a fragment navigation into it. It fires a task after the state has already changed,
// and it doesn't bubble, so it has to be a capture listener.
document.addEventListener('toggle', (event) => hydrateIfNeeded(event.target), true);
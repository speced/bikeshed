# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals

import hashlib
import itertools
import io

from . import config
from . import datablocks
from . import markdown
from .htmlhelpers import *
from .messages import *

def processInclusions(doc):
    iters = 0
    while True:
        iters += 1
        if iters > 100:
            die("Looked for include-blocks more than 100 times, something is wrong.")
            return
        els = findAll("pre.include", doc)
        if not els:
            break
        for el in els:
            macros = {}
            for i in itertools.count(0):
                m = el.get("macro-" + str(i))
                if m is None:
                    break
                k,_,v = m.partition(" ")
                macros[k.lower()] = v
            if el.get("path"):
                path = el.get("path")
                try:
                    with io.open(config.docPath(doc, path), 'r', encoding="utf-8") as f:
                        lines = f.readlines()
                except Exception, err:
                    die("Couldn't find include file '{0}'. Error was:\n{1}", path, err, el=el)
                    removeNode(el)
                    continue
                # hash the content + path together for identity
                # can't use just path, because they're relative; including "foo/bar.txt" might use "foo/bar.txt" further nested
                # can't use just content, because then you can't do the same thing twice.
                # combined does a good job unless you purposely pervert it
                hash = hashlib.md5(path + ''.join(lines).encode("ascii", "xmlcharrefreplace")).hexdigest()
                if el.get('hash'):
                    # This came from another included file, check if it's a loop-include
                    if hash in el.get('hash'):
                        # WHOOPS
                        die("Include loop detected - “{0}” is included in itself.", path)
                        removeNode(el)
                        continue
                    hash += " " + el.get('hash')
                depth = int(el.get('depth')) if el.get('depth') is not None else 0
                if depth > 100:
                    # Just in case you slip past the nesting restriction
                    die("Nesting depth > 100, literally wtf are you doing.")
                    removeNode(el)
                    continue
                lines = datablocks.transformDataBlocks(doc, lines)
                lines = markdown.parse(lines, doc.md.indent, opaqueElements=doc.md.opaqueElements)
                text = ''.join(lines)
                text = doc.fixText(text, moreMacros=macros)
                subtree = parseHTML(text)
                for childInclude in findAll("pre.include", E.div({}, *subtree)):
                    childInclude.set("hash", hash)
                    childInclude.set("depth", str(depth + 1))
                replaceNode(el, *subtree)
            else:
                die("Whoops, an include-block didn't get parsed correctly, so I can't include anything.")
                removeNode(el)
                continue


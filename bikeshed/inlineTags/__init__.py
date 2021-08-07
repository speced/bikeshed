from subprocess import PIPE, Popen

from .. import constants
from ..h import *
from ..messages import *


def processTags(doc):
    for el in findAll("[data-span-tag]", doc):
        if not constants.executeCode:
            die("Found an inline code tag, but arbitrary code execution isn't allowed. See the --allow-execute flag.")
            return
        tag = el.get("data-span-tag")
        if tag not in doc.md.inlineTagCommands:
            die("Unknown inline tag '{0}' found:\n  {1}", tag, outerHTML(el), el=el)
            continue
        command = doc.md.inlineTagCommands[tag]
        with Popen(command, stdin=PIPE, stdout=PIPE, stderr=PIPE, shell=True) as p:
            out, err = p.communicate(innerHTML(el).encode("utf-8"))
            try:
                out = out.decode("utf-8")
            except UnicodeDecodeError as e:
                die(
                    "When trying to process {0}, got invalid unicode in stdout:\n{1}",
                    outerHTML(el),
                    e,
                    el=el,
                )
            try:
                err = err.decode("utf-8")
            except UnicodeDecodeError as e:
                die(
                    "When trying to process {0}, got invalid unicode in stderr:\n{1}",
                    outerHTML(el),
                    e,
                    el=el,
                )
            if p.returncode:
                die(
                    "When trying to process {0}, got return code {1} and the following stderr:\n{2}",
                    outerHTML(el),
                    p.returncode,
                    err,
                    el=el,
                )
                continue
            replaceContents(el, parseHTML(out))

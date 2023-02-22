from __future__ import annotations

from subprocess import PIPE, Popen

from .. import constants, h, messages as m, t


def processTags(doc: t.SpecT) -> None:
    for el in h.findAll("[data-span-tag]", doc):
        if not constants.executeCode:
            m.die("Found an inline code tag, but arbitrary code execution isn't allowed. See the --allow-execute flag.")
            return
        tag = el.get("data-span-tag")
        if tag not in doc.md.inlineTagCommands:
            m.die(f"Unknown inline tag '{tag}' found:\n  {h.outerHTML(el)}", el=el)
            continue
        command = doc.md.inlineTagCommands[tag]
        with Popen(command, stdin=PIPE, stdout=PIPE, stderr=PIPE, shell=True) as p:
            out, err = t.cast("tuple[str|bytes, str|bytes]", p.communicate(h.innerHTML(el).encode("utf-8")))
            try:
                out = t.cast(bytes, out).decode("utf-8")
            except UnicodeDecodeError as e:
                m.die(f"When trying to process {h.outerHTML(el)}, got invalid unicode in stdout:\n{e}", el=el)
                return
            try:
                err = t.cast(bytes, err).decode("utf-8")
            except UnicodeDecodeError as e:
                m.die(f"When trying to process {h.outerHTML(el)}, got invalid unicode in stderr:\n{e}", el=el)
                return
            if p.returncode:
                m.die(
                    f"When trying to process {h.outerHTML(el)}, got return code {p.returncode} and the following stderr:\n{str(err)}",
                    el=el,
                )
                continue
            h.replaceContents(el, h.parseHTML(str(out)))

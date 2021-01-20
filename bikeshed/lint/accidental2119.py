import re

from ..h import *
from ..messages import *


def accidental2119(doc):
    """
    Looks for usage of 2119 keywords in non-normative sections.
    You can override this, allowing the keyword,
    by putting an "allow-2119" class on the text's containing element specifically
    (not an ancestor, to avoid accidentally over-silencing).
    """
    if not doc.md.complainAbout["accidental-2119"]:
        return
    keywords = r"\b(may|must|should|shall|optional|recommended|required)\b"

    def searchFor2119(el):
        if isNormative(el, doc):
            # 2119 is fine, just look at children
            pass
        elif hasClass(el, "allow-2119"):
            # Override 2119 detection on this element's text specifically,
            # so you can use the keywords in examples *describing* the keywords.
            pass
        else:
            if el.text is not None:
                match = re.search(keywords, el.text)
                if match:
                    warn(
                        "RFC2119 keyword in non-normative section (use: might, can, has to, or override with <span class=allow-2119>): {0}",
                        el.text,
                        el=el,
                    )
            for child in el:
                if child.tail is not None:
                    match = re.search(keywords, child.tail)
                    if match:
                        warn(
                            "RFC2119 keyword in non-normative section (use: might, can, has to, or override with <span class=allow-2119>): {0}",
                            child.tail,
                            el=el,
                        )
        for child in el:
            searchFor2119(child)

    searchFor2119(doc.body)

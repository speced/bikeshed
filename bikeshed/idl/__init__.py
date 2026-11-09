from __future__ import annotations

from .main import (
    combineIdlLinkingTexts,
    getContentStartingLineNum,
    getParser,
    markupIDL,
    markupIDLBlock,
    normalizeIdlWhitespace,
    processIDL,
)
from .markers import IDLUI, DebugMarker, IDLMarker, IDLSilent, endTag, startTag
from .merge import mergeMarkup
from .methods import find_webidl_methods
from .productions import nodesFromType

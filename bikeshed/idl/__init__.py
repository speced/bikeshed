from __future__ import annotations

from .main import (
    IDLParser,
    combineIdlLinkingTexts,
    getParser,
    markupIDL,
    markupIDLBlock,
    normalizeIdlWhitespace,
    processIDL,
)
from .markers import IDLUI, DebugIDLBuilder, IDLBuilder, IDLSilent, IDLTreeBuilder
from .merge import mergeMarkup
from .methods import find_webidl_methods
from .productions import nodesFromType

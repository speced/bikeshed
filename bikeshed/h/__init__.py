from . import parser
from .dom import (
    DuplicatedLinkText,
    E,
    addClass,
    addOldIDs,
    appendChild,
    appendContents,
    approximateLineNumber,
    childElements,
    childNodes,
    circledDigits,
    clearContents,
    closestAncestor,
    closestAttr,
    collectAutolinks,
    collectIds,
    collectLinksWithSectionNames,
    collectSyntaxHighlightables,
    createElement,
    dedupIDs,
    emptyText,
    escapeAttr,
    escapeCSSIdent,
    escapeHTML,
    escapeUrlFrag,
    filterAncestors,
    find,
    findAll,
    firstLinkTextFromElement,
    fixSurroundingTypography,
    fixupIDs,
    foldWhitespace,
    hasAncestor,
    hasAnyAttr,
    hasAttr,
    hasAttrs,
    hasChildElements,
    hasClass,
    hashContents,
    hasOnlyChild,
    headingLevelOfElement,
    innerHTML,
    insertAfter,
    insertBefore,
    isElement,
    isEmpty,
    isNormative,
    isOddNode,
    isOnlyChild,
    linkTextsFromElement,
    moveContents,
    nextSiblingElement,
    nextSiblingNode,
    nodeIter,
    outerHTML,
    parentElement,
    parseDocument,
    parseHTML,
    prependChild,
    previousElements,
    printNodeTree,
    relevantHeadings,
    removeAttr,
    removeClass,
    removeNode,
    renameAttr,
    replaceContents,
    replaceMacrosTextly,
    replaceNode,
    replaceWithContents,
    rootElement,
    safeID,
    scopingElements,
    sectionName,
    serializeTag,
    sortElements,
    tagName,
    textContent,
    textContentIgnoringDecorative,
    transferAttributes,
    treeAttr,
    unescape,
    unfixTypography,
    uniqueID,
    wrapContents,
)
from .parser import (
    ParseConfig,
    debugNodes,
    initialDocumentParse,
    nodesFromHtml,
    parseLines,
    parseText,
    parseTitle,
    strFromNodes,
)
from .serializer import Serializer

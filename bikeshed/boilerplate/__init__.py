from .indexes import (
    addCDDLSection,
    addExplicitIndexes,
    addIDLSection,
    addIndexOfExternallyDefinedTerms,
    addIndexOfLocallyDefinedTerms,
    addIndexSection,
    addIssuesSection,
    addPropertyIndex,
    addReferencesSection,
)
from .main import parseBoilerplate
from .metadata import addSpecMetadataSection
from .misc import (
    addAbstract,
    addAtRisk,
    addBikeshedStyleScripts,
    addBikeshedVersion,
    addCanonicalURL,
    addCopyright,
    addCustomBoilerplate,
    addDarkmodeIndicators,
    addExpiryNotice,
    addFavicon,
    addHeaderFooter,
    addLogo,
    addObsoletionNotice,
    addSpecVersion,
    addStatusSection,
    addStyles,
    removeUnwantedBoilerplate,
    w3cStylesheetInUse,
)
from .toc import addTOCSection, buildTOCGraph

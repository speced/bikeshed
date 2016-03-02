# -*- coding: utf-8 -*-

from __future__ import division, unicode_literals
import re
from collections import defaultdict
import io
import os
import sys
import lxml
import json
import urllib
import urllib2
import argparse
import itertools
from datetime import date, datetime

from . import config
from . import biblio
from . import update
from . import markdown
from . import test
from . import MetadataManager as metadata
from . import HTMLSerializer
from . import headings
from . import shorthands
from . import boilerplate
from . import datablocks
from . import lexers
from .ReferenceManager import ReferenceManager
from .htmlhelpers import *
from .messages import *
from .widlparser.widlparser import parser
from contextlib import closing


def main():
    # Hack around argparse's lack of optional subparsers
    if len(sys.argv) == 1:
        sys.argv.append("spec")

    argparser = argparse.ArgumentParser(description="Processes spec source files into valid HTML.")
    argparser.add_argument("-q", "--quiet", dest="quiet", action="count", default=0,
                            help="Suppresses everything but fatal errors from printing.")
    argparser.add_argument("-f", "--force", dest="force", action="store_true",
                           help="Force the preprocessor to run to completion; fatal errors don't stop processing.")
    argparser.add_argument("-d", "--dry-run", dest="dryRun", action="store_true",
                           help="Prevents the processor from actually saving anything to disk, but otherwise fully runs.")

    subparsers = argparser.add_subparsers(title="Subcommands", dest='subparserName')

    specParser = subparsers.add_parser('spec', help="Process a spec source file into a valid output file.")
    specParser.add_argument("infile", nargs="?",
                            default=None,
                            help="Path to the source file.")
    specParser.add_argument("outfile", nargs="?",
                            default=None,
                            help="Path to the output file.")
    specParser.add_argument("--para", dest="paragraphMode", default="markdown",
                            help="Pass 'markdown' for Markdown-style paragraph, or 'html' for normal HTML paragraphs. [default: %(default)s]")
    specParser.add_argument("--debug", dest="debug", action="store_true", help="Switches on some debugging tools. Don't use for production!")
    specParser.add_argument("--gh-token", dest="ghToken", nargs="?",
                           help="GitHub access token. Useful to avoid API rate limits. Generate tokens: https://github.com/settings/tokens.")
    minifyGroup = specParser.add_argument_group("Minification")
    specParser.set_defaults(minify=True)
    minifyGroup.add_argument("--minify", dest="minify", action="store_true",
                             help="Turn on minification. [default]")
    minifyGroup.add_argument("--no-minify", dest="minify", action="store_false",
                            help="Turn off minification.")

    watchParser = subparsers.add_parser('watch', help="Process a spec source file into a valid output file, automatically rebuilding when it changes.")
    watchParser.add_argument("infile", nargs="?",
                            default=None,
                            help="Path to the source file.")
    watchParser.add_argument("outfile", nargs="?",
                            default=None,
                            help="Path to the output file.")
    minifyGroup = watchParser.add_argument_group("Minification")
    watchParser.set_defaults(minify=True)
    watchParser.add_argument("--minify", dest="minify", action="store_true",
                             help="Turn on minification. [default]")
    watchParser.add_argument("--no-minify", dest="minify", action="store_false",
                            help="Turn off minification.")
    watchParser.add_argument("--gh-token", dest="ghToken", nargs="?",
                           help="GitHub access token. Useful to avoid API rate limits. Generate tokens: https://github.com/settings/tokens.")

    updateParser = subparsers.add_parser('update', help="Update supporting files (those in /spec-data).", epilog="If no options are specified, everything is downloaded.")
    updateParser.add_argument("--anchors", action="store_true", help="Download crossref anchor data.")
    updateParser.add_argument("--biblio", action="store_true", help="Download biblio data.")
    updateParser.add_argument("--link-defaults", dest="linkDefaults", action="store_true", help="Download link default data.")
    updateParser.add_argument("--test-suites", dest="testSuites", action="store_true", help="Download test suite data.")

    issueParser = subparsers.add_parser('issues-list', help="Process a plain-text issues file into HTML. Call with no args to see an example input text.")
    issueParser.add_argument("-t",
                              dest="printTemplate",
                              action="store_true",
                              help="Output example Issues List template.")
    issueParser.add_argument("infile", nargs="?",
                              default=None,
                              help="Path to the plain-text issue file.")
    issueParser.add_argument("outfile", nargs="?",
                              default=None,
                              help="Path to the output file. Default is file of the same name as input, with .html.")

    debugParser = subparsers.add_parser('debug', help="Run various debugging commands.")
    debugParser.add_argument("infile", nargs="?",
                             default=None,
                             help="Path to the source file.")
    debugCommands = debugParser.add_mutually_exclusive_group(required=True)
    debugCommands.add_argument("--print-exports", dest="printExports", action="store_true",
                               help="Prints those terms that will be exported for cross-ref purposes.")
    debugCommands.add_argument("--print-refs-for", dest="linkText",
                               help="Prints the ref data for a given link text.")
    debugCommands.add_argument("--print", dest="code",
                               help="Runs the specified code and prints it.")
    debugCommands.add_argument("--print-json", dest="jsonCode",
                               help="Runs the specified code and prints it as formatted JSON.")

    refParser = subparsers.add_parser('refs', help="Search Bikeshed's ref database.")
    refParser.add_argument("infile", nargs="?",
                             default=None,
                             help="Path to the source file.")
    refParser.add_argument("--text", dest="text", default=None)
    refParser.add_argument("--type", dest="linkType", default=None)
    refParser.add_argument("--for", dest="linkFor", default=None)
    refParser.add_argument("--spec", dest="spec", default=None)
    refParser.add_argument("--status", dest="status", default=None)
    refParser.add_argument("--exact", dest="exact", action="store_true")

    sourceParser = subparsers.add_parser('source', help="Tools for formatting the *source* document.")
    sourceParser.add_argument("--big-text",
                              dest="bigText",
                              action="store_true",
                              help="Finds HTML comments containing 'Big Text: foo' and turns them into comments containing 'foo' in big text.")
    sourceParser.add_argument("infile", nargs="?",
                            default=None,
                            help="Path to the source file.")
    sourceParser.add_argument("outfile", nargs="?",
                            default=None,
                            help="Path to the output file.")

    testParser = subparsers.add_parser('test', help="Tools for running Bikeshed's testsuite.")
    testParser.add_argument("--rebase",
                            dest="rebaseFiles",
                            default=None,
                            metavar="FILE",
                            nargs="*",
                            help="Rebase the specified files. If called with no args, rebases everything.")

    profileParser = subparsers.add_parser('profile', help="Profiling Bikeshed. Needs graphviz, gprof2dot, and xdot installed.")
    profileParser.add_argument("--root",
                               dest="root",
                               default=None,
                               metavar="ROOTFUNC",
                               help="Prune the graph to start with the specified root node.")
    profileParser.add_argument("--leaf",
                               dest="leaf",
                               default=None,
                               metavar="LEAFFUNC",
                               help="Prune the graph to only show ancestors of the specified leaf node.")
    profileParser.add_argument("--svg", dest="svgFile", default=None, help="Save the graph to a specified SVG file, rather than outputting with xdot immediately.")

    profileParser = subparsers.add_parser('template', help="Outputs a skeleton .bs file for you to start with.")

    options, extras = argparser.parse_known_args()

    config.quiet = options.quiet
    config.force = options.force
    config.dryRun = options.dryRun
    config.minify = getattr(options, 'minify', True)

    update.fixupDataFiles()
    if options.subparserName == "update":
        update.update(anchors=options.anchors, biblio=options.biblio, linkDefaults=options.linkDefaults, testSuites=options.testSuites)
    elif options.subparserName == "spec":
        doc = Spec(inputFilename=options.infile, paragraphMode=options.paragraphMode, debug=options.debug, token=options.ghToken)
        doc.md.addOverrides(extras)
        doc.preprocess()
        doc.finish(outputFilename=options.outfile)
    elif options.subparserName == "watch":
        # Can't have an error killing the watcher
        config.force = True
        doc = Spec(inputFilename=options.infile, token=options.ghToken)
        doc.md.addOverrides(extras)
        doc.watch(outputFilename=options.outfile)
    elif options.subparserName == "debug":
        config.force = True
        config.quiet = 2
        if options.printExports:
            doc = Spec(inputFilename=options.infile)
            doc.preprocess()
            doc.printTargets()
        elif options.jsonCode:
            doc = Spec(inputFilename=options.infile)
            doc.preprocess()
            exec("print json.dumps({0}, indent=2)".format(options.jsonCode))
        elif options.code:
            doc = Spec(inputFilename=options.infile)
            doc.preprocess()
            exec("print {0}".format(options.code))
        elif options.linkText:
            doc = Spec(inputFilename=options.infile)
            doc.preprocess()
            refs = doc.refs.refs[options.linkText] + doc.refs.refs[options.linkText+"\n"]
            config.quiet = options.quiet
            if not config.quiet:
                p("Refs for '{0}':".format(options.linkText))
            # Get ready for JSONing
            for ref in refs:
                ref['level'] = str(ref['level'])
            p(config.printjson(refs))
    elif options.subparserName == "refs":
        config.force = True
        config.quiet = 2
        doc = Spec(inputFilename=options.infile)
        if doc.valid:
            doc.preprocess()
            rm = doc.refs
        else:
            rm = ReferenceManager()
            rm.initializeRefs()
        refs,_ = list(rm.queryRefs(text=options.text, linkFor=options.linkFor, linkType=options.linkType, status=options.status, spec=options.spec, exact=options.exact))
        p(config.printjson(refs))
    elif options.subparserName == "issues-list":
        from . import issuelist as il
        if options.printTemplate:
            il.printHelpMessage()
        else:
            il.printIssueList(options.infile, options.outfile)
    elif options.subparserName == "source":
        if not options.bigText: # If no options are given, do all options.
            options.bigText = True
        if options.bigText:
            from . import fonts
            font = fonts.Font()
            fonts.replaceComments(font=font, inputFilename=options.infile, outputFilename=options.outfile)
    elif options.subparserName == "test":
        if options.rebaseFiles is not None:
            test.rebase(options.rebaseFiles)
        else:
            config.force = True
            config.quiet = 2
            result = test.runAllTests(constructor=Spec)
            sys.exit(0 if result else 1)
    elif options.subparserName == "profile":
        root = "--root=\"{0}\"".format(options.root) if options.root else ""
        leaf = "--leaf=\"{0}\"".format(options.leaf) if options.leaf else ""
        if options.svgFile:
            os.system("python -m cProfile -o stat.prof ~/bikeshed/bikeshed.py && gprof2dot -f pstats --skew=.0001 {root} {leaf} stat.prof | dot -Tsvg -o {svg} && rm stat.prof".format(root=root, leaf=leaf, svg=options.svgFile))
        else:
            os.system("python -m cProfile -o /tmp/stat.prof ~/bikeshed/bikeshed.py && gprof2dot -f pstats --skew=.0001 {root} {leaf} /tmp/stat.prof | xdot &".format(root=root, leaf=leaf))
    elif options.subparserName == "template":
        p('''<pre class='metadata'>
Title: Your Spec Title
Shortname: your-spec
Level: 1
Status: ED
Group: WGNAMEORWHATEVER
URL: http://example.com/url-this-spec-will-live-at
Editor: Your Name, Your Company http://example.com/your-company, your-email@example.com, http://example.com/your-personal-website
Abstract: A short description of your spec, one or two sentences.
</pre>

Introduction {#intro}
=====================

Introduction here.
''')

class Spec(object):

    def __init__(self, inputFilename, paragraphMode="markdown", debug=False, token=None):
        self.valid = False
        if inputFilename is None:
            # Default to looking for a *.bs file.
            # Otherwise, look for a *.src.html file.
            # Otherwise, use standard input.
            import glob
            if glob.glob("*.bs"):
                inputFilename = glob.glob("*.bs")[0]
            elif glob.glob("*.src.html"):
                inputFilename = glob.glob("*.src.html")[0]
            else:
                die("No input file specified, and no *.bs or *.src.html files found in current directory.\nPlease specify an input file, or use - to pipe from STDIN.")
                return
        self.inputSource = inputFilename
        self.debug = debug
        self.token = token

        self.valid = self.initializeState()

    def initializeState(self):
        self.normativeRefs = {}
        self.informativeRefs = {}
        self.refs = ReferenceManager()
        self.externalRefsUsed = defaultdict(dict)
        self.md = metadata.MetadataManager(doc=self)
        self.biblios = {}
        self.paragraphMode = "markdown"
        self.macros = defaultdict(lambda x: "???")
        self.widl = parser.Parser(ui=IDLUI())
        self.testSuites = json.loads(config.retrieveDataFile("test-suites.json", quiet=True, str=True))
        self.languages = json.loads(config.retrieveDataFile("languages.json", quiet=True, str=True))

        try:
            if self.inputSource == "-":
                self.lines = [unicode(line, encoding="utf-8") for line in sys.stdin.readlines()]
                self.md.date = datetime.today()
            else:
                self.lines = io.open(self.inputSource, 'r', encoding="utf-8").readlines()
                self.md.date = datetime.fromtimestamp(os.path.getmtime(self.inputSource))
        except OSError:
            die("Couldn't find the input file at the specified location '{0}'.", self.inputSource)
            return False
        except IOError:
            die("Couldn't open the input file '{0}'.", self.inputSource)
            return False
        return True

    def preprocess(self):
        # Textual hacks
        stripBOM(self)

        # Extract and process metadata
        self.lines = metadata.parse(md = self.md, lines=self.lines)
        self.loadDefaultMetadata()
        self.md.finish()
        self.md.fillTextMacros(self.macros, doc=self)

        # Initialize things
        self.refs.initializeRefs(self);
        self.refs.initializeBiblio();

        # Deal with further <pre> blocks, and markdown
        self.lines = datablocks.transformDataBlocks(self, self.lines)
        self.lines = markdown.parse(self.lines, self.md.indent, opaqueElements=self.md.opaqueElements)

        self.refs.setSpecData(self.md)

        # Convert to a single string of html now, for convenience.
        self.html = ''.join(self.lines)
        boilerplate.addHeaderFooter(self)
        self.html = self.fixText(self.html)

        # Build the document
        self.document = parseDocument(self.html)
        processInclusions(self)
        metadata.parseDoc(self)

        # Fill in and clean up a bunch of data
        boilerplate.addBikeshedVersion(self)
        boilerplate.addStatusSection(self)
        boilerplate.addLogo(self)
        boilerplate.addCopyright(self)
        boilerplate.addSpecMetadataSection(self)
        boilerplate.addAbstract(self)
        boilerplate.addObsoletionNotice(self)
        boilerplate.addAtRisk(self)
        addNoteHeaders(self)
        boilerplate.removeUnwantedBoilerplate(self)
        shorthands.transformProductionPlaceholders(self)
        shorthands.transformMaybePlaceholders(self)
        shorthands.transformAutolinkShortcuts(self)
        shorthands.transformProductionGrammars(self)
        canonicalizeShortcuts(self)
        fixManualDefTables(self)
        headings.processHeadings(self)
        checkVarHygiene(self)
        processIssuesAndExamples(self)
        markupIDL(self)
        inlineRemoteIssues(self)


        # Handle all the links
        processDfns(self)
        processIDL(self)
        fillAttributeInfoSpans(self)
        formatArgumentdefTables(self)
        formatElementdefTables(self)
        processAutolinks(self)
        boilerplate.addIndexSection(self)
        boilerplate.addExplicitIndexes(self)
        boilerplate.addStyles(self)
        processBiblioLinks(self)
        boilerplate.addReferencesSection(self)
        boilerplate.addPropertyIndex(self)
        boilerplate.addIDLSection(self)
        boilerplate.addIssuesSection(self)
        boilerplate.addCustomBoilerplate(self)
        headings.processHeadings(self, "all") # again
        boilerplate.removeUnwantedBoilerplate(self)
        boilerplate.addTOCSection(self)
        addSelfLinks(self)
        processAutolinks(self)
        boilerplate.addAnnotations(self)
        boilerplate.removeUnwantedBoilerplate(self)
        addSyntaxHighlighting(self)
        fixIntraDocumentReferences(self)
        fixInterDocumentReferences(self)

        # Any final HTML cleanups
        cleanupHTML(self)

        return self


    def serialize(self):
        rendered = HTMLSerializer.HTMLSerializer(self.document, self.md.opaqueElements).serialize()
        rendered = finalHackyCleanup(rendered)
        return rendered

    def fixMissingOutputFilename(self, outputFilename):
        if outputFilename is None:
            # More sensible defaults!
            if self.inputSource.endswith(".bs"):
                outputFilename = self.inputSource[0:-3] + ".html"
            elif self.inputSource.endswith(".src.html"):
                outputFilename = self.inputSource[0:-9] + ".html"
            elif self.inputSource == "-":
                outputFilename = "-"
            else:
                outputFilename = "-"
        return outputFilename

    def finish(self, outputFilename):
        outputFilename = self.fixMissingOutputFilename(outputFilename)
        rendered = self.serialize()
        if not config.dryRun:
            try:
                if outputFilename == "-":
                    outputFile = sys.stdout.write(rendered)
                else:
                    with io.open(outputFilename, "w", encoding="utf-8") as f:
                        f.write(rendered)
            except Exception, e:
                die("Something prevented me from saving the output document to {0}:\n{1}", outputFilename, e)

    def watch(self, outputFilename):
        import time
        outputFilename = self.fixMissingOutputFilename(outputFilename)
        if self.inputSource == "-" or outputFilename == "-":
            die("Watch mode doesn't support streaming from STDIN or to STDOUT.")
            return
        try:
            lastInputModified = os.stat(self.inputSource).st_mtime
            self.preprocess()
            self.finish(outputFilename)
            p("==============DONE==============")
            while(True):
                inputModified = os.stat(self.inputSource).st_mtime
                if inputModified > lastInputModified:
                    resetSeenMessages()
                    lastInputModified = inputModified
                    formattedTime = datetime.fromtimestamp(inputModified).strftime("%H:%M:%S")
                    p("Source file modified at {0}. Rebuilding...".format(formattedTime))
                    self.initializeState()
                    self.preprocess()
                    self.finish(outputFilename)
                    p("==============DONE==============")
                time.sleep(1)
        except Exception, e:
            die("Something went wrong while watching the file:\n{0}", e)




    def loadDefaultMetadata(self):
        data = config.retrieveBoilerplateFile(self, 'defaults', error=False)
        try:
            defaults = json.loads(data)
        except Exception, e:
            if data != "":
                die("Error loading defaults:\n{0}", str(e))
            return
        for key,val in defaults.items():
            self.md.addDefault(key, val)

    def fixText(self, text, moreMacros=None):
        # Do several textual replacements that need to happen *before* the document is parsed as HTML.

        # If markdown shorthands are on, temporarily remove `foo` while processing.
        codeSpanReplacements = []
        if "markdown" in self.md.markupShorthands:
            def replaceCodeSpans(m):
                codeSpanReplacements.append(m.group(2))
                return "\ue0ff"
            text = re.sub(r"(`+)(.*?[^`])\1(?=[^`])", replaceCodeSpans, text, flags=re.DOTALL)

        # Replace the [FOO] text macros.
        # [FOO?] macros are optional; failure just removes them.
        def macroReplacer(match):
            fullText = match.group(0)
            innerText = match.group(2).lower() or ""
            optional = match.group(3) == "?"
            if fullText.startswith("\\"):
                # Escaped
                return fullText[1:]
            if fullText.startswith("[["):
                # Actually a biblio link
                return fullText
            if innerText.isdigit():
                # No refs are all-digits (this is probably JS code).
                return fullText
            if innerText in self.macros:
                # For some reason I store all the macros in lowercase,
                # despite requiring them to be spelled with uppercase.
                return self.macros[innerText.lower()]
            if moreMacros and innerText in moreMacros:
                return moreMacros[innerText.lower()]
            # Nothing has matched, so start failing the macros.
            if optional:
                return ""
            die("Found unmatched text macro {0}. Correct the macro, or escape it with a leading backslash.", fullText)
            return fullText
        text = re.sub(r"(\\|\[)?\[([A-Z0-9-]+)(\??)\]", macroReplacer, text)
        text = fixTypography(text)
        if "css" in self.md.markupShorthands:
            # Replace the <<production>> shortcuts, because they won't survive the HTML parser.
            text = re.sub("<<([^>\s]+)>>", r"<fake-production-placeholder class=production>\1</fake-production-placeholder>", text)
            # Replace the ''maybe link'' shortcuts.
            # They'll survive the HTML parser, but they don't match if they contain an element.
            # (The other shortcuts are "atomic" and can't contain elements.)
            text = re.sub(r"''([^=\n]+?)''", r'<fake-maybe-placeholder>\1</fake-maybe-placeholder>', text)

        if codeSpanReplacements:
            codeSpanReplacements.reverse()
            def codeSpanReviver(_):
                # Match object is the PUA character, which I can ignore.
                # Instead, sub back the replacement in order,
                # massaged per the Commonmark rules.
                import string
                t = escapeHTML(codeSpanReplacements.pop()).strip(string.whitespace)
                t = re.sub("["+string.whitespace+"]{2,}", " ", t)
                return "<code data-opaque>"+t+"</code>"
            text = re.sub("\ue0ff", codeSpanReviver, text)
        return text

    def printTargets(self):
        p("Exported terms:")
        for el in findAll("[data-export]", self):
            for term in  config.linkTextsFromElement(el):
                p("  " + term)
        p("Unexported terms:")
        for el in findAll("[data-noexport]", self):
            for term in  config.linkTextsFromElement(el):
                p("  " + term)

    def isOpaqueElement(self, el):
        if el.tag in self.md.opaqueElements:
            return True
        if el.get("data-opaque") is not None:
            return True
        return False

config.specClass = Spec






def stripBOM(doc):
    if len(doc.lines) >= 1 and doc.lines[0][0:1] == "\ufeff":
        doc.lines[0] = doc.lines[0][1:]
        warn("Your document has a BOM. There's no need for that, please re-save it without a BOM.")


# Definitions and the like

def fixManualDefTables(doc):
    # Def tables generated via datablocks are guaranteed correct,
    # but manually-written ones often don't link up the names in the first row.
    for table in findAll("table.propdef, table.descdef, table.elementdef", doc):
        if hasClass(table, "partial"):
            tag = "a"
            attr = "data-link-type"
        else:
            tag = "dfn"
            attr = "data-dfn-type"
        tag = "a" if hasClass(table, "partial") else "dfn"
        if hasClass(table, "propdef"):
            type = "property"
        elif hasClass(table, "descdef"):
            type = "descriptor"
        elif hasClass(table, "elementdef"):
            type = "element"
        cell = findAll("tr:first-child > :nth-child(2)", table)[0]
        names = [x.strip() for x in textContent(cell).split(',')]
        newContents = config.intersperse((createElement(tag, {attr:type}, name) for name in names), ", ")
        replaceContents(cell, newContents)

def canonicalizeShortcuts(doc):
    # Take all the invalid-HTML shortcuts and fix them.

    attrFixup = {
        "export":"data-export",
        "noexport":"data-noexport",
        "spec":"data-link-spec",
        "status":"data-link-status",
        "dfn-for":"data-dfn-for",
        "link-for":"data-link-for",
        "link-for-hint":"data-link-for-hint",
        "dfn-type":"data-dfn-type",
        "link-type":"data-link-type",
        "force":"data-dfn-force",
        "section":"data-section",
        "attribute-info":"data-attribute-info",
        "dict-member-info":"data-dict-member-info",
        "lt":"data-lt",
        "local-lt":"data-local-lt",
        "algorithm":"data-algorithm"
    }
    for el in findAll(",".join("[{0}]".format(attr) for attr in attrFixup.keys()), doc):
        for attr, fixedAttr in attrFixup.items():
            if el.get(attr) is not None:
                el.set(fixedAttr, el.get(attr))
                del el.attrib[attr]

    # The next two aren't in the above dict because some of the words conflict with existing attributes on some elements.
    # Instead, limit the search/transforms to the relevant elements.
    for el in findAll("dfn, h2, h3, h4, h5, h6", doc):
        for dfnType in config.dfnTypes.union(["dfn"]):
            if el.get(dfnType) == "":
                del el.attrib[dfnType]
                el.set("data-dfn-type", dfnType)
                break
    for el in findAll("a", doc):
        for linkType in config.linkTypes.union(["dfn"]):
            if el.get(linkType) is not None:
                del el.attrib[linkType]
                el.set("data-link-type", linkType)
                break
    for el in findAll(",".join("{0}[for]".format(x) for x in config.dfnElements.union(["a"])), doc):
        if el.tag == "a":
            el.set("data-link-for", el.get('for'))
        else:
            el.set("data-dfn-for", el.get('for'))
        del el.attrib['for']


def checkVarHygiene(doc):
    def nearestAlgo(var):
        # Find the nearest "algorithm" container,
        # either an ancestor with [algorithm] or the nearest heading with same.
        algo = treeAttr(var, "data-algorithm")
        if algo:
            return algo or None
        for h in relevantHeadings(var):
            algo = h.get("data-algorithm")
            if algo is not None and algo is not "":
                return algo

    # Look for vars that only show up once. These are probably typos.
    singularVars = []
    varCounts = Counter((foldWhitespace(textContent(el)), nearestAlgo(el)) for el in findAll("var", doc))
    for var,count in varCounts.items():
        if count == 1 and var[0].lower() not in doc.md.ignoredVars:
            singularVars.append(var)
    if singularVars:
        printVars = ""
        for var,algo in singularVars:
            if algo:
                printVars += "  '{0}', in algorithm '{1}'\n".format(var, algo)
            else:
                printVars += "  '{0}'\n".format(var)
        warn("The following <var>s were only used once in the document:\n{0}If these are not typos, please add them to the 'Ignored Vars' metadata.", printVars)

    # Look for algorithms that show up twice; these are errors.
    for algo, count in Counter(el.get('data-algorithm') for el in findAll("[data-algorithm]", doc)).items():
        if count > 1:
            die("Multiple declarations of the '{0}' algorithm.", algo)
            return




def fixIntraDocumentReferences(doc):
    ids = {el.get('id'):el for el in findAll("[id]", doc)}
    headingIDs = {el.get('id'):el for el in findAll("[id].heading", doc)}
    for el in findAll("a[href^='#']:not([href='#']):not(.self-link):not([data-link-type])", doc):
        targetID = el.get("href")[1:]
        if el.get('data-section') is not None and targetID not in headingIDs:
            die("Couldn't find target document section {0}:\n{1}", targetID, outerHTML(el))
            continue
        elif targetID not in ids:
            die("Couldn't find target anchor {0}:\n{1}", targetID, outerHTML(el))
            continue
        if (el.text is None or el.text.strip() == '') and len(el) == 0:
            # TODO Allow this to respect "safe" markup (<sup>, etc) in the title
            target = ids[targetID]
            content = find(".content", target)
            if content is None:
                die("Tried to generate text for a section link, but the target isn't a heading:\n{0}", outerHTML(el))
                continue
            text = textContent(content).strip()
            if target.get('data-level') is not None:
                text = "§{1} {0}".format(text, target.get('data-level'))
            appendChild(el, text)

def fixInterDocumentReferences(doc):
    for el in findAll("[spec-section]", doc):
        spec = el.get('data-link-spec')
        section = el.get('spec-section', '')
        if spec is None:
            die("Spec-section autolink doesn't have a 'spec' attribute:\n{0}", outerHTML(el))
            continue
        if section is None:
            die("Spec-section autolink doesn't have a 'spec-section' attribute:\n{0}", outerHTML(el))
            continue
        if spec in doc.refs.headings:
            # Bikeshed recognizes the spec
            specData = doc.refs.headings[spec]
            if section in specData:
                heading = specData[section]
            else:
                die("Couldn't find section '{0}' in spec '{1}':\n{2}", section, spec, outerHTML(el))
                continue
            if isinstance(heading, list):
                # Multipage spec
                if len(heading) == 1:
                    # only one heading of this name, no worries
                    heading = specData[heading[0]]
                else:
                    # multiple headings of this id, user needs to disambiguate
                    die("Multiple headings with id '{0}' for spec '{1}'. Please specify:\n{2}", section, spec, "\n".join("  [[{0}]]".format(spec+x) for x in heading))
                    continue
            el.tag = "a"
            el.set("href", heading['url'])
            el.text = "{spec} §{number} {text}".format(**heading)
        elif doc.refs.getBiblioRef(spec):
            # Bikeshed doesn't know the spec, but it's in biblio
            bib = doc.refs.getBiblioRef(spec)
            if isinstance(bib, biblio.StringBiblioEntry):
                die("Can't generate a cross-spec section ref for '{0}', because the biblio entry has no url.", spec)
                continue
            el.tag = "a"
            el.set("href", bib.url + section)
            el.text = bib.title + " §" + section[1:]
        else:
            # Unknown spec
            die("Spec-section autolink tried to link to non-existent '{0}' spec:\n{1}", spec, outerHTML(el))
            continue
        removeAttr(el, 'data-link-spec')
        removeAttr(el, 'spec-section')

def fillAttributeInfoSpans(doc):
    # Auto-add <span attribute-info> to <dt><dfn> when it's an attribute or dict-member.
    for dt in findAll("dt", doc):
        if find("span[data-attribute-info]", dt) is not None:
            # Already has one, no need to do any work here
            continue
        dfn = find("dfn", dt)
        if dfn is None:
            continue
        dfnType = dfn.get("data-dfn-type")
        if dfnType == "attribute":
            attrName = "data-attribute-info"
        elif dfnType == "dict-member":
            attrName = "data-dict-member-info"
        else:
            continue
        spanFor = config.linkTextsFromElement(dfn)[0]
        # Internal slots (denoted by [[foo]] naming scheme) don't have attribute info
        if spanFor.startswith("[["):
            continue
        if dfn.get("data-dfn-for"):
            spanFor = dfn.get("data-dfn-for") + "/" + spanFor
        insertAfter(dfn,
            ", ",
            E.span({attrName:"", "for":spanFor}))

    for el in findAll("span[data-attribute-info], span[data-dict-member-info]", doc):
        if el.get('data-attribute-info') is not None:
            refType = "attribute"
        else:
            refType = "dict-member"
        if (el.text is None or el.text.strip() == '') and len(el) == 0:
            referencedAttribute = el.get("for")
            if referencedAttribute is None or referencedAttribute == "":
                die("Missing for reference in attribute info span.")
                continue
            if "/" in referencedAttribute:
                interface, referencedAttribute = referencedAttribute.split("/")
                target = findAll('[data-link-type={2}][data-lt="{0}"][data-link-for="{1}"]'.format(referencedAttribute, interface, refType), doc)
            else:
                target = findAll('[data-link-type={1}][data-lt="{0}"]'.format(referencedAttribute, refType), doc)
            if len(target) == 0:
                die("Couldn't find target {1} '{0}':\n{2}", referencedAttribute, refType, outerHTML(el))
                continue
            elif len(target) > 1:
                die("Multiple potential target {1}s '{0}':\n{2}", referencedAttribute, refType, outerHTML(el))
                continue
            target = target[0]
            datatype = target.get("data-type").strip()
            default = target.get("data-default");
            decorations = []
            if target.get("data-readonly") is not None:
                decorations.append(", readonly")
            if datatype[-1] == "?":
                decorations.append(", nullable")
                datatype = datatype[:-1]
            if default is not None:
                decorations.append(", defaulting to ")
                decorations.append(E.code(default))
            if datatype[0] == "(":
                # Union type
                # TODO(Nov 2015): actually handle this properly, don't have time to think through it right now.
                appendChild(el,
                    " of type ",
                    E.code({"class":"idl-code"}, datatype),
                    *decorations)
            elif re.match(r"(\w+)<(\w+)>", datatype):
                # Sequence type
                match = re.match(r"(\w+)<(\w+)>", datatype)
                appendChild(el,
                    " of type ",
                    match.group(1),
                    "<",
                    E.a({"data-link-type":"idl-name"}, match.group(2)),
                    ">",
                    *decorations)
            else:
                # Everything else
                appendChild(el,
                    " of type ",
                    E.a({"data-link-type":"idl-name"}, datatype),
                    *decorations)

def processDfns(doc):
    dfns = findAll(config.dfnElementsSelector, doc)
    classifyDfns(doc, dfns)
    fixupIDs(doc, dfns)
    doc.refs.addLocalDfns(dfn for dfn in dfns if dfn.get('id') is not None)


def determineDfnType(dfn):
    # 1. Look at data-dfn-type
    if dfn.get('data-dfn-type'):
        return dfn.get('data-dfn-type')
    # 2. Look for a prefix on the id
    if dfn.get('id'):
        id = dfn.get('id')
        for prefix, type in config.dfnClassToType.items():
            if id.startswith(prefix):
                return type
    # 3. Look for a class or data-dfn-type on the ancestors
    for ancestor in dfn.iterancestors():
        if ancestor.get('data-dfn-type'):
            return ancestor.get('data-dfn-type')
        classList = ancestor.get('class') or ''
        for cls, type in config.dfnClassToType.items():
            if hasClass(ancestor, cls):
                return type
            if hasClass(ancestor, "idl") and not hasClass(ancestor, "extract"):
                return "interface"
    # 4. Introspect on the text
    text = textContent(dfn)
    if text[0:1] == "@":
        return "at-rule"
    elif len(dfn) == 1 and dfn[0].get('data-link-type') == "maybe":
        return "value"
    elif text[0:1] == "<" and text[-1:] == ">":
        return "type"
    elif text[0:1] == ":":
        return "selector"
    elif re.match(r"^[\w-]+\(.*\)$", text) and not (dfn.get('id') or '').startswith("dom-"):
        return "function"
    else:
        return "dfn"

def classifyDfns(doc, dfns):
    dfnTypeToPrefix = {v:k for k,v in config.dfnClassToType.items()}
    for el in dfns:
        dfnType = determineDfnType(el)
        dfnTexts = config.linkTextsFromElement(el)
        dfnFor = treeAttr(el, "data-dfn-for")
        if len(dfnTexts):
            primaryDfnText = dfnTexts[0]
        else:
            die("Dfn has no linking text:\n{0}", outerHTML(el))
            continue
        # Push the dfn type down to the <dfn> itself.
        if el.get('data-dfn-type') is None:
            el.set('data-dfn-type', dfnType)
        # Push the for value too.
        if dfnFor:
            el.set('data-dfn-for', dfnFor)
        elif dfnType in config.typesUsingFor:
            die("'{0}' definitions need to specify what they're for.\nAdd a 'for' attribute to {1}, or add 'dfn-for' to an ancestor.", dfnType, outerHTML(el))
            continue
        # Some error checking
        if dfnType in config.functionishTypes:
            if not re.match(r"^[\w-]+\(.*\)$", primaryDfnText):
                die("Functions/methods must end with () in their linking text, got '{0}'.", primaryDfnText)
                continue
            elif el.get('data-lt') is None:
                if dfnType == "function":
                    # CSS function, define it with no args in the text
                    primaryDfnText = re.match(r"^([\w-]+)\(.*\)$", primaryDfnText).group(1)+"()"
                    el.set('data-lt', primaryDfnText)
                elif dfnType in config.idlTypes:
                    # IDL methodish construct, ask the widlparser what it should have.
                    # If the method isn't in any IDL, this tries its best to normalize it anyway.
                    names = doc.widl.normalizedMethodNames(primaryDfnText, el.get('data-dfn-for'))
                    primaryDfnText = names[0]
                    el.set('data-lt', "|".join(names))
                else:
                    die("BIKESHED ERROR: Unhandled functionish type '{0}' in classifyDfns. Please report this to Bikeshed's maintainer.", dfnType)
        # If type=argument, try to infer what it's for.
        if dfnType == "argument" and el.get('data-dfn-for') is None:
            parent = el.getparent()
            parentFor = parent.get('data-dfn-for')
            if parent.get('data-dfn-type') in config.functionishTypes and parentFor is not None:
                dfnFor = ", ".join(parentFor+"/"+name for name in doc.widl.normalizedMethodNames(textContent(parent), parentFor))
            elif treeAttr(el, "data-dfn-for") is None:
                die("'argument' dfns need to specify what they're for, or have it be inferrable from their parent. Got:\n{0}", outerHTML(el))
                continue
        # Automatically fill in id if necessary.
        if el.get('id') is None:
            if dfnFor:
                singleFor = config.splitForValues(dfnFor)[0]
            if dfnType in config.functionishTypes.intersection(config.idlTypes):
                id = config.simplifyText("{_for}-{id}".format(_for=singleFor, id=re.match(r"[^(]*", primaryDfnText).group(0)+"()"))
                el.set("data-alternate-id", config.simplifyText("dom-{_for}-{id}".format(_for=singleFor, id=primaryDfnText)))
            else:
                if dfnFor:
                    id = config.simplifyText("{_for}-{id}".format(_for=singleFor, id=primaryDfnText))
                else:
                    id = config.simplifyText(primaryDfnText)
            if dfnType == "dfn":
                pass
            elif dfnType == "interface":
                pass
            elif dfnType == "event":
                # Special case 'event' because it needs a different format from IDL types
                id = config.simplifyText("{type}-{id}".format(type=dfnTypeToPrefix[dfnType], _for=singleFor, id=id))
            elif dfnType == "attribute" and primaryDfnText.startswith("[["):
                # Slots get their identifying [] stripped from their ID, so gotta dedup them some other way.
                id = config.simplifyText("dom-{id}-slot".format(_for=singleFor, id=id))
            elif dfnType in config.idlTypes.intersection(config.typesUsingFor):
                id = config.simplifyText("dom-{id}".format(id=id))
            else:
                id = "{type}-{id}".format(type=dfnTypeToPrefix[dfnType], id=id)
            el.set('id', id)
        # Set lt if it's not set, and textContent doesn't match
        if el.get('data-lt') is None and textContent(el) != primaryDfnText:
            el.set('data-lt', primaryDfnText)
        # Push export/noexport down to the definition
        if el.get('data-export') is None and el.get('data-noexport') is None:
            for ancestor in el.iterancestors():
                if ancestor.get('data-export') is not None:
                    el.set('data-export', '')
                    break
                elif ancestor.get('data-noexport') is not None:
                    el.set('data-noexport', '')
                    break
            else:
                if dfnType == "dfn":
                    el.set('data-noexport', '')
                else:
                    el.set('data-export', '')


def determineLinkType(el):
    # 1. Look at data-link-type
    linkType = treeAttr(el, 'data-link-type')
    if linkType:
        if linkType in config.linkTypes.union(["dfn"]):
            return linkType
        die("Unknown link type '{0}' on:\n{1}", linkType, outerHTML(el))
        return "unknown-type"
    # 2. Introspect on the text
    text = textContent(el)
    if config.typeRe["at-rule"].match(text):
        return "at-rule"
    elif config.typeRe["type"].match(text):
        return "type"
    elif config.typeRe["selector"].match(text):
        return "selector"
    elif config.typeRe["function"].match(text):
        return "functionish"
    else:
        return "dfn"


def determineLinkText(el):
    linkType = el.get('data-link-type')
    contents = textContent(el)
    if el.get('data-lt'):
        linkText = el.get('data-lt')
    elif linkType in config.functionishTypes.union(["functionish"]) and re.match(r"^[\w-]+\(.*\)$", contents):
        linkText = re.match(r"^([\w-]+)\(.*\)$", contents).group(1)+"()"
        # Need to fix this using the idl parser.
    else:
        linkText = contents
    linkText = foldWhitespace(linkText)
    if len(linkText) == 0:
        die("Autolink {0} has no linktext.", outerHTML(el))
    return linkText


def classifyLink(el):
    linkType = determineLinkType(el)
    el.set('data-link-type', linkType)
    linkText = determineLinkText(el)

    el.set('data-lt', linkText)
    for attr in ["data-link-status", "data-link-for", "data-link-spec", "data-link-for-hint"]:
        val = treeAttr(el, attr)
        if val is not None:
            el.set(attr, val)
    return el













# Additional Processing


def processBiblioLinks(doc):
    biblioLinks = findAll("a[data-link-type='biblio']", doc)
    for el in biblioLinks:
        biblioType = el.get('data-biblio-type')
        if biblioType == "normative":
            storage = doc.normativeRefs
        elif biblioType == "informative":
            storage = doc.informativeRefs
        else:
            die("Unknown data-biblio-type value '{0}' on {1}. Only 'normative' and 'informative' allowed.", biblioType, outerHTML(el))
            continue

        linkText = determineLinkText(el)
        if linkText[0] == "[" and linkText[-1] == "]":
            linkText = linkText[1:-1]

        biblioStatus = treeAttr(el, "data-biblio-status")
        if not biblioStatus:
            biblioStatus = doc.md.defaultBiblioStatus

        okayToFail = el.get('data-okay-to-fail') is not None

        ref = doc.refs.getBiblioRef(linkText, status=biblioStatus, generateFakeRef=okayToFail, el=el)
        if not ref:
            if not okayToFail:
                closeBiblios = biblio.findCloseBiblios(doc.refs.biblioKeys, linkText)
                die("Couldn't find '{0}' in bibliography data. Did you mean:\n{1}", linkText, '\n'.join("  "+b for b in closeBiblios))
            el.tag = "span"
            continue

        id = config.simplifyText(ref.linkText)
        el.set('href', '#biblio-'+id)
        storage[ref.linkText] = ref


def processAutolinks(doc):
    # An <a> without an href is an autolink.
    # <i> is a legacy syntax for term autolinks. If it links up, we change it into an <a>.
    # We exclude bibliographical links, as those are processed in `processBiblioLinks`.
    query = "a:not([href]):not([data-link-type='biblio'])"
    if doc.md.useIAutolinks:
        query += ", i"
    autolinks = findAll(query, doc)
    for el in autolinks:
        # Explicitly empty linking text indicates this shouldn't be an autolink.
        if el.get('data-lt') == '':
            continue

        classifyLink(el)
        linkType = el.get('data-link-type')
        linkText = el.get('data-lt')

        # Properties and descriptors are often written like 'foo-*'. Just ignore these.
        if linkType in ("property", "descriptor", "propdesc") and "*" in linkText:
            continue

        linkFor = config.splitForValues(el.get('data-link-for'))
        if linkFor:
            linkFor = linkFor[0]
        ref = doc.refs.getRef(linkType, linkText,
                              spec=el.get('data-link-spec'),
                              status=el.get('data-link-status'),
                              linkFor=linkFor,
                              linkForHint=el.get('data-link-for-hint'),
                              el=el,
                              error=(linkText.lower() not in doc.md.ignoredTerms))
        # Capture the reference (and ensure we add a biblio entry) if it
        # points to an external specification. We check the spec name here
        # rather than checking `status == "local"`, as "local" refs include
        # those defined in `<pre class="anchor">` datablocks, which we do
        # want to capture here.
        if ref and ref.spec is not None and ref.spec is not "" and ref.spec != doc.refs.specVName:
            if ref.text not in doc.externalRefsUsed[ref.spec]:
                doc.externalRefsUsed[ref.spec][ref.text] = ref
            if isNormative(el):
                biblioStatus = "normative"
                biblioStorage = doc.normativeRefs
            else:
                biblioStatus = "informative"
                biblioStorage = doc.informativeRefs
            biblioRef = doc.refs.getBiblioRef(ref.spec, status=biblioStatus, generateFakeRef=True)
            if biblioRef:
                biblioStorage[biblioRef.linkText] = biblioRef

        if ref:
            el.set('href', ref.url)
            el.tag = "a"
            decorateAutolink(doc, el, linkType=linkType, linkText=linkText)
        else:
            if linkType == "maybe":
                el.tag = "css"
                if el.get("data-link-type"):
                    del el.attrib["data-link-type"]
                if el.get("data-lt"):
                    del el.attrib["data-lt"]

def decorateAutolink(doc, el, linkType, linkText):
    # Add additional effects to some autolinks.
    if linkType == "type":
        # Get all the values that the type expands to, add it as a title.
        if linkText in decorateAutolink.cache:
            titleText = decorateAutolink.cache[linkText]
            error = False
        else:
            refs, error = doc.refs.queryRefs(linkFor=linkText)
            if not error:
                titleText = "Expands to: " + ' | '.join(ref.text for ref in refs)
                decorateAutolink.cache[linkText] = titleText
        if not error:
            el.set('title', titleText)
decorateAutolink.cache = {}


def processIssuesAndExamples(doc):
    import hashlib
    # Add an auto-genned and stable-against-changes-elsewhere id to all issues and
    # examples, and link to remote issues if possible:
    for el in findAll(".issue:not([id])", doc):
        el.set('id', "issue-"+hashContents(el))
        remoteIssueID = el.get('data-remote-issue-id')
        if remoteIssueID:
            del el.attrib['data-remote-issue-id']
            # Eventually need to support a way to trigger other repo url structures,
            # but defaulting to GH is fine for now.
            githubMatch = re.match(r"\s*([\w-]+)/([\w-]+)#(\d+)\s*$", remoteIssueID)
            numberMatch = re.match(r"\s*(\d+)\s*$", remoteIssueID)
            remoteIssueURL = None
            if githubMatch:
                remoteIssueURL = "https://github.com/{0}/{1}/issues/{2}".format(*githubMatch.groups())
                if doc.md.inlineGithubIssues:
                    el.set("data-inline-github", "{0} {1} {2}".format(*githubMatch.groups()))
            elif numberMatch and doc.md.repository.type == "github":
                remoteIssueURL = doc.md.repository.formatIssueUrl(numberMatch.group(1))
                if doc.md.inlineGithubIssues:
                    el.set("data-inline-github", "{0} {1} {2}".format(doc.md.repository.user, doc.md.repository.repo, numberMatch.group(1)))
            elif doc.md.issueTrackerTemplate:
                remoteIssueURL = doc.md.issueTrackerTemplate.format(remoteIssueID)
            if remoteIssueURL:
                appendChild(el, " ", E.a({"href": remoteIssueURL }, "<" + remoteIssueURL + ">"))
    for el in findAll(".example:not([id])", doc):
        el.set('id', "example-"+hashContents(el))
    fixupIDs(doc, findAll(".issue, .example", doc))



def addSelfLinks(doc):
    def makeSelfLink(el):
        return E.a({"href": "#" + urllib.quote(el.get('id', '')), "class":"self-link"})

    dfnElements = findAll(config.dfnElementsSelector, doc)

    foundFirstNumberedSection = False
    for el in findAll("h2, h3, h4, h5, h6", doc):
        foundFirstNumberedSection = foundFirstNumberedSection or (el.get('data-level') is not None)
        if el in dfnElements:
            # It'll get a self-link or dfn-panel later.
            continue
        if foundFirstNumberedSection:
            appendChild(el, makeSelfLink(el))
    for el in findAll(".issue[id], .example[id], .note[id], li[id], dt[id]", doc):
        if list(el.iterancestors("figure")):
            # Skipping - element is inside a figure and is part of an example.
            continue
        prependChild(el, makeSelfLink(el))
    if doc.md.useDfnPanels:
        addDfnPanels(doc, dfnElements)
    else:
        for el in dfnElements:
            if list(el.iterancestors("a")):
                warn("Found <a> ancestor, skipping self-link. Swap <dfn>/<a> order?\n  {0}", outerHTML(el))
                continue
            appendChild(el, makeSelfLink(el))

def addDfnPanels(doc, dfns):
    from .DefaultOrderedDict import DefaultOrderedDict
    # Constructs "dfn panels" which show all the local references to a term
    atLeastOnePanel = False
    # Gather all the <a href>s together
    allRefs = DefaultOrderedDict(list)
    for a in findAll("a", doc):
        href = a.get("href")
        if href is None:
            continue
        if not href.startswith("#"):
            continue
        allRefs[href[1:]].append(a)
    for dfn in dfns:
        id = dfn.get("id")
        if not id:
            # Something went wrong, bail.
            continue
        refs = DefaultOrderedDict(list)
        for link in allRefs[id]:
            h = relevantHeadings(link).next()
            if hasClass(h, "no-ref"):
                continue
            sectionText = textContent(h)
            refs[sectionText].append(link)
        if not refs:
            # Just insert a self-link instead
            appendChild(dfn,
                E.a({"href": "#" + urllib.quote(id), "class":"self-link"}))
            continue
        addClass(dfn, "dfn-paneled")
        atLeastOnePanel = True
        panel = E.span({"class": "dfn-panel", "bs-decorative": ""},
            E.b(
                E.a({"href":"#"+urllib.quote(id)}, "#"+id)),
            E.b("Referenced in:"))
        counter = 0
        for text,els in refs.items():
            li = appendChild(panel, E.span())
            for i,el in enumerate(els):
                counter += 1
                refID = el.get("id")
                if refID is None:
                    refID = "ref-for-{0}-{1}".format(id, counter)
                    el.set("id", refID)
                if i == 0:
                    appendChild(li,
                        E.a({"href": "#"+urllib.quote(refID)}, text))
                else:
                    appendChild(li,
                        " ",
                        E.a({"href": "#"+urllib.quote(refID)}, "("+str(i+1)+")"))
        appendChild(dfn, panel)
    if atLeastOnePanel:
        script = '''
        document.body.addEventListener("click", function(e) {
            var queryAll = function(sel) { return [].slice.call(document.querySelectorAll(sel)); }
            // Find the dfn element or panel, if any, that was clicked on.
            var el = e.target;
            var target;
            while(el.parentElement) {
                if(el.tagName == "DFN") {
                    target = "dfn";
                    break;
                }
                if(/H\d/.test(el.tagName) && el.getAttribute('data-dfn-type') != null) {
                    target = "dfn";
                    break;
                }
                if(el.classList.contains("dfn-panel")) {
                    target = "dfn-panel";
                    break;
                }
                el = el.parentElement;
            }
            if(target != "dfn-panel") {
                // Turn off any currently "on" or "activated" panels.
                queryAll(".dfn-panel.on, .dfn-panel.activated").forEach(function(el){
                    el.classList.remove("on");
                    el.classList.remove("activated");
                });
            }
            if(target == "dfn") {
                // open the panel
                var dfnPanel = el.querySelector(".dfn-panel");
                if(dfnPanel) {
                    dfnPanel.classList.add("on");
                }
            } else if(target == "dfn-panel") {
                // Switch it to "activated" state, which pins it.
                el.classList.add("activated");
            }

        });
        '''
        style = '''
        .dfn-panel {
            display: inline-block;
            position: absolute;
            z-index: 35;
            height: auto;
            width: -webkit-fit-content;
            max-width: 300px;
            max-height: 500px;
            overflow: auto;
            padding: 0.5em 0.75em;
            font: small Helvetica Neue, sans-serif, Droid Sans Fallback;
            background: #DDDDDD;
            color: black;
            border: outset 0.2em;
        }
        .dfn-panel:not(.on) { display: none; }
        .dfn-panel * { margin: 0; padding: 0; text-indent: 0; }
        .dfn-panel > b { display: block; }
        .dfn-panel a { color: black; }
        .dfn-panel a:not(:hover) { text-decoration: none !important; border-bottom: none !important; }
        .dfn-panel > b + b { margin-top: 0.25em; }
        .dfn-panel > span { display: list-item; list-style: inside; }
        .dfn-panel.activated {
            display: inline-block;
            position: fixed;
            left: .5em;
            bottom: .5em;
            margin: 0 auto;
            max-width: calc(100vw - 1.5em - .4em - .5em);
            max-height: 30vh;
        }

        .dfn-paneled { cursor: pointer; }
        '''
        body = find("body", doc)
        appendChild(body, E.script(script), E.style(style))




class DebugMarker(object):
    # Debugging tool for IDL markup

    def markupConstruct(self, text, construct):
        return ('<' + construct.idlType + '>', '</' + construct.idlType + '>')

    def markupType(self, text, construct):
        return ('<TYPE for=' + construct.idlType + '>', '</TYPE>')

    def markupTypeName(self, text, construct):
        return ('<TYPE-NAME for=' + construct.idlType + '>', '</TYPE-NAME>')

    def markupName(self, text, construct):
        return ('<NAME for=' + construct.idlType + '>', '</NAME>')

    def markupKeyword(self, text, construct):
        return ('<KEYWORD for=' + construct.idlType + '>', '</KEYWORD>')

class IDLMarker(object):
    def markupConstruct(self, text, construct):
        # Fires for every 'construct' in the WebIDL.
        # Some things are "productions", not "constructs".
        return (None, None)

    def markupType(self, text, construct):
        # Fires for entire type definitions.
        # It'll contain keywords or names, or sometimes more types.
        # For example, a "type" wrapper surrounds an entire union type,
        # as well as its component types.
        return (None, None)

    def markupTypeName(self, text, construct):
        # Fires for non-defining type names, such as arg types.

        # The names in [Exposed=Foo] are [Global] tokens, not interface names.
        # Since I don't track globals as a link target yet, don't link them at all.
        if construct.idlType == "extended-attribute" and construct.name == "Exposed":
            return (None, None)

        # The name in [PutForwards=foo] is an attribute of the same interface.
        if construct.idlType == "extended-attribute" and construct.name == "PutForwards":
            # In [PutForwards=value] attribute DOMString foo
            # the "value" is a DOMString attr
            attr = construct.parent
            if hasattr(attr.member, "rest"):
                type = attr.member.rest.type
            elif hasattr(attr.member, "attribute"):
                type = attr.member.attribute.type
            typeName = str(type).strip()
            if typeName.endswith("?"):
                typeName = typeName[:-1]
            return ('<a data-link-type=attribute data-link-for="{0}">'.format(typeName), '</a>')

        if construct.idlType == "constructor":
            # This shows up for the method name in a [NamedConstructor] extended attribute.
            # The "NamedConstructor" Name already got markup up, so ignore this one.
            return (None, None)

        return ('<a data-link-type="idl-name">', '</a>')

    def markupKeyword(self, text, construct):
        # Fires on the various "keywords" of WebIDL -
        # words that are part of the WebIDL syntax,
        # rather than names exposed to JS.
        # Examples: "interface", "stringifier", the IDL-defined type names like "DOMString" and "long".
        if text == "stringifier":
            if construct.name is None:
                # If no name was defined, you're required to define stringification behavior.
                return ("<a dfn for='{0}' data-lt='stringification behavior'>".format(construct.parent.fullName), "</a>")
            else:
                # Otherwise, you *can* point to/dfn stringification behavior if you want.
                return ("<idl data-idl-type=dfn data-idl-for='{0}' data-lt='stringification behavior' id='{0}-stringification-behavior'>".format(construct.parent.fullName), "</idl>")
        return (None, None)

    def markupName(self, text, construct):
        # Fires for defining names: method names, arg names, interface names, etc.
        if construct.idlType not in config.idlTypes:
            return (None,None)

        idlType = construct.idlType
        extraParameters = ''
        idlTitle = construct.normalName
        refType="idl"
        if idlType in config.functionishTypes:
            idlTitle = '|'.join(self.methodLinkingTexts(construct))
        elif idlType == "attribute":
            if hasattr(construct.member, "rest"):
                rest = construct.member.rest
            elif hasattr(construct.member, "attribute"):
                rest = construct.member.attribute
            else:
                die("Can't figure out how to construct attribute-info from:\n  {0}", construct)
            if rest.readonly is not None:
                readonly = 'data-readonly'
            else:
                readonly = ''
            extraParameters = '{0} data-type="{1}"'.format(readonly, rest.type)
        elif idlType == "dict-member":
            extraParameters = 'data-type="{0}"'.format(construct.type)
            if construct.default is not None:
                value = escapeAttr("{0}".format(construct.default.value))
                extraParameters += ' data-default="{0}"'.format(value)
        elif idlType == "interface":
            if construct.partial:
                refType="link"

        if refType == "link":
            elementName = "a"
        else:
            elementName = "idl"

        if idlType in config.typesUsingFor:
            if idlType == "argument" and construct.parent.idlType == "method":
                interfaceName = construct.parent.parent.name
                methodNames = ["{0}/{1}".format(interfaceName, m) for m in construct.parent.methodNames]
                idlFor = "data-idl-for='{0}'".format(", ".join(methodNames))
            else:
                idlFor = "data-idl-for='{0}'".format(construct.parent.fullName)
        else:
            idlFor = ""
        return ('<{name} data-lt="{0}" data-{refType}-type="{1}" {2} {3}>'.format(idlTitle, idlType, idlFor, extraParameters, name=elementName, refType=refType), '</{0}>'.format(elementName))

    def encode(self, text):
        return escapeHTML(text)

    def methodLinkingTexts(self, method):
        '''
        Given a method-ish widlparser Construct,
        finds all possible linking texts.
        The full linking text is "foo(bar, baz)";
        beyond that, any optional or variadic arguments can be omitted.
        So, if both were optional,
        "foo(bar)" and "foo()" would both also be valid linking texts.
        '''
        if getattr(method, "arguments", None) is None:
            return [method.normalName]
        for i,arg in enumerate(method.arguments):
            if arg.optional or arg.variadic:
                optStart = i
                break
        else:
            # No optionals, so no work to be done
            return [method.normalName]
        prefix = method.name + "("
        texts = []
        for i in range(optStart, len(method.arguments)):
            argText = ', '.join(arg.name for arg in method.arguments[:i])
            texts.append(prefix + argText + ")")
        texts.append(method.normalName)
        return reversed(texts)

class IDLUI(object):
    def warn(self, msg):
        die("{0}", msg)

def markupIDL(doc):
    for el in findAll("pre.idl", doc):
        if el.get("data-no-idl") is not None:
            continue
        if not isNormative(el):
            continue
        text = textContent(el)
        # Parse once with a fresh parser, so I can spit out just this <pre>'s markup.
        # Parse a second time with the global one, which collects all data in the doc.
        widl = parser.Parser(text, IDLUI())
        doc.widl.parse(text)
        marker = DebugMarker() if doc.debug else IDLMarker()
        text = unicode(widl.markup(marker))
        replaceContents(el, parseHTML(text))



def processIDL(doc):
    for pre in findAll("pre.idl", doc):
        if pre.get("data-no-idl") is not None:
            continue
        if not isNormative(pre):
            continue
        forcedInterfaces = []
        for x in (treeAttr(pre, "data-dfn-force") or "").split():
            x = x.strip()
            if x.endswith("<interface>"):
                x = x[:-11]
            forcedInterfaces.append(x)
        for el in findAll("idl", pre):
            idlType = el.get('data-idl-type')
            url = None
            forceDfn = False
            ref = None
            for idlText in el.get('data-lt').split('|'):
                if idlType == "interface" and idlText in forcedInterfaces:
                    forceDfn = True
                if idlType == "interface":
                    ref = doc.refs.getRef("interface", idlText, status="local", el=el, error=False)
                    if ref:
                        url = ref.url
                    else:
                        forceDfn = True
                else:
                    for linkFor in config.splitForValues(el.get('data-idl-for', '')) or [None]:
                        ref = doc.refs.getRef(idlType, idlText,
                                              linkFor=linkFor,
                                              el=el,
                                              error=False)
                        if ref:
                            url = ref.url
                            break
                if ref:
                    break
            if url is None or forceDfn:
                el.tag = "dfn"
                el.set('data-dfn-type', idlType)
                del el.attrib['data-idl-type']
                if el.get('data-idl-for'):
                    el.set('data-dfn-for', el.get('data-idl-for'))
                    del el.attrib['data-idl-for']
            else:
                el.tag = "a"
                el.set('data-link-type', idlType)
                el.set('data-lt', idlText)
                del el.attrib['data-idl-type']
                if el.get('data-idl-for'):
                    el.set('data-link-for', el.get('data-idl-for'))
                    del el.attrib['data-idl-for']
                if el.get('id'):
                    # ID was defensively added by the Marker.
                    del el.attrib['id']
    dfns = findAll("pre.idl:not([data-no-idl]) dfn", doc)
    classifyDfns(doc, dfns)
    fixupIDs(doc, dfns)
    doc.refs.addLocalDfns(dfn for dfn in dfns if dfn.get('id') is not None)



def addSyntaxHighlighting(doc):
    try:
        import pygments as pyg
        from pygments.lexers import get_lexer_by_name
        from pygments import formatters
        from pygments import token
        from pygments import style
    except ImportError:
        die("Bikeshed now uses Pygments for syntax highlighting.\nPlease run `$ sudo pip install pygments` from your command line.")
        return

    class PrismStyle(style.Style):
        default_style = "#000000"
        styles = {
            token.Name: "#0077aa",
            token.Name.Tag: "#669900",
            token.Name.Builtin: "noinherit",
            token.Name.Other: "noinherit",
            token.Operator: "#999999",
            token.Punctuation: "#999999",
            token.Keyword: "#990055",
            token.Literal: "#000000",
            token.Literal.Number: "#000000",
            token.Literal.String: "#a67f59",
            token.Comment: "#708090"
        }

    customLexers = {
        "css": lexers.CSSLexer()
    }

    def highlight(el, lang):
        text = textContent(el)
        if lang in customLexers:
            lexer = customLexers[lang]
        else:
            try:
                lexer = get_lexer_by_name(lang, encoding="utf-8", stripAll=True)
            except pyg.util.ClassNotFound:
                die("'{0}' isn't a known syntax-highlighting language. See http://pygments.org/docs/lexers/. Seen on:\n{1}", lang, outerHTML(el))
                return
        highlighted = parseHTML(pyg.highlight(text, lexer, formatters.HtmlFormatter()))[0][0]
        # Remove the trailing newline
        if len(highlighted):
            highlighted[-1].tail = highlighted[-1].tail.rstrip()
        replaceContents(el, highlighted)
        addClass(el, "highlight")

    highlightingOccurred = False

    def translateLang(lang):
        # Translates some names to ones Pygment understands
        if lang == "aspnet":
            return "aspx-cs"
        if lang in ["markup", "svg"]:
            return "html"
        return lang

    # Translate Prism-style highlighting into Pygment-style
    for el in findAll("[class*=language-], [class*=lang-]", doc):
        match = re.search("(?:lang|language)-(\w+)", el.get("class"))
        if match:
            el.set("highlight", match.group(1))

    # Highlight all the appropriate elements
    for el in findAll("pre, code", doc):
        if el.tag == "pre":
            children = list(childElements(el))
            if len(children):
                # If there's any internal structure, don't override it with highlighting.
                continue
        attr, lang = closestAttr(el, "nohighlight", "highlight")
        if attr == "nohighlight" or attr is None:
            continue
        highlight(el, translateLang(lang))
        highlightingOccurred = True

    if highlightingOccurred:
        style = formatters.HtmlFormatter(style=PrismStyle).get_style_defs('.highlight')
        style += """
        .highlight { background: hsl(24, 20%, 95%); }
        code.highlight { padding: .1em; border-radius: .3em; }
        pre.highlight, pre > code.highlight { display: block; padding: 1em; margin: .5em 0; overflow: auto; border-radius: 0; }
        """
        body = find("body", doc)
        appendChild(body,
            E.style(style))


def cleanupHTML(doc):
    # Cleanup done immediately before serialization.

    # Move any stray <link>, <meta>, or <style> into the <head>.
    head = find("head", doc)
    for el in findAll("body link, body meta, body style:not([scoped])", doc):
        head.append(el)

    # Move any <style scoped> to be the first child of their parent.
    for el in findAll("style[scoped]", doc):
        parent = parentElement(el)
        prependChild(parent, el)

    # Convert the technically-invalid <nobr> element to an appropriate <span>
    for el in findAll("nobr", doc):
        el.tag = "span"
        el.set("style", el.get('style', '') + ";white-space:nowrap")

    # If we accidentally recognized an autolink shortcut in SVG, kill it.
    for el in findAll("svg|a[data-link-type]", doc):
        del el.attrib["data-link-type"]
        el.tag = "{http://www.w3.org/2000/svg}tspan"

    # Mark pre.idl blocks as .def, for styling
    for el in findAll("pre.idl:not(.def)", doc):
        addClass(el, "def")

    # Tag classes on wide types of dfns/links
    def selectorForTypes(types):
        return (",".join("{0}[data-dfn-type={1}]".format(elName,type) for elName in config.dfnElements for type in types)
            + "," + ",".join("a[data-link-type={0}]".format(type) for type in types))
    for el in findAll(selectorForTypes(config.idlTypes), doc):
        addClass(el, 'idl-code')
    for el in findAll(selectorForTypes(config.maybeTypes.union(config.linkTypeToDfnType['propdesc'])), doc):
        addClass(el, 'css')
    # Correct over-application of the .css class
    for el in findAll("pre .css", doc):
        removeClass(el, 'css')

    # Remove comments from the generated HTML
    if config.minify:
        comments = list(doc.document.iter(lxml.etree.Comment))
        for comment in comments:
            removeNode(comment)

    # Remove duplicate linking texts.
    for el in findAll(",".join(x+"[data-lt]" for x in config.anchorishElements), doc):
        if el.get('data-lt') == textContent(el):
            del el.attrib['data-lt']

    # Transform the <css> fake tag into markup.
    # (Used when the ''foo'' shorthand doesn't work.)
    for el in findAll("css", doc):
        el.tag = "span"
        addClass(el, "css")

    # Transform the <assert> fake tag into a span with a unique ID based on its contents.
    # This is just used to tag arbitrary sections with an ID so you can point tests at it.
    # (And the ID will be guaranteed stable across publications, but guaranteed to change when the text changes.)
    for el in findAll("assert", doc):
        el.tag = "span"
        el.set("id", "assert-" + hashContents(el))

    # Add ARIA role of "note" to class="note" elements
    for el in findAll("."+doc.md.noteClass, doc):
        el.set("role", "note")

    # Look for nested <a> elements, and warn about them.
    for el in findAll("a a", doc):
        warn("The following (probably auto-generated) link is illegally nested in another link:\n{0}", outerHTML(el))

    # If the <h1> contains only capital letters, add a class=allcaps for styling hook
    h1 = find("h1", doc)
    for letter in textContent(h1):
        if letter.isalpha() and letter.islower():
            break
    else:
        addClass(h1, "allcaps")

    # Remove a bunch of attributes
    for el in findAll("[data-attribute-info], [data-dict-member-info]", doc):
        removeAttr(el, 'data-attribute-info')
        removeAttr(el, 'data-dict-member-info')
        removeAttr(el, 'for')
    for el in findAll("a, span", doc):
        removeAttr(el, 'data-link-for')
        removeAttr(el, 'data-link-for-hint')
        removeAttr(el, 'data-link-status')
        removeAttr(el, 'data-link-spec')
        removeAttr(el, 'data-section')
        removeAttr(el, 'data-biblio-type')
        removeAttr(el, 'data-biblio-status')
        removeAttr(el, 'data-okay-to-fail')
        removeAttr(el, 'data-lt')
    for el in findAll("[data-link-for]:not(a), [data-link-type]:not(a)", doc):
        removeAttr(el, 'data-link-for')
        removeAttr(el, 'data-link-type')
    for el in findAll("[data-dfn-for]{0}, [data-dfn-type]{0}".format("".join(":not({0})".format(x) for x in config.dfnElements)), doc):
        removeAttr(el, 'data-dfn-for')
        removeAttr(el, 'data-dfn-type')
    for el in findAll("[data-export]{0}, [data-noexport]{0}".format("".join(":not({0})".format(x) for x in config.dfnElements)), doc):
        removeAttr(el, 'data-export')
        removeAttr(el, 'data-noexport')
    for el in findAll("[oldids], [data-alternate-id], [highlight], [nohighlight], [data-opaque], [bs-decorative]", doc):
        removeAttr(el, 'oldids')
        removeAttr(el, 'data-alternate-id')
        removeAttr(el, 'highlight')
        removeAttr(el, 'nohiglight')
        removeAttr(el, 'data-opaque')
        removeAttr(el, 'bs-decorative')


def finalHackyCleanup(text):
    # For hacky last-minute string-based cleanups of the rendered html.

    return text


def processInclusions(doc):
    import hashlib
    includeHashes = set()
    while True:
        els = findAll("include", doc)
        if not els:
            break
        for el in els:
            if el.get("data-from-block") is None:
                warn("The <include> element is going away. Please switch to <pre class=include>.")
            macros = {}
            for i in itertools.count(0):
                m = el.get("data-macro-"+str(i))
                if m is None:
                    break
                k,_,v = m.partition(" ")
                macros[k.lower()] = v
            if el.get("path"):
                path = el.get("path")
                try:
                    with io.open(path, 'r', encoding="utf-8") as f:
                        lines = f.readlines()
                except Exception, err:
                    die("Couldn't find include file '{0}'. Error was:\n{1}", path, err)
                    removeNode(el)
                    continue
                hash = hashlib.md5(''.join(lines).encode("ascii", "xmlcharrefreplace")).hexdigest()
                if hash in includeHashes:
                    die("<include> loop detected: '{0}' was already included.", path)
                    removeNode(el)
                    continue
                else:
                    includeHashes.add(hash)
                lines = datablocks.transformDataBlocks(doc, lines)
                lines = markdown.parse(lines, doc.md.indent, opaqueElements=doc.md.opaqueElements)
                text = ''.join(lines)
                text = doc.fixText(text, moreMacros=macros)
                subtree = parseHTML(text)
                replaceNode(el, *subtree)
    else:
        die("<include> recursion depth exceeded")
        for el in findAll("include", doc):
            removeNode(el)
        return


def formatElementdefTables(doc):
    for table in findAll("table.elementdef", doc):
        elements = findAll("tr:first-child dfn", table)
        elementsFor = ' '.join(textContent(x) for x in elements)
        for el in findAll("a[data-element-attr-group]", table):
            groupName = textContent(el).strip()
            groupAttrs = sorted(doc.refs.queryRefs(linkType="element-attr", linkFor=groupName)[0], key=lambda x:x.text)
            if len(groupAttrs) == 0:
                die("The element-attr group '{0}' doesn't have any attributes defined for it.", groupName)
                continue
            el.tag = "details"
            clearContents(el)
            del el.attrib["data-element-attr-group"]
            del el.attrib["dfn"]
            ul = appendChild(el,
                E.summary(
                    E.a({"data-link-type":"dfn"}, groupName)),
                E.ul())
            for ref in groupAttrs:
                appendChild(ul,
                    E.li(
                        E.dfn({"id":"element-attrdef-"+config.simplifyText(textContent(elements[0]))+"-"+ref.text, "for":elementsFor, "data-dfn-type":"element-attr"},
                            E.a({"data-link-type":"element-attr", "for":groupName},
                                ref.text.strip()))))


def formatArgumentdefTables(doc):
    for table in findAll("table.argumentdef", doc):
        forMethod = doc.widl.normalizedMethodNames(table.get("data-dfn-for"))
        method = doc.widl.find(table.get("data-dfn-for"))
        if not method:
            die("Can't find method '{0}'.", forMethod)
            continue
        for tr in findAll("tbody > tr", table):
            tds = findAll("td", tr)
            argName = textContent(tds[0]).strip()
            arg = method.findArgument(argName)
            if arg:
                appendChild(tds[1], unicode(arg.type))
                if unicode(arg.type).strip().endswith("?"):
                    appendChild(tds[2],
                        E.span({"class":"yes"}, "✔"))
                else:
                    appendChild(tds[2],
                        E.span({"class":"no"}, "✘"))
                if arg.optional:
                    appendChild(tds[3],
                        E.span({"class":"yes"}, "✔"))
                else:
                    appendChild(tds[3],
                        E.span({"class":"no"}, "✘"))
            else:
                die("Can't find the '{0}' argument of method '{1}' in the argumentdef block.", argName, method.fullName)
                continue


def inlineRemoteIssues(doc):
    # Finds properly-marked-up "remote issues",
    # and inlines their contents into the issue.

    # Right now, only github inline issues are supported.
    # More can be supported when someone cares.
    for el in findAll("[data-inline-github]", doc):
        user, repo, id = el.get('data-inline-github').split()
        headers = {"Accept": "application/vnd.github.v3.html+json"}
        if doc.token is not None:
            headers["Authorization"] = "token " + doc.token
        removeAttr(el, "data-inline-github")
        req = urllib2.Request(url="https://api.github.com/repos/{0}/{1}/issues/{2}".format(user, repo, id),
            headers=headers)
        try:
            with closing(urllib2.urlopen(req)) as fh:
                issue = json.load(fh)
                clearContents(el)
                appendChild(el,
                    E.a({"href":issue['html_url'], "class":"marker"},
                        "Issue #{0} on GitHub: “{1}”".format(issue['number'], issue['title'])),
                    *parseHTML(issue['body_html']))
                if el.tag == "p":
                    el.tag = "div"
                addClass(el, "no-marker")
        except urllib2.HTTPError as err:
            if doc.token and err.code == 401:
                die("Unauthorized Access to GitHub's API. There might be an issue with your token.")
                break
            if doc.token is None and err.code == 403:
                die("You've reached GitHub API's rate limit for unauthenticated requests.\nTo increase it, please provide an auth token. Tokens can be generated from https://github.com/settings/tokens.")
                break
            die("Error inlining GitHub issues:\n{0}", err)
            continue
        except Exception as err:
            die("Error inlining GitHub issues:\n{0}", err)
            continue

def addNoteHeaders(doc):
    # Finds <foo heading="bar"> and turns it into a marker-heading
    for el in findAll("[heading]", doc):
        addClass(el, "no-marker")
        if hasClass(el, "note"):
            preText = "NOTE: "
        elif hasClass(el, "issue"):
            preText = "ISSUE: "
        elif hasClass(el, "example"):
            preText = "EXAMPLE: "
        else:
            preText = ""
        prependChild(el,
            E.div({"class":"marker"}, preText, *parseHTML(el.get('heading'))))
        removeAttr(el, "heading")

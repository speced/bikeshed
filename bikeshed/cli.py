# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals

import argparse
import os
import sys

from . import config
from . import metadata
from . import publish
from . import test
from . import update
from .messages import *
from .Spec import Spec

def main():
    # Hack around argparse's lack of optional subparsers
    if len(sys.argv) == 1:
        sys.argv.append("spec")

    argparser = argparse.ArgumentParser(description="Processes spec source files into valid HTML.")
    argparser.add_argument("-q", "--quiet", dest="quiet", action="count", default=0,
                           help="Silences one level of message, least-important first.")
    argparser.add_argument("-s", "--silent", dest="silent", action="store_true",
                           help="Shorthand for 'as many -q as you need to shut it up'")
    argparser.add_argument("-f", "--force", dest="force", action="store_true",
                           help="Force the preprocessor to run to completion; fatal errors don't stop processing.")
    argparser.add_argument("-d", "--dry-run", dest="dryRun", action="store_true",
                           help="Prevents the processor from actually saving anything to disk, but otherwise fully runs.")
    argparser.add_argument("--print", dest="printMode", action="store", default="console",
                           help="Print mode. Options are 'plain' (just text), 'console' (colored with console color codes), 'markup', and 'json'.")

    subparsers = argparser.add_subparsers(title="Subcommands", dest='subparserName')

    specParser = subparsers.add_parser('spec', help="Process a spec source file into a valid output file.")
    specParser.add_argument("infile", nargs="?",
                            default=None,
                            help="Path to the source file.")
    specParser.add_argument("outfile", nargs="?",
                            default=None,
                            help="Path to the output file.")
    specParser.add_argument("--debug", dest="debug", action="store_true", help="Switches on some debugging tools. Don't use for production!")
    specParser.add_argument("--gh-token", dest="ghToken", nargs="?",
                            help="GitHub access token. Useful to avoid API rate limits. Generate tokens: https://github.com/settings/tokens.")
    specParser.add_argument("--byos", dest="byos", action="store_true",
                            help="Bring-Your-Own-Spec: turns off all the Bikeshed auto-niceties, so you can piecemeal its features into your existing doc instead. Experimental, let me know if things get crashy or weird.")
    specParser.add_argument("-l", "--line-numbers", dest="lineNumbers", action="store_true",
                            help="Hacky support for outputting line numbers on all error messages. Disables output, as this is hacky and might mess up your source.")

    echidnaParser = subparsers.add_parser('echidna', help="Process a spec source file into a valid output file and publish it according to certain automatic protocols.")
    echidnaParser.add_argument("infile", nargs="?",
                               default=None,
                               help="Path to the source file.")
    echidnaParser.add_argument("--gh-token", dest="ghToken", nargs="?",
                               help="GitHub access token. Useful to avoid API rate limits. Generate tokens: https://github.com/settings/tokens.")
    echidnaParser.add_argument("--u", dest="un", metavar="USERNAME", required=False, help="W3C username.")
    echidnaParser.add_argument("--p", dest="pw", metavar="PASSWORD", required=False, help="W3C password.")
    echidnaParser.add_argument("--d", dest="decision", metavar="DECISION_URL", required=False, help="URL recording the decision to publish.")
    echidnaParser.add_argument("--additional-directories", dest="additionalDirectories", required=False, nargs="*", help="Directories to bundle in the tar file. Defaults to examples/, diagrams/, and images/.")
    echidnaParser.add_argument("--self-contained", dest="selfContained", action="store_true", help="The spec is self-contained, do not bundle any extra directories in the tar file.")
    echidnaParser.add_argument("--just-tar", dest="justTar", action="store_true")

    watchParser = subparsers.add_parser('watch', help="Process a spec source file into a valid output file, automatically rebuilding when it changes.")
    watchParser.add_argument("infile", nargs="?",
                             default=None,
                             help="Path to the source file.")
    watchParser.add_argument("outfile", nargs="?",
                             default=None,
                             help="Path to the output file.")
    watchParser.add_argument("--gh-token", dest="ghToken", nargs="?",
                             help="GitHub access token. Useful to avoid API rate limits. Generate tokens: https://github.com/settings/tokens.")
    watchParser.add_argument("--byos", dest="byos", action="store_true",
                             help="Bring-Your-Own-Spec: turns off all the Bikeshed auto-niceties, so you can piecemeal its features into your existing doc instead. Experimental, let me know if things get crashy or weird.")


    serveParser = subparsers.add_parser('serve', help="Identical to 'watch', but also serves the folder on localhost.")
    serveParser.add_argument("infile", nargs="?",
                             default=None,
                             help="Path to the source file.")
    serveParser.add_argument("outfile", nargs="?",
                             default=None,
                             help="Path to the output file.")
    serveParser.add_argument("--port", dest="port", nargs="?", default="8000",
                             help="Specify the port to serve it over.")
    serveParser.add_argument("--gh-token", dest="ghToken", nargs="?",
                             help="GitHub access token. Useful to avoid API rate limits. Generate tokens: https://github.com/settings/tokens.")
    serveParser.add_argument("--byos", dest="byos", action="store_true",
                             help="Bring-Your-Own-Spec: turns off all the Bikeshed auto-niceties, so you can piecemeal its features into your existing doc instead. Experimental, let me know if things get crashy or weird.")

    updateParser = subparsers.add_parser('update', help="Update supporting files (those in /spec-data).", epilog="If no options are specified, everything is downloaded.")
    updateParser.add_argument("--force", action="store_true", help="Forces a full update, skipping the manifest.")
    updateParser.add_argument("--anchors", action="store_true", help="Download crossref anchor data.")
    updateParser.add_argument("--biblio", action="store_true", help="Download biblio data.")
    updateParser.add_argument("--caniuse", action="store_true", help="Download Can I Use... data.")
    updateParser.add_argument("--link-defaults", dest="linkDefaults", action="store_true", help="Download link default data.")
    updateParser.add_argument("--test-suites", dest="testSuites", action="store_true", help="Download test suite data.")
    updateParser.add_argument("--languages", dest="languages", action="store_true", help="Download language/translation data.")

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
    debugCommands.add_argument("--refresh-data", dest="refreshData", action="store_true",
                               help="Clobbers the readonly data files with the mutable ones.")

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
                            default=False,
                            action="store_true",
                            help="Rebase the specified files.")
    testParser.add_argument('testFiles',
                            default=[],
                            metavar="FILE",
                            nargs="*",
                            help="Run these tests. If called with no args, tests everything.")

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

    templateParser = subparsers.add_parser('template', help="Outputs a skeleton .bs file for you to start with.")

    options, extras = argparser.parse_known_args()

    config.quiet = options.quiet
    if options.silent:
        config.quiet = float("infinity")
    config.force = options.force
    config.dryRun = options.dryRun
    config.printMode = options.printMode

    update.fixupDataFiles()
    if options.subparserName == "update":
        update.update(anchors=options.anchors, biblio=options.biblio, caniuse=options.caniuse, linkDefaults=options.linkDefaults, testSuites=options.testSuites, languages=options.languages, dryRun=config.dryRun, force=options.force)
    elif options.subparserName == "spec":
        doc = Spec(inputFilename=options.infile, debug=options.debug, token=options.ghToken, lineNumbers=options.lineNumbers)
        doc.md = metadata.fromCommandLine(extras, doc)
        if options.byos:
            doc.md.addData("Group", "byos")
        doc.preprocess()
        doc.finish(outputFilename=options.outfile)
    elif options.subparserName == "echidna":
        doc = Spec(inputFilename=options.infile, token=options.ghToken)
        doc.md = metadata.fromCommandLine(extras, doc)
        doc.md.addData("Prepare For TR", "yes")
        doc.preprocess()
        addDirs = [] if options.selfContained else options.additionalDirectories
        if options.justTar:
            publish.prepareTar(doc, visibleTar=True, additionalDirectories=addDirs)
        else:
            publish.publishEchidna(doc, username=options.un, password=options.pw, decision=options.decision, additionalDirectories=addDirs)
    elif options.subparserName == "watch":
        # Can't have an error killing the watcher
        config.force = True
        doc = Spec(inputFilename=options.infile, token=options.ghToken)
        doc.md = metadata.fromCommandLine(extras, doc)
        if options.byos:
            doc.md.addData("Group", "byos")
        doc.watch(outputFilename=options.outfile)
    elif options.subparserName == "serve":
        config.force = True
        doc = Spec(inputFilename=options.infile, token=options.ghToken)
        doc.md = metadata.fromCommandLine(extras, doc)
        if options.byos:
            doc.md.addData("Group", "byos")
        doc.watch(outputFilename=options.outfile, port=int(options.port))
    elif options.subparserName == "debug":
        config.force = True
        config.quiet = 2
        if options.printExports:
            doc = Spec(inputFilename=options.infile)
            doc.md = metadata.fromCommandLine(extras, doc)
            doc.preprocess()
            doc.printTargets()
        elif options.jsonCode:
            doc = Spec(inputFilename=options.infile)
            doc.md = metadata.fromCommandLine(extras, doc)
            doc.preprocess()
            exec("print config.printjson({0})".format(options.jsonCode))
        elif options.code:
            doc = Spec(inputFilename=options.infile)
            doc.md = metadata.fromCommandLine(extras, doc)
            doc.preprocess()
            exec("print {0}".format(options.code))
        elif options.linkText:
            doc = Spec(inputFilename=options.infile)
            doc.md = metadata.fromCommandLine(extras, doc)
            doc.preprocess()
            refs = doc.refs.refs[options.linkText] + doc.refs.refs[options.linkText + "\n"]
            config.quiet = options.quiet
            if not config.quiet:
                p("Refs for '{0}':".format(options.linkText))
            # Get ready for JSONing
            for ref in refs:
                ref['level'] = str(ref['level'])
            p(config.printjson(refs))
        elif options.refreshData:
            config.quiet = 0
            update.updateReadonlyDataFiles()
            warn("Don't forget to bump the version number!")
    elif options.subparserName == "refs":
        config.force = True
        config.quiet = 10
        doc = Spec(inputFilename=options.infile)
        if doc.valid:
            doc.md = metadata.fromCommandLine(extras, doc)
            doc.preprocess()
            rm = doc.refs
        else:
            rm = ReferenceManager()
            rm.initializeRefs()
        if options.text:
            options.text = unicode(options.text, encoding="utf-8")
        refs = rm.queryAllRefs(text=options.text, linkFor=options.linkFor, linkType=options.linkType, status=options.status, spec=options.spec, exact=options.exact)
        if config.printMode == "json":
            p(json.dumps(refs, indent=2, default=config.getjson))
        else:
            p(config.printjson(refs))
    elif options.subparserName == "issues-list":
        from . import issuelist as il
        if options.printTemplate:
            il.printHelpMessage()
        else:
            il.printIssueList(options.infile, options.outfile)
    elif options.subparserName == "source":
        if not options.bigText:  # If no options are given, do all options.
            options.bigText = True
        if options.bigText:
            from . import fonts
            font = fonts.Font()
            fonts.replaceComments(font=font, inputFilename=options.infile, outputFilename=options.outfile)
    elif options.subparserName == "test":
        if options.rebase:
            test.rebase(options.testFiles)
        else:
            config.force = True
            config.quiet = 2
            result = test.runAllTests(Spec, options.testFiles)
            sys.exit(0 if result else 1)
    elif options.subparserName == "profile":
        root = "--root=\"{0}\"".format(options.root) if options.root else ""
        leaf = "--leaf=\"{0}\"".format(options.leaf) if options.leaf else ""
        if options.svgFile:
            os.system("python -m cProfile -o stat.prof ~/bikeshed/bikeshed.py -f spec && gprof2dot -f pstats --skew=.0001 {root} {leaf} stat.prof | dot -Tsvg -o {svg} && rm stat.prof".format(root=root, leaf=leaf, svg=options.svgFile))
        else:
            os.system("python -m cProfile -o /tmp/stat.prof ~/bikeshed/bikeshed.py -f spec && gprof2dot -f pstats --skew=.0001 {root} {leaf} /tmp/stat.prof | xdot &".format(root=root, leaf=leaf))
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

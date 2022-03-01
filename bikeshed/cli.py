import argparse
import json
import os
import sys

from . import config, constants, update, messages as m


def main():
    # Hack around argparse's lack of optional subparsers
    if len(sys.argv) == 1:
        sys.argv.append("spec")

    try:
        with open(config.scriptPath("..", "semver.txt"), encoding="utf-8") as fh:
            semver = fh.read().strip()
            semverText = f"Bikeshed v{semver}: "
    except FileNotFoundError:
        semver = "???"
        semverText = ""

    argparser = argparse.ArgumentParser(description=f"{semverText}Processes spec source files into valid HTML.")
    argparser.add_argument("--version", action="version", version=semver)
    argparser.add_argument(
        "-q",
        "--quiet",
        dest="quiet",
        action="count",
        default=0,
        help="Silences one level of message, least-important first.",
    )
    argparser.add_argument(
        "-s",
        "--silent",
        dest="silent",
        action="store_true",
        help="Shorthand for 'as many -q as you need to shut it up'",
    )
    argparser.add_argument(
        "-f",
        "--force",
        dest="errorLevel",
        action="store_const",
        const="nothing",
        help="Force the preprocessor to run to completion; fatal errors don't stop processing.",
    )
    argparser.add_argument(
        "-d",
        "--dry-run",
        dest="dryRun",
        action="store_true",
        help="Prevents the processor from actually saving anything to disk, but otherwise fully runs.",
    )
    argparser.add_argument(
        "-a",
        "--ascii-only",
        dest="asciiOnly",
        action="store_true",
        help="Force all Bikeshed messages to be ASCII-only.",
    )
    argparser.add_argument(
        "--print",
        dest="printMode",
        action="store",
        default=None,
        help="Print mode. Options are 'plain' (just text), 'console' (colored with console color codes), 'markup', and 'json'. Defaults to 'console'.",
    )
    argparser.add_argument(
        "--die-on",
        dest="errorLevel",
        choices=["nothing", "fatal", "link-error", "warning", "everything"],
        help="Determines what sorts of errors cause Bikeshed to die (quit immediately with an error status code). Default is 'fatal'; the -f flag is a shorthand for 'nothing'",
    )
    argparser.add_argument(
        "--allow-nonlocal-files",
        dest="allowNonlocalFiles",
        action="store_true",
        help="Allows Bikeshed to see/include files from folders higher than the one your source document is in.",
    )
    argparser.add_argument(
        "--allow-execute",
        dest="allowExecute",
        action="store_true",
        help="Allow some features to execute arbitrary code from outside the Bikeshed codebase.",
    )

    subparsers = argparser.add_subparsers(title="Subcommands", dest="subparserName")

    specParser = subparsers.add_parser("spec", help="Process a spec source file into a valid output file.")
    specParser.add_argument("infile", nargs="?", default=None, help="Path to the source file.")
    specParser.add_argument("outfile", nargs="?", default=None, help="Path to the output file.")
    specParser.add_argument(
        "--debug",
        dest="debug",
        action="store_true",
        help="Switches on some debugging tools. Don't use for production!",
    )
    specParser.add_argument(
        "--gh-token",
        dest="ghToken",
        nargs="?",
        help="GitHub access token. Useful to avoid API rate limits. Generate tokens: https://github.com/settings/tokens.",
    )
    specParser.add_argument(
        "--byos",
        dest="byos",
        action="store_true",
        help="Bring-Your-Own-Spec: turns off all the Bikeshed auto-niceties, so you can piecemeal its features into your existing doc instead. Experimental, let me know if things get crashy or weird.",
    )
    specParser.add_argument(
        "-l",
        "--line-numbers",
        dest="lineNumbers",
        action="store_true",
        help="Hacky support for outputting line numbers on all error messages. Disables output, as this is hacky and might mess up your source.",
    )

    echidnaParser = subparsers.add_parser(
        "echidna",
        help="Process a spec source file into a valid output file and publish it according to certain automatic protocols.",
    )
    echidnaParser.add_argument("infile", nargs="?", default=None, help="Path to the source file.")
    echidnaParser.add_argument(
        "--gh-token",
        dest="ghToken",
        nargs="?",
        help="GitHub access token. Useful to avoid API rate limits. Generate tokens: https://github.com/settings/tokens.",
    )
    echidnaParser.add_argument("--u", dest="un", metavar="USERNAME", required=False, help="W3C username.")
    echidnaParser.add_argument("--p", dest="pw", metavar="PASSWORD", required=False, help="W3C password.")
    echidnaParser.add_argument(
        "--decision",
        dest="decision",
        metavar="DECISION_URL",
        required=False,
        help="URL recording the decision to publish.",
    )
    echidnaParser.add_argument(
        "--editorial",
        dest="editorial",
        action="store_true",
        required=False,
        help="Flags update as editorial.",
    )
    echidnaParser.add_argument(
        "--cc",
        dest="cc",
        metavar="EMAIL",
        required=False,
        help="Comma-separated list of email addresses to ping with the publication status when complete.",
    )
    echidnaParser.add_argument(
        "--additional-directories",
        dest="additionalDirectories",
        required=False,
        nargs="*",
        help="Directories to bundle in the tar file. Defaults to examples/, diagrams/, and images/.",
    )
    echidnaParser.add_argument(
        "--self-contained",
        dest="selfContained",
        action="store_true",
        help="The spec is self-contained, do not bundle any extra directories in the tar file.",
    )
    echidnaParser.add_argument("--just-tar", dest="justTar", action="store_true")

    watchParser = subparsers.add_parser(
        "watch",
        help="Process a spec source file into a valid output file, automatically rebuilding when it changes.",
    )
    watchParser.add_argument("infile", nargs="?", default=None, help="Path to the source file.")
    watchParser.add_argument("outfile", nargs="?", default=None, help="Path to the output file.")
    watchParser.add_argument(
        "--gh-token",
        dest="ghToken",
        nargs="?",
        help="GitHub access token. Useful to avoid API rate limits. Generate tokens: https://github.com/settings/tokens.",
    )
    watchParser.add_argument(
        "--byos",
        dest="byos",
        action="store_true",
        help="Bring-Your-Own-Spec: turns off all the Bikeshed auto-niceties, so you can piecemeal its features into your existing doc instead. Experimental, let me know if things get crashy or weird.",
    )

    serveParser = subparsers.add_parser("serve", help="Identical to 'watch', but also serves the folder on localhost.")
    serveParser.add_argument("infile", nargs="?", default=None, help="Path to the source file.")
    serveParser.add_argument("outfile", nargs="?", default=None, help="Path to the output file.")
    serveParser.add_argument(
        "--port",
        dest="port",
        nargs="?",
        default="8000",
        help="Specify the port to serve it over.",
    )
    serveParser.add_argument(
        "--localhost",
        dest="localhost",
        action="store_true",
        help="Only allow connections from localhost.",
    )
    serveParser.add_argument(
        "--gh-token",
        dest="ghToken",
        nargs="?",
        help="GitHub access token. Useful to avoid API rate limits. Generate tokens: https://github.com/settings/tokens.",
    )
    serveParser.add_argument(
        "--byos",
        dest="byos",
        action="store_true",
        help="Bring-Your-Own-Spec: turns off all the Bikeshed auto-niceties, so you can piecemeal its features into your existing doc instead. Experimental, let me know if things get crashy or weird.",
    )

    updateParser = subparsers.add_parser(
        "update",
        help="Update supporting files (those in /spec-data).",
        epilog="If no options are specified, everything is downloaded.",
    )
    updateParser.add_argument(
        "--skip-manifest",
        dest="force",
        action="store_true",
        help="Forces Bikeshed to do a full update manually, rather than using the manifest to get the preprocessed update (which can be several minutes old).",
    )
    updateParser.add_argument("--anchors", action="store_true", help="Download crossref anchor data.")
    updateParser.add_argument("--backrefs", action="store_true", help="Download link backref data.")
    updateParser.add_argument("--biblio", action="store_true", help="Download biblio data.")
    updateParser.add_argument("--boilerplate", action="store_true", help="Download boilerplate files.")
    updateParser.add_argument("--caniuse", action="store_true", help="Download Can I Use... data.")
    updateParser.add_argument("--mdn", action="store_true", help="Download MDN Spec Links... data.")
    updateParser.add_argument(
        "--link-defaults",
        dest="linkDefaults",
        action="store_true",
        help="Download link default data.",
    )
    updateParser.add_argument(
        "--test-suites",
        dest="testSuites",
        action="store_true",
        help="Download test suite data.",
    )
    updateParser.add_argument(
        "--languages",
        dest="languages",
        action="store_true",
        help="Download language/translation data.",
    )
    updateParser.add_argument(
        "--wpt",
        dest="wpt",
        action="store_true",
        help="Download web-platform-tests data.",
    )

    issueParser = subparsers.add_parser(
        "issues-list",
        help="Process a plain-text issues file into HTML. Call with no args to see an example input text.",
    )
    issueParser.add_argument(
        "-t",
        dest="printTemplate",
        action="store_true",
        help="Output example Issues List template.",
    )
    issueParser.add_argument("infile", nargs="?", default=None, help="Path to the plain-text issue file.")
    issueParser.add_argument(
        "outfile",
        nargs="?",
        default=None,
        help="Path to the output file. Default is file of the same name as input, with .html.",
    )

    debugParser = subparsers.add_parser("debug", help="Run various debugging commands.")
    debugParser.add_argument("infile", nargs="?", default=None, help="Path to the source file.")
    debugCommands = debugParser.add_mutually_exclusive_group(required=True)
    debugCommands.add_argument(
        "--print-exports",
        dest="printExports",
        action="store_true",
        help="Prints those terms that will be exported for cross-ref purposes.",
    )
    debugCommands.add_argument("--print", dest="code", help="Runs the specified code and prints it.")
    debugCommands.add_argument(
        "--print-json",
        dest="jsonCode",
        help="Runs the specified code and prints it as formatted JSON.",
    )
    debugCommands.add_argument(
        "--refresh-data",
        dest="refreshData",
        action="store_true",
        help="Clobbers the readonly data files with the mutable ones.",
    )
    debugCommands.add_argument(
        "--print-metadata",
        dest="printMetadata",
        action="store_true",
        help="Prints all the metadata parsed for the spec as JSON. Top-level keys are presented in increasing order of importance; second-level keys are in order of first appearance in each context.",
    )

    refParser = subparsers.add_parser("refs", help="Search Bikeshed's ref database.")
    refParser.add_argument("infile", nargs="?", default=None, help="Path to the source file.")
    refParser.add_argument("--text", dest="text", default=None)
    refParser.add_argument("--type", dest="linkType", default=None)
    refParser.add_argument("--for", dest="linkFor", default=None)
    refParser.add_argument("--spec", dest="spec", default=None)
    refParser.add_argument("--status", dest="status", default=None)
    refParser.add_argument(
        "--exact",
        dest="exact",
        action="store_true",
        help="Only search for the exact text provided; don't apply Bikeshed's automatic conjugation help for plurals/etc.",
    )
    refParser.add_argument(
        "--latest-only",
        dest="latestOnly",
        action="store_true",
        help="Apply Bikeshed's logic for only returning the latest version of a given ref when it exists in multiple levels of a spec.",
    )

    sourceParser = subparsers.add_parser("source", help="Tools for formatting the *source* document.")
    sourceParser.add_argument(
        "--big-text",
        dest="bigText",
        action="store_true",
        help="Finds HTML comments containing 'Big Text: foo' and turns them into comments containing 'foo' in big text.",
    )
    sourceParser.add_argument("infile", nargs="?", default=None, help="Path to the source file.")
    sourceParser.add_argument("outfile", nargs="?", default=None, help="Path to the output file.")

    testParser = subparsers.add_parser("test", help="Tools for running Bikeshed's testsuite.")
    testParser.add_argument(
        "--rebase",
        default=False,
        action="store_true",
        help="Rebase the specified files.",
    )
    testParser.add_argument(
        "--manual-only",
        dest="manualOnly",
        default=False,
        action="store_true",
        help="Skip testing the real-world files in the repo, and only run the manually-written ones.",
    )
    testParser.add_argument(
        "testFiles",
        default=[],
        metavar="FILE",
        nargs="*",
        help="Run these tests. If called with no args, tests everything.",
    )

    profileParser = subparsers.add_parser(
        "profile",
        help="Profiling Bikeshed. Needs graphviz, gprof2dot, and xdot installed.",
    )
    profileParser.add_argument(
        "--root",
        dest="root",
        default=None,
        metavar="ROOTFUNC",
        help="Prune the graph to start with the specified root node.",
    )
    profileParser.add_argument(
        "--leaf",
        dest="leaf",
        default=None,
        metavar="LEAFFUNC",
        help="Prune the graph to only show ancestors of the specified leaf node.",
    )
    profileParser.add_argument(
        "--svg",
        dest="svgFile",
        default=None,
        help="Save the graph to a specified SVG file, rather than outputting with xdot immediately.",
    )

    subparsers.add_parser("template", help="Outputs a skeleton .bs file for you to start with.")

    wptParser = subparsers.add_parser("wpt", help="Tools for writing Web Platform Tests.")
    wptParser.add_argument(
        "--template",
        default=False,
        action="store_true",
        help="Outputs a skeleton WPT file for you to start with.",
    )

    options, extras = argparser.parse_known_args()

    constants.quiet = options.quiet
    if options.silent:
        constants.quiet = float("infinity")
    constants.setErrorLevel(options.errorLevel)
    constants.dryRun = options.dryRun
    constants.asciiOnly = options.asciiOnly
    if options.printMode is None:
        if "NO_COLOR" in os.environ or os.environ.get("TERM") == "dumb":
            constants.printMode = "plain"
        else:
            constants.printMode = "console"
    else:
        constants.printMode = options.printMode
    constants.chroot = not options.allowNonlocalFiles
    constants.executeCode = options.allowExecute

    update.fixupDataFiles()
    if options.subparserName == "update":
        handleUpdate(options)
    elif options.subparserName == "spec":
        handleSpec(options, extras)
    elif options.subparserName == "echidna":
        handleEchidna(options, extras)
    elif options.subparserName == "watch":
        handleWatch(options, extras)
    elif options.subparserName == "serve":
        handleServe(options, extras)
    elif options.subparserName == "debug":
        handleDebug(options, extras)
    elif options.subparserName == "refs":
        handleRefs(options, extras)
    elif options.subparserName == "issues-list":
        handleIssuesList(options)
    elif options.subparserName == "source":
        handleSource(options)
    elif options.subparserName == "test":
        handleTest(options, extras)
    elif options.subparserName == "profile":
        handleProfile(options)
    elif options.subparserName == "template":
        handleTemplate()
    elif options.subparserName == "wpt":
        handleWpt(options)


def handleUpdate(options):
    update.update(
        anchors=options.anchors,
        backrefs=options.backrefs,
        biblio=options.biblio,
        boilerplate=options.boilerplate,
        caniuse=options.caniuse,
        mdn=options.mdn,
        linkDefaults=options.linkDefaults,
        testSuites=options.testSuites,
        languages=options.languages,
        wpt=options.wpt,
        dryRun=constants.dryRun,
        force=options.force,
    )


def handleSpec(options, extras):
    from . import metadata
    from .Spec import Spec

    doc = Spec(
        inputFilename=options.infile,
        debug=options.debug,
        token=options.ghToken,
        lineNumbers=options.lineNumbers,
    )
    doc.mdCommandLine = metadata.fromCommandLine(extras)
    if options.byos:
        doc.mdCommandLine.addData("Group", "byos")
    doc.preprocess()
    doc.finish(outputFilename=options.outfile)


def handleEchidna(options, extras):
    from . import metadata, publish
    from .Spec import Spec

    doc = Spec(inputFilename=options.infile, token=options.ghToken)
    doc.mdCommandLine = metadata.fromCommandLine(extras)
    doc.mdCommandLine.addData("Prepare For TR", "yes")
    doc.preprocess()
    addDirs = [] if options.selfContained else options.additionalDirectories
    if options.justTar:
        publish.prepareTar(doc, visibleTar=True, additionalDirectories=addDirs)
    else:
        publish.publishEchidna(
            doc,
            username=options.un,
            password=options.pw,
            decision=options.decision,
            additionalDirectories=addDirs,
            cc=options.cc,
            editorial=options.editorial,
        )


def handleWatch(options, extras):
    from . import metadata
    from .Spec import Spec

    # Can't have an error killing the watcher
    constants.setErrorLevel("nothing")
    doc = Spec(inputFilename=options.infile, token=options.ghToken)
    doc.mdCommandLine = metadata.fromCommandLine(extras)
    if options.byos:
        doc.mdCommandLine.addData("Group", "byos")
    doc.watch(outputFilename=options.outfile)


def handleServe(options, extras):
    from . import metadata
    from .Spec import Spec

    constants.setErrorLevel("nothing")
    doc = Spec(inputFilename=options.infile, token=options.ghToken)
    doc.mdCommandLine = metadata.fromCommandLine(extras)
    if options.byos:
        doc.mdCommandLine.addData("Group", "byos")
    doc.watch(outputFilename=options.outfile, port=int(options.port))


def handleDebug(options, extras):
    from . import metadata
    from .Spec import Spec

    constants.setErrorLevel("nothing")
    constants.quiet = 2
    if options.printExports:
        doc = Spec(inputFilename=options.infile)
        doc.mdCommandLine = metadata.fromCommandLine(extras)
        doc.preprocess()
        doc.printTargets()
    elif options.jsonCode:
        doc = Spec(inputFilename=options.infile)
        doc.mdCommandLine = metadata.fromCommandLine(extras)
        doc.preprocess()
        exec(f"print(config.printjson({options.jsonCode}))")
    elif options.code:
        doc = Spec(inputFilename=options.infile)
        doc.mdCommandLine = metadata.fromCommandLine(extras)
        doc.preprocess()
        exec(f"print({options.code})")
    elif options.refreshData:
        constants.quiet = 0
        update.updateReadonlyDataFiles()
        m.warn("Don't forget to bump the version number!")
    elif options.printMetadata:
        doc = Spec(inputFilename=options.infile)
        doc.mdCommandLine = metadata.fromCommandLine(extras)
        doc.preprocess()
        md = {
            "defaults.include": doc.mdDefaults.allData,
            "computed-metadata.include": doc.mdOverridingDefaults.allData,
            "document": doc.mdDocument.allData,
            "command-line": doc.mdCommandLine.allData,
        }
        print(json.dumps(md, indent=2, default=config.getjson))


def handleRefs(options, extras):
    from . import metadata
    from .refs.ReferenceManager import ReferenceManager
    from .Spec import Spec

    constants.setErrorLevel("nothing")
    constants.quiet = 10
    doc = Spec(inputFilename=options.infile)
    if doc.valid:
        doc.mdCommandLine = metadata.fromCommandLine(extras)
        doc.preprocess()
        rm = doc.refs
    else:
        rm = ReferenceManager()
        rm.initializeRefs()
    if options.text:
        options.text = options.text
    refs = rm.queryAllRefs(
        text=options.text,
        linkFor=options.linkFor,
        linkType=options.linkType,
        status=options.status,
        spec=options.spec,
        latestOnly=options.latestOnly,
        exact=options.exact,
    )
    if constants.printMode == "json":
        m.p(json.dumps(refs, indent=2, default=config.getjson))
    else:
        m.p(config.printjson(refs))


def handleIssuesList(options):
    from . import issuelist

    if options.printTemplate:
        issuelist.printHelpMessage()
    else:
        issuelist.printIssueList(options.infile, options.outfile)


def handleSource(options):
    if not options.bigText:  # If no options are given, do all options.
        options.bigText = True
    if options.bigText:
        from . import fonts

        font = fonts.Font()
        fonts.replaceComments(font=font, inputFilename=options.infile, outputFilename=options.outfile)


def handleTest(options, extras):
    from . import metadata, test

    md = metadata.fromCommandLine(extras)
    constants.setErrorLevel("nothing")
    constants.quiet = 100
    if options.rebase:
        test.rebase(options.testFiles, md=md)
    else:
        result = test.runAllTests(options.testFiles, manualOnly=options.manualOnly, md=md)
        sys.exit(0 if result else 1)


def handleProfile(options):
    root = f'--root="{options.root}"' if options.root else ""
    leaf = f'--leaf="{options.leaf}"' if options.leaf else ""
    if options.svgFile:
        os.system(
            "time python -m cProfile -o stat.prof -m bikeshed -f spec && gprof2dot -f pstats --skew=.0001 {root} {leaf} stat.prof | dot -Tsvg -o {svg} && rm stat.prof".format(
                root=root, leaf=leaf, svg=options.svgFile
            )
        )
    else:
        os.system(
            "time python -m cProfile -o /tmp/stat.prof -m bikeshed -f spec && gprof2dot -f pstats --skew=.0001 {root} {leaf} /tmp/stat.prof | xdot &".format(
                root=root, leaf=leaf
            )
        )


def handleTemplate():
    m.p(
        """<pre class='metadata'>
Title: Your Spec Title
Shortname: your-spec
Level: 1
Status: w3c/UD
Group: WGNAMEORWHATEVER
URL: http://example.com/url-this-spec-will-live-at
Editor: Your Name, Your Company http://example.com/your-company, your-email@example.com, http://example.com/your-personal-website
Abstract: A short description of your spec, one or two sentences.
</pre>

Introduction {#intro}
=====================

Introduction here.
"""
    )


def handleWpt(options):
    if options.template:
        m.p(
            """
<!DOCTYPE html>
<meta charset=utf-8>
<title>window.offscreenBuffering</title>
<link rel=author title="AUTHOR NAME HERE" href="mailto:AUTHOR EMAIL HERE">
<link rel=help href="LINK TO ROUGHLY WHAT'S BEING TESTED HERE">
<script src="/resources/testharness.js"></script>
<script src="/resources/testharnessreport.js"></script>
<script>
/* Choose the test type you want: */


/* Standard, synchronous test */
test(function() {
    /* test code here */
}, "TEST NAME HERE / SHORT DESCRIPTION PHRASE");


/* Async test */
let t = async_test("TEST NAME HERE / SHORT DESCRIPTION PHRASE");
somethingWithACallback( function(){ t.step(()=>{ /* test code here */}) );
something.addEventListener('foo', t.step_func(()=>{ /* test code here */}));
t.done(); // when all tests are finished running
// or call the following if there's only one test, automatically does .done() for you
something.addEventListener('foo', t.step_func_done(()=>{ /* test code here */}));


/* Promise test */
promise_test(function(){
    return somePromiseFunc().then(()=>{ /* test code here */ });
}, "TEST NAME HERE / SHORT DESCRIPTION PHRASE");
// auto-finishes when the returned promise fulfills
// or if promise should reject:
promise_test(function(t){
    return promise_rejects(t, new ExpectedError(), somePromiseCode());
}, "TEST NAME HERE / SHORT DESCRIPTION PHRASE");


/* "test code here" Asserts */
// Only use inside of /* test code here */ regions
assert_true(VALUE HERE, "TEST DESCRIPTION");
assert_equals(ACTUAL VALUE HERE, EXPECTED VALUE HERE, "TEST DESCRIPTION");
// lots more at http://web-platform-tests.org/writing-tests/testharness-api.html#list-of-assertions
</script>
"""
        )

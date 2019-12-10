# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals
import io
import json
import os
from collections import OrderedDict
from . import config
from .htmlhelpers import *  # noqa


def addMdnPanels(doc):
    if not doc.md.includeMdnPanels:
        return

    mdnBaseUrl = "https://developer.mozilla.org/en-US/docs/Web/"
    bcdBaseUrl = "https://github.com/mdn/browser-compat-data/blob/master/"

    browsersProvidingCurrentEngines = ["firefox", "safari", "chrome"]
    browsersWithBorrowedEngines = ["opera", "edge_blink"]
    browsersWithRetiredEngines = ["edge", "ie"]
    browsersForMobileDevices = ["firefox_android", "safari_ios",
                                "chrome_android", "webview_android",
                                "samsunginternet_android", "opera_android"]

    # BCD/mdn-spec-links shortnames to full names
    nameFromCodeName = {
        "chrome": "Chrome",
        "chrome_android": "Chrome for Android",
        "edge": "Edge (Legacy)",
        "edge_blink": "Edge",
        "firefox": "Firefox",
        "firefox_android": "Firefox for Android",
        "ie": "IE",
        "nodejs": "Node.js",
        "opera": "Opera",
        "opera_android": "Opera Mobile",
        "safari": "Safari",
        "samsunginternet_android": "Samsung Internet",
        "safari_ios": "iOS Safari",
        "webview_android": "Android WebView"
    }

    doc.extraScripts["script-mdn-anno"] = '''
        window.addEventListener("load", function(){
            var annos = [].slice.call(document.querySelectorAll(".mdn-anno"));
            for(var i = 0; i < annos.length; i++) {
                var anno = annos[i];
                id = anno.getAttribute("data-dfn-id");
                var dfn = document.querySelector("#" + id);
                if (dfn !== null) {
                    var rect = dfn.getBoundingClientRect(id);
                    anno.style.top = (window.scrollY + rect.top) + "px";
                    /* See https://domspec.herokuapp.com/#dom-event-cancelable
                     * for an example of a spec that defines multiple terms in
                     * the same sentence on the same line. In such cases, we
                     * need to offset the vertical positioning of each Nth anno
                     * for that term, to prevent the annos from being placed
                     * exactly on top of the previous ones at that position. */
                    var top = anno.style.top;
                    var offset = 10 * (document.querySelectorAll("[style='top: " + top + ";']").length - 1)
                    anno.style.top = (Number(top.slice(0, -2)) + offset) + "px";
                } else {
                    console.error('MDN anno references non-existent element ID "%s".%o', id, anno);
                }
            }
        });
        document.body.addEventListener("click", function(e) {
            parentnode = e.target.parentNode;
            if (!parentnode) {
                return;
            }
            if(parentnode.classList.contains("mdn-anno-btn")) {
                parentnode.parentNode.classList.toggle("wrapped");
            }
        });'''  # noqa

    # FIXME: Update the Edge logo URL when we get
    #       https://github.com/whatwg/whatwg.org/pull/267 resolved
    doc.extraStyles["style-mdn-anno"] = '''
        @media (max-width: 767px) { .mdn-anno { opacity: .1 } }
        .mdn-anno { font: 1em sans-serif; padding: 0.3em; position: absolute; z-index: 8; top: auto; right: 0.3em; background: #EEE; color: black; box-shadow: 0 0 3px #999; overflow: hidden; border-collapse: initial; border-spacing: initial; min-width: 9em; max-width: min-content; overflow-wrap: normal; word-wrap: normal; hyphens: none}
        .mdn-anno:not(.wrapped) { opacity: 1}
        .mdn-anno:hover { z-index: 9 }
        .mdn-anno.wrapped { min-width: 0 }
        .mdn-anno.wrapped > :not(button) { display: none; }
        .mdn-anno > .mdn-anno-btn { cursor: pointer; border: none; color: #000; background: transparent; margin: -8px; outline: none; }
        .mdn-anno > .mdn-anno-btn > .less-than-two-engines-flag { color: red; padding-right: 2px; }
        .mdn-anno > .mdn-anno-btn > .all-engines-flag { color: green; padding-right: 2px; }
        .mdn-anno > .mdn-anno-btn > span { color: #fff; background-color: #000; font-weight: normal; font-family: zillaslab, Palatino, "Palatino Linotype", serif; padding: 2px 3px 0px 3px; line-height: 1.3em; vertical-align: top; }
        .mdn-anno > .feature { margin-top: 2px; }
        .mdn-anno > .feature:not(:first-of-type) { border-top: 1px solid #999; margin-top: 6px; padding-top: 2px; }
        .mdn-anno > .feature > .less-than-two-engines-text { color: red }
        .mdn-anno > .feature > .all-engines-text { color: green }
        .mdn-anno > .feature > p { font-size: .75em; margin-top: 6px; margin-bottom: 0; }
        .mdn-anno > .feature > p + p { margin-top: 3px; }
        .mdn-anno > .feature > .support { display: block; font-size: 0.6em; margin: 0; padding: 0; margin-top: 2px }
        .mdn-anno > .feature > .support + div { padding-top: 0.5em; }
        .mdn-anno > .feature > .support > hr { display: block; border-top: 1px dotted #999; padding: 3px 0px 0px 0px; margin: 2px 3px 0px 3px; }
        .mdn-anno > .feature > .support > hr::before { content: ""; }
        .mdn-anno > .feature > .support > span { padding: 0.2em 0; display: block; display: table; }
        .mdn-anno > .feature > .support > span.no { color: #CCCCCC; filter: grayscale(100%); }
        .mdn-anno > .feature > .support > span.no::before { opacity: 0.5; }
        .mdn-anno > .feature > .support > span:first-of-type { padding-top: 0.5em; }
        .mdn-anno > .feature > .support > span > span { padding: 0 0.5em; display: table-cell; vertical-align: top; }
        .mdn-anno > .feature > .support > span > span:first-child { width: 100%; }
        .mdn-anno > .feature > .support > span > span:last-child { width: 100%; white-space: pre; padding: 0; }
        .mdn-anno > .feature > .support > span::before { content: ' '; display: table-cell; min-width: 1.5em; height: 1.5em; background: no-repeat center center; background-size: contain; text-align: right; font-size: 0.75em; font-weight: bold; }
        .mdn-anno > .feature > .support > .chrome_android::before { background-image: url(https://resources.whatwg.org/browser-logos/chrome.svg); }
        .mdn-anno > .feature > .support > .firefox_android::before { background-image: url(https://resources.whatwg.org/browser-logos/firefox.png); }
        .mdn-anno > .feature > .support > .chrome::before { background-image: url(https://resources.whatwg.org/browser-logos/chrome.svg); }
        .mdn-anno > .feature > .support > .edge_blink::before { background-image: url(https://raw.githubusercontent.com/alrra/browser-logos/master/src/edge/edge_16x16.png); }
        .mdn-anno > .feature > .support > .edge::before { background-image: url(https://resources.whatwg.org/browser-logos/edge.svg); }
        .mdn-anno > .feature > .support > .firefox::before { background-image: url(https://resources.whatwg.org/browser-logos/firefox.png); }
        .mdn-anno > .feature > .support > .ie::before { background-image: url(https://resources.whatwg.org/browser-logos/ie.png); }
        .mdn-anno > .feature > .support > .safari_ios::before { background-image: url(https://resources.whatwg.org/browser-logos/safari-ios.svg); }
        .mdn-anno > .feature > .support > .nodejs::before { background-image: url(https://nodejs.org/static/images/favicons/favicon.ico); }
        .mdn-anno > .feature > .support > .opera_android::before { background-image: url(https://resources.whatwg.org/browser-logos/opera.svg); }
        .mdn-anno > .feature > .support > .opera::before { background-image: url(https://resources.whatwg.org/browser-logos/opera.svg); }
        .mdn-anno > .feature > .support > .safari::before { background-image: url(https://resources.whatwg.org/browser-logos/safari.png); }
        .mdn-anno > .feature > .support > .samsunginternet_android::before { background-image: url(https://resources.whatwg.org/browser-logos/samsung.svg); }
        .mdn-anno > .feature > .support > .webview_android::before { background-image: url(https://resources.whatwg.org/browser-logos/android-webview.png); }
        .name-slug-mismatch { color: red }
        '''  # noqa
    charactersDisallowedInSelectors = "!\"#$%&'()*+,./:;<=>?@[\]^`{|}~"

    try:
        # TODO: If may turn out that for some specs, in order to make Bikeshed
        # match the right filename from https://github.com/w3c/mdn-spec-links,
        # we need to add an option for controlling whether or not it looks for
        # a version-numbered filename.
        specShortname = doc.md.shortname
        vSpecShortname = doc.md.vshortname
        p = os.path.join(config.scriptPath("spec-data", "mdnspeclinks",
                                           specShortname + ".json"))
        pV = os.path.join(config.scriptPath("spec-data", "mdnspeclinks",
                                            vSpecShortname + ".json"))
        p = pV if os.path.exists(pV) else p
        with io.open(p, "r", encoding="utf-8") as fh:
            data = json.loads(unicode(fh.read()), encoding="utf-8",
                              object_pairs_hook=OrderedDict)
            for elementID in data.keys():
                # Some specs have IDs with characters not allowed in selectors;
                # e.g., https://xhr.spec.whatwg.org/#the-abort()-method
                escapedElementID = elementID
                # FIXME: There must be a more efficient/idiomatic way to do this
                for char in elementID:
                    if char in charactersDisallowedInSelectors:
                        escapedElementID = \
                            escapedElementID.replace(char, "\\" + char)
                # TODO: This find() is expensive, but if we add an anno to the
                # document with a reference to an ID that doesn't actually exist
                # in the document, the anno won't actually get displayed next to
                # whatever feature in the spec it's intended to annotate...
                features = data[elementID]
                anno = E.aside({"class": "mdn-anno wrapped", "data-deco": ""})
                mdnButton = E.button({"class": "mdn-anno-btn"})
                mdnLogo = E.span("MDN")
                appendChild(anno, mdnButton)
                anno.set("data-dfn-id", escapedElementID)
                appendChild(doc.body, anno)
                lessThanTwoEngines = 0
                onlyTwoEngines = 0
                allEngines = 0
                for feature in features:
                    if find("#" + escapedElementID, doc) is None:
                        mdnSuggest = ""
                        if "slug" in feature:
                            mdnSuggest = " Update " + mdnBaseUrl \
                                + feature["slug"] + " Specifications table?"
                        warn("No \"{0}\" ID found." + mdnSuggest, elementID)
                        continue
                    if "engines" in feature:
                        engines = feature["engines"]
                        if engines < 2:
                            lessThanTwoEngines = lessThanTwoEngines + 1
                        elif engines == 2:
                            onlyTwoEngines = onlyTwoEngines + 1
                        elif engines >= len(browsersProvidingCurrentEngines):
                            allEngines = allEngines + 1l
                    featureDiv = mdnPanelFor(feature, mdnBaseUrl, bcdBaseUrl,
                                             nameFromCodeName,
                                             browsersProvidingCurrentEngines,
                                             browsersWithBorrowedEngines,
                                             browsersWithRetiredEngines,
                                             browsersForMobileDevices)
                    appendChild(anno, featureDiv)
                if lessThanTwoEngines > 0:
                    appendChild(mdnButton,
                                E.b({"class": "less-than-two-engines-flag",
                                     "title": "This feature is in less than" +
                                     " two current engines."}, u"\u26A0"))
                elif allEngines > 0 \
                        and lessThanTwoEngines == 0 \
                        and onlyTwoEngines == 0:
                    appendChild(mdnButton,
                                E.b({"class": "all-engines-flag",
                                     "title": "This feature is in" +
                                     " all current engines."}, u"\u2714"))
                appendChild(mdnButton, mdnLogo)
    except Exception as e:
        warn("Couldn't load MDN Spec Links data for this spec.\n{0}", e)
        return


def addSupportRow(browserCodeName, nameFromCodeName, support, supportData):
    if browserCodeName not in support:
        return
    isEdgeLegacy = True if browserCodeName == "edge" else False
    isIE = True if browserCodeName == "ie" else False
    versionAdded = None
    versionRemoved = None
    minVersion = None
    thisBrowserSupport = support[browserCodeName]
    if isinstance(thisBrowserSupport, dict):
        if "version_added" in thisBrowserSupport:
            versionAdded = thisBrowserSupport["version_added"]
        if "version_removed" in thisBrowserSupport:
            versionRemoved = thisBrowserSupport["version_removed"]
    if isinstance(thisBrowserSupport, list):
        if "version_added" in thisBrowserSupport[0]:
            versionAdded = thisBrowserSupport[0]["version_added"]
        if "version_removed" in thisBrowserSupport[0]:
            versionRemoved = thisBrowserSupport[0]["version_removed"]
    statusCode = "n"
    if versionAdded is None:
        minVersion = "?"
    elif versionAdded is False:
        minVersion = "None"
    elif versionAdded is True:
        minVersion = "Yes"
        statusCode = "y"
    else:
        if versionRemoved is None:
            statusCode = "y"
            minVersion = versionAdded + "+"
            if (isEdgeLegacy and versionAdded == "18"):
                minVersion = "18"
            if (isIE and versionAdded == "11"):
                minVersion = "11"
        else:
            statusCode = "n"
            if versionAdded is not None:
                minVersion = versionAdded + u"\u2013" + versionRemoved
            else:
                minVersion = "None"
    browserFullName = nameFromCodeName[browserCodeName]
    appendChild(supportData, browserCompatSpan(browserCodeName, browserFullName,
                                               statusCode, minVersion))


def mdnPanelFor(feature, mdnBaseUrl, bcdBaseUrl, nameFromCodeName,
                browsersProvidingCurrentEngines, browsersWithBorrowedEngines,
                browsersWithRetiredEngines, browsersForMobileDevices):
    featureDiv = E.div({"class": "feature"})
    featureName = ""
    if "name" in feature:
        featureName = feature["name"]
    if "slug" in feature:
        slug = feature["slug"]
        displaySlug = slug.split("/", 1)[1]
        title = ""
        if "summary" in feature:
            title = feature["summary"]
        mdnURL = mdnBaseUrl + slug
        nameFromSlug = slug.rsplit("/", 1)[-1]
        if featureName is not None and featureName != "" \
                and not featureName.startswith("input-") \
                and featureName != nameFromSlug:
            bcdSuggest = ""
            if "filename" in feature and feature["filename"] is not None:
                bcdSuggest = \
                    " Update %s%s file?" % (bcdBaseUrl, feature["filename"])
            warn("BCD \"{0}\" feature has mismatched MDN URL {1}." + bcdSuggest,
                 featureName, mdnURL)
            slugLink = E.a({"class": "name-slug-mismatch", "href": mdnURL,
                            "title": title}, featureName)
        else:
            slugLink = E.a({"href": mdnURL, "title": title}, displaySlug)
        slugPara = E.p(slugLink)
        appendChild(featureDiv, slugPara)
    if "engines" in feature:
        engines = feature["engines"]
        enginesPara = None
        if engines == 0:
            enginesPara = E.p({"class": "less-than-two-engines-text"},
                              "In no current engines.")
        elif engines == 1:
            enginesPara = E.p({"class": "less-than-two-engines-text"},
                              "In only one current engine.")
        elif engines >= len(browsersProvidingCurrentEngines):
            enginesPara = E.p({"class": "all-engines-text"},
                              "In all current engines.")
        if enginesPara is not None:
            appendChild(featureDiv, enginesPara)
    supportData = E.div({"class": "support"})
    appendChild(featureDiv, supportData)
    support = feature["support"]
    for browserCodeName in browsersProvidingCurrentEngines:
        addSupportRow(browserCodeName, nameFromCodeName, support, supportData)
    appendChild(supportData, E.hr())
    for browserCodeName in browsersWithBorrowedEngines:
        addSupportRow(browserCodeName, nameFromCodeName, support, supportData)
    appendChild(supportData, E.hr())
    for browserCodeName in browsersWithRetiredEngines:
        addSupportRow(browserCodeName, nameFromCodeName, support, supportData)
    appendChild(supportData, E.hr())
    for browserCodeName in browsersForMobileDevices:
        addSupportRow(browserCodeName, nameFromCodeName, support, supportData)
    if "nodejs" in support:
        appendChild(supportData, E.hr())
        addSupportRow("nodejs", nameFromCodeName, support, supportData)
    return featureDiv


def browserCompatSpan(browserCodeName, browserFullName, statusCode, minVersion):
    # browserCodeName: e.g. "chrome"
    # browserFullName: e.g. "Chrome for Android"
    statusClass = {"y": "yes", "n": "no"}[statusCode]
    outer = E.span({"class": browserCodeName + " " + statusClass})
    appendChild(outer, E.span({}, browserFullName))
    appendChild(outer, E.span({}, minVersion))
    return outer

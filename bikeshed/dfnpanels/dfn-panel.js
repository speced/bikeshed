document.addEventListener("DOMContentLoaded", ()=>{
    genAllDfnPanels();

    document.body.addEventListener("click", (e) => {
        // If not handled already, just hide all dfn panels.
        hideAllDfnPanels();
    });
});

window.addEventListener("resize", () => {
    // Pin any visible dfn panel
    queryAll(".dfn-panel.on, .dfn-panel.activated").forEach(el=>positionDfnPanel(el));
});

function genAllDfnPanels() {
    for(const panelData of Object.values(dfnPanelData)) {
        const dfnID = panelData.dfnID;
        const dfn = document.getElementById(dfnID);
        if(!dfn) {
            console.log(`Can't find dfn#${dfnID}.`, panelData);
            continue;
        }
        dfn.panelData = panelData;
        insertDfnPopupAction(dfn);
    }
}

function genDfnPanel(dfn, { dfnID, url, dfnText, refSections, external }) {
    const dfnPanel = mk.aside({
        class: "dfn-panel on",
        id: `infopanel-for-${dfnID}`,
        "data-for": dfnID,
        "aria-labelled-by":`infopaneltitle-for-${dfnID}`,
        },
        mk.span({id:`infopaneltitle-for-${dfnID}`, style:"display:none"},
            `Info about the '${dfnText}' ${external?"external":""} reference.`),
        mk.a({href:url, class:"dfn-link"}, url),
        refSections.length == 0 ? [] :
            mk.b({}, "Referenced in:"),
            mk.ul({},
                ...refSections.map(section=>
                    mk.li({},
                        ...section.refs.map((ref, refI)=>
                            [
                                mk.a({ href: `#${ref.id}` },
                                    (refI == 0) ? section.title : `(${refI + 1})`
                                ),
                                " ",
                            ]
                        ),
                    ),
                ),
            ),
        genLinkingSyntaxes(dfn),
    );

    dfnPanel.addEventListener('click', (event) => {
        if (event.target.nodeName == 'A') {
            scrollToTargetAndHighlight(event);
            pinDfnPanel(dfnPanel);
        }
        event.stopPropagation();
        refocusOnTarget(event);
    });
    dfnPanel.addEventListener('keydown', (event) => {
        if(event.keyCode == 27) { // Escape key
            hideDfnPanel({dfnPanel});
            event.stopPropagation();
            event.preventDefault();
        }
    });

    dfnPanel.dfn = dfn;
    dfn.dfnPanel = dfnPanel;
    return dfnPanel;
}



function hideAllDfnPanels() {
    // Delete the currently-active dfn panel.
    queryAll(".dfn-panel").forEach(dfnPanel=>hideDfnPanel({dfnPanel}));
}

function showDfnPanel(dfn) {
    hideAllDfnPanels(); // Only display one at a time.

    dfn.setAttribute("aria-expanded", "true");

    const dfnPanel = genDfnPanel(dfn, dfn.panelData);

    // Give the dfn a unique tabindex, and then
    // give all the tabbable panel bits successive indexes.
    let tabIndex = 100;
    dfn.tabIndex = tabIndex++;
    const tabbable = dfnPanel.querySelectorAll(":is(a, button)");
    for (const el of tabbable) {
        el.tabIndex = tabIndex++;
    }

    append(document.body, dfnPanel);
    positionDfnPanel(dfnPanel);
}

function positionDfnPanel(dfnPanel) {
    const dfn = dfnPanel.dfn;
    const dfnPos = getBounds(dfn);
    dfnPanel.style.top = dfnPos.bottom + "px";
    dfnPanel.style.left = dfnPos.left + "px";

    const panelPos = dfnPanel.getBoundingClientRect();
    const panelMargin = 8;
    const maxRight = document.body.parentNode.clientWidth - panelMargin;
    if (panelPos.right > maxRight) {
        const overflowAmount = panelPos.right - maxRight;
        const newLeft = Math.max(panelMargin, dfnPos.left - overflowAmount);
        dfnPanel.style.left = newLeft + "px";
    }
}

function pinDfnPanel(dfnPanel) {
    // Switch it to "activated" state, which pins it.
    dfnPanel.classList.add("activated");
    dfnPanel.style.position = "fixed";
    dfnPanel.style.left = null;
    dfnPanel.style.top = null;
}

function hideDfnPanel({dfn, dfnPanel}) {
    if(!dfnPanel) dfnPanel = dfn.dfnPanel;
    if(!dfn) dfn = dfnPanel.dfn;
    dfn.dfnPanel = undefined;
    dfnPanel.dfn = undefined;
    dfn.setAttribute("aria-expanded", "false");
    dfn.tabIndex = undefined;
    dfnPanel.remove()
}

function toggleDfnPanel(dfn) {
    if(dfn.dfnPanel) {
        hideDfnPanel(dfn);
    } else {
        showDfnPanel(dfn);
    }
}

function insertDfnPopupAction(dfn) {
    dfn.setAttribute('role', 'button');
    dfn.setAttribute('aria-expanded', 'false')
    dfn.tabIndex = 0;
    dfn.classList.add('has-dfn-panel');
    dfn.addEventListener('click', (event) => {
        toggleDfnPanel(dfn);
        event.stopPropagation();
    });
    dfn.addEventListener('keypress', (event) => {
        const kc = event.keyCode;
        // 32->Space, 13->Enter
        if(kc == 32 || kc == 13) {
            toggleDfnPanel(dfn);
            event.stopPropagation();
            event.preventDefault();
        }
    });
}

function refocusOnTarget(event) {
    const target = event.target;
    setTimeout(() => {
        // Refocus on the event.target element.
        // This is needed after browser scrolls to the destination.
        target.focus();
    });
}

// TODO: shared util
// Returns the root-level absolute position {left and top} of element.
function getBounds(el, relativeTo=document.body) {
    const relativeRect = relativeTo.getBoundingClientRect();
    const elRect = el.getBoundingClientRect();
    const top = elRect.top - relativeRect.top;
    const left = elRect.left - relativeRect.left;
    return {
        top,
        left,
        bottom: top + elRect.height,
        right: left + elRect.width,
    }
}

function scrollToTargetAndHighlight(event) {
    let hash = event.target.hash;
    if (hash) {
        hash = decodeURIComponent(hash.substring(1));
        const dest = document.getElementById(hash);
        if (dest) {
            dest.classList.add('highlighted');
            setTimeout(() => dest.classList.remove('highlighted'), 1000);
        }
    }
}

// Functions, divided by link type, that wrap an autolink's
// contents with the appropriate outer syntax.
// Alternately, a string naming another type they format
// the same as.
function needsFor(type) {
    switch(type) {
        case "descriptor":
        case "value":
        case "element-attr":
        case "attr-value":
        case "element-state":
        case "method":
        case "constructor":
        case "argument":
        case "attribute":
        case "const":
        case "dict-member":
        case "event":
        case "enum-value":
        case "stringifier":
        case "serializer":
        case "iterator":
        case "maplike":
        case "setlike":
        case "state":
        case "mode":
        case "context":
        case "facet": return true;

        default: return false;
    }
}
function refusesFor(type) {
    switch(type) {
        case "property":
        case "element":
        case "interface":
        case "namespace":
        case "callback":
        case "dictionary":
        case "enum":
        case "exception":
        case "typedef":
        case "http-header":
        case "permission": return true;

        default: return false;
    }
}
function linkFormatterFromType(type) {
    switch(type) {
        case 'scheme':
        case 'permission':
        case 'dfn': return (text) => `[=${text}=]`;

        case 'abstract-op': return (text) => `[\$${text}\$]`;

        case 'function':
        case 'at-rule':
        case 'selector':
        case 'value': return (text) => `''${text}''`;

        case 'http-header': return (text) => `[:${text}:]`;

        case 'interface':
        case 'constructor':
        case 'method':
        case 'argument':
        case 'attribute':
        case 'callback':
        case 'dictionary':
        case 'dict-member':
        case 'enum':
        case 'enum-value':
        case 'exception':
        case 'const':
        case 'typedef':
        case 'stringifier':
        case 'serializer':
        case 'iterator':
        case 'maplike':
        case 'setlike':
        case 'extended-attribute':
        case 'event':
        case 'idl': return (text) => `{{${text}}}`;

        case 'element-state':
        case 'element-attr':
        case 'attr-value':
        case 'element': return (element) => `<{${element}}>`;

        case 'grammar': return (text) => `${text} (within a <pre class=prod>)`;

        case 'type': return (text)=> `<<${text}>>`;

        case 'descriptor':
        case 'property': return (text) => `'${text}'`;

        default: return;
    };
};

function genLinkingSyntaxes(dfn) {
    if(dfn.tagName != "DFN") return;

    const type = dfn.getAttribute('data-dfn-type');
    if(!type) {
        console.log(`<dfn> doesn't have a data-dfn-type:`, dfn);
        return [];
    }

    // Return a function that wraps link text based on the type
    const linkFormatter = linkFormatterFromType(type);
    if(!linkFormatter) {
        console.log(`<dfn> has an unknown data-dfn-type:`, dfn);
        return [];
    }

    let ltAlts;
    if(dfn.hasAttribute('data-lt')) {
        ltAlts = dfn.getAttribute('data-lt')
            .split("|")
            .map(x=>x.trim());
    } else {
        ltAlts = [dfn.textContent.trim()];
    }
    if(type == "type") {
        // lt of "<foo>", but "foo" is the interior;
        // <<foo/bar>> is how you write it with a for,
        // not <foo/<bar>> or whatever.
        for(var i = 0; i < ltAlts.length; i++) {
            const lt = ltAlts[i];
            const match = /<(.*)>/.exec(lt);
            if(match) { ltAlts[i] = match[1]; }
        }
    }

    let forAlts;
    if(dfn.hasAttribute('data-dfn-for')) {
        forAlts = dfn.getAttribute('data-dfn-for')
            .split(",")
            .map(x=>x.trim());
    } else {
        forAlts = [''];
    }

    let linkingSyntaxes = [];
    if(!needsFor(type)) {
        for(const lt of ltAlts) {
            linkingSyntaxes.push(linkFormatter(lt));
        }
    }
    if(!refusesFor(type)) {
        for(const f of forAlts) {
            linkingSyntaxes.push(linkFormatter(`${f}/${ltAlts[0]}`))
        }
    }
    return [
        mk.b({}, 'Possible linking syntaxes:'),
        mk.ul({},
            ...linkingSyntaxes.map(link => {
                const copyLink = async () =>
                    await navigator.clipboard.writeText(link);
                return mk.li({},
                    mk.div({ class: 'link-item' },
                        mk.button({
                            class: 'copy-icon', title: 'Copy',
                            type: 'button',
                            _onclick: copyLink,
                            tabindex: 0,
                        }, mk.span({ class: 'icon' }) ),
                        mk.span({}, link)
                    )
                );
            })
        )
    ];
}
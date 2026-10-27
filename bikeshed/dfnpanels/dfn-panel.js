document.addEventListener("DOMContentLoaded", ()=>{
    genAllDfnPanels();
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
        genDfnPanel(dfn, panelData);
    }
}

function genDfnPanel(dfn, { dfnID, url, dfnText, refSections, external }) {
    const dfnPanel = mk.dialog({
        class: "dfn-panel",
        id: `infopanel-for-${dfnID}`,
        popover: "hint",
        "data-for": dfnID,
        "aria-labelledby": `infopaneltitle-for-${dfnID}`,
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

    dfnPanel.addEventListener('toggle', event=>{
        if(event.newState == "closed") {
            unpinDfnPanel(dfnPanel);
        }
    });

    dfnPanel.dfn = dfn;
    dfn.dfnPanel = dfnPanel;
    dfn.after(dfnPanel);
    const button = mk.button(
        {
            class:"dfn-panelbutton",
            "popovertarget":dfnPanel.id
        },
        ...dfn.childNodes
    );
    dfn.append(button);
    return dfnPanel;
}

function pinDfnPanel(dfnPanel) {
    // Switch it to "activated" state, which pins it.
    dfnPanel.classList.add("activated");
}

function unpinDfnPanel(dfnPanel) {
    dfnPanel.classList.remove("activated");
}

function refocusOnTarget(event) {
    const target = event.target;
    setTimeout(() => {
        // Refocus on the event.target element.
        // This is needed after browser scrolls to the destination.
        target.focus();
    });
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
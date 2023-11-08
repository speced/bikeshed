"use strict";
{
    // Functions, divided by link type, that wrap an autolink's
    // contents with the appropriate outer syntax.
    // Alternately, a string naming another type they format
    // the same as.
    const typeFormatters = {
        'dfn': (text) => `[=${text}=]`,
        'abstract-op': (text) => `[\$${text}\$]`,
        'value': (text) => `''${text}''`,
        'http-header': (text) => `[:${text}:]`,
        'idl': (text) => `{{${text}}}`,
        'interface': 'idl',
        'constructor': 'idl',
        'method': 'idl',
        'argument': 'idl',
        'attribute': 'idl',
        'callback': 'idl',
        'dictionary': 'idl',
        'dict-member': 'idl',
        'enum': 'idl',
        'enum-value': 'idl',
        'exception': 'idl',
        'const': 'idl',
        'typedef': 'idl',
        'stringifier': 'idl',
        'serializer': 'idl',
        'iterator': 'idl',
        'maplike': 'idl',
        'setlike': 'idl',
        'extended-attribute': 'idl',
        'event': 'idl',
        'element': (element) => `<{${element}}>`,
        'element-state': 'element',
        'element-attr': 'element',
        'attr-value': 'element',
        'scheme': 'dfn',
        'permission': 'dfn',
        'grammar': (text) => `${text} (within a <pre class=prod>)`,
        'type': (text)=> `<<${text}>>`,
        'property': (text) => `'${text}'`,
        'descriptor': 'property',
        'function': 'value',
        'at-rule': 'value',
        'selector': 'value',
    };
    const typesUsingFor = new Set(
        [
            "descriptor",
            "value",
            "element-attr",
            "attr-value",
            "element-state",
            "method",
            "constructor",
            "argument",
            "attribute",
            "const",
            "dict-member",
            "event",
            "enum-value",
            "stringifier",
            "serializer",
            "iterator",
            "maplike",
            "setlike",
            "state",
            "mode",
            "context",
            "facet",
        ],
    )
    const typesNotUsingFor = new Set(
        [
            "property",
            "element",
            "interface",
            "namespace",
            "callback",
            "dictionary",
            "enum",
            "exception",
            "typedef",
            "http-header",
            "permission",
        ],
    )
    function linkFormatterFromType(type) {
        const fnOrType = typeFormatters[type];
        if(typeof fnOrType === 'string') {
            // follow the alias
            return linkFormatterFromType(fnOrType);
        }
        return fnOrType;
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
        if(!typesUsingFor.has(type)) {
            for(const lt of ltAlts) {
                linkingSyntaxes.push(linkFormatter(lt));
            }
        }
        if(!typesNotUsingFor.has(type)) {
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

    function genDfnPanel({ dfn, dfnID, url, dfnText, refSections, external }) {
        const dfnPanel = mk.aside({
            class: "dfn-panel",
            id: `infopanel-for-${dfnID}`,
            "data-for": dfnID,
            "aria-labelled-by":`infopaneltitle-for-${dfnID}`,
            },
            mk.span({id:`infopaneltitle-for-${dfnID}`, style:"display:none"},
                `Info about the '${dfnText}' ${external?"external":""} reference.`),
            mk.a({href:url, class:"dfn-link"}, url),
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
        dfnPanel.forDfn = dfn;
        if(!dfn) { console.log(dfnPanel); }
        return dfnPanel;
    }

    function genAllDfnPanels() {
        for(const panelData of Object.values(window.dfnpanelData)) {
            const dfnID = panelData.dfnID;
            const dfn = document.getElementById(dfnID);
            if(!dfn) {
                console.log(`Can't find dfn#${dfnID}.`, panelData);
                continue;
            }
            const panel = genDfnPanel({ ...panelData, dfn });
            append(document.body, panel);
            insertDfnPopupAction(panel)
        }
    }

    document.addEventListener("DOMContentLoaded", ()=>{
        genAllDfnPanels();

        document.body.addEventListener("click", (e) => {
            // If not handled already, just hide all dfn panels.
            hideAllDfnPanels();
        });
    })

    function hideAllDfnPanels() {
        // Turn off any currently "on" or "activated" panels.
        queryAll(".dfn-panel.on, .dfn-panel.activated").forEach(el=>hideDfnPanel(el));
    }

    function showDfnPanel(dfnPanel) {
        hideAllDfnPanels(); // Only display one at this time.

        const dfn = dfnPanel.forDfn;
        dfn.setAttribute("aria-expanded", "true");

        dfnPanel.classList.add("on");
        positionDfnPanel(dfnPanel);

        let tabIndex = 100;
        dfn.tabIndex = tabIndex++;
        // Increment tabindex for each anchor and button tags in panel
        const tabbable = dfnPanel.querySelectorAll(":is(a, button)");
        for (const el of tabbable) {
            el.tabIndex = tabIndex++;
        }
    }

    function positionDfnPanel(dfnPanel) {
        const dfn = dfnPanel.forDfn;
        const dfnPos = getRootLevelAbsolutePosition(dfn);
        dfnPanel.style.top = dfnPos.bottom + "px";
        dfnPanel.style.left = dfnPos.left + "px";

        const panelPos = dfnPanel.getBoundingClientRect();
        const panelMargin = 8;
        const maxRight = document.body.parentNode.clientWidth - panelMargin;
        if (panelPos.right > maxRight) {
            const overflowAmount = panelPos.right - maxRight;
            const newLeft = Math.max(panelMargin, dfnPos.left - overflowAmount);
            dfnPanel.style.left = newLeft + "px";
        }}

    function pinDfnPanel(dfnPanel) {
        // Switch it to "activated" state, which pins it.
        dfnPanel.classList.add("activated");
        dfnPanel.style.position = "fixed";
        dfnPanel.style.left = null;
        dfnPanel.style.top = null;
    }

    function hideDfnPanel(dfnPanel) {
        const dfn = dfnPanel.forDfn;
        dfn.setAttribute("aria-expanded", "false");
        dfn.tabIndex = undefined;
        dfnPanel.style.position = "absolute"; // unfix it
        dfnPanel.classList.remove("on");
        dfnPanel.classList.remove("activated");
    }

    function toggleDfnPanel(dfnPanel) {
        if(dfnPanel.classList.contains("on")) {
            hideDfnPanel(dfnPanel);
        } else {
            showDfnPanel(dfnPanel);
        }
    }

    function insertDfnPopupAction(dfnPanel) {
        const dfn = dfnPanel.forDfn;
        dfn.setAttribute('role', 'button');
        dfn.setAttribute('aria-expanded', 'false')
        dfn.tabIndex = 0;
        dfn.classList.add('has-dfn-panel');
        dfn.addEventListener('click', (event) => {
            showDfnPanel(dfnPanel);
            event.stopPropagation();
        });
        dfn.addEventListener('keypress', (event) => {
            const kc = event.keyCode;
            // 32->Space, 13->Enter
            if(kc == 32 || kc == 13) {
                toggleDfnPanel(dfnPanel);
                event.stopPropagation();
                event.preventDefault();
            }
        });

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
                hideDfnPanel(dfnPanel, dfn);
                event.stopPropagation();
                event.preventDefault();
            }
        })
    }

    function refocusOnTarget(event) {
        const target = event.target;
        setTimeout(() => {
            // Refocus on the event.target element.
            // This is needed after browser scrolls to the destination.
            target.focus();
        });
    }

    // Returns the root-level absolute position {left and top} of element.
    function getRootLevelAbsolutePosition(el) {
        const boundsRect = el.getBoundingClientRect();
        let xPos = 0;
        let yPos = 0;

        while (el) {
            let xScroll = el.scrollLeft;
            let yScroll = el.scrollTop;

            // Ignore scrolling of body.
            if (el.tagName === "BODY") {
                xScroll = 0;
                yScroll = 0;
            }
            xPos += (el.offsetLeft - xScroll + el.clientLeft);
            yPos += (el.offsetTop - yScroll + el.clientTop);

            el = el.offsetParent;
        }
        return {
            left: xPos,
            top: yPos,
            right: xPos + boundsRect.width,
            bottom: yPos + boundsRect.height,
        };
    }

    function scrolledIntoView(element) {
        const rect = element.getBoundingClientRect();
        return (
            rect.top > 0 &&
            rect.bottom < window.innerHeight
        );
    }

    function scrollToTargetAndHighlight(event) {
        let hash = event.target.hash;
        if (hash) {
            hash = decodeURIComponent(hash.substring(1));
            const dest = document.getElementById(hash);
            if (dest) {
                // Maybe prevent default scroll.
                if (scrolledIntoView(dest)) {
                    event.preventDefault();
                }
                dest.classList.add('highlighted');
                setTimeout(() => dest.classList.remove('highlighted'), 1000);
            }
        }
    }

    window.addEventListener("resize", () => {
        // Pin any visible dfn panel
        queryAll(".dfn-panel.on, .dfn-panel.activated").forEach(el=>positionDfnPanel(el));
    });
}

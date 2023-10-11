"use strict";
{
    const dfnsJson = window.dfnsJson || {};

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
        return mk.aside({
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
            insertDfnPopupAction(dfn, panel)
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

    function showDfnPanel(dfnPanel, dfn) {
        hideAllDfnPanels(); // Only display one at this time.
        dfn.setAttribute("aria-expanded", "true");

        // Reinsert panel into the span following the dfn.
        const dfnSpan = dfn.nextElementSibling;
        dfnSpan.appendChild(dfnPanel);

        dfnPanel.classList.add("on");
        dfnPanel.style.left = "5px";
        dfnPanel.style.top = "0px";
        const panelRect = dfnPanel.getBoundingClientRect();
        if (panelRect.right > document.body.scrollWidth) {
            // Panel's overflowing the screen.
            // Just drop it below the dfn and flip it rightward instead.
            // This still wont' fix things if the screen is *really* wide,
            // but fixing that's a lot harder without 'anchor()'.
            dfnPanel.style.top = "1.5em";
            dfnPanel.style.left = "auto";
            dfnPanel.style.right = "0px";
        }

        // Compute the root-level absolute position, and move it there.
        const absPos = getRootLevelAbsolutePosition(dfnPanel);
        document.body.appendChild(dfnPanel);
        dfnPanel.style.position = "absolute";
        dfnPanel.style.top = absPos.top + "px";
        dfnPanel.style.left = absPos.left + "px";

        let tabIndex = 100;
        dfn.tabIndex = tabIndex++;
        // Increment tabindex for each anchor and button tags in panel
        const tabbable = dfnPanel.querySelectorAll(":is(a, button)");
        for (const el of tabbable) {
            el.tabIndex = tabIndex++;
        }

    }

    function pinDfnPanel(dfnPanel) {
        // Switch it to "activated" state, which pins it.
        dfnPanel.classList.add("activated");
        dfnPanel.style.position = "fixed";
        dfnPanel.style.left = null;
        dfnPanel.style.top = null;
    }

    function hideDfnPanel(dfnPanel, dfn) {
        if(!dfn) {
            dfn = document.getElementById(dfnPanel.getAttribute("data-for"));
        }
        dfn.setAttribute("aria-expanded", "false");
        dfn.tabIndex = undefined;
        dfnPanel.style.position = "absolute"; // unfix it
        dfnPanel.classList.remove("on");
        dfnPanel.classList.remove("activated");
    }

    function toggleDfnPanel(dfnPanel, dfn) {
        if(dfnPanel.classList.contains("on")) {
            hideDfnPanel(dfnPanel, dfn);
        } else {
            showDfnPanel(dfnPanel, dfn);
        }
    }

    function insertDfnPopupAction(dfn, dfnPanel) {
        const panelWrapper = document.createElement('span');
        panelWrapper.appendChild(dfnPanel);
        panelWrapper.style.position = "relative";
        panelWrapper.style.height = "0px";
        dfn.insertAdjacentElement("afterend", panelWrapper);
        dfn.setAttribute('role', 'button');
        dfn.setAttribute('aria-expanded', 'false')
        dfn.tabIndex = 0;
        dfn.classList.add('has-dfn-panel');
        dfn.addEventListener('click', (event) => {
            showDfnPanel(dfnPanel, dfn);
            event.stopPropagation();
        });
        dfn.addEventListener('keypress', (event) => {
            const kc = event.keyCode;
            // 32->Space, 13->Enter
            if(kc == 32 || kc == 13) {
                toggleDfnPanel(dfnPanel, dfn);
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
        });

        dfnPanel.addEventListener('keydown', (event) => {
            if(event.keyCode == 27) { // Escape key
                hideDfnPanel(dfnPanel, dfn);
                event.stopPropagation();
                event.preventDefault();
            }
        })
    }

    // // Returns the root-level fixed position {left and top} of element.
    // // Maybe use el.getBoundingClientRect()?
    // function getRootLevelFixedPosition(el) {
    //     let { left, top } = getRootLevelAbsolutePosition(el);
    //     // Deal with browser quirks involving page scroll.
    //     left -= document.documentElement.scrollLeft;
    //     top -= document.documentElement.scrollTop;
    //     return { left, top };
    // }

    // Returns the root-level absolute position {left and top} of element.
    function getRootLevelAbsolutePosition(el) {
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
            top: yPos
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
}

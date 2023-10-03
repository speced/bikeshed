"use strict";
{
    const dfnsJson = window.dfnsJson || {};

    const wrapperSyntax = {
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
        'event': 'idl',  // Not in bikeshed doc
        'element': (element) => `<{${element}}>`,
        'element-state': 'element',
        'element-attr': 'element',
        'attr-value': 'element',
        'scheme': 'dfn',
        'permission': 'dfn',
        'grammar': (text) => `grammar? '${text}'`,
        'type': 'dfn',
        'css': (text) => `'${text}'`, // property or descriptor
        'css?': (text) => `''${text}''`, // anything else 'value'
        'production': (text) => `<<${text}>>`,
        'property': (text) => `<<'${text}'>>`, // property or descriptor
        'descriptor': 'property',
        'function': (text) => `<<${text}()>>`,
        'at-rule': (text) => `<<@${text}>>`,
        'selector': 'css',
    };

    function genDfnPanel({ dfn, dfnID, url, dfnText, refSections, external }) {
        const type = dfn.getAttribute('data-dfn-type') || 'dfn';

        // Return a function that wraps link text based on the type
        const wsLookup = (type) => {
            const fnOrType = wrapperSyntax[type];
            if (typeof fnOrType === 'string') {
                return wsLookup(fnOrType);
            }
            if (!fnOrType) {
                throw new Error(`unexpected type "${type}"`);
            }
            return fnOrType;
        };
        const autoLinkingFn = wsLookup(type);

        const ltAttr = dfn.getAttribute('data-lt');
        const ltAlts = ltAttr ? ltAttr.split(/\s*\|\s*/) : [dfn.textContent];

        const dfAttr = dfn.getAttribute('data-dfn-for');
        // '',  Should the empty case be included always?
        const dfAlts = [...(dfAttr ? dfAttr.split(/\s*,\s*/) : [''])];

        let linkingSyntaxes = [];
        if (autoLinkingFn && (ltAlts.length + dfAlts.length) > 1) {
            linkingSyntaxes = [
                mk.b({}, 'Possible linking syntax(es):'),
                mk.ul({}, ...ltAlts.map(lt => dfAlts.map((f) => {
                    const link = autoLinkingFn(f ? `${f}/${lt}` : lt);
                    const copyLink = async () =>
                        await navigator.clipboard.writeText(link);
                    return mk.li({},
                        mk.div({ class: 'link-item', _onclick: copyLink },
                            mk.button({
                                class: 'copy-icon', title: 'Copy',
                                type: 'button',

                            }, mk.span({ class: 'icon' }) ),
                            mk.span({}, link)
                        ));
                })))
            ];
        }

        return mk.aside({
            class: "dfn-panel",
            id: `infopanel-for-${dfnID}`,
            "data-for": dfnID,
            "aria-labelled-by":`infopaneltitle-for-${dfnID}`,
            },
            mk.span({id:`infopaneltitle-for-${dfnID}`, style:"display:none"},
                `Info about the '${dfnText}' ${external?"external":""} reference.`),
            mk.a({href:url}, url),
            mk.b({}, "Referenced in:"),
            mk.ul({},
                ...refSections.map(section=>
                    mk.li({},
                        ...section.refs.map((ref, refI)=>
                            [
                                mk.a({
                                    href: `#${ref.id}`
                                    },
                                    (refI == 0) ? section.title : `(${refI + 1})`
                                ),
                                " ",
                            ]
                        ),
                    ),
                ),
            ),
            ...linkingSyntaxes,
        );
    }

    function genAllDfnPanels() {
        for(const panelData of Object.values(window.dfnpanelData)) {
            const dfnID = panelData.dfnID;
            const dfn = document.getElementById(dfnID);
            if(!dfn) {
                console.log(`Can't find dfn#${dfnID}.`, panelData);
            } else {
                const panel = genDfnPanel({ ...panelData, dfn });
                // dfn.setAttribute('popovertarget', panel.id);
                // panel.setAttribute('popover', 'auto');
                append(document.body, panel);
                insertDfnPopupAction(dfn, panel)
            }
        }
    }

    document.addEventListener("DOMContentLoaded", ()=>{
        genAllDfnPanels();

        // Add popup behavior to all dfns to show the corresponding dfn-panel.
        var dfns = queryAll('.dfn-paneled');
        for(let dfn of dfns) { ; }

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
        dfnPanel.classList.add("on");
        dfnPanel.style.left = "5px";
        dfnPanel.style.top = "0px";
        const panelRect = dfnPanel.getBoundingClientRect();
        const panelWidth = panelRect.right - panelRect.left;
        if (panelRect.right > document.body.scrollWidth) {
            // Panel's overflowing the screen.
            // Just drop it below the dfn and flip it rightward instead.
            // This still wont' fix things if the screen is *really* wide,
            // but fixing that's a lot harder without 'anchor()'.
            dfnPanel.style.top = "1.5em";
            dfnPanel.style.left = "auto";
            dfnPanel.style.right = "0px";
        }
    }

    function pinDfnPanel(dfnPanel) {
        // Switch it to "activated" state, which pins it.
        dfnPanel.classList.add("activated");
        dfnPanel.style.left = null;
        dfnPanel.style.top = null;
    }

    function hideDfnPanel(dfnPanel, dfn) {
        if(!dfn) {
            dfn = document.getElementById(dfnPanel.getAttribute("data-for"));
        }
        dfn.setAttribute("aria-expanded", "false")
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
        // Find dfn panel
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
                pinDfnPanel(dfnPanel);
            }
            event.stopPropagation();
            event.preventDefault();
        });

        dfnPanel.addEventListener('keydown', (event) => {
            if(event.keyCode == 27) { // Escape key
                hideDfnPanel(dfnPanel, dfn);
                event.stopPropagation();
                event.preventDefault();
            }
        })
    }
}

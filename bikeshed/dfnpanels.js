"use strict";
{
    function queryAll(sel) {
        return [].slice.call(document.querySelectorAll(sel));
    }

    // Add popup behavior to all dfns to show the corresponding dfn-panel.
    var dfns = document.querySelectorAll('.dfn-paneled');
    for (let dfn of dfns) { insertDfnPopupAction(dfn); }

    document.body.addEventListener("click", (e) => {
        // If not handled already, just hide all dfn panels.
        hideAllDfnPanels();
    });

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

    function insertDfnPopupAction(dfn) {
        // Find dfn panel
        const dfnPanel = document.querySelector(`.dfn-panel[data-for='${dfn.id}']`);
        if (dfnPanel) {
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
                pinDfnPanel(dfnPanel);
                event.stopPropagation();
            });

            dfnPanel.addEventListener('keydown', (event) => {
                if(event.keyCode == 27) { // Escape key
                    hideDfnPanel(dfnPanel, dfn);
                    event.stopPropagation();
                    event.preventDefault();
                }
            })

        } else {
            console.log("Couldn't find .dfn-panel[data-for='" + dfn.id + "']");
        }
    }
}

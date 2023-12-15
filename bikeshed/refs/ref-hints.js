function genRefHint(link, ref) {
    const linkText = link.textContent;
    let dfnTextElements = '';
    if (ref.text != linkText) {
        dfnTextElements =
            mk.li({},
                mk.b({}, "DFN: "),
                mk.code({ class: "dfn-text" }, ref.text)
            );
    }
    const forList = ref.for_;
    const forListElements = forList.length === 0 ? '' : mk.li({},
        mk.b({}, "For: "),
        mk.ul({},
            ...forList.map(forItem =>
                mk.li({},
                    mk.span({}, `${forItem}`)
                ),
            ),
        ),
    );
    const url = ref.url;
    const safeUrl = encodeURIComponent(url);
    const hintPanel = mk.aside({
        class: "ref-hint",
        id: `ref-hint-for-${safeUrl}`,
        "data-for": url,
        "aria-labelled-by": `ref-hint-for-${safeUrl}`,
    },
        mk.ul({},
            dfnTextElements,
            mk.li({},
                mk.b({}, "URL: "),
                mk.a({ href: url, class: "ref" }, url),
            ),
            mk.li({},
                mk.b({}, "Type: "),
                mk.span({}, `${ref.type}`),
            ),
            mk.li({},
                mk.b({}, "Spec: "),
                mk.span({}, `${ref.spec ? ref.spec : ''}`),
            ),
            forListElements
        ),
    );
    hintPanel.forLink = link;
    return hintPanel;
}
function genAllRefHints() {
    for(const refData of Object.values(refsData)) {
        const refUrl = refData.url;
        const links = document.querySelectorAll(`a[href="${refUrl}"]`);
        if (links.length == 0) {
            console.log(`Can't find link href="${refUrl}".`, refData);
            continue;
        }
        for (let i = 0; i < links.length; i++) {
            const link = links[i];
            const hint = genRefHint(link, refData);
            append(document.body, hint);
            insertLinkPopupAction(hint)
        }
    }
}

function hideAllRefHints() {
    queryAll(".ref-hint.on").forEach(el=>hideRefHint(el));
}

function hideRefHint(refHint) {
    const link = refHint.forLink;
    link.setAttribute("aria-expanded", "false");
    refHint.style.position = "absolute"; // unfix it
    refHint.classList.remove("on");
    const teardown = refHint.teardownEventListeners;
    if (teardown) {
        refHint.teardownEventListeners = undefined;
        teardown();
    }
}

function showRefHint(refHint) {
    hideAllRefHints(); // Only display one at this time.

    const link = refHint.forLink;
    link.setAttribute("aria-expanded", "true");
    refHint.classList.add("on");
    positionRefHint(refHint);
    setupRefHintEventListeners(refHint);
}

function setupRefHintEventListeners(refHint) {
    if (refHint.teardownEventListeners) return;
    const link = refHint.forLink;
    // Add event handlers to hide the refHint after the user moves away
    // from both the link and refHint, if not hovering either within one second.
    let timeout = null;
    const startHidingRefHint = (event) => {
        if (timeout) {
            clearTimeout(timeout);
        }
        timeout = setTimeout(() => {
            hideRefHint(refHint);
        }, 1000);
    }
    const resetHidingRefHint = (event) => {
        if (timeout) clearTimeout(timeout);
        timeout = null;
    };
    link.addEventListener("mouseleave", startHidingRefHint);
    link.addEventListener("mouseenter", resetHidingRefHint);
    link.addEventListener("blur", startHidingRefHint);
    link.addEventListener("focus", resetHidingRefHint);
    refHint.addEventListener("mouseleave", startHidingRefHint);
    refHint.addEventListener("mouseenter", resetHidingRefHint);
    refHint.addEventListener("blur", startHidingRefHint);
    refHint.addEventListener("focus", resetHidingRefHint);

    refHint.teardownEventListeners = () => {
        // remove event listeners
        resetHidingRefHint();
        link.removeEventListener("mouseleave", startHidingRefHint);
        link.removeEventListener("mouseenter", resetHidingRefHint);
        link.removeEventListener("blur", startHidingRefHint);
        link.removeEventListener("focus", resetHidingRefHint);
        refHint.removeEventListener("mouseleave", startHidingRefHint);
        refHint.removeEventListener("mouseenter", resetHidingRefHint);
        refHint.removeEventListener("blur", startHidingRefHint);
        refHint.removeEventListener("focus", resetHidingRefHint);
    };
}

function positionRefHint(refHint) {
    const link = refHint.forLink;
    const linkPos = getRootLevelAbsolutePosition(link);
    refHint.style.top = linkPos.bottom + "px";
    refHint.style.left = linkPos.left + "px";

    const panelPos = refHint.getBoundingClientRect();
    const panelMargin = 8;
    const maxRight = document.body.parentNode.clientWidth - panelMargin;
    if (panelPos.right > maxRight) {
        const overflowAmount = panelPos.right - maxRight;
        const newLeft = Math.max(panelMargin, linkPos.left - overflowAmount);
        refHint.style.left = newLeft + "px";
    }
}

// TODO: shared util
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

function insertLinkPopupAction(refHint) {
    const link = refHint.forLink;
    // link.setAttribute('role', 'button');
    link.setAttribute('aria-expanded', 'false')
    link.classList.add('has-ref-hint');
    link.addEventListener('mouseover', (event) => {
        showRefHint(refHint);
    });
    link.addEventListener('focus', (event) => {
        showRefHint(refHint);
    })
}

document.addEventListener("DOMContentLoaded", () => {
    genAllRefHints();

    document.body.addEventListener("click", (e) => {
        // If not handled already, just hide all link panels.
        hideAllRefHints();
    });
});

window.addEventListener("resize", () => {
    // Hide any open ref hint.
    hideAllRefHints();
});

function mkRefHint(link, ref) {
    const linkText = link.textContent;
    let dfnTextElements = '';
    if (ref.displayText.toLowerCase() != linkText.toLowerCase()) {
        // Give the original term if it's being displayed in a different way.
        // But allow casing differences, they're insignificant.
        dfnTextElements =
            mk.li({},
                mk.b({}, "Term: "),
                mk.span({}, ref.displayText)
            );
    }
    const forList = ref.for_;
    let forListElements;
    if(forList.length == 0) {
        forListElements = [];
    } else if(forList.length == 1) {
        forListElements = mk.li({},
            mk.b({}, "For: "),
            mk.span({}, forList[0]),
        );
    } else {
        forListElements = mk.li({},
            mk.b({}, "For: "),
            mk.ul({},
                ...forList.map(forItem =>
                    mk.li({},
                        mk.span({}, forItem)
                    ),
                ),
            ),
        );
    }
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
    setupRefHintEventListeners(link, hintPanel);
    return hintPanel;
}

function hideAllRefHints() {
    queryAll(".ref-hint").forEach(el=>hideRefHint(el));
}

function hideRefHint(refHint) {
    const link = refHint.forLink;
    link.setAttribute("aria-expanded", "false");
    if(refHint.teardownEventListeners) {
        refHint.teardownEventListeners();
    }
    refHint.remove();
}

function showRefHint(link) {
    if(link.classList.contains("dfn-link")) return;
    const url = link.getAttribute("href");
    const ref = refsData[url];
    if(!ref) return;

    hideAllRefHints(); // Only display one at this time.

    const refHint = mkRefHint(link, ref);
    append(document.body, refHint);
    link.setAttribute("aria-expanded", "true");
    positionRefHint(refHint);
}

function setupRefHintEventListeners(link, refHint) {
    if (refHint.teardownEventListeners) return;
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
    const linkPos = getBounds(link);
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

function showRefHintListener(e) {
    // If the target isn't in a link (or is a link),
    // just ignore it.
    let link = e.target.closest("a");
    if(!link) return;

    // If the target is in a ref-hint panel
    // (aka a link in the already-open one),
    // also just ignore it.
    if(link.closest(".ref-hint")) return;

    // Otherwise, show the panel for the link.
    showRefHint(link);
}

function hideAllHintsListener(e) {
    // If the click is inside a ref-hint panel, ignore it.
    if(e.target.closest(".ref-hint")) return;
    // Otherwise, close all the current panels.
    hideAllRefHints();
}

document.addEventListener("DOMContentLoaded", () => {
    document.body.addEventListener("mousedown", showRefHintListener);
    document.body.addEventListener("focus", showRefHintListener);

    document.body.addEventListener("click", hideAllHintsListener);
});

window.addEventListener("resize", () => {
    // Hide any open ref hint.
    hideAllRefHints();
});

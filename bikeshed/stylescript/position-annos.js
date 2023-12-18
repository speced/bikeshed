function repositionAnnoPanels(){
    const panels = [...document.querySelectorAll("[data-anno-for]")];
    hydratePanels(panels);
    let vSoFar = 0;
    for(const panel of panels.sort(cmpTops)) {
        if(panel.top < vSoFar) {
            panel.top = vSoFar;
            panel.style.top = vSoFar + "px";
        }
        vSoFar = panel.top + panel.height + 15;
    }
}
function hydratePanels(panels) {
    const main = document.querySelector("main");
    let mainRect;
    if(main) mainRect = main.getBoundingClientRect();
    // First display them all, if they're not already visible.
    for(const panel of panels) {
        panel.classList.remove("unpositioned");
    }
    // Measure them all
    for(const panel of panels) {
        const dfn = document.getElementById(panel.getAttribute("data-anno-for"));
        if(!dfn) {
            console.log("Can't find the annotation panel target:", panel);
            continue;
        }
        panel.dfn = dfn;
        panel.top = window.scrollY + dfn.getBoundingClientRect().top;
        let panelRect = panel.getBoundingClientRect();
        panel.height = panelRect.height;
        if(main) {
            panel.overlappingMain = panelRect.left < mainRect.right;
        } else {
            panel.overlappingMain = false;
        }
    }
    // And finally position them
    for(const panel of panels) {
        const dfn = panel.dfn;
        if(!dfn) continue;
        panel.style.top = panel.top + "px";
        panel.classList.toggle("overlapping-main", panel.overlappingMain);
    }
}

function cmpTops(a,b) {
    return a.top - b.top;
}

window.addEventListener("load", repositionAnnoPanels);
window.addEventListener("resize", repositionAnnoPanels);

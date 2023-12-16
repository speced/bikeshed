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
    // First display them all
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
        panel.dfnRect = dfn.getBoundingClientRect();
        panel.panelRect = panel.getBoundingClientRect();
    }
    // And finally position them
    for(const panel of panels) {
        const dfn = panel.dfn;
        if(!dfn) continue;
        const dfnRect = panel.dfnRect;
        const panelRect = panel.panelRect;
        const top = window.scrollY + dfnRect.top
        panel.style.top = top + "px";
        panel.top = top;
        panel.height = dfnRect.height;
        if(main) {
            panel.classList.toggle("overlapping-main", panelRect.left < mainRect.right)
        }
    }
}

function cmpTops(a,b) {
    return a.top - b.top;
}

window.addEventListener("load", repositionAnnoPanels);
window.addEventListener("resize", repositionAnnoPanels);

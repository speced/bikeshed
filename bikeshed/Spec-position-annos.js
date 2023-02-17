"use strict";
{

function repositionAnnoPanels(){
    const panels = [...document.querySelectorAll("[data-anno-for]")];
    const main = document.querySelector("main");
    let mainRect;
    if(main) mainRect = main.getBoundingClientRect();
    for(const panel of panels) {
        const dfn = document.getElementById(panel.getAttribute("data-anno-for"));
        if(!dfn) {
            console.log("Can't find the annotation panel target:", panel);
            continue;
        }
        const rect = dfn.getBoundingClientRect();
        const top = window.scrollY + rect.top
        panel.style.top = top + "px";
        panel.top = top;
        panel.height = rect.height;
        panel.classList.remove("unpositioned");
        const panelRect = panel.getBoundingClientRect()
        if(main) {
            panel.classList.toggle("overlapping-main", panelRect.left < mainRect.right)
        }
    }
    let vSoFar = 0;
    for(const panel of panels.sort(cmpTops)) {
        console.log(panel.top, vSoFar);
        if(panel.top < vSoFar) {
            panel.top = vSoFar;
            panel.style.top = vSoFar + "px";
        }
        vSoFar = panel.top + panel.height + 15;
    }
}

function cmpTops(a,b) {
    return a.top - b.top;
}

window.addEventListener("load", repositionAnnoPanels);
window.addEventListener("resize", repositionAnnoPanels);
}
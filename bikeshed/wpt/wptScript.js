"use strict";

document.addEventListener("DOMContentLoaded", async ()=>{
    if(wptPath == "/") return;

    const runsUrl = "https://wpt.fyi/api/runs?label=master&label=stable&max-count=1&product=chrome&product=firefox&product=safari&product=edge";
    const runs = await (await fetch(runsUrl)).json();

    const testResults = await( await fetch("https://wpt.fyi/api/search", {
        method:"POST",
        headers:{
            "Content-Type":"application/json",
        },
        body: JSON.stringify({
            "run_ids": runs.map(x=>x.id),
            "query": {"path": wptPath},
        })
    })).json();

    const browsers = runs.map(x=>({name:x.browser_name, version:x.browser_version, passes:0, total: 0}));
    const resultsFromPath = new Map(testResults.results.map(result=>{
        const testPath = result.test;
        const passes = result.legacy_status.map(x=>[x.passes, x.total]);
        return [testPath, passes];
    }));
    document.querySelectorAll(".wpt-name").forEach(nameEl=>{
        const passData = resultsFromPath.get("/" + nameEl.getAttribute("title"));
        const numTests = passData[0][1];
        if(numTests > 1) {
            nameEl.insertAdjacentElement("beforeend",
                el("small", {}, ` (${numTests} tests)`));
        }
        if(passData == undefined) return;
        passData.forEach((p,i) => {
            browsers[i].passes += p[0];
            browsers[i].total += p[1];
        })
        const resultsEl = el("span",{"class":"wpt-results"},
            ...passData.map((p,i) => el("span",
            {
                "title": `${browsers[i].name} ${p[0]}/${p[1]}`,
                "class": "wpt-result",
                "style": `background: conic-gradient(forestgreen ${p[0]/p[1]*360}deg, darkred 0deg);`,
            })),
        );
        nameEl.insertAdjacentElement("afterend", resultsEl);
    });
    const overview = document.querySelector(".wpt-overview");
    if(overview) {
        overview.appendChild(el('ul',{}, ...browsers.map(formatWptResult)));
        document.head.appendChild(el('style', {},
            `.wpt-overview ul { display: flex; flex-flow: row wrap; gap: .2em; justify-content: start; list-style: none; padding: 0; margin: 0;}
             .wpt-overview li { padding: .25em 1em; color: black; text-align: center; }
             .wpt-overview img { height: 1.5em; height: max(1.5em, 32px); background: transparent; }
             .wpt-overview .browser { font-weight: bold; }
             .wpt-overview .passes-none { background: #e57373; }
             .wpt-overview .passes-hardly { background: #ffb74d; }
             .wpt-overview .passes-a-few { background: #ffd54f; }
             .wpt-overview .passes-half { background: #fff176; }
             .wpt-overview .passes-lots { background: #dce775; }
             .wpt-overview .passes-most { background: #aed581; }
             .wpt-overview .passes-all { background: #81c784; }`));
    }
});
function el(name, attrs, ...content) {
    const x = document.createElement(name);
    for(const [k,v] of Object.entries(attrs)) {
        x.setAttribute(k, v);
    }
    for(let child of content) {
        if(typeof child == "string") child = document.createTextNode(child);
        try {
        x.appendChild(child);
        } catch(e) { console.log({x, child}); }
    }
    return x;
}
function formatWptResult({name, version, passes, total}) {
    const passRate = passes/total;
    let passClass = "";
    if(passRate == 0)      passClass = "passes-none";
    else if(passRate < .2) passClass = "passes-hardly";
    else if(passRate < .4) passClass = "passes-a-few";
    else if(passRate < .6) passClass = "passes-half";
    else if(passRate < .8) passClass = "passes-lots";
    else if(passRate < 1)  passClass = "passes-most";
    else                   passClass = "passes-all";

    name = name[0].toUpperCase() + name.slice(1);
    const shortVersion = /^\d+/.exec(version);
    const icon = []

    if(name == "Chrome") icon.push(el('img', {alt:"", src:"https://wpt.fyi/static/chrome-dev_64x64.png"}));
    if(name == "Edge") icon.push(el('img', {alt:"", src:"https://wpt.fyi/static/edge-dev_64x64.png"}));
    if(name == "Safari") icon.push(el('img', {alt:"", src:"https://wpt.fyi/static/safari-preview_64x64.png"}));
    if(name == "Firefox") icon.push(el('img', {alt:"", src:"https://wpt.fyi/static/firefox-nightly_64x64.png"}));

    return el('li', {"class":passClass},
        el('nobr', {'class':'browser'}, ...icon, ` ${name} ${shortVersion}`),
        el('br', {}),
        el('nobr', {'class':'pass-rate'}, `${passes}/${total}`)
    );
}
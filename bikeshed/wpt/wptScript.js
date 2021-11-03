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

    const browsers = runs.map(x=>x.browser_name)
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
        const resultsEl = el("span",{"class":"wpt-results"},
            ...passData.map((p,i) => el("span",
            {
                "title": `${browsers[i]} ${p[0]}/${p[1]}`,
                "class": "wpt-result",
                "style": `background: conic-gradient(forestgreen ${p[0]/p[1]*360}deg, darkred 0deg);`,
            })),
        );
        nameEl.insertAdjacentElement("afterend", resultsEl);
    })
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

document.addEventListener("DOMContentLoaded", async ()=>{
    if(wptData.paths.length == 0) return;

    const runsUrl = "https://wpt.fyi/api/runs?label=master&label=stable&max-count=1&product=chrome&product=firefox&product=safari&product=edge";
    const runs = await (await fetch(runsUrl)).json();

    let testResults = [];
    for(const pathPrefix of wptData.paths) {
        const pathResults = await (await fetch("https://wpt.fyi/api/search", {
            method:"POST",
            headers:{
                "Content-Type":"application/json",
            },
            body: JSON.stringify({
                "run_ids": runs.map(x=>x.id),
                "query": {"path": pathPrefix},
            })
        })).json();
        testResults = testResults.concat(pathResults.results);
    }

    const browsers = runs.map(x=>({name:x.browser_name, version:x.browser_version, passes:0, total: 0}));
    const resultsFromPath = new Map(testResults.map(result=>{
        const testPath = result.test;
        const passes = result.legacy_status.map(x=>[x.passes, x.total]);
        return [testPath, passes];
    }));
    const seenTests = new Set();
    document.querySelectorAll(".wpt-name").forEach(nameEl=>{
        const passData = resultsFromPath.get("/" + nameEl.getAttribute("title"));
        if(!passData) {
            console.log("Couldn't find test in results:", nameEl);
            return
        }
        const numTests = passData[0][1];
        if(numTests > 1) {
            nameEl.insertAdjacentElement("beforeend",
                mk.small({}, ` (${numTests} tests)`));
        }
        if(passData == undefined) return;
        const resultsEl = mk.span({"class":"wpt-results"},
            ...passData.map((p,i) => mk.span(
            {
                "title": `${browsers[i].name} ${p[0]}/${p[1]}`,
                "class": "wpt-result",
                "style": `background: conic-gradient(forestgreen ${p[0]/p[1]*360}deg, darkred 0deg);`,
            })),
        );
        nameEl.insertAdjacentElement("afterend", resultsEl);

        // Only update the summary pass/total count if we haven't seen this
        // test before, to support authors listing the same test multiple times
        // in a spec.
        if (!seenTests.has(nameEl.getAttribute("title"))) {
            seenTests.add(nameEl.getAttribute("title"));
            passData.forEach((p,i) => {
                browsers[i].passes += p[0];
                browsers[i].total += p[1];
            });
        }
    });
    const overview = document.querySelector(".wpt-overview");
    if(overview) {
        overview.appendChild(mk.ul({}, ...browsers.map(formatWptResult)));
        document.head.appendChild(mk.style({},
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

    if(name == "Chrome") icon.push(mk.img({alt:"", src:"https://wpt.fyi/static/chrome_64x64.png"}));
    if(name == "Edge") icon.push(mk.img({alt:"", src:"https://wpt.fyi/static/edge_64x64.png"}));
    if(name == "Safari") icon.push(mk.img({alt:"", src:"https://wpt.fyi/static/safari_64x64.png"}));
    if(name == "Firefox") icon.push(mk.img({alt:"", src:"https://wpt.fyi/static/firefox_64x64.png"}));

    return mk.li({"class":passClass},
        mk.nobr({'class':'browser'}, ...icon, ` ${name} ${shortVersion}`),
        mk.br(),
        mk.nobr({'class':'pass-rate'}, `${passes}/${total}`)
    );
}

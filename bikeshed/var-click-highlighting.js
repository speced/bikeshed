
    "use strict";
    {
        document.addEventListener("click", e=>{
            if(e.target.nodeName == "VAR") {
                highlightSameAlgoVars(e.target);
            }
        });
        const indexCounts = new Map();
        const indexNames = new Map();
        function highlightSameAlgoVars(v) {
            // Find the algorithm container.
            let algoContainer = null;
            let searchEl = v;
            while(algoContainer == null && searchEl != document.body) {
                searchEl = searchEl.parentNode;
                if(searchEl.hasAttribute("data-algorithm")) {
                    algoContainer = searchEl;
                }
            }

            // Not highlighting document-global vars,
            // too likely to be unrelated.
            if(algoContainer == null) return;

            const algoName = algoContainer.getAttribute("data-algorithm");
            const varName = getVarName(v);
            const addClass = !v.classList.contains("selected");
            let highlightClass = null;
            if(addClass) {
                const index = chooseHighlightIndex(algoName, varName);
                indexCounts.get(algoName)[index] += 1;
                indexNames.set(algoName+"///"+varName, index);
                highlightClass = nameFromIndex(index);
            } else {
                const index = previousHighlightIndex(algoName, varName);
                indexCounts.get(algoName)[index] -= 1;
                highlightClass = nameFromIndex(index);
            }

            // Find all same-name vars, and toggle their class appropriately.
            for(const el of algoContainer.querySelectorAll("var")) {
                if(getVarName(el) == varName) {
                    el.classList.toggle("selected", addClass);
                    el.classList.toggle(highlightClass, addClass);
                }
            }
        }
        function getVarName(el) {
            return el.textContent.replace(/(\s|\xa0)+/, " ").trim();
        }
        function chooseHighlightIndex(algoName, varName) {
            let indexes = null;
            if(indexCounts.has(algoName)) {
                indexes = indexCounts.get(algoName);
            } else {
                // 7 classes right now
                indexes = [0,0,0,0,0,0,0];
                indexCounts.set(algoName, indexes);
            }

            // If the element was recently unclicked,
            // *and* that color is still unclaimed,
            // give it back the same color.
            const lastIndex = previousHighlightIndex(algoName, varName);
            if(indexes[lastIndex] === 0) return lastIndex;

            // Find the earliest index with the lowest count.
            const minCount = Math.min.apply(null, indexes);
            let index = null;
            for(var i = 0; i < indexes.length; i++) {
                if(indexes[i] == minCount) {
                    return i;
                }
            }
        }
        function previousHighlightIndex(algoName, varName) {
            return indexNames.get(algoName+"///"+varName);
        }
        function nameFromIndex(index) {
            return "selected" + index;
        }
    }

window.addEventListener("load", function(){
    var panels = [].slice.call(document.querySelectorAll(".caniuse-status"));
    for(var i = 0; i < panels.length; i++) {
        var panel = panels[i];
        var dfn = document.querySelector("#" + panel.getAttribute("data-dfn-id"));
        var rect = dfn.getBoundingClientRect();
        panel.style.top = (window.scrollY + rect.top) + "px";
    }
});
document.body.addEventListener("click", function(e) {
    if(e.target.classList.contains("caniuse-panel-btn")) {
        e.target.parentNode.classList.toggle("wrapped");
    }
});
document.body.addEventListener("click", (e) => {
    if(e.target.closest(".mdn-anno-btn")) {
        e.target.closest(".mdn-anno").classList.toggle("wrapped");
    }
});
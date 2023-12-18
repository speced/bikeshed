document.addEventListener("DOMContendLoaded", ()=>{
    const warning = document.querySelector('#expiry-notice');
    const expiresOn = warning.dataset.expires;
    const today = new Date().toISOString();
    if(expires < today) {
        warning.setAttribute("open", "");
        for(const swap of warning.querySelectorAll("[data-after-expiry]")) {
            swap.textContent = swap.dataset.afterExpiry;
        }
    }
});
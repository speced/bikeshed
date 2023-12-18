function setTypeTitles() {
	for(let el of document.querySelectorAll("a[href]")) {
		if(el.href in linkTitleData && !el.hasAttribute("title")) {
			el.setAttribute("title", linkTitleData[el.href]);
		}
	}
}

document.addEventListener("DOMContentLoaded", setTypeTitles);
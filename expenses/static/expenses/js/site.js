// Runs on every page: the collapsible menu on small screens and the service worker.
(function () {
    const navbar = document.getElementById("navbar");
    const toggle = document.getElementById("nav-toggle");
    if (navbar && toggle) {
        toggle.hidden = false;
        navbar.classList.add("collapsible");
        toggle.addEventListener("click", () => {
            const open = navbar.classList.toggle("open");
            toggle.setAttribute("aria-expanded", String(open));
        });
    }

    // Caches static files and the offline page only; see templates/pwa/sw.js.
    const serviceWorkerUrl = document.currentScript && document.currentScript.dataset.serviceWorker;
    if (serviceWorkerUrl && "serviceWorker" in navigator) {
        window.addEventListener("load", () => {
            navigator.serviceWorker.register(serviceWorkerUrl).catch(() => {});
        });
    }
})();

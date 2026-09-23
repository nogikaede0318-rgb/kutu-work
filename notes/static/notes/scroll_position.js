(() => {
    // sessionStorage keeps positions separate for each browser tab.
    const params = new URLSearchParams(window.location.search);
    params.sort();
    const pageKey = document.querySelector('[data-scroll-key]')?.dataset.scrollKey
        || `${window.location.pathname}?${params}`;
    const storageKey = `shift-manager:scroll:${pageKey}`;
    let position;
    try {
        position = JSON.parse(sessionStorage.getItem(storageKey));
        // Verify storage access before taking over browser restoration.
        sessionStorage.setItem(storageKey, JSON.stringify(position));
    } catch {
        return;
    }

    if ('scrollRestoration' in history) history.scrollRestoration = 'manual';

    const save = () => {
        try {
            sessionStorage.setItem(storageKey, JSON.stringify({ x: window.scrollX, y: window.scrollY }));
        } catch {
            // A storage quota or browser setting must not prevent navigation.
        }
    };

    window.addEventListener('pagehide', save);
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'hidden') save();
    });
    window.addEventListener('pageshow', (event) => {
        // The back/forward cache already retains the live document position.
        if (event.persisted || window.location.hash) return;
        if (!Number.isFinite(position?.x) || !Number.isFinite(position?.y)) return;
        // Run after the shared header has moved the title and action buttons.
        requestAnimationFrame(() => {
            window.scrollTo({ left: position.x, top: position.y, behavior: 'instant' });
        });
    });
})();

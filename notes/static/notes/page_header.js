(() => {
    const header = document.querySelector('[data-fixed-page-header]');
    const controls = document.querySelector('[data-fixed-page-controls]');
    const main = document.querySelector('main.container');
    if (!header || !controls || !main) return;

    const title = main.querySelector('.page-title');
    if (title) {
        controls.append(title);
    } else {
        const heading = main.querySelector('.form-panel > h1');
        if (heading) {
            const panel = document.createElement('section');
            panel.className = 'page-title';
            panel.append(heading);
            controls.append(panel);
        }
    }

    // Keep each moved submit button associated with its original form.
    main.querySelectorAll('.form-actions, .bulk-actions').forEach((actions, index) => {
        if (actions.closest('dialog, .settings-list')) return;
        actions.querySelectorAll('button, input, select, textarea').forEach((control) => {
            const form = control.form;
            if (!form) return;
            if (!form.id) form.id = `page-action-form-${index}`;
            control.setAttribute('form', form.id);
        });
        controls.append(actions);
    });

    const updateHeight = () => {
        document.documentElement.style.setProperty('--fixed-header-height', `${header.offsetHeight}px`);
    };
    new ResizeObserver(updateHeight).observe(header);
    updateHeight();
    document.body.classList.add('has-fixed-header');
})();

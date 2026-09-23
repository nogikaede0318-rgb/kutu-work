document.querySelectorAll('[data-day-off-button]').forEach((button) => {
    const select = button.closest('.shift-type-controls').querySelector('select');
    const dayOffOption = Array.from(select.options).find((option) => option.dataset.code === '休');

    if (!dayOffOption) {
        button.disabled = true;
        button.title = '勤務区分に「休」を登録してください';
        return;
    }

    const updateButton = () => {
        button.setAttribute('aria-pressed', String(select.value === dayOffOption.value));
    };
    button.addEventListener('click', () => {
        select.value = dayOffOption.value;
        select.dispatchEvent(new Event('change', { bubbles: true }));
    });
    select.addEventListener('change', updateButton);
    updateButton();
});

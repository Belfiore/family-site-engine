document.addEventListener('click', function (event) {
    var link = event.target.closest('a.record-link');
    if (!link) return;
    // a middle click, or a click with a modifier key, keeps its normal meaning: open the picture in a new tab
    if (event.defaultPrevented || event.button || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    var image = link.querySelector('img');
    var box = document.createElement('div');
    box.className = 'record-lightbox';
    box.setAttribute('role', 'dialog');
    box.setAttribute('aria-modal', 'true');
    box.setAttribute('aria-label', image && image.alt ? 'Full size: ' + image.alt : 'Full-size image');
    box.tabIndex = -1;
    var big = document.createElement('img');
    big.src = link.getAttribute('href');
    big.alt = image ? image.alt : '';
    var caption = document.createElement('p');
    caption.textContent = image ? image.alt : '';
    box.appendChild(big);
    box.appendChild(caption);
    function close() {
        box.remove();
        document.removeEventListener('keydown', onKey);
        try { link.focus(); } catch (e) { /* the link is gone */ }
    }
    function onKey(e) { if (e.key === 'Escape') close(); }
    box.addEventListener('click', close);
    document.addEventListener('keydown', onKey);
    document.body.appendChild(box);
    box.focus();
});

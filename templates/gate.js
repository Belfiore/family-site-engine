(function () {
    var root = document.documentElement;
    var form = document.getElementById('gate'), pw = document.getElementById('pw'), go = document.getElementById('go');
    var msg = document.getElementById('msg'), show = document.getElementById('show');
    var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    var seen = false;
    try { seen = sessionStorage.getItem('fs.gate.seen') === '1'; } catch (e) {}
    if (seen || reduce) root.classList.add('g-skip');
    try { sessionStorage.setItem('fs.gate.seen', '1'); } catch (e) {}
    // any key or tap skips what is still moving
    function skip() { root.classList.add('g-skip'); }
    window.addEventListener('keydown', skip, { once: true });
    window.addEventListener('pointerdown', skip, { once: true });

    show.addEventListener('click', function () {
        var on = pw.type === 'password';
        pw.type = on ? 'text' : 'password';
        show.textContent = on ? 'Hide' : 'Show';
        show.setAttribute('aria-pressed', on ? 'true' : 'false');
        pw.focus();
    });

    function say(text) { msg.textContent = text; }
    form.addEventListener('submit', function (e) {
        e.preventDefault();
        if (go.disabled || !pw.value.trim()) { pw.focus(); return; }
        go.disabled = true; say('');
        var label = go.textContent; go.textContent = 'Opening';
        fetch('/__gate/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'same-origin', body: JSON.stringify({ password: pw.value }) })
            .then(function (r) {
                if (r.ok) {
                    pw.value = '';
                    root.classList.add('g-open');
                    setTimeout(function () { location.reload(); }, reduce ? 0 : 420);
                    return;
                }
                go.disabled = false; go.textContent = label;
                say(r.status === 401 ? 'That is not the family password. Please try again.' : 'Something went wrong. Please try again in a moment.');
                pw.focus();
            })
            .catch(function () { go.disabled = false; go.textContent = label; say('Could not reach the site. Check your connection and try again.'); });
    });
})();

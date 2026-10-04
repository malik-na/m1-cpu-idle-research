/* THROWAWAY. One shared switcher; no persistent state or live acquisition. */
(() => {
  const names = { A: 'Guided story', B: 'Trace inspector', C: 'Evidence map' };
  const stateByVariant = { A: {}, B: {}, C: {} };
  let active = 'A';
  function renderState() {
    document.getElementById('prototype-state').textContent = JSON.stringify({
      prototype: true, variant: active, name: names[active],
      sourceRevision: window.PROTOTYPE_DATA.revision,
      evidence: { commandReads: 2185, busyWords: 71, strictSoftwareWitnesses: 18,
        pcpmReads: 90, pcpmWord: '0x000021f0', ps3Image: 'installed, unbooted' },
      interaction: stateByVariant[active]
    }, null, 2);
  }
  window.prototypeState = (state) => { stateByVariant[active] = state; renderState(); };
  function selectVariant(key, changeUrl = true) {
    active = names[key] ? key : 'A';
    document.querySelectorAll('[data-variant]').forEach(el => { el.hidden = el.dataset.variant !== active; });
    document.getElementById('prototype-label').textContent = active + ' · ' + names[active];
    document.body.dataset.prototypeVariant = active;
    if (changeUrl) {
      const url = new URL(location.href); url.searchParams.set('variant', active);
      history.replaceState(null, '', url);
    }
    renderState();
  }
  function cycle(delta) {
    const keys = Object.keys(names); selectVariant(keys[(keys.indexOf(active) + delta + keys.length) % keys.length]);
  }
  for (const key of Object.keys(names)) {
    active = key;
    window['initVariant' + key]?.();
  }
  selectVariant(new URL(location.href).searchParams.get('variant') || 'A', false);
  document.getElementById('prototype-previous').onclick = () => cycle(-1);
  document.getElementById('prototype-next').onclick = () => cycle(1);
  const stateToggle = document.getElementById('prototype-state-toggle');
  stateToggle.onclick = () => {
    const panel = document.getElementById('prototype-state'); panel.hidden = !panel.hidden;
    stateToggle.setAttribute('aria-expanded', String(!panel.hidden));
  };
  addEventListener('keydown', event => {
    if (event.target.closest('input, textarea, select, [contenteditable]') || event.altKey || event.ctrlKey || event.metaKey) return;
    if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
      event.preventDefault(); cycle(event.key === 'ArrowLeft' ? -1 : 1);
    }
  });
  addEventListener('popstate', () => selectVariant(new URL(location.href).searchParams.get('variant') || 'A', false));
})();

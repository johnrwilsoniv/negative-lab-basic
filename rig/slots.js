// The branch switcher in every page's nav on nlb.jrwiv.com (website.py copies this to /<slot>/slots.js and each page
// loads it, deferred, with data-slot naming its own slot). It lists the published slots from /slots/ (nginx's listing
// of the site root, deploy/nginx.conf) and swaps the nav's "preview: <slot>" badge for a menu of them. Picking one
// opens the same page in that slot, or its home page if that slot has no such page. With one slot, or no listing
// (opened from disk), the nav is left as it is.
(() => {
  const here = document.currentScript.dataset.slot;
  const home = (slot) => (slot === 'main' ? '/' : `/${slot}/`);

  // This page within its slot ("print-preview/"), so the same page can be opened in another
  function page() {
    const path = location.pathname;
    return path.startsWith(`/${here}/`) ? path.slice(here.length + 2) : '';
  }

  async function go(slot) {
    const sub = page();
    const target = sub ? `/${slot}/${sub}` : home(slot);
    try {
      if (sub && !(await fetch(target, { method: 'HEAD' })).ok) return location.assign(home(slot));
    } catch { /* offline: try the page anyway */ }
    location.assign(target);
  }

  const STYLE = `
nav.site select.slot {
  appearance: none; -webkit-appearance: none; cursor: pointer; background: transparent; max-width: 30ch;
  field-sizing: content;   /* as wide as the slot shown, not the longest one listed */
  font: 500 11.5px/1 var(--f-num); color: var(--muted); border: 1px solid var(--line); border-radius: 3px;
  padding: 3px 17px 3px 5px; text-overflow: ellipsis;
  background-image: linear-gradient(45deg, transparent 50%, currentColor 50%), linear-gradient(-45deg, transparent 50%, currentColor 50%);
  background-size: 4px 4px; background-repeat: no-repeat; background-position: right 8px center, right 4px center;
}
nav.site select.slot.preview { color: var(--print); border-color: currentColor; }
nav.site select.slot:hover { color: var(--fg); }
nav.site select.slot.preview:hover { color: var(--print); background-color: color-mix(in srgb, var(--print) 12%, transparent); }
nav.site select.slot:focus-visible { outline: 2px solid var(--print); outline-offset: 2px; }
nav.site select.slot option { color: var(--fg); background: var(--panel); }`;

  async function slots() {
    const r = await fetch('/slots/', { headers: { Accept: 'application/json' } });
    if (!r.ok) throw new Error(`/slots/: ${r.status}`);
    const names = (await r.json()).filter((e) => e.type === 'directory').map((e) => e.name);
    // main first, then the previews by name
    return names.sort((a, b) => (b === 'main') - (a === 'main') || a.localeCompare(b));
  }

  async function mount() {
    const nav = document.querySelector('nav.site');
    if (!nav || !here) return;
    let names;
    try { names = await slots(); } catch { return; }
    if (!names.includes(here)) names.push(here);
    if (names.length < 2) return;

    const style = document.createElement('style');
    style.textContent = STYLE;
    document.head.append(style);

    const pick = document.createElement('select');
    pick.className = here === 'main' ? 'slot' : 'slot preview';
    pick.setAttribute('aria-label', 'Branch');
    pick.title = 'Published branches: main is the current rig, the rest are design previews';
    for (const name of names) pick.append(new Option(name === 'main' ? 'main' : `preview: ${name}`, name, name === here, name === here));
    pick.addEventListener('change', () => go(pick.value));
    window.addEventListener('pageshow', () => { pick.value = here; });   // back from the other slot: this one again

    const badge = nav.querySelector('.slot');
    if (badge) badge.replaceWith(pick); else nav.append(pick);
  }

  mount();
})();

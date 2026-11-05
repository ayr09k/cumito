/* Cumito en el celular (Android / iPhone): la misma página, pero en vez de
   hablar con Python habla directo con el servidor por WebSocket (/ws).
   Lo que en la PC guarda Python (nombre, búsquedas recientes) aquí queda
   guardado en el propio celular. */
(function () {
  'use strict';
  if (!window.CUMITO_MOBILE) return;
  const T = window.CUMITO_TEST;
  const LS = {
    get(k, d) { try { const v = localStorage.getItem('cumito.' + k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem('cumito.' + k, JSON.stringify(v)); } catch (e) {} },
  };
  const KNOWN = ['search_results', 'playlist_preview', 'activity_list', 'status', 'lyrics', 'stats', 'albums', 'album',
    'album_cover', 'album_added', 'error'];
  const ev = (t, d) => T.onEvent(t, JSON.stringify(d));
  let name = LS.get('name', '');
  let ws = null, alive = false, wait = 1000, timer = null;

  function config() { ev('config', { name: name || null, recent_searches: LS.get('recent', []), visual: {}, scale: 1 }); }

  function connect() {
    if (!name || (ws && ws.readyState <= 1)) return;
    clearTimeout(timer);
    ws = new WebSocket((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws');
    ws.onopen = () => { alive = true; wait = 1000; ws.send(JSON.stringify({ type: 'hello', name: name })); ev('connected', true); };
    ws.onmessage = (m) => {
      let d; try { d = JSON.parse(m.data); } catch (e) { return; }
      ev(KNOWN.includes(d.type) ? d.type : 'state', d);
    };
    ws.onclose = () => {
      if (alive) ev('connected', false);
      alive = false; ws = null;
      timer = setTimeout(connect, wait);
      wait = Math.min(wait * 2, 15000);
    };
    ws.onerror = () => { try { ws.close(); } catch (e) {} };
  }
  function cmd(action, kw) {
    if (ws && ws.readyState === 1) ws.send(JSON.stringify(Object.assign({ type: 'command', action: action }, kw || {})));
  }

  // portada de un disco: elegir una foto del celular y achicarla antes de mandarla
  function pickCover() {
    const inp = document.createElement('input');
    inp.type = 'file'; inp.accept = 'image/*';
    inp.onchange = () => {
      const f = inp.files && inp.files[0];
      if (!f) return;
      const img = new Image();
      img.onload = () => {
        const S = 700, k = Math.min(1, S / Math.min(img.width, img.height));
        const c = document.createElement('canvas');
        c.width = Math.round(img.width * k); c.height = Math.round(img.height * k);
        const g = c.getContext('2d');
        g.fillStyle = '#100E16'; g.fillRect(0, 0, c.width, c.height);
        g.drawImage(img, 0, 0, c.width, c.height);
        ev('cover_picked', { b64: c.toDataURL('image/jpeg', 0.88).split(',')[1] });
        URL.revokeObjectURL(img.src);
      };
      img.onerror = () => ev('cover_picked', { error: 'No pude abrir esa imagen' });
      img.src = URL.createObjectURL(f);
    };
    inp.click();
  }

  T.setBridge({
    send: (a, kw) => { let o = {}; try { o = JSON.parse(kw || '{}'); } catch (e) {} cmd(a, o); },
    search: (q, l, o, k) => cmd('search', { query: q, limit: l, offset: o, kind: k }),
    win_cmd: () => {},
    save: (k, v) => {
      try { v = JSON.parse(v); } catch (e) { return; }
      if (k === 'recent_searches') LS.set('recent', v);
      else if (k === 'display_name' && v) {
        name = String(v).slice(0, 32); LS.set('name', name); config();
        if (ws) ws.close(); else connect();
      }
    },
    pick_cover: pickCover,
    ready: () => {},
  });
  config();
  if (!name) prompt2('¿Cómo te llamas?', 'Así te van a ver los demás en Cumito.', '', 'display_name', true);
  else connect();
  // al volver a la app (estaba en segundo plano) se reconecta al toque
  document.addEventListener('visibilitychange', () => { if (!document.hidden && !ws) { wait = 1000; connect(); } });
})();

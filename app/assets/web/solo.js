/* Modo solo (solo en el celular): tu propia música, sonando en TU teléfono,
   aparte de lo que suena en Discord.

   La lista y el reproductor viven aquí. El servidor deja lista cada canción
   (la baja a su disco) y nos dice de dónde descargarla (/audio/...). Todo lo
   demás de la app (la pantalla, la lista, el buscador, la letra, los discos)
   es el mismo de siempre: SOLO.view() le arma un "estado" igual al del grupo
   y SOLO.intercept() atiende aquí los botones (pausa, siguiente, quitar...)
   en vez de mandárselos al bot.

   En el inicio: quién está escuchando qué ("Escuchar con Ana") y
   recomendaciones ("Para ti"). */
(function () {
  'use strict';
  const ls = {
    get(k, d) { try { const v = localStorage.getItem('cumito.solo.' + k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem('cumito.solo.' + k, JSON.stringify(v)); } catch (e) {} },
  };
  // medio segundo de silencio: "destraba" el audio en el iPhone con el primer toque
  const SILENT = 'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=';
  const audio = new Audio();
  audio.preload = 'auto';
  audio.setAttribute('playsinline', '');
  let nextUid = 1;

  const O = window.SOLO = {
    on: false, home: false, q: [], cur: null, played: [], repeat: 'off',
    radio: ls.get('radio', true), follow: null, want: false, ended: false, startAt: 0,
    hist: ls.get('hist', []), recs: { items: [], at: 0, key: '', loading: false },
    radioBusy: false, radioForce: false, unlocked: false,
  };

  function rs(action, kw) { if (B) B.send(action, JSON.stringify(kw || {})); }   // directo al servidor
  function meta(t) { return { title: t.title, uploader: t.uploader, duration: t.duration, art_url: t.art_url, webpage_url: t.webpage_url }; }
  function mk(m, extra) {
    return Object.assign({ uid: nextUid++, title: m.title || 'Cargando…', uploader: m.uploader || '', duration: m.duration || 0,
      art_url: m.art_url || null, webpage_url: m.webpage_url, src: null }, extra || {});
  }
  function shuffleArr(a) { for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; }

  /* ---------- el "estado" que ve el resto de la app ---------- */
  O.view = function () {
    const g = S.group || {};
    const c = O.cur;
    const tg = O.follow ? targets().find((x) => x.id === O.follow) : null;
    return Object.assign({}, g, {
      now_playing: c ? {
        title: c.title || 'Cargando…', uploader: c.uploader || '', art_url: c.art_url, webpage_url: c.webpage_url,
        duration: c.duration || (isFinite(audio.duration) ? Math.round(audio.duration) : 0),
        paused: !O.want, elapsed: audio.currentTime || O.startAt || 0, req: c.req, who: null,
        with: tg ? (tg.id === '@discord' ? 'el grupo' : tg.who) : null,
      } : null,
      queue: O.q.map((t) => ({ uid: t.uid, req: t.req, title: t.title || 'Cargando…', uploader: t.uploader, duration: t.duration,
        art_url: t.art_url, prepared: true, ready: true, loading: false, radio: !!t.radio, who: t.radio ? 'Radio' : S.me })),
      repeat: O.repeat, radio: O.radio, sleep: null,
      can_prev: O.played.length > 0 || audio.currentTime > 5,
      features: (g.features || []).filter((f) => f !== 'react' && f !== 'sleep' && f !== 'normalize'),
      recent: O.hist.slice(0, 10),
    });
  };
  function refresh() {
    if (!O.on) return;
    S.st = O.view();
    S.elapsed = audio.currentTime || O.startAt || 0; S.elapsedAt = performance.now();
    renderAll();
    if (P.open === 'lyrics') lyricsFollow();
    updateAddedTiles();
    media();
    saveSoon();
  }

  /* ---------- reproducir ---------- */
  function start(t, at, keepFollow) {
    endedUid = null;
    if (O.cur && O.cur !== t) { O.played.push(O.cur); if (O.played.length > 60) O.played.shift(); }
    O.cur = t; O.want = true; O.ended = false; O.startAt = at || 0;
    if (!keepFollow) O.follow = null;
    addHist(t);
    if (t.src) load(t);
    else { audio.pause(); fetchTrack(t, false); }
    refresh();
    report(true);
    prefetch();
    if (O.radio && O.q.length < 2 && !O.follow) fetchRadio(t, false, false);
  }
  function load(t) {
    O.loadingUid = t.uid;
    audio.src = t.src;
    if (O.want) audio.play().catch(() => { if (O.cur === t) { O.want = false; refresh(); toast('Toca ▶ para empezar'); } });
  }
  function fetchTrack(t, pre) {
    if (t.asking === (pre ? 'pre' : 'now') || t.asking === 'now') return;
    t.asking = pre ? 'pre' : 'now';
    rs('solo_get', { url: t.webpage_url, title: t.title !== 'Cargando…' ? t.title : null, pre: !!pre });
  }
  // deja listas las 2 que siguen (si la siguiente no está bajada cuando se acaba
  // la actual, con la pantalla apagada el celular puede no recibir la respuesta)
  function prefetch() { O.q.slice(0, 2).forEach((n) => { if (n && !n.src) fetchTrack(n, true); }); }
  function next(manual) {
    if (manual) O.follow = null;
    if (O.repeat === 'all' && O.cur) O.q.push(mk(O.cur, { radio: O.cur.radio }));
    const t = O.q.shift();
    if (!t) {
      if (O.radio && O.cur) { fetchRadio(O.cur, true, false); if (manual) toast('Buscando parecidas…', 1400); }
      else { O.want = false; O.ended = true; audio.pause(); refresh(); report(false); }
      return;
    }
    start(t, 0, false);
  }
  function prev() {
    O.follow = null;
    if (audio.currentTime > 5 || !O.played.length) { audio.currentTime = 0; O.startAt = 0; refresh(); report(false); return; }
    const p = O.played.pop();
    if (O.cur) O.q.unshift(O.cur);
    O.cur = null;
    start(p, 0, false);
  }
  function addTracks(list, now, req) {
    const items = (list || []).filter((m) => m && m.webpage_url).map((m) => mk(m, { req: req, radio: !!m.radio }));
    if (!items.length) return;
    if (now) { O.q.unshift.apply(O.q, items.slice(1)); start(items[0], 0, false); return; }
    O.q.push.apply(O.q, items);
    if (!O.cur || (O.ended && !O.want)) start(O.q.shift(), 0, false);
    else { prefetch(); refresh(); }
  }
  // lo que ya conocemos de una canción (del buscador, recomendaciones, discos...)
  function metaFor(url) {
    const pools = [SR.results, O.recs.items, O.hist, (S.group || {}).listening, (S.group || {}).recent,
      AL.cur && AL.cur.tracks, SR.preview && SR.preview.entries, O.q, O.played];
    for (const p of pools) {
      const m = (p || []).find((x) => x && x.webpage_url === url);
      if (m) return meta(m);
    }
    const np = (S.group || {}).now_playing;
    if (np && np.webpage_url === url) return meta(np);
    return null;
  }

  /* ---------- la radio y "Generar recomendaciones" ---------- */
  function fetchRadio(seed, startAfter, force) {
    if (!seed || !seed.webpage_url || O.radioBusy) return;
    O.radioBusy = true; O.radioStart = startAfter; O.radioForce = !!force;
    rs('recs', { seeds: [seed.webpage_url], tag: 'radio' });
    setTimeout(() => { O.radioBusy = false; }, 20000);
  }
  function takeRadio(items) {
    O.radioBusy = false; QS.gen = false;
    if (!O.radio && !O.radioForce) return refresh();
    const seen = new Set([O.cur, ...O.q, ...O.played.slice(-40)].filter(Boolean).map((t) => t.webpage_url));
    const add = (items || []).filter((t) => !seen.has(t.webpage_url)).slice(0, 8).map((t) => Object.assign({}, t, { radio: true }));
    if (!add.length) { if (O.radioForce) toast('No encontré parecidas a esta'); return refresh(); }
    O.radioForce = false;
    O.q.push.apply(O.q, add.map((m) => mk(m, { radio: true })));
    if (O.radioStart && !O.follow) next(false); else { prefetch(); refresh(); }
  }

  /* ---------- lo que tocan en la app ---------- */
  O.intercept = function (a, kw) {
    if (!O.on) return false;
    switch (a) {
      case 'play': {
        const q = String(kw.query || '').trim();
        if (!q) return true;
        const m = !kw.as_playlist && metaFor(q);
        if (m) addTracks([m], !!kw.now, kw.req);
        else rs('solo_add', { query: q, as_playlist: !!kw.as_playlist, now: !!kw.now });
        return true;
      }
      case 'pause': O.want = false; audio.pause(); refresh(); report(false); return true;
      case 'resume':
        if (!O.cur) return true;
        O.want = true;
        if (O.ended) { O.ended = false; audio.currentTime = 0; }
        if (O.cur.src) { if (audio.src !== O.cur.src && !audio.src.endsWith(O.cur.src)) load(O.cur); else audio.play().catch(() => {}); }
        else fetchTrack(O.cur, false);
        refresh(); report(false); return true;
      case 'skip': next(true); return true;
      case 'prev': prev(); return true;
      case 'seek': {
        O.follow = null;
        const pos = Math.max(0, +kw.pos || 0);
        if (O.cur && O.cur.src) audio.currentTime = pos; else O.startAt = pos;
        refresh(); report(false); return true;
      }
      case 'set_repeat': O.repeat = ['off', 'all', 'one'].includes(kw.mode) ? kw.mode : 'off'; refresh(); return true;
      case 'shuffle': shuffleArr(O.q); refresh(); prefetch(); return true;
      case 'set_radio':
        O.radio = !!kw.on; ls.set('radio', O.radio);
        if (O.radio && O.cur && O.q.length < 2) fetchRadio(O.cur, false, false);
        refresh(); return true;
      case 'radio_now': if (O.cur) fetchRadio(O.cur, false, true); return true;
      case 'queue_remove': {
        const i = O.q.findIndex((t) => t.uid === kw.uid);
        if (i >= 0) O.q.splice(i, 1);
        emptied(); refresh(); prefetch(); return true;
      }
      case 'queue_move': {
        const i = O.q.findIndex((t) => t.uid === kw.uid);
        if (i >= 0) { const [t] = O.q.splice(i, 1); O.q.splice(Math.max(0, Math.min(O.q.length, +kw.to || 0)), 0, t); }
        refresh(); prefetch(); return true;
      }
      case 'queue_clear': O.q = []; emptied(); refresh(); return true;
      case 'play_index': {
        const i = O.q.findIndex((t) => t.uid === kw.uid);
        if (i >= 0) { const [t] = O.q.splice(i, 1); start(t, 0, false); }
        return true;
      }
      case 'prepare': return true;
      case 'album_play': {
        const tr = AL.cur && AL.cur.id === kw.id ? (AL.cur.tracks || []).map(meta) : [];
        if (!tr.length) { toast('Abre el disco para ponerlo'); return true; }
        if (kw.shuffle) shuffleArr(tr);
        O.q = []; O.follow = null;
        addTracks(tr, true);
        return true;
      }
      case 'album_add': {
        let t = null;
        if (kw.current) t = O.cur;
        else if (kw.uid != null) t = O.q.find((x) => x.uid === kw.uid);
        else return false;   // ya trae las canciones: va tal cual al servidor
        if (t) rs('album_add', { id: kw.id, tracks: [meta(t)] });
        return true;
      }
      case 'lyrics':
        if (O.cur) rs('lyrics', { webpage_url: O.cur.webpage_url, title: O.cur.title, uploader: O.cur.uploader, duration: O.cur.duration });
        return true;
    }
    return false;
  };
  // vaciar la lista con la radio prendida la apaga (si no, se vuelve a llenar en bucle)
  function emptied() {
    if (!O.q.length && O.radio) { O.radio = false; ls.set('radio', false); toast('Vaciaste la lista: la radio se apagó'); }
  }

  /* ---------- respuestas del servidor ---------- */
  O.onReady = function (d) {
    const all = [O.cur, ...O.q].filter((t) => t && t.webpage_url === d.url);
    all.forEach((t) => {
      t.asking = null;
      if (d.error) { t.failed = true; return; }
      t.src = d.src;
      ['title', 'uploader', 'duration', 'art_url'].forEach((k) => { if (d[k] && (!t[k] || t[k] === 'Cargando…')) t[k] = d[k]; });
    });
    const c = O.cur;
    if (c && c.webpage_url === d.url) {
      if (!d.error) fixHist(c);
      if (d.error) {
        toast(d.error);
        if (O.want) setTimeout(() => { if (O.cur === c) next(false); }, 1500);
      } else if (O.want) load(c);
    }
    refresh();
  };
  O.onTracks = function (d) {
    if (d.error) toast(d.error);
    if (!(d.tracks || []).length) { if (!d.error) toast('No encontré eso'); return; }
    addTracks(d.tracks, d.now);
    if (d.name || d.tracks.length > 1) toast((d.tracks.length) + ' canciones' + (d.name ? ' de «' + d.name + '»' : '') + ' en tu lista');
  };
  O.onRecs = function (d) {
    if (d.tag === 'radio') return takeRadio(d.items);
    O.recs = { items: d.items || [], at: Date.now(), key: O.recs.key, loading: false };
    renderHome();
  };
  O.loadRecs = function (force, other) {
    if (!O.on || !S.connected || !B) return;
    let seeds = O.hist.slice(0, 3).map((t) => t.webpage_url);
    if (other && O.hist.length > 1) seeds = shuffleArr(O.hist.slice(0, 15)).slice(0, 2).map((t) => t.webpage_url);
    const key = seeds.join('|');
    if (!force && O.recs.at && key === O.recs.key && Date.now() - O.recs.at < 15 * 60 * 1000) return;
    if (O.recs.loading && !force) return;
    O.recs.key = key; O.recs.loading = true;
    rs('recs', { seeds: seeds, tag: 'home' });
    clearTimeout(O.recsT);
    O.recsT = setTimeout(() => { if (O.recs.loading) { O.recs.loading = false; O.recs.at = Date.now() - 14 * 60 * 1000; renderHome(); } }, 25000);
    renderHome();
  };
  O.onConnected = function () { if (O.on && O.cur) report(false); };

  /* ---------- quién escucha qué / escuchar con alguien ---------- */
  function targets() {
    const g = S.group || {};
    const out = [];
    const np = g.now_playing;
    if (np && np.webpage_url) {
      out.push({ id: '@discord', who: 'Discord', by: np.who, track: np, paused: !!np.paused,
        elapsed: (+np.elapsed || 0) + (np.paused ? 0 : (performance.now() - (S.groupAt || performance.now())) / 1000) });
    }
    (g.listening || []).forEach((e) => {
      if (e.who === S.me || !e.webpage_url) return;
      out.push({ id: e.who, who: e.who, track: e, paused: !!e.paused,
        elapsed: (+e.elapsed || 0) + (e.paused ? 0 : Math.max(0, Date.now() / 1000 - (e.at || 0))) });
    });
    return out;
  }
  O.followToggle = function (id) {
    if (O.follow === id) { O.follow = null; toast('Ya no estás siguiendo a nadie'); refresh(); return; }
    O.follow = id;
    unlock();
    syncFollow(true);
    const tg = targets().find((x) => x.id === id);
    if (tg) toast(id === '@discord' ? 'Escuchando lo mismo que en Discord' : 'Escuchando con ' + tg.who);
    O.goHome(false);
  };
  function syncFollow(force) {
    const tg = targets().find((x) => x.id === O.follow);
    if (!tg) {
      if (O.follow) { toast((O.follow === '@discord' ? 'Discord' : O.follow) + ' dejó de escuchar'); O.follow = null; refresh(); }
      return;
    }
    const url = tg.track.webpage_url;
    if (!O.cur || O.cur.webpage_url !== url) {
      const m = Object.assign(meta(tg.track), metaFor(url) || {});
      start(mk(m), tg.elapsed, true);
    } else if (force && O.cur.src && Math.abs(audio.currentTime - tg.elapsed) > 4) audio.currentTime = tg.elapsed;
    if (tg.paused && O.want) { O.want = false; audio.pause(); refresh(); }
    else if (!tg.paused && !O.want && O.cur && !force) { O.intercept('resume', {}); }
  }
  O.onGroup = function () {
    const f = (S.group || {}).features || [];
    if (O.on && S.group && S.group.features && !f.includes('solo')) { O.on = false; O.want = false; audio.pause(); S.st = S.group; }
    if (O.on && O.follow) syncFollow(false);
  };

  /* ---------- avisarle al servidor qué suena aquí ---------- */
  function report(started) {
    if (!O.on) return;
    const c = O.cur;
    if (!c || O.ended) { rs('solo_status', { track: null }); return; }
    rs('solo_status', { track: meta(c), elapsed: audio.currentTime || O.startAt || 0, paused: !O.want, started: !!started });
  }
  setInterval(() => { if (O.on && O.cur && O.want) report(false); }, 45000);

  /* ---------- entrar / salir del modo solo ---------- */
  O.toggle = function () {
    if (!O.on) {
      O.on = true; unlock();
      O.home = false;
      toast('Modo solo: la música suena en tu celular 🎧', 2400);
      O.loadRecs(false);
      if (O.cur) report(false);
    } else {
      report(false); rs('solo_status', { track: null });
      O.on = false; O.want = false; O.follow = null; O.home = false; audio.pause();
      toast('Volviste a lo del grupo');
      const np = (S.group || {}).now_playing;
      if (np) { S.elapsed = +np.elapsed || 0; S.elapsedAt = S.groupAt || performance.now(); }
    }
    ls.set('on', O.on);
    S.st = O.on ? O.view() : (S.group || S.st);
    closeSheet();
    renderAll();
    media();
  };
  O.goHome = function (on) {
    if (has('is-search')) closeSearch();
    if (has('is-sheet')) closeSheet();
    if (P.open) closePanel();
    O.home = !!on && O.on;
    renderAll();
    if (O.home) O.loadRecs(false);
  };
  ACT.recsMore = () => O.loadRecs(true, true);

  /* ---------- el inicio en modo solo ---------- */
  function cardHtml(r) {
    return '<button class="card" type="button" style="width:112px" data-play="' + esc(r.webpage_url) + '" data-now="1">' +
      '<div class="cv" style="width:112px;height:112px;border-radius:18px;' + coverStyle(r.art_url, r.title) + ';box-shadow:0 12px 24px -12px rgba(0,0,0,.6)"><span class="playdot">' + I.play + '</span></div>' +
      '<div class="ell" style="font-size:12px;font-weight:800;margin-top:7px">' + esc(r.title) + '</div>' +
      '<div class="ell" style="font-size:10.5px;font-weight:600;color:rgba(244,242,250,.55)">' + esc(r.uploader || '') + '</div></button>';
  }
  O.renderHome = function () {
    const tg = O.on ? targets() : [];
    $('hlisten').classList.toggle('hide', !O.on || !tg.length);
    $('hrecs').classList.toggle('hide', !O.on || (!O.recs.items.length && !O.recs.loading));
    if (!O.on) return;
    const lsig = tg.map((x) => [x.id, x.track.webpage_url, x.paused, O.follow === x.id].join(',')).join('|');
    if ($('listenCards').dataset.sig !== lsig) {
      $('listenCards').dataset.sig = lsig;
      $('listenCards').innerHTML = tg.map((x) => {
        const dc = x.id === '@discord';
        const name = dc ? 'el grupo' : x.who;
        const label = dc ? 'En Discord' + (x.by ? ' · puso ' + x.by : '') : x.who;
        const on = O.follow === x.id;
        return '<div class="lcard' + (dc ? ' dc' : '') + '"><div class="lt"><span class="lc" style="' + coverStyle(x.track.art_url, x.track.title) + '"></span>' +
          '<span style="flex:1;min-width:0"><span class="who"><span class="av" style="background:' + (dc ? '#5865F2' : pcolor(x.who)) + '">' + (dc ? '♪' : initial(x.who)) + '</span>' +
          '<span class="ell">' + esc(label) + '</span><span class="live' + (x.paused ? ' off' : '') + '"></span></span>' +
          '<span class="t ell">' + esc(x.track.title) + '</span><span class="a ell">' + esc(x.track.uploader || '') + '</span></span></div>' +
          '<button class="btn go' + (on ? ' on' : '') + '" type="button" data-follow="' + esc(x.id) + '">' +
          (on ? '<span class="eqm"><i></i><i></i><i></i></span>Escuchando con ' + esc(name) : 'Escuchar con ' + esc(name)) + '</button></div>';
      }).join('');
    }
    const it = O.recs.items;
    const rsig = it.map((r) => r.webpage_url).join('|') + O.recs.loading;
    if ($('recCards').dataset.sig !== rsig) {
      $('recCards').dataset.sig = rsig;
      $('recCards').innerHTML = it.length ? it.map(cardHtml).join('')
        : '<div class="tip">Buscando canciones para ti…</div>';
    }
    if (!O.recs.at && !O.recs.loading) setTimeout(() => O.loadRecs(false), 0);
  };

  /* ---------- historial (para "Lo último que escuchaste" y las recomendaciones) ---------- */
  function addHist(t) {
    if (!t.webpage_url || String(t.webpage_url).startsWith('busca:')) return;
    O.hist = [meta(t)].concat(O.hist.filter((x) => x.webpage_url !== t.webpage_url)).slice(0, 30);
    ls.set('hist', O.hist);
  }
  // el título/portada pueden llegar después (al prepararla): se actualiza el historial
  function fixHist(t) {
    const h = O.hist.find((x) => x.webpage_url === t.webpage_url);
    if (h && (h.title === 'Cargando…' || !h.art_url)) { Object.assign(h, meta(t)); ls.set('hist', O.hist); }
  }

  /* ---------- la pantalla de bloqueo del celular (y audífonos) ---------- */
  const MS = 'mediaSession' in navigator ? navigator.mediaSession : null;
  if (MS) {
    const h = (k, f) => { try { MS.setActionHandler(k, f); } catch (e) {} };
    h('play', () => O.intercept('resume', {}));
    h('pause', () => O.intercept('pause', {}));
    h('nexttrack', () => O.intercept('skip', {}));
    h('previoustrack', () => O.intercept('prev', {}));
    h('seekto', (d) => O.intercept('seek', { pos: d.seekTime }));
  }
  function media() {
    if (!MS) return;
    const c = O.on ? O.cur : null;
    try {
      if (!c) { MS.metadata = null; MS.playbackState = 'none'; return; }
      const key = c.uid + '|' + c.title + '|' + c.art_url;
      if (O.msKey !== key) {
        O.msKey = key;
        MS.metadata = new MediaMetadata({ title: c.title || '', artist: c.uploader || '', album: 'Cumito',
          artwork: c.art_url ? [{ src: c.art_url, sizes: '480x360', type: 'image/jpeg' }] : [] });
      }
      MS.playbackState = O.want ? 'playing' : 'paused';
      if (MS.setPositionState && c.duration && isFinite(audio.currentTime)) {
        MS.setPositionState({ duration: c.duration, position: Math.min(c.duration, audio.currentTime || 0), playbackRate: 1 });
      }
    } catch (e) {}
  }

  /* ---------- eventos del audio ---------- */
  const isSilent = () => audio.src === SILENT || audio.src.startsWith('data:');
  audio.addEventListener('loadedmetadata', () => {
    if (isSilent()) return;
    if (O.startAt) { try { audio.currentTime = O.startAt; } catch (e) {} O.startAt = 0; }
    if (O.cur && !O.cur.duration && isFinite(audio.duration)) { O.cur.duration = Math.round(audio.duration); refresh(); }
  });
  audio.addEventListener('playing', () => {
    if (isSilent() || !O.on) return;
    if (O.cur) fixHist(O.cur);
    S.elapsed = audio.currentTime; S.elapsedAt = performance.now();
    if (!O.want) { O.want = true; refresh(); report(false); } else media();
  });
  // ¿se quedó parado en el final? (algunos celulares no avisan 'ended' porque el
  // archivo dice durar un poquito más de lo que dura de verdad)
  const atEnd = () => { const d = audio.duration || (O.cur && O.cur.duration) || 0; return d > 0 && audio.currentTime >= d - 1.2; };
  audio.addEventListener('pause', () => {
    // pausó el sistema (llamada, audífonos desconectados...): que la app lo muestre
    if (isSilent() || !O.on || audio.ended || !O.want || !O.cur || !O.cur.src) return;
    setTimeout(() => {
      if (!audio.paused || !O.want || audio.ended || audio.readyState < 2) return;
      if (atEnd()) return finished();
      O.want = false; refresh(); report(false);
    }, 400);
  });
  let endedUid = null;
  function finished() {
    if (!O.cur || endedUid === O.cur.uid) return;   // una sola vez por canción
    endedUid = O.cur.uid;
    if (O.follow) {
      // espera a que la otra persona pase a la siguiente; si en unos segundos no
      // llega nada (se le apagó el celular), sigue con tu lista
      O.want = false; refresh();
      const c = O.cur, who = O.follow;
      setTimeout(() => {
        if (O.follow === who && O.cur === c) {
          O.follow = null;
          toast('Se cortó la sala de ' + (who === '@discord' ? 'Discord' : who) + ': sigo con tu lista');
          next(false);
        }
      }, 7000);
      return;
    }
    if (O.repeat === 'one') { endedUid = null; audio.currentTime = 0; audio.play().catch(() => {}); report(true); return; }
    next(false);
  }
  audio.addEventListener('ended', () => { if (!isSilent() && O.on) finished(); });
  // por si el celular no avisó: cada 2 s revisa si la canción ya terminó
  setInterval(() => {
    if (!O.on || !O.cur || !O.want || isSilent() || !O.cur.src) return;
    if (audio.ended || (audio.paused && audio.readyState >= 2 && atEnd())) finished();
  }, 2000);
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden && O.on && O.cur && O.want && (audio.ended || atEnd())) finished();
  });
  audio.addEventListener('error', () => {
    if (isSilent() || !O.on || !O.cur) return;
    const c = O.cur;
    if (!c.retried) { c.retried = true; c.src = null; fetchTrack(c, false); return; }   // se borró del caché: pedirla de nuevo
    toast('No pude reproducir «' + (c.title || 'esa canción') + '»');
    setTimeout(() => { if (O.cur === c) next(false); }, 1200);
  });
  let lastTick = 0;
  audio.addEventListener('timeupdate', () => {
    if (isSilent() || !O.on) return;
    const now = performance.now();
    if (now - lastTick < 900) return;
    lastTick = now;
    S.elapsed = audio.currentTime; S.elapsedAt = now;
    if (S.st.now_playing) S.st.now_playing.elapsed = audio.currentTime;
    saveSoon();
  });

  function unlock() {
    if (O.unlocked) return;
    O.unlocked = true;
    if (audio.src && !isSilent()) return;
    audio.src = SILENT;
    audio.play().then(() => { if (isSilent()) audio.pause(); }).catch(() => { O.unlocked = false; });
  }
  document.addEventListener('touchend', () => { if (O.on && !O.unlocked) unlock(); }, { passive: true });
  document.addEventListener('click', () => { if (O.on && !O.unlocked) unlock(); });

  /* ---------- seguir donde quedó al volver a abrir la app ---------- */
  let saveT = null;
  function saveSoon() {
    if (saveT) return;
    saveT = setTimeout(() => {
      saveT = null;
      ls.set('sess', { cur: O.cur ? meta(O.cur) : null, at: audio.currentTime || O.startAt || 0, q: O.q.slice(0, 200).map((t) => Object.assign(meta(t), { radio: !!t.radio })), repeat: O.repeat });
    }, 4000);
  }
  if (window.CUMITO_MOBILE) {
    O.on = !!ls.get('on', false);
    const s = ls.get('sess', null);
    if (s && s.cur && s.cur.webpage_url) {
      O.cur = mk(s.cur); O.startAt = s.at || 0; O.want = false;
      O.q = (s.q || []).map((m) => mk(m, { radio: m.radio }));
      O.repeat = s.repeat || 'off';
    }
    if (O.on) { S.st = O.view(); renderAll(); }
  }
})();

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
  const isSilent = () => !audio.src || audio.src === SILENT || audio.src.startsWith('data:');

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
        duration: c.duration || 0,
        paused: !O.want, elapsed: elapsed(), req: c.req, who: null,
        with: tg ? (tg.id === '@discord' ? 'el grupo' : tg.who) : null,
      } : null,
      queue: O.q.map((t) => ({ uid: t.uid, req: t.req, title: t.title || 'Cargando…', uploader: t.uploader, duration: t.duration,
        art_url: t.art_url, prepared: true, ready: true, loading: false, radio: !!t.radio, who: t.radio ? 'Radio' : S.me })),
      repeat: O.repeat, radio: O.radio, sleep: null,
      can_prev: O.played.length > 0 || elapsed() > 5,
      features: (g.features || []).filter((f) => f !== 'react' && f !== 'sleep' && f !== 'normalize'),
      recent: O.hist.slice(0, 10),
    });
  };
  function refresh() {
    if (!O.on) return;
    S.st = O.view();
    S.elapsed = elapsed(); S.elapsedAt = performance.now();
    renderAll();
    if (P.open === 'lyrics') lyricsFollow();
    updateAddedTiles();
    media();
    saveSoon();
  }

  /* ---------- reproducir: UNA transmisión continua ----------
     El servidor arma un solo audio sin fin con tu lista (solostream.py). Así
     el celular nunca tiene que "empezar otra canción": con la pantalla apagada
     la música sigue sola. Por el WebSocket nos dice en qué segundo de la
     transmisión empieza cada canción (solo_seg) para mostrar la correcta. */
  let reqN = 0, planT = null, lastRe = 0, reTries = 0;
  // avisos al servidor para poder ver qué pasa en el celular (journalctl -u cumito)
  function slog(ev, extra) { try { rs('solo_log', Object.assign({ ev: ev, hidden: document.hidden, t: (O.cur && O.cur.title) || null }, extra || {})); } catch (e) {} }
  function plan() {
    const list = O.follow ? [O.cur] : [O.cur].concat(O.q);
    return list.filter(Boolean).map((t) => Object.assign(meta(t), { uid: t.uid }));
  }
  function planOpts() { return { repeat: O.follow ? 'off' : O.repeat, radio: !!(O.radio && !O.follow) }; }
  function sendPlan() {
    clearTimeout(planT);
    planT = setTimeout(() => { if (O.sid && O.stream) rs('solo_plan', Object.assign({ sid: O.sid, items: plan() }, planOpts())); }, 250);
  }
  function curSeg() {
    const st = O.stream;
    if (!st || !st.segs.length) return null;
    const t = audio.currentTime + 0.05;
    let sg = null;
    for (const x of st.segs) if (x.t0 <= t) sg = x;
    return sg;
  }
  function elapsed() {
    const sg = curSeg();
    if (sg && O.cur && sg.uid === O.cur.uid && !isSilent()) return Math.max(0, sg.base + audio.currentTime - sg.t0);
    return O.startAt || 0;
  }
  O.elapsed = elapsed;
  function findUid(uid) { if (O.cur && O.cur.uid === uid) return O.cur; return O.q.find((t) => t.uid === uid) || null; }
  function pushPlayed(t) { O.played.push(t); if (O.played.length > 60) O.played.shift(); }
  function playFrom(t, pos, keepFollow) {
    if (!t) return;
    if (!feat('solo_stream')) { toast('El servidor se está actualizando. Prueba en un minuto'); O.cur = O.cur || t; refresh(); return; }
    if (O.cur && O.cur !== t && !O.q.includes(O.cur)) pushPlayed(O.cur);
    O.cur = t; O.want = true; O.ended = false; O.startAt = pos || 0;
    if (!keepFollow) O.follow = null;
    addHist(t);
    O.stream = null; O.endAnnounced = false;
    if (!isSilent()) audio.pause();
    rs('solo_play', Object.assign({ sid: O.sid, req: ++reqN, items: plan(), uid: t.uid, pos: pos || 0 }, planOpts()));
    refresh();
  }
  O.onStream = function (d) {
    if (d.req !== reqN) return;
    O.sid = d.sid; O.stream = { id: d.stream, segs: [] }; O.endAnnounced = false;
    audio.src = d.url;
    if (O.want) audio.play().catch((err) => {
      slog('play-fail', { err: String(err && err.name) });
      if (document.hidden) { O.pendingPlay = true; return; }
      O.want = false; refresh(); toast('Toca ▶ para empezar');
    });
  };
  O.onSeg = function (d) {
    if (!O.stream || d.stream !== O.stream.id) return;
    if (!d.t0) O.stream.segs = [];
    O.stream.segs.push({ uid: d.uid, t0: d.t0, base: d.base });
    const t = findUid(d.uid);
    if (t && d.item) ['title', 'uploader', 'duration', 'art_url'].forEach((k) => { if (d.item[k] && (!t[k] || t[k] === 'Cargando…')) t[k] = d.item[k]; });
    reTries = 0;
    sync();
    refresh();
  };
  O.onPlanAdd = function (d) {
    if (d.sid !== O.sid) return;
    (d.items || []).forEach((it) => { if (!findUid(it.uid)) O.q.push(mk(it, { uid: it.uid, radio: true })); });
    refresh();
  };
  O.onEnd = function (d) { if (O.stream && d.stream === O.stream.id) O.endAnnounced = true; };
  // ¿ya va sonando la siguiente en la transmisión? -> la pantalla avanza sola
  function sync() {
    const sg = curSeg();
    if (!sg || (O.cur && sg.uid === O.cur.uid)) return;
    const i = O.q.findIndex((t) => t.uid === sg.uid);
    if (i < 0) return;
    const skipped = O.q.splice(0, i);   // las que el servidor no pudo preparar
    const t = O.q.shift();
    if (O.cur) { if (O.repeat === 'all') O.q.push(O.cur); else pushPlayed(O.cur); }
    skipped.forEach(pushPlayed);
    O.cur = t;
    addHist(t);
    refresh();
    sendPlan();
  }
  function next(manual) {
    if (manual) O.follow = null;
    const t = O.q.shift();
    if (!t) {
      if (O.radio && O.cur) { fetchRadio(O.cur, true, false); if (manual) toast('Buscando parecidas…', 1400); }
      else stopAtEnd();
      return;
    }
    if (O.repeat === 'all' && O.cur) O.q.push(O.cur);
    playFrom(t, 0, false);
  }
  function stopAtEnd() {
    O.want = false; O.ended = true;
    if (!isSilent()) audio.pause();
    if (O.sid) rs('solo_stop', { sid: O.sid });
    refresh(); report(false);
  }
  function prev() {
    O.follow = null;
    if (elapsed() > 5 || !O.played.length) { playFrom(O.cur, 0, false); return; }
    const p = O.played.pop();
    if (O.cur) O.q.unshift(O.cur);
    O.cur = null;
    playFrom(p, 0, false);
  }
  function addTracks(list, now, req) {
    const items = (list || []).filter((m) => m && m.webpage_url).map((m) => mk(m, { req: req, radio: !!m.radio }));
    if (!items.length) return;
    if (now) { O.q.unshift.apply(O.q, items.slice(1)); playFrom(items[0], 0, false); return; }
    O.q.push.apply(O.q, items);
    if (!O.cur || (O.ended && !O.want)) playFrom(O.q.shift(), 0, false);
    else { sendPlan(); refresh(); }
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
    if (O.radioStart && !O.follow) next(false); else { sendPlan(); refresh(); }
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
      case 'pause':
        O.want = false; audio.pause();
        if (O.sid) rs('solo_pause', { sid: O.sid, elapsed: elapsed() });
        refresh(); return true;
      case 'resume':
        if (!O.cur) return true;
        if (O.ended || !O.stream || isSilent()) { playFrom(O.cur, O.ended ? 0 : elapsed(), true); return true; }
        O.want = true;
        audio.play().catch(() => playFrom(O.cur, elapsed(), true));
        rs('solo_resume', { sid: O.sid, elapsed: elapsed() });
        refresh(); return true;
      case 'skip': next(true); return true;
      case 'prev': prev(); return true;
      case 'seek': {
        const pos = Math.max(0, +kw.pos || 0);
        if (O.cur) { if (O.want || O.stream) playFrom(O.cur, pos, false); else { O.startAt = pos; refresh(); } }
        return true;
      }
      case 'set_repeat': O.repeat = ['off', 'all', 'one'].includes(kw.mode) ? kw.mode : 'off'; sendPlan(); refresh(); return true;
      case 'shuffle': shuffleArr(O.q); sendPlan(); refresh(); return true;
      case 'set_radio':
        O.radio = !!kw.on; ls.set('radio', O.radio);
        sendPlan(); refresh(); return true;
      case 'radio_now': if (O.cur) fetchRadio(O.cur, false, true); return true;
      case 'queue_remove': {
        const i = O.q.findIndex((t) => t.uid === kw.uid);
        if (i >= 0) O.q.splice(i, 1);
        emptied(); sendPlan(); refresh(); return true;
      }
      case 'queue_move': {
        const i = O.q.findIndex((t) => t.uid === kw.uid);
        if (i >= 0) { const [t] = O.q.splice(i, 1); O.q.splice(Math.max(0, Math.min(O.q.length, +kw.to || 0)), 0, t); }
        sendPlan(); refresh(); return true;
      }
      case 'queue_clear': O.q = []; emptied(); sendPlan(); refresh(); return true;
      case 'play_index': {
        const i = O.q.findIndex((t) => t.uid === kw.uid);
        if (i >= 0) { const [t] = O.q.splice(i, 1); playFrom(t, 0, false); }
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
  O.onReady = function () {};   // (de la versión anterior, ya no se usa)
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
  O.onConnected = function () {
    if (!O.on || !O.cur) return;
    report(false);
    if (O.sid && O.stream) sendPlan();   // el servidor vuelve a saber a quién avisarle
  };

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
      playFrom(mk(m), tg.elapsed, true);
    } else if (force && Math.abs(elapsed() - tg.elapsed) > 5) playFrom(O.cur, tg.elapsed, true);
    if (tg.paused && O.want) { O.want = false; audio.pause(); if (O.sid) rs('solo_pause', { sid: O.sid, elapsed: elapsed() }); refresh(); }
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
    rs('solo_status', { track: meta(c), elapsed: elapsed(), paused: !O.want, started: !!started });
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
      if (O.sid) rs('solo_stop', { sid: O.sid });
      O.on = false; O.want = false; O.follow = null; O.home = false; audio.pause(); O.stream = null;
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
      if (MS.setPositionState && c.duration) {
        MS.setPositionState({ duration: c.duration, position: Math.min(c.duration, elapsed()), playbackRate: 1 });
      }
    } catch (e) {}
  }

  /* ---------- eventos del audio ---------- */
  audio.addEventListener('playing', () => {
    if (isSilent() || !O.on) return;
    if (O.cur) fixHist(O.cur);
    S.elapsed = elapsed(); S.elapsedAt = performance.now();
    if (!O.want) { O.want = true; if (O.sid) rs('solo_resume', { sid: O.sid, elapsed: elapsed() }); refresh(); } else media();
  });
  audio.addEventListener('pause', () => {
    // pausó el sistema (llamada, audífonos desconectados...): que la app lo muestre
    if (isSilent() || !O.on || audio.ended || !O.want || !O.stream) return;
    setTimeout(() => {
      if (!audio.paused || !O.want || audio.ended || audio.readyState < 2) return;
      O.want = false; if (O.sid) rs('solo_pause', { sid: O.sid, elapsed: elapsed() }); refresh();
    }, 400);
  });
  // se cortó la transmisión sin que el servidor dijera "se acabó" (internet,
  // el celular cerró la conexión...): se retoma donde iba
  function reconnect(why) {
    if (!O.cur || !O.want) return;
    if (Date.now() - lastRe < 4000 || reTries >= 4) {
      if (reTries >= 4) { slog('give-up', { why: why }); O.want = false; refresh(); toast('Se cortó la música. Toca ▶ para seguir'); }
      return;
    }
    lastRe = Date.now(); reTries++;
    slog('reconnect', { why: why, at: Math.round(elapsed()) });
    sync();
    playFrom(O.cur, elapsed(), true);
  }
  audio.addEventListener('ended', () => {
    if (isSilent() || !O.on) return;
    sync();
    if (!O.endAnnounced && O.want) return reconnect('ended');
    if (O.follow) {
      // espera a que la otra persona pase a la siguiente; si no llega nada, sigue con tu lista
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
    O.want = false; O.ended = true; refresh(); report(false);
  });
  audio.addEventListener('error', () => { if (!isSilent() && O.on && O.stream) reconnect('error'); });
  document.addEventListener('visibilitychange', () => {
    if (document.hidden || !O.on || !O.cur) return;
    sync();
    if (O.pendingPlay && O.want) { O.pendingPlay = false; audio.play().catch(() => playFrom(O.cur, elapsed(), true)); return; }
    refresh();
  });
  let lastTick = 0;
  audio.addEventListener('timeupdate', () => {
    if (isSilent() || !O.on) return;
    const now = performance.now();
    if (now - lastTick < 700) return;
    lastTick = now;
    sync();
    S.elapsed = elapsed(); S.elapsedAt = now;
    if (S.st.now_playing) S.st.now_playing.elapsed = S.elapsed;
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
      ls.set('sess', { cur: O.cur ? meta(O.cur) : null, at: elapsed(), q: O.q.slice(0, 200).map((t) => Object.assign(meta(t), { radio: !!t.radio })), repeat: O.repeat });
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

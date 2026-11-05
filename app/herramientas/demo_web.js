// Hace de "Python" para probar la página en un navegador común (sin Cumito).
(function () {
  const T = window.CUMITO_TEST;
  const sent = window.SENT = [];
  const ev = (type, d) => T.onEvent(type, JSON.stringify(d));
  const C = (a, b, c) => 'data:image/svg+xml;utf8,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="400" height="400"><defs><radialGradient id="g" cx="25%" cy="20%" r="80%"><stop offset="0" stop-color="' + b + '"/><stop offset="1" stop-color="' + a + '"/></radialGradient></defs><rect width="400" height="400" fill="url(#g)"/><circle cx="300" cy="300" r="140" fill="' + c + '" opacity=".55"/></svg>');
  const ART = [C('#E0457B', '#F7A35C', '#6C4CF5'), C('#22A699', '#F2D16B', '#1F5FBF'), C('#B8323A', '#E9C46A', '#3A2D6B'), C('#6E8B2A', '#C7D45A', '#3B2152'), C('#E87AA4', '#7FD1F7', '#5A3FC0'), C('#3A7BD5', '#F06D4F', '#7B2FF7')];
  window.ART = ART;
  T.setBridge({
    send: (a, kw) => { sent.push([a, JSON.parse(kw)]); (window.ON_SEND || (() => {}))(a, JSON.parse(kw)); },
    search: (q, l, o, k) => { sent.push(['search', q, k]); setTimeout(() => ev('search_results', { query: q, kind: k, offset: o, results: [
      ['DtMF', 'Bad Bunny', 237], ['Tití Me Preguntó', 'Bad Bunny', 243], ['Ojitos Lindos', 'Bad Bunny, Bomba Estéreo', 258], ['Me Porto Bonito', 'Bad Bunny, Chencho Corleone', 178],
      ['Callaita', 'Bad Bunny, Tainy', 250], ['Yo Perreo Sola', 'Bad Bunny', 172], ['La Canción', 'J Balvin, Bad Bunny', 242], ['Safaera', 'Bad Bunny', 295]].map((r, i) => ({ title: r[0], uploader: r[1], duration: r[2], webpage_url: 'https://yt/' + i, art_url: ART[i % 6] })) }), 700); },
    win_cmd: (c) => sent.push(['win', c]), save: (k, v) => sent.push(['save', k, JSON.parse(v)]), pick_cover: () => {}, ready: () => {},
  });
  window.ev = ev;
  ev('config', { name: 'Juan', recent_searches: ['bad bunny', 'travis scott', 'la bachata', 'queen'], visual: {}, scale: 1 });
})();

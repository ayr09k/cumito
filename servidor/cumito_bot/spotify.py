"""
Enlaces de Spotify: Spotify no deja sacar su audio, así que se lee qué
canciones son (nombre y artista, desde su página pública para "insertar")
y cada una se busca en YouTube Music recién cuando le toca prepararse.
Solo es una consulta por internet: corre en el carril liviano.
"""
from __future__ import annotations

import json
import re
import urllib.request

from .extractor import SEARCH_PREFIX

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Safari/537.36")
_LINK = re.compile(r"(?:open\.spotify\.com/(?:intl-[a-z]{2}/)?|spotify:)(track|album|playlist)[/:]([A-Za-z0-9]{10,})")


def is_spotify(q: str) -> bool:
    return bool(_LINK.search(q or ""))


def kind(q: str) -> str | None:
    m = _LINK.search(q or "")
    return m.group(1) if m else None


def _artists(x) -> str | None:
    names = [a.get("name") for a in (x.get("artists") or []) if isinstance(a, dict) and a.get("name")]
    if names:
        return ", ".join(names)
    return x.get("subtitle") or None


def _cover(x) -> str | None:
    srcs = ((x.get("coverArt") or {}).get("sources") or []) or (x.get("visualIdentity") or {}).get("image") or []
    srcs = [s for s in srcs if isinstance(s, dict) and s.get("url")]
    if not srcs:
        return None
    srcs.sort(key=lambda s: -(s.get("width") or s.get("maxWidth") or 0))
    return srcs[0]["url"]


def _secs(ms):
    try:
        return int(ms) // 1000 if ms else None
    except (TypeError, ValueError):
        return None


def _track(title, artist, duration, art):
    terms = f"{artist} - {title}" if artist else title
    return {"title": title, "uploader": artist, "duration": duration, "art_url": art,
            "webpage_url": SEARCH_PREFIX + terms, "source": "spotify"}


def resolve(url: str) -> dict:
    """-> {"kind", "title", "tracks": [...]}. Cada canción trae
    webpage_url = "busca:Artista - Título" (el extractor la busca)."""
    m = _LINK.search(url or "")
    if not m:
        raise ValueError("Ese enlace de Spotify no se entiende")
    k, sid = m.group(1), m.group(2)
    req = urllib.request.Request(f"https://open.spotify.com/embed/{k}/{sid}",
                                 headers={"User-Agent": UA, "Accept-Language": "es,en;q=0.8"})
    with urllib.request.urlopen(req, timeout=12) as r:
        html = r.read().decode("utf-8", "replace")
    nd = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.S)
    if not nd:
        raise ValueError("Spotify no mostró las canciones (¿es privada?)")
    data = json.loads(nd.group(1))
    ent = (((data.get("props") or {}).get("pageProps") or {}).get("state") or {}).get("data", {}).get("entity") or {}
    if not ent:
        raise ValueError("Spotify no mostró las canciones (¿es privada?)")
    name = ent.get("name") or ent.get("title")
    cover = _cover(ent)
    if k == "track":
        return {"kind": k, "title": name,
                "tracks": [_track(name, _artists(ent), _secs(ent.get("duration")), cover)]}
    tracks = []
    for t in ent.get("trackList") or []:
        if not isinstance(t, dict) or not t.get("title"):
            continue
        tracks.append(_track(t["title"], t.get("subtitle") or _artists(t), _secs(t.get("duration")), cover))
    return {"kind": k, "title": name, "tracks": tracks}

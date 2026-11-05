"""Prueba con internet de verdad las piezas nuevas del servidor 2.0
(Spotify, letras de LRCLIB, radio de YouTube Music, búsquedas y preparar una
canción) y guarda el resultado. Corre en GitHub (la VM no se toca)."""
import json, sys, time, traceback
sys.path.insert(0, "servidor")
from cumito_bot import extractor as X, lyrics, spotify

out = {}
def probar(nombre, fn, *a):
    t = time.time()
    try:
        r = fn(*a)
        out[nombre] = {"ok": True, "segundos": round(time.time() - t, 2), "resultado": r}
    except Exception as e:
        out[nombre] = {"ok": False, "segundos": round(time.time() - t, 2), "error": repr(e)[:300],
                       "traza": traceback.format_exc()[-1500:]}

def corto(d):
    if isinstance(d, dict) and "tracks" in d:
        return {**d, "n": len(d["tracks"]), "tracks": d["tracks"][:4]}
    return d

probar("spotify canción", lambda: corto(spotify.resolve("https://open.spotify.com/track/3n3Ppam7vgaVa1iaRUc9Lp")))
probar("spotify álbum", lambda: corto(spotify.resolve("https://open.spotify.com/album/4aawyAB9vmqN3uQ7FjRGTy")))
probar("spotify playlist", lambda: corto(spotify.resolve("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M")))
for t, a, d in [("Ojitos Lindos", "Bad Bunny, Bomba Estéreo", 258),
                ("Daddy Yankee - Gasolina (Video Oficial)", "DaddyYankeeVEVO", 193),
                ("La Bachata", "Manuel Turizo", 162),
                ("Bohemian Rhapsody (Remastered 2011)", "Queen - Topic", 355)]:
    probar(f"letra {t}", lambda t=t, a=a, d=d: {**(r := lyrics.fetch(t, a, d)),
                                                 "synced": (r.get("synced") or "")[:160],
                                                 "plain": (r.get("plain") or "")[:80]})
probar("búsqueda música", lambda: X.search_sync("ojitos lindos", 4, 0, "music"))
semilla = (out["búsqueda música"].get("resultado") or [{}])[0].get("webpage_url") or "https://www.youtube.com/watch?v=7GDp7S1HgSk"
probar("radio", lambda: X.radio_sync(semilla, 8))
probar("resolver 'busca:'", lambda: X._resolve_search("Bad Bunny - Tití Me Preguntó"))
probar("preparar 'busca:'", lambda: {k: v for k, v in X._extract_sync("busca:Bad Bunny - Tití Me Preguntó").items()
                                     if k in ("title", "webpage_url", "duration", "uploader", "source")})
open(sys.argv[1], "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False, indent=1))
print({k: v["ok"] for k, v in out.items()})

"""
Formato de los mensajes que viajan entre este servidor y las apps Cumito
de todo el grupo, sobre un WebSocket simple, en JSON.

App -> Servidor:
    {"type": "hello", "name": "Juan"}
    {"type": "command", "action": "play", "query": "..."}
    {"type": "command", "action": "pause" | "resume" | "skip" | "stop"}
    {"type": "command", "action": "stop_and_leave"}
    {"type": "command", "action": "queue_remove", "index": 2, "uid": 42}
    {"type": "command", "action": "queue_move", "uid": 42, "to": 0}     # reordenar (solo preparadas)
    {"type": "command", "action": "queue_clear"}
    {"type": "command", "action": "set_volume", "value": 0.6}
    {"type": "command", "action": "search", "query": "...", "limit": 8, "offset": 0,
     "kind": "music" | "all"}   # music = como YouTube Music (versiones de audio)
    {"type": "command", "action": "play", "query": "<link>", "as_playlist": true}
    {"type": "command", "action": "playlist_preview", "url": "<link de playlist>"}
        -> responde solo a quien preguntó:
           {"type": "playlist_preview", "url": "...", "title": "...",
            "entries": [{"title", "duration", "uploader", "art_url"}, ...]}
    {"type": "command", "action": "play_index", "index": 3, "uid": 42}   # poner ya esa
    {"type": "command", "action": "prepare", "index": 3, "uid": 42}      # dejarla lista
    {"type": "command", "action": "activity_list"}
        -> responde solo a quien preguntó:
           {"type": "activity_list", "entries": [<actividad>, ...]}   # lo más viejo primero

  --- 2.0 (las apps viejas nunca mandan esto) ---
    {"type": "command", "action": "prev"}                      # atrás (o al inicio si lleva >5 s)
    {"type": "command", "action": "seek", "pos": 95}           # adelantar/atrasar (segundos)
    {"type": "command", "action": "set_repeat", "mode": "off" | "one" | "all"}
    {"type": "command", "action": "shuffle"}                   # mezclar la lista una vez
    {"type": "command", "action": "set_radio", "on": true}     # al acabarse la lista, parecidas
    {"type": "command", "action": "set_normalize", "on": true} # volumen parejo
    {"type": "command", "action": "sleep", "minutes": 30}      # 0 = quitar
    {"type": "command", "action": "sleep", "end_of_track": true}
    {"type": "command", "action": "react", "emoji": "🔥"}
    {"type": "command", "action": "lyrics"}                    # la que suena (o con webpage_url/title/uploader/duration)
        -> {"type": "lyrics", "key", "webpage_url", "found", "title", "artist",
            "synced": "[00:12.34] línea..." | None, "plain": "..." | None, "instrumental": bool}
           ("pending": true si la canción aún no se preparó: pedirla de nuevo luego)
    {"type": "command", "action": "stats", "period": "week" | "month" | "year" | "all", "who": "Juan"?}
        -> {"type": "stats", "plays", "minutes", "days", "skipped", "top_songs": [...],
            "top_artists": [...], "top_people": [...], "hours": [24 números], "first_ts"}
    Discos (todas responden solo a quien preguntó; si algo cambió, sube "albums_rev"
    en el estado de todos y las apps vuelven a pedir album_list):
    {"type": "command", "action": "album_list"}  -> {"type": "albums", "albums": [<disco>], "rev"}
    {"type": "command", "action": "album_get", "id": 3}  -> {"type": "album", "album": <disco + "tracks">}
    {"type": "command", "action": "album_cover", "cover": "<hash>"}  -> {"type": "album_cover", "cover", "data": b64 JPEG}
    {"type": "command", "action": "album_create", "name", "color": "#RRGGBB"?, "cover_b64"?, "note"?}
    {"type": "command", "action": "album_update", "id", "name"?, "color"?, "cover_b64"?, "remove_cover"?, "note"?}
    {"type": "command", "action": "album_delete", "id"}
    {"type": "command", "action": "album_add", "id", "current": true | "uid": 42 | "tracks": [...]}
        -> {"type": "album_added", "id", "added": n}
    {"type": "command", "action": "album_remove", "id", "track_id"}
    {"type": "command", "action": "album_move", "id", "track_id", "to"}
    {"type": "command", "action": "album_play", "id", "shuffle": false}
    <disco> = {"id", "name", "owner", "color", "cover": hash | None, "note", "count", "duration",
               "arts": [hasta 4 miniaturas], "created", "updated"}
    Errores de estas acciones: {"type": "error", "message": "...", "action": "..."}
    Enlaces de Spotify (canción, álbum o playlist) funcionan en "play" y "playlist_preview".

Servidor -> apps (se manda a todas cada vez que algo cambia):
    {
      "type": "state",
      "host_label": "Juan",
      "now_playing": {
          "title": "...", "duration": 213, "elapsed": 42,
          "art_url": "https://...jpg" | None,
      } | None,
      "queue": [{"uid": 42, "title": "...", "duration": 180, "uploader": "...",
                 "ready": true, "loading": false, "art_url": "..." | None}, ...],
      "members": ["Juan", "Pedro"],
      "volume": 0.6,
      "activity_last": {"id": 12, "ts": 1730000000.0, "who": "Juan", "kind": "add",
                        "text": "agregó 1 canción", "title": "...", "sub": "artista", "art": "url"} | None,
      "recent": [  # lo último que sonó, lo más nuevo primero (máx. 8)
          {"title": "...", "webpage_url": "...", "duration": 200,
           "art_url": "...", "uploader": "..."}, ...
      ],
      # 2.0 (las apps viejas los ignoran):
      "server_v": 2, "features": ["prev", "seek", ...],
      "repeat": "off" | "one" | "all", "radio": bool, "normalize": bool,
      "sleep": {"at": epoch | None, "eot": bool} | None, "can_prev": bool,
      "reaction": {"id", "who", "emoji", "ts"} | None,   # animar cuando cambia el id
      "albums_rev": 123,                                  # cambió algún Disco
      # now_playing y cada canción de la cola traen además "who" (quién la puso)
      # y "radio"; now_playing trae "webpage_url" y "source".
    }
    {"type": "error", "message": "..."}

Servidor -> la app que pidió una búsqueda (respuesta directa, no se difunde):
    {
      "type": "search_results",
      "query": "...",
      "results": [
          {"title": "...", "webpage_url": "...", "duration": 210,
           "art_url": "https://...jpg", "uploader": "..."},
          ...
      ],
    }
"""
import json
import time

PROTOCOL_VERSION = 2


def dumps(type_, **data):
    return json.dumps({"type": type_, "v": PROTOCOL_VERSION, "ts": time.time(), **data})


def loads(raw):
    data = json.loads(raw)
    if not isinstance(data, dict) or "type" not in data:
        raise ValueError("mensaje mal formado")
    return data


def hello(name):
    return dumps("hello", name=name)


def command(action, **kw):
    return dumps("command", action=action, **kw)


def state(host_label, now_playing, queue, members, volume=None):
    return dumps(
        "state",
        host_label=host_label,
        now_playing=now_playing,
        queue=queue,
        members=members,
        volume=volume,
    )


def search_results(query, results, offset=0, kind="all"):
    return dumps("search_results", query=query, results=results, offset=offset, kind=kind)


def error(message):
    return dumps("error", message=message)

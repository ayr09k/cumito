"""
Formato de los mensajes que viajan entre este servidor y las apps Cumito
de todo el grupo, sobre un WebSocket simple, en JSON.

App -> Servidor:
    {"type": "hello", "name": "Juan"}
    {"type": "command", "action": "play", "query": "..."}
    {"type": "command", "action": "pause" | "resume" | "skip" | "stop"}
    {"type": "command", "action": "stop_and_leave"}
    {"type": "command", "action": "queue_remove", "index": 2}
    {"type": "command", "action": "queue_clear"}
    {"type": "command", "action": "set_volume", "value": 0.6}
    {"type": "command", "action": "search", "query": "...", "limit": 8, "offset": 0}
    {"type": "command", "action": "play", "query": "<link>", "as_playlist": true}
    {"type": "command", "action": "playlist_preview", "url": "<link de playlist>"}
        -> responde solo a quien preguntó:
           {"type": "playlist_preview", "url": "...", "title": "...",
            "entries": [{"title", "duration", "uploader", "art_url"}, ...]}
    {"type": "command", "action": "play_index", "index": 3, "uid": 42}   # poner ya esa
    {"type": "command", "action": "prepare", "index": 3, "uid": 42}      # dejarla lista

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
      "recent": [  # lo último que sonó, lo más nuevo primero (máx. 8)
          {"title": "...", "webpage_url": "...", "duration": 200,
           "art_url": "...", "uploader": "..."}, ...
      ],
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


def search_results(query, results, offset=0):
    return dumps("search_results", query=query, results=results, offset=offset)


def error(message):
    return dumps("error", message=message)

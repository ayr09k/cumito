"""
Formato de los mensajes que viajan entre Cumito y el servidor, sobre un
WebSocket simple, en JSON. Ver el mismo archivo del lado del servidor
(CumitoServidor/cumito_bot/protocol.py) para la descripción completa --
los dos deben coincidir.
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


def search_results(query, results):
    return dumps("search_results", query=query, results=results)

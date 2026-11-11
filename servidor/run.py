"""
Cumito - servidor (bot de Discord + relay)
============================================
Esto es lo que corre 24/7 en tu VM (por ejemplo, una de Oracle Cloud).
No tiene ventana ni interfaz gráfica -- es un programa de consola que se
queda corriendo. Las apps "Cumito" de tu grupo se conectan a este
servidor por el puerto 8765.

La PRIMERA vez que lo corres, te pregunta por consola el token del bot,
el ID del servidor de Discord, el ID del canal de voz y un nombre para
mostrar -- y los guarda en config.json (al lado de este archivo). Las
siguientes veces arranca directo, sin preguntar nada.

Para cambiar algo después: edita config.json a mano, o bórralo para que
vuelva a preguntar.
"""
import asyncio
import time
import logging
import signal
import sys

from cumito_bot import config, protocol
from cumito_bot.relay import RelayServer

RELAY_PORT = 8765

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def _ask(prompt, numeric=False):
    while True:
        value = input(prompt).strip().strip('"').strip("'")
        if not value:
            print("  (no puede quedar vacío)")
        elif numeric and not value.isdigit():
            print("  (eso no parece un ID: tiene que ser solo números, ej. 123456789012345678)")
        else:
            return value


def _first_time_setup():
    print("=" * 60)
    print(" Cumito - configuración (esto solo se pregunta una vez)")
    print("=" * 60)
    cfg = config.load()
    cfg["token"] = _ask("Token del bot de Discord: ")
    cfg["guild_id"] = _ask("ID del servidor de Discord: ", numeric=True)
    print("\nEl bot entra solo al canal de voz donde esté la gente. Si quieres,")
    print("puedes darle un canal de respaldo para cuando no haya nadie conectado.")
    while True:
        ch = input("ID del canal de voz de respaldo (opcional, Enter para saltar): ").strip()
        if not ch or ch.isdigit():
            cfg["channel_id"] = ch
            break
        print("  (tiene que ser solo números, o déjalo vacío)")
    cfg["host_display_name"] = input("Tu nombre (como te verán en Cumito): ").strip() or "Admin"
    config.save(cfg)
    print("\nGuardado en config.json.\n")
    return cfg


class CumitoServer:
    """Igual que el bot + relay de siempre, solo que sin la parte de Qt:
    todo corre en un único loop de asyncio, en el hilo principal -- no
    hace falta un hilo aparte porque no hay ninguna interfaz que proteger."""

    def __init__(self, cfg):
        # se importa aquí (no arriba): los "ayudantes" que preparan canciones
        # vuelven a leer este archivo al arrancar, y así no cargan Discord
        from cumito_bot.bot import BotCore
        from cumito_bot.salud import Salud
        from cumito_bot.solo import Solo
        from cumito_bot.solostream import SoloStreams
        self.salud = Salud()
        self.relay = RelayServer(RELAY_PORT, on_command=self._on_relay_command)
        self.bot = BotCore(
            cfg["token"], int(cfg["guild_id"]),
            int(cfg["channel_id"]) if str(cfg.get("channel_id") or "").isdigit() else None,
            cfg.get("host_display_name") or "Admin",
            on_change=self._on_change,
        )
        self.solo = Solo(self.bot, self._on_change)
        self.solostreams = SoloStreams(self.solo, self._reply)

    def _on_change(self):
        snap = self.bot.snapshot()
        extra = {k: v for k, v in snap.items() if k not in ("host_label", "now_playing", "queue", "volume", "recent")}
        solo = getattr(self, "solo", None)
        if solo is not None:
            extra["listening"] = solo.listing()   # modo solo: quién escucha qué en su celular
        asyncio.create_task(self.relay.broadcast_state(
            snap["host_label"], snap["now_playing"], snap["queue"],
            volume=snap.get("volume"), recent=snap.get("recent"), **extra,
        ))

    @staticmethod
    async def _reply(ws, type_, **data):
        """Respuesta solo para quien preguntó (las apps viejas nunca piden
        estas cosas, así que nunca les llega un tipo que no conocen)."""
        if ws is None:
            return
        try:
            await ws.send(protocol.dumps(type_, **data))
        except Exception:
            pass

    async def _albums_changed(self, ws, album=None):
        # a todos: cambia "albums_rev" en el estado y las apps nuevas vuelven a pedir la lista
        self._on_change()
        if album is not None:
            await self._reply(ws, "album", album=album)

    async def _album_command(self, action, data, who, ws):
        bot, db = self.bot, self.bot.db
        aid = data.get("id")
        try:
            aid = int(aid) if aid is not None else None
        except (TypeError, ValueError):
            aid = None
        try:
            if action == "album_list":
                await self._reply(ws, "albums", albums=await db.run(db.albums), rev=db.albums_rev)
            elif action == "album_get":
                await self._reply(ws, "album", album=await db.run(db.album, aid), id=aid)
            elif action == "album_cover":
                h = str(data.get("cover") or "")
                await self._reply(ws, "album_cover", cover=h, data=await db.run(db.cover, h))
            elif action == "album_create":
                alb = await db.run(db.album_create, data.get("name", ""), who, data.get("color"),
                                   data.get("cover_b64"), data.get("note"))
                bot.log_activity(who, "album_new", f"creó el disco «{alb['name']}»", title=alb["name"])
                await self._albums_changed(ws, alb)
            elif action == "album_update":
                alb = await db.run(db.album_update, aid, data.get("name"), data.get("color"),
                                   data.get("cover_b64"), bool(data.get("remove_cover")), data.get("note"))
                if alb:
                    await self._albums_changed(ws, alb)
            elif action == "album_delete":
                name = await db.run(db.album_delete, aid)
                if name:
                    bot.log_activity(who, "album_del", f"borró el disco «{name}»", title=name)
                    await self._albums_changed(ws)
            elif action == "album_add":
                if data.get("current") or data.get("uid") is not None:
                    t = bot.track_for_album("current" if data.get("current") else "queue", data.get("uid"))
                    tracks = [t] if t else []
                else:
                    tracks = [t for t in (data.get("tracks") or []) if isinstance(t, dict)][:200]
                n = await db.run(db.album_add, aid, tracks, who)
                alb = await db.run(db.album, aid) if aid is not None else None
                if n and alb:
                    what = f"«{tracks[0].get('title')}»" if n == 1 else f"{n} canciones"
                    bot.log_activity(who, "album_add", f"guardó {what} en el disco «{alb['name']}»",
                                     title=tracks[0].get("title") if n == 1 else alb["name"],
                                     sub=tracks[0].get("uploader") if n == 1 else None,
                                     art=tracks[0].get("art_url") if n == 1 else None)
                await self._reply(ws, "album_added", id=aid, added=n)
                if n:
                    await self._albums_changed(ws, alb)
            elif action == "album_remove":
                if await db.run(db.album_remove, aid, int(data.get("track_id", -1))):
                    await self._albums_changed(ws, await db.run(db.album, aid))
            elif action == "album_move":
                if await db.run(db.album_move, aid, int(data.get("track_id", -1)), int(data.get("to", 0))):
                    await self._albums_changed(ws, await db.run(db.album, aid))
            elif action == "album_play":
                err = await bot.album_play(aid, shuffle=bool(data.get("shuffle")), who=who)
                if err:
                    await self._reply(ws, "error", message=err)
        except ValueError as e:   # p. ej. una imagen que no se pudo leer
            await self._reply(ws, "error", message=str(e)[:160], action=action)

    async def _room_command(self, action, data, who, ws):
        """Salas del modo solo: reacciones que ven todos, y pedirle una canción al dueño."""
        import json as _json
        rl = self._room_rl = getattr(self, "_room_rl", {})
        now = time.time()
        room = str(data.get("room") or "")[:40]
        if action == "room_react":
            kind = str(data.get("kind") or "")[:12]
            if not room or kind not in ("heart", "fire", "star", "jaja", "note") or now - rl.get(("r", who), 0) < 0.5:
                return
            rl[("r", who)] = now
            await self.relay.send_cap("m3", _json.dumps({"type": "room_react", "room": room, "who": who, "kind": kind}))
        elif action == "room_ask":
            t = data.get("track") or {}
            if not room or room == who or not str(t.get("webpage_url") or "").startswith("http"):
                return
            if now - rl.get(("a", who), 0) < 8:
                await self._reply(ws, "room_ask_done", ok=False, wait=True, track=t, by=room)
                return
            rl[("a", who)] = now
            self._ask_n = getattr(self, "_ask_n", 0) + 1
            track = {k: t.get(k) for k in ("title", "uploader", "webpage_url", "duration", "art_url")}
            msg = {"type": "room_ask", "id": self._ask_n, "from": who, "track": track,
                   "note": str(data.get("note") or "")[:80]}
            n = await self.relay.send_cap("m3", _json.dumps(msg), names={room})
            if not n:
                await self._reply(ws, "room_ask_done", ok=False, gone=True, track=track, by=room)
        elif action == "room_ask_reply":
            to = str(data.get("to") or "")[:32]
            msg = {"type": "room_ask_done", "ok": bool(data.get("ok")), "track": data.get("track") or {}, "by": who}
            await self.relay.send_cap("m3", _json.dumps(msg), names={to})

    async def _catalog_command(self, action, data, ws):
        """App 3.0: buscar artistas/álbumes/playlists, perfiles e inicio."""
        from cumito_bot import catalog
        from cumito_bot.lanes import LANES
        cache = self._cat_cache = getattr(self, "_cat_cache", {})
        try:
            if action == "cat_search":
                q, kind = str(data.get("query") or "")[:200], str(data.get("kind") or "all")
                key = ("s", q.lower(), kind)
                res = cache.get(key)
                if not res or time.time() - res[0] > 900:
                    res = cache[key] = (time.time(), await LANES.light(catalog.search_sync, q, kind, 20, timeout=25))
                await self._reply(ws, "cat_results", query=q, kind=kind, tag=data.get("tag"), **res[1])
            elif action == "artist":
                aid = str(data.get("id") or "")
                key = ("a", aid)
                res = cache.get(key)
                if not res or time.time() - res[0] > 3600:
                    res = cache[key] = (time.time(), await LANES.light(catalog.artist_sync, aid, timeout=25))
                await self._reply(ws, "artist", **res[1])
            elif action == "artist_songs":
                bid = str(data.get("id") or "")
                tracks = await LANES.light(catalog.artist_songs_sync, bid, timeout=40)
                await self._reply(ws, "artist_songs", id=bid, tracks=tracks)
            elif action == "yt_album":
                aid = str(data.get("id") or "")
                key = ("al", aid)
                res = cache.get(key)
                if not res or time.time() - res[0] > 3600:
                    res = cache[key] = (time.time(), await LANES.light(catalog.album_sync, aid, timeout=25))
                await self._reply(ws, "yt_album", **res[1])
            elif action == "yt_playlist":
                from cumito_bot.extractor import playlist_sync
                url = str(data.get("url") or "")
                tracks, name = await LANES.light(playlist_sync, url, 200, timeout=40)
                await self._reply(ws, "yt_playlist", url=url, name=name, tracks=tracks)
            elif action == "home_feed":
                seeds = [x for x in (data.get("seeds") or []) if isinstance(x, dict)][:5]
                key = ("h", tuple(x.get("webpage_url") for x in seeds))
                res = cache.get(key)
                if not res or time.time() - res[0] > 1800:
                    res = cache[key] = (time.time(), await LANES.light(catalog.home_sync, seeds, None, timeout=90))
                await self._reply(ws, "home_feed", **res[1])
            if len(cache) > 300:
                for k in list(cache)[:100]:
                    cache.pop(k, None)
        except Exception as e:
            logging.getLogger("cumito.catalog").warning("%s: %s", action, str(e)[:200])
            await self._reply(ws, "cat_error", action=action, message="No pude cargar eso ahora")

    async def _solo_command(self, action, data, ws):
        try:
            if action == "solo_get":
                url = str(data.get("url") or "")
                res = await self.solo.get(url, data.get("title"), pre=bool(data.get("pre")))
                await self._reply(ws, "solo_ready", url=url, **res)
            elif action == "solo_add":
                res = await self.solo.add(str(data.get("query") or ""), bool(data.get("as_playlist")))
                await self._reply(ws, "solo_tracks", now=bool(data.get("now")), **res)
            elif action == "recs":
                await self._reply(ws, "recs", tag=data.get("tag"), **await self.solo.recs(data.get("seeds") or []))
        except Exception:
            logging.getLogger("cumito.solo").exception("Modo solo: %s", action)

    async def _on_relay_command(self, data, sender_name, ws=None):
        bot = self.bot
        who = sender_name
        action = data.get("action")
        if action == "play":
            await bot.action_play(data.get("query", ""), as_playlist=bool(data.get("as_playlist")),
                                  req=data.get("req"), who=who)
        elif action in ("cat_search", "artist", "yt_album", "artist_songs", "home_feed", "yt_playlist"):
            asyncio.create_task(self._catalog_command(action, data, ws))
        elif action in ("solo_get", "solo_add", "recs"):
            # modo solo: pueden tardar unos segundos, así que van aparte para no
            # frenar lo demás que mande ese mismo celular
            asyncio.create_task(self._solo_command(action, data, ws))
        elif action == "solo_play":
            asyncio.create_task(self.solostreams.play(who, ws, data))
        elif action == "solo_plan":
            self.solostreams.plan(who, ws, data)
        elif action == "solo_tick":
            self.solostreams.tick(who, data)
        elif action in ("solo_pause", "solo_resume"):
            self.solostreams.pause(who, data, action == "solo_pause")
        elif action == "solo_stop":
            self.solostreams.stop(who, data)
        elif action == "solo_log":
            logging.getLogger("cumito.solo").info("celular de %s: %s", who,
                                                  {k: str(v)[:80] for k, v in data.items() if k not in ("type", "action")})
        elif action == "solo_status":
            await self.solo.status(who, data)
        elif action in ("fav_list", "fav_set"):
            db = bot.db
            if action == "fav_set":
                await db.run(db.fav_set, who, data.get("track") or {}, bool(data.get("on")))
            await self._reply(ws, "favs", tracks=await db.run(db.favs, who))
        elif action == "bring":
            err = await bot.bring_tracks(data.get("tracks") or [], front=bool(data.get("front")), who=who)
            await self._reply(ws, "bring_done", ok=not err, message=err, n=len(data.get("tracks") or []))
        elif action in ("room_react", "room_ask", "room_ask_reply"):
            await self._room_command(action, data, who, ws)
        elif action == "playlist_preview":
            # responde solo a quien preguntó, como la búsqueda
            preview = await bot.action_playlist_preview(data.get("url", ""))
            if ws is not None:
                try:
                    await ws.send(protocol.dumps("playlist_preview", **preview))
                except Exception:
                    pass
        elif action == "pause":
            await bot.action_pause(who=who)
        elif action == "resume":
            await bot.action_resume(who=who)
        elif action == "skip":
            await bot.action_skip(who=who)
        elif action == "stop":
            await bot.action_stop(who=who)
        elif action == "stop_and_leave":
            await bot.action_stop_and_leave(who=who)
        elif action == "queue_remove":
            await bot.action_queue_remove(int(data.get("index", -1)), who=who, uid=data.get("uid"))
        elif action == "queue_move":
            await bot.action_queue_move(data.get("uid"), int(data.get("to", 0)), who=who)
        elif action == "radio_now":
            await bot.action_radio_now(who=who)
        elif action == "queue_clear":
            await bot.action_queue_clear(who=who)
        elif action == "set_volume":
            await bot.action_set_volume(data.get("value", 0.6), who=who)
        elif action == "play_index":
            await bot.action_play_index(int(data.get("index", -1)), uid=data.get("uid"), who=who)
        elif action == "status":
            # la salud de la VM, solo para quien la pidió (Opciones -> Estado del servidor)
            await self._reply(ws, "status", **self.salud.snapshot(bot, self.relay))
        elif action == "activity_list":
            # el historial completo, solo para quien lo pidió (Ajustes > Actividad)
            if ws is not None:
                try:
                    await ws.send(protocol.dumps("activity_list", entries=bot.activity_list()))
                except Exception:
                    pass
        elif action == "prev":
            await bot.action_prev(who=who)
        elif action == "seek":
            await bot.action_seek(data.get("pos", 0), who=who)
        elif action == "set_repeat":
            await bot.action_set_repeat(str(data.get("mode", "off")), who=who)
        elif action == "shuffle":
            await bot.action_shuffle(who=who)
        elif action == "set_radio":
            await bot.action_set_radio(bool(data.get("on")), who=who)
        elif action == "set_normalize":
            await bot.action_set_normalize(bool(data.get("on")), who=who)
        elif action == "sleep":
            await bot.action_sleep(data.get("minutes"), end_of_track=bool(data.get("end_of_track")), who=who)
        elif action == "react":
            bot.action_react(data.get("emoji"), who=who)
        elif action == "lyrics":
            # la de la canción que suena (o la que se pida), solo para quien la pidió
            track = bot.current if not data.get("webpage_url") else {
                "webpage_url": data.get("webpage_url"), "title": data.get("title") or "",
                "uploader": data.get("uploader"), "duration": data.get("duration")}
            if track:
                await self._reply(ws, "lyrics", **await bot.lyrics_for(track))
            else:
                await self._reply(ws, "lyrics", found=False, key=None, webpage_url=None)
        elif action == "stats":
            period = str(data.get("period") or "month")
            mine = data.get("who") if data.get("who") else None
            await self._reply(ws, "stats", **await bot.db.run(bot.db.stats, period, mine))
        elif isinstance(action, str) and action.startswith("album_"):
            await self._album_command(action, data, who, ws)
        elif action == "prepare":
            await bot.action_prepare(int(data.get("index", -1)), uid=data.get("uid"))
        elif action == "search":
            # Esta sí responde directo a quien preguntó, no se difunde.
            offset = int(data.get("offset", 0) or 0)
            kind = "music" if data.get("kind") == "music" else "all"
            results = await bot.action_search(data.get("query", ""), limit=int(data.get("limit", 8)),
                                              offset=offset, kind=kind)
            if ws is not None:
                try:
                    await ws.send(protocol.search_results(data.get("query", ""), results, offset=offset,
                                                          kind=kind))
                except Exception:
                    pass

    async def run(self):
        asyncio.create_task(self.salud.run())
        asyncio.create_task(self.solo.sweep())
        await self.solostreams.start()
        from cumito_bot.lanes import LANES
        LANES.warm()
        await self.relay.start()
        print(f"Relay escuchando en el puerto {RELAY_PORT}. Conectando el bot a Discord...")
        try:
            await self.bot.start()
        finally:
            await self.relay.stop()
            await self.bot.close()


async def main():
    cfg = config.load()
    if not config.is_complete(cfg):
        cfg = _first_time_setup()
    server = CumitoServer(cfg)
    # systemd apaga con SIGTERM (al actualizar o reiniciar): se atrapa para
    # cerrar ordenado y dejar anotado en qué segundo iba la canción.
    task = asyncio.current_task()
    try:
        asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, task.cancel)
    except (NotImplementedError, RuntimeError):
        pass
    try:
        await server.run()
    except asyncio.CancelledError:
        print("Cumito servidor detenido (se guardó dónde iba).")


if __name__ == "__main__":
    # "python3 run.py --configurar": solo pregunta los datos y sale (lo usa
    # instalar.sh antes de dejar el servicio corriendo solo).
    if "--configurar" in sys.argv:
        _first_time_setup()
        sys.exit(0)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nCumito servidor detenido.")
        sys.exit(0)

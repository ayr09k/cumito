"""Prueba la búsqueda del servidor y muestra los datos crudos de YouTube Music."""
import json, sys
sys.path.insert(0, "servidor")
import yt_dlp
from cumito_bot import bot

out = {}
url = "https://music.youtube.com/search?q=ojitos+lindos#songs"
with yt_dlp.YoutubeDL(dict(bot.SEARCH_YTDL_OPTS, playlistend=3)) as ydl:
    info = ydl.extract_info(url, download=False)
out["crudo"] = [{k: v for k, v in e.items() if k not in ("http_headers",)} for e in info["entries"][:3]]
# sin extract_flat: ¿trae más?
with yt_dlp.YoutubeDL(dict(bot.SEARCH_YTDL_OPTS, extract_flat=True, playlistend=2)) as ydl:
    info2 = ydl.extract_info(url, download=False)
out["crudo_flat_true"] = list(info2["entries"])[:2]
open(sys.argv[1], "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False, indent=1, default=str))

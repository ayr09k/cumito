"""Prueba la búsqueda del servidor ("música" vs "todo") y guarda el resultado."""
import asyncio, json, sys, time
sys.path.insert(0, "servidor")
from cumito_bot import bot

out = {}
for q in ["ojitos lindos", "bohemian rhapsody", "la bachata manuel turizo"]:
    for kind in ("music", "all"):
        t = time.time()
        try:
            r = asyncio.run(bot.search(q, limit=6, offset=0, kind=kind))
        except Exception as e:
            r = [{"error": str(e)}]
        out[f"{q} [{kind}]"] = {"segundos": round(time.time() - t, 1), "resultados": r}
    try:
        out[f"{q} [music, más]"] = asyncio.run(bot.search(q, limit=4, offset=6, kind="music"))
    except Exception as e:
        out[f"{q} [music, más]"] = str(e)
open(sys.argv[1], "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False, indent=1))

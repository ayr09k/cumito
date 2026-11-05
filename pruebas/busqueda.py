"""Prueba la búsqueda del servidor ("música" vs "todo") y guarda el resultado."""
import asyncio, json, sys, time
sys.path.insert(0, "servidor")
from cumito_bot import bot

def main():
    out = {}
    for q in ["ojitos lindos", "bohemian rhapsody", "la bachata manuel turizo"]:
        for kind in ("music",):
            t = time.time()
            r = asyncio.run(bot.search(q, limit=6, offset=0, kind=kind))
            out[f"{q} [{kind}]"] = {"segundos": round(time.time() - t, 1), "resultados": r}
        t = time.time()
        out[f"{q} [music, más]"] = {"segundos": round(time.time() - t, 1),
                                    "resultados": asyncio.run(bot.search(q, limit=4, offset=8, kind="music"))}
    open(sys.argv[1], "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()

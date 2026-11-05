"""Baja la letra Manrope (licencia libre OFL) a assets/fonts antes de armar
la app. La corre GitHub al construir; si falla, Cumito usa Segoe UI."""
import sys
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "assets" / "fonts"
OUT.mkdir(parents=True, exist_ok=True)
ok = 0
for w, name in ((500, "Medium"), (600, "SemiBold"), (700, "Bold"), (800, "ExtraBold")):
    for subset in ("latin",):
        url = f"https://cdn.jsdelivr.net/fontsource/fonts/manrope@latest/{subset}-{w}-normal.ttf"
        dest = OUT / f"Manrope-{name}-{subset}.ttf"
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                data = r.read()
            if data[:4] in (b"\x00\x01\x00\x00", b"OTTO", b"true"):
                dest.write_bytes(data)
                ok += 1
                print("ok", dest.name, len(data))
            else:
                print("no es una fuente:", url)
        except Exception as e:
            print("no se pudo:", url, e)
try:
    lic = urllib.request.urlopen("https://raw.githubusercontent.com/google/fonts/main/ofl/manrope/OFL.txt",
                                 timeout=30).read()
    (OUT / "OFL.txt").write_bytes(lic)
except Exception:
    pass
print(f"{ok} archivos de Manrope")
sys.exit(0)

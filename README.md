# Cumito

Bot de música para Discord + la app de escritorio Cumito.

- `app/` — la app de Windows (PySide6). Cada cambio aquí genera solo un instalador nuevo en **Releases**, y las apps instaladas se actualizan desde ahí.
- `servidor/` — el bot que corre 24/7 en la VM. La VM revisa este repo cada 10 minutos y se actualiza sola.

Para sacar una versión nueva: cambiar el número en `VERSION` y anotar qué cambió en `NOVEDADES.md`.

Los datos privados del servidor (token, cookies, config) viven solo en la VM y nunca se suben aquí.

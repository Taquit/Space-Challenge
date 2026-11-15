# Servir el front desde el backend (un solo proceso, sin CORS)

El front es estático, así que el backend de FastAPI puede servirlo en `/`. Así ORBITAL corre con **un solo comando** y sin CORS (mismo origen). Pensado para la demo local y offline.

> **Estado:** la opción A ya está aplicada en el backend (`src/api/main.py` + `FRONT_DIR` en `src/config.py`, por defecto `front/Space-Challenge-Front-main`, configurable con `ORBITAL_FRONT_DIR`). Basta con `python -m src.api.main` y abrir `http://localhost:8000/`.

## Opción A (recomendada): montar la carpeta del front

1. Copia esta carpeta (o apúntala con una variable de entorno) dentro del backend, p. ej. `Space-Challenge/front/`.
2. En `src/api/main.py`, **al final del archivo** (después de incluir los routers y el middleware), agrega:

```python
import os
from pathlib import Path
from fastapi.staticfiles import StaticFiles

# Front estático de ORBITAL (carpeta con index.html). Configurable con ORBITAL_FRONT_DIR.
_front = Path(os.environ.get("ORBITAL_FRONT_DIR", config.RAIZ / "front"))
if _front.is_dir():
    # Debe montarse DESPUÉS de todas las rutas de la API para no taparlas.
    app.mount("/", StaticFiles(directory=str(_front), html=True), name="front")
```

3. Arranca como siempre:

```bash
python -m src.api.main
# ORBITAL completo en http://localhost:8000/   ·   API en /salud, /tripulantes, /docs
```

Como el front queda en el mismo origen que la API, el front detecta el backend solo (mismo host y puerto) — no hace falta `?api=`. Si lo sirves aparte, usa `?api=http://localhost:8000`.

> El `mount` en `/` captura todo lo que no sea una ruta de la API, así que debe ir **después** de `app.include_router(...)` y de las rutas `@app.get(...)`. `/docs`, `/salud`, `/tripulantes`, `/preguntar` siguen funcionando porque se registran antes.

## Opción B: servidor estático aparte

Sirve el front en un origen que el backend permita por CORS (`localhost:3000`, `localhost:5173`, `127.0.0.1:5173`):

```bash
python3 -m http.server 5173 --bind 127.0.0.1   # en la carpeta del front
```

Si usas otro origen, agrégalo a `CORS_ORIGENES` en `src/config.py` del backend.

## Comprobar

```bash
curl -s localhost:8000/salud         # {"estado":"ok", ...}
# abrir http://localhost:8000/ (opción A) o http://127.0.0.1:5173/index.html (opción B)
```

El indicador de arriba a la derecha debe decir **"Backend en vivo"**. Si dice "En vivo" a secas, está en modo demostración (no alcanzó el backend).

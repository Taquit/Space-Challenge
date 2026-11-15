"""Genera sesiones cognitivas simuladas en data/cognitivo.json (docs/COGNITIVO.md, fase 1).

    python scripts/simular_cognitivo.py

  astro_1: estable (siempre dentro de su línea base)
  astro_2: caída súbita (las dos últimas sesiones muy peores)
  astro_3: deriva lenta (empeora poco a poco)
Cada usuario: 1 sesión de familiarización (peor por el efecto de práctica) + 3 de línea base + sesiones en vuelo.
Determinista: la semilla fija los datos. No se usan pruebas reales; son números inventados para demo.
"""
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.datos.cognitivo import DatosCognitivo  # noqa: E402

ZONA = timezone(timedelta(hours=-6))
INICIO = datetime(2026, 9, 6, 9, 30, tzinfo=ZONA)
SEPARACION = timedelta(days=7)


def sesion(rng, i, deterioro, familiarizacion=False):
    """`deterioro` 0 = su nivel habitual; 0.5 = caída clara (reacciones más lentas, más lapsos, menos aciertos)."""
    practica = 0.12 if familiarizacion else 0.0
    d = deterioro + practica
    rt = rng.gauss(282, 9) * (1 + 0.30 * d)
    n_est = 24
    lapsos = max(0, round(rng.gauss(1.0, 0.7) + 7 * d))
    falsos = max(0, round(rng.gauss(0.5, 0.6)))
    rt_ds = rng.gauss(2000, 70) * (1 + 0.25 * d)
    intentos_ds = max(10, round(90 / (rt_ds / 1000) * rng.uniform(0.97, 1.0)))
    correctas_ds = max(0, min(intentos_ds, round(intentos_ds * (rng.gauss(0.955, 0.01) - 0.10 * d))))
    items = max(1, round(rng.gauss(10.5, 0.5) - 6 * d))
    ok_mx = max(0, min(items, round(rng.gauss(8.0, 0.45) - 4.5 * d)))
    t_mx = rng.gauss(140, 8) * (1 + 0.2 * d)
    return {
        "id": i,
        "fecha": (INICIO + SEPARACION * (i - 1)).isoformat(),
        "forma": "ABC"[(i - 1) % 3],
        "semilla": rng.randrange(1000, 9999),
        "familiarizacion": familiarizacion,
        "pruebas": {
            "pvt": {"rt_media_ms": round(rt, 1), "rt_mediana_ms": round(rt * 0.96, 1), "lapsos": lapsos,
                    "falsos_inicios": falsos, "n_estimulos": n_est},
            "dsst": {"correctas": correctas_ds, "intentos": intentos_ds, "precision": round(correctas_ds / intentos_ds, 3),
                     "throughput": round(correctas_ds / 90, 3), "rt_media_ms": round(rt_ds, 1)},
            "matrix": {"correctas": ok_mx, "intentos": items, "precision": round(ok_mx / items, 3),
                       "tiempo_total_s": round(t_mx, 1), "throughput": round(ok_mx / t_mx, 3)},
        },
        "contexto": {"comentario": ""},
    }


PERFILES = {
    "astro_1": lambda k, n: 0.0,                          # estable
    "astro_2": lambda k, n: 0.5 if k >= n - 1 else 0.0,   # caída súbita al final
    "astro_3": lambda k, n: 0.04 * k,                     # deriva lenta
}
EN_VUELO = {"astro_1": 6, "astro_2": 6, "astro_3": 9}


def generar():
    out = {}
    for u, (semilla, perfil) in zip(PERFILES, enumerate(PERFILES.values(), start=1)):
        rng = random.Random(100 + semilla)
        n = EN_VUELO[u]
        ses = [sesion(rng, 1, 0.0, familiarizacion=True)]
        ses += [sesion(rng, 1 + j, 0.0) for j in range(1, 4)]                       # línea base (ids 2-4)
        ses += [sesion(rng, 4 + k, perfil(k, n)) for k in range(1, n + 1)]
        out[u] = ses
    return out


if __name__ == "__main__":
    datos = DatosCognitivo()
    datos.reemplazar_todo(generar())
    for u in PERFILES:
        print(u, len(datos.sesiones(u)), "sesiones")
    print("Guardado en", datos.ruta)

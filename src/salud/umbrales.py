"""Umbrales configurables. Se leen de `umbrales.env` (raíz del proyecto) y de variables de entorno
(prioridad). Los valores por defecto de abajo se usan si la clave no está en ninguno. Documentado en docs/UMBRALES.md.
"""
import os

from src import config

DEFAULTS = {
    "PULSO_VIGILAR_MIN": 60, "PULSO_VIGILAR_MAX": 100, "PULSO_ALERTA_MIN": 50, "PULSO_ALERTA_MAX": 110,
    "PULSO_CRITICO_MIN": 40, "PULSO_CRITICO_MAX": 130,
    "SPO2_VIGILAR_MIN": 95, "SPO2_ALERTA_MIN": 92, "SPO2_CRITICO_MIN": 90,
    "SISTOLICA_VIGILAR_MAX": 130, "SISTOLICA_ALERTA_MAX": 140, "SISTOLICA_CRITICO_MAX": 180,
    "SISTOLICA_ALERTA_MIN": 90, "SISTOLICA_CRITICO_MIN": 80,
    "DIASTOLICA_VIGILAR_MAX": 80, "DIASTOLICA_ALERTA_MAX": 90, "DIASTOLICA_CRITICO_MAX": 120,
    "DIASTOLICA_ALERTA_MIN": 60, "DIASTOLICA_CRITICO_MIN": 50,
    "INDICE_CHOQUE_MAX": 0.9, "PRESION_PULSO_MIN": 25, "PRESION_PULSO_MAX": 60,
    "PERSISTENCIA_LECTURAS": 3, "BASELINE_LECTURAS": 15,
    "DERIVA_UMBRAL_PULSO": 8, "DERIVA_UMBRAL_SPO2": 2, "DERIVA_UMBRAL_SISTOLICA": 10, "DERIVA_UMBRAL_DIASTOLICA": 6,
    "DERIVA_SIGMAS": 2, "DERIVA_VENTANA_LECTURAS": 36, "DERIVA_PROMEDIO_LECTURAS": 6, "DERIVA_REARME_LECTURAS": 12,
    "TENDENCIA_UMBRAL": 0.05,
    "MODELO_Z_ADVERTENCIA": 2.0, "MODELO_Z_ANOMALIA": 3.0, "MODELO_Z_ANOMALIA_ISO": 2.5,
    "PATRON_SPO2_MAX": 95, "PATRON_MIN_VARIABLES": 3,
}


def _leer_archivo(ruta):
    out = {}
    try:
        for linea in ruta.read_text(encoding="utf-8").splitlines():
            linea = linea.split("#", 1)[0].strip()
            if "=" in linea:
                k, v = linea.split("=", 1)
                out[k.strip()] = v.strip()
    except OSError:
        pass
    return out


def cargar():
    ruta = config.RAIZ / os.environ.get("UMBRALES_ENV", "umbrales.env")
    crudo = _leer_archivo(ruta)
    valores = {}
    for k, por_defecto in DEFAULTS.items():
        txt = os.environ.get(k, crudo.get(k))
        try:
            valores[k] = type(por_defecto)(float(txt)) if txt is not None else por_defecto
        except ValueError:
            raise ValueError(f"Umbral inválido en umbrales.env: {k}={txt!r} (se esperaba un número)")
    desconocidas = set(crudo) - set(DEFAULTS)
    if desconocidas:
        raise ValueError(f"Claves desconocidas en umbrales.env: {', '.join(sorted(desconocidas))}")
    return valores


U = cargar()

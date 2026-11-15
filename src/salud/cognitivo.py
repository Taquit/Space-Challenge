"""Inferencia cognitiva (PVT, DSST, Matrix). Orientativa, no es diagnóstico médico. Ver docs/COGNITIVO.md.

Cada persona es su propia referencia: las sesiones se comparan contra SU línea base (las primeras
COG_BASELINE_SESIONES sesiones, sin contar la de familiarización). Solo observa: nunca decide no apto
(ver aptitud.py). Todo es determinista; los umbrales están en umbrales.env (prefijo COG_).
"""
from datetime import datetime
from statistics import mean, stdev

from src import config
from src.salud import codigos
from src.salud import referencias as ref
from src.salud.umbrales import U

# clave -> (prueba, campo, sentido del deterioro, es conteo)
METRICAS = {
    "cog_pvt_rt": ("pvt", "rt_media_ms", "sube", False),
    "cog_pvt_lapsos": ("pvt", "lapsos", "sube", True),
    "cog_dsst_throughput": ("dsst", "throughput", "baja", False),
    "cog_matrix_correctas": ("matrix", "correctas", "baja", True),
}
AVISO = "Orientativo, no es diagnóstico médico: una sesión atípica suele deberse a fatiga, distracción o poco esfuerzo."
RECOMENDACION = ("Repetir la sesión cognitiva, descartar causas no cognitivas (fatiga, distracción, esfuerzo) "
                 "y revisar sueño y signos vitales.")


def _fecha(s):
    return datetime.fromisoformat(s["fecha"]).timestamp()


def _valor(sesion, clave):
    prueba, campo, _, _ = METRICAS[clave]
    return (sesion.get("pruebas") or {}).get(prueba, {}).get(campo)


def _nivel(z):
    if z >= U["COG_Z_ALERTA"]:
        return ref.ALERTA
    if z >= U["COG_Z_VIGILAR"]:
        return ref.VIGILAR
    return ref.NORMAL


def z_deterioro(valor, media, sd_efectiva, sentido):
    """Positivo = peor que su línea base."""
    return (valor - media) / sd_efectiva if sentido == "sube" else (media - valor) / sd_efectiva


def _linea_base(sesiones_base):
    """{clave: {media, sd, sd_efectiva, n}} con piso de desviación para evitar z explosivos."""
    out = {}
    for clave, (_, _, _, conteo) in METRICAS.items():
        vals = [v for v in (_valor(s, clave) for s in sesiones_base) if v is not None]
        if len(vals) < 2:
            continue
        media, sd = mean(vals), stdev(vals)
        sd_ef = max(sd, U["COG_SD_MIN_REL"] * abs(media), U["COG_SD_MIN_ABS_CONTEO"] if conteo else 0.0)
        if sd_ef <= 0:
            continue
        out[clave] = {"media": round(media, 3), "sd": round(sd, 3), "sd_efectiva": round(sd_ef, 3), "n": len(vals)}
    return out


def _evaluar_sesion(sesion, base):
    metricas, nivel = {}, ref.NORMAL
    for clave, b in base.items():
        v = _valor(sesion, clave)
        if v is None:
            continue
        z = z_deterioro(v, b["media"], b["sd_efectiva"], METRICAS[clave][2])
        n = _nivel(z)
        metricas[clave] = {"valor": v, "z": round(z, 2), "nivel": n}
        nivel = ref.mas_grave(nivel, n)
    return {"id": sesion.get("id"), "fecha": sesion["fecha"], "nivel": nivel,
            "codigo_nivel": codigos.NIVEL_COGNITIVO[nivel], "metricas": metricas}


def _deriva(evaluadas):
    """Promedio de z de las últimas COG_DERIVA_VENTANA sesiones por métrica. Hay deriva si el promedio
    es >= COG_DERIVA_Z y la mayoría de las sesiones de la ventana tienen z >= COG_DERIVA_Z/2 (una atípica aislada no cuenta)."""
    v = U["COG_DERIVA_VENTANA"]
    out = {"detectada": False, "ventana": v, "z_promedio": {}, "variables": [], "codigo": 4101, "nombre": codigos.nombre(4101)}
    if len(evaluadas) < v:
        return out
    ventana = evaluadas[-v:]
    for clave in METRICAS:
        zs = [s["metricas"][clave]["z"] for s in ventana if clave in s["metricas"]]
        if len(zs) < 2:
            continue
        prom = mean(zs)
        out["z_promedio"][clave] = round(prom, 2)
        if prom >= U["COG_DERIVA_Z"] and sum(z >= U["COG_DERIVA_Z"] / 2 for z in zs) > len(zs) / 2:
            out["variables"].append(clave)
    if out["variables"]:
        out.update(detectada=True, codigo=4110, nombre=codigos.nombre(4110))
    return out


def evaluar(sesiones):
    """Evalúa las sesiones de un usuario (cualquier orden). La de familiarización se descarta."""
    orden = sorted(sesiones, key=_fecha)
    validas = [s for s in orden if not s.get("familiarizacion")]
    n_base = U["COG_BASELINE_SESIONES"]
    out = {"estado": "SIN_LINEA_BASE", "codigo_nivel": 8000, "nombre_nivel": codigos.nombre(8000),
           "sesiones_totales": len(orden), "sesiones_validas": len(validas), "sesiones_linea_base": n_base,
           "linea_base_completa": False, "linea_base": {}, "evaluacion": [], "ultima": None,
           "alerta_sostenida": False, "deriva": _deriva([]), "orientativo": AVISO}
    if len(validas) < n_base:
        return out
    base = _linea_base(validas[:n_base])
    evaluadas = [_evaluar_sesion(s, base) for s in validas[n_base:]]
    p = U["COG_PERSISTENCIA_SESIONES"]
    estado = evaluadas[-1]["nivel"] if evaluadas else ref.NORMAL
    out.update(estado=estado, codigo_nivel=codigos.NIVEL_COGNITIVO[estado], nombre_nivel=codigos.nombre(codigos.NIVEL_COGNITIVO[estado]),
               linea_base_completa=True, linea_base=base, evaluacion=evaluadas, ultima=evaluadas[-1] if evaluadas else None,
               alerta_sostenida=len(evaluadas) >= p and all(s["nivel"] == ref.ALERTA for s in evaluadas[-p:]),
               deriva=_deriva(evaluadas))
    return out


def _contexto_fisiologico(resumen):
    """(sueño deficiente sostenido, fisiología desviada o fuera de rango) a partir de `inferencia.resumen_global`."""
    if not resumen:
        return False, False
    sueno = any(p["codigo"] == 5017 for p in resumen["patrones"])
    fisio = any(m and m["variable"] not in config.VARIABLES_SUENO
                and (m["nivel_clinico"] != ref.NORMAL or m["estado_modelo"] in ("ADVERTENCIA", "ANOMALIA"))
                for m in resumen["medidas"].values())
    return sueno, fisio


def observaciones(ev, sueno_deficiente=False, fisio_desviada=False):
    """Observaciones 5018-5020 (patrones) y 5005 (deriva). Nunca son motivos de no apto."""
    out = []
    if ev["estado"] in (ref.VIGILAR, ref.ALERTA):
        u = ev["ultima"]
        malas = [k for k, m in u["metricas"].items() if m["nivel"] != ref.NORMAL]
        out.append(codigos.evento(5018, f"Rendimiento cognitivo por debajo de su línea base ({ev['estado']}; "
                                        f"{', '.join(malas)}). {AVISO}", "cognitivo"))
        if sueno_deficiente:
            out.append(codigos.evento(5019, "Sueño deficiente sostenido junto con caída cognitiva "
                                            "(se usa el sueño más reciente disponible).", "cognitivo"))
        if fisio_desviada:
            out.append(codigos.evento(5020, "Alguna medida fisiológica desviada o fuera de rango junto con caída cognitiva.", "cognitivo"))
    d = ev["deriva"]
    if d["detectada"]:
        out.append(codigos.evento(5005, f"cognitivo: deriva lenta del rendimiento ({', '.join(d['variables'])}; "
                                        f"z promedio de las últimas {d['ventana']} sesiones)", "cognitivo"))
    return out


def bloque(sesiones, resumen=None):
    """Evaluación completa + observaciones. `resumen` = `inferencia.resumen_global(...)` del mismo usuario (opcional)."""
    ev = evaluar(sesiones)
    sueno, fisio = _contexto_fisiologico(resumen)
    ev["observaciones"] = observaciones(ev, sueno, fisio)
    ev["recomendacion"] = RECOMENDACION if any(o["codigo"] in (5018, 5019, 5020) for o in ev["observaciones"]) else None
    return ev


def texto_chat(ev):
    """Líneas para el contexto del chat: solo cifras ya calculadas."""
    if not ev["linea_base_completa"]:
        return [f"- Cognitivo: {ev['nombre_nivel']} ({ev['sesiones_validas']} de {ev['sesiones_linea_base']} sesiones de línea base)."]
    lin = [f"- Cognitivo: estado {ev['estado']} ({ev['codigo_nivel']}) frente a su línea base; orientativo, no es diagnóstico."]
    if ev["ultima"]:
        for k, m in ev["ultima"]["metricas"].items():
            b = ev["linea_base"][k]
            lin.append(f"  · {k}: última sesión {m['valor']} (línea base {b['media']}), z de deterioro {m['z']} ({m['nivel']}).")
    if ev["alerta_sostenida"]:
        lin.append("  · Alerta cognitiva sostenida en sesiones seguidas.")
    if ev["deriva"]["detectada"]:
        lin.append(f"  · Deriva lenta del rendimiento ({', '.join(ev['deriva']['variables'])}).")
    for o in ev.get("observaciones", []):
        if o["codigo"] in (5019, 5020):
            lin.append(f"  · {o['mensaje']}")
    return lin

"""Inferencias por tripulante sobre sus lecturas, usando SU modelo personal.

Fuente del "esperado": data/resultados/deviations.json (generado por `python -m src.series.analizar`),
que contiene, por usuario y variable, las desviaciones respecto al intervalo de predicción personal.
Una lectura sin registro de desviación se considera normal para esa persona.
"""
import json
from statistics import mean, pstdev

from src import config
from src.datos.salud import UNIDADES
from src.salud import codigos
from src.salud import referencias as ref
from src.salud.umbrales import U

PERSISTENCIA = U["PERSISTENCIA_LECTURAS"]   # lecturas consecutivas fuera de rango para considerarlo sostenido
BASELINE_N = U["BASELINE_LECTURAS"]
UMBRAL_TENDENCIA = U["TENDENCIA_UMBRAL"]    # relativo al σ de la ventana

_cache = {"mtime": None, "datos": {}}


def _norm(ts):
    return ts.replace("T", " ")


def desviaciones():
    """{usuario: {variable: {summary, deviations, metadata}}} (cache por fecha de archivo)."""
    ruta = config.DESVIACIONES
    if not ruta.exists():
        return {}
    m = ruta.stat().st_mtime
    if _cache["mtime"] != m:
        _cache.update(mtime=m, datos=json.loads(ruta.read_text(encoding="utf-8")))
    return _cache["datos"]


def _desv_variable(usuario, variable):
    col = config.VARIABLES_ANALIZADAS.get(variable)
    r = desviaciones().get(usuario, {}).get(variable)
    return (r["deviations"] if r else []), r


def pendiente(valores):
    """Pendiente de la regresión lineal (unidades por lectura)."""
    n = len(valores)
    if n < 2:
        return 0.0
    x = list(range(n))
    mx, my = mean(x), mean(valores)
    den = sum((a - mx) ** 2 for a in x)
    return sum((a - mx) * (b - my) for a, b in zip(x, valores)) / den if den else 0.0


# Deriva lenta: cambio acumulado mínimo (unidades) para avisar aunque cada lectura parezca normal
UMBRAL_DERIVA = {"pulso": U["DERIVA_UMBRAL_PULSO"], "spo2": U["DERIVA_UMBRAL_SPO2"],
                 "presion_sistolica": U["DERIVA_UMBRAL_SISTOLICA"], "presion_diastolica": U["DERIVA_UMBRAL_DIASTOLICA"]}
VENTANA_DERIVA = U["DERIVA_VENTANA_LECTURAS"]     # lecturas (~6 h a 1 lectura/10 min) para comparar contra el pasado reciente
N_PROMEDIO = U["DERIVA_PROMEDIO_LECTURAS"]          # lecturas que se promedian para suavizar el ruido


def deriva(variable, serie):
    """Detecta cambios lentos acumulados: promedio reciente vs. la línea base (primeras lecturas)
    y vs. el promedio de hace VENTANA_DERIVA lecturas. Cubre lo que el modelo one-step no ve."""
    vals = [v for _, v in serie]
    out = {"detectada": False, "cambio": 0.0, "umbral": UMBRAL_DERIVA.get(variable, 0.0),
           "referencia": None, "sentido": None, "codigo": 4101, "nombre": codigos.nombre(4101)}
    if len(vals) < BASELINE_N + N_PROMEDIO:
        return out
    base = vals[:BASELINE_N]
    umbral = max(UMBRAL_DERIVA.get(variable, 0.0), U["DERIVA_SIGMAS"] * pstdev(base))
    reciente = mean(vals[-N_PROMEDIO:])
    cambios = [("línea base", reciente - mean(base))]
    if len(vals) >= VENTANA_DERIVA:
        cambios.append(("últimas 6 h", reciente - mean(vals[-VENTANA_DERIVA:-VENTANA_DERIVA + N_PROMEDIO])))
    refe, cambio = max(cambios, key=lambda c: abs(c[1]))
    out.update(cambio=round(cambio, 2), umbral=round(umbral, 2), referencia=refe,
               sentido="ascendente" if cambio > 0 else "descendente")
    if abs(cambio) >= umbral:
        out.update(detectada=True, codigo=4110, nombre=codigos.nombre(4110))
    return out


def persistencia_clinica(variable, serie, n=PERSISTENCIA, minimo=ref.ALERTA):
    """True si las últimas `n` lecturas están todas en nivel >= `minimo` según los límites clínicos
    (independiente del modelo personal)."""
    ult = [v for _, v in serie][-n:]
    return len(ult) == n and all(ref.ORDEN[ref.clasificar(variable, v)[0]] >= ref.ORDEN[minimo] for v in ult)


def resumen_medida(usuario, variable, serie, tope=None):
    """Resumen de una variable. `serie` = [(timestamp, valor), ...] hasta el instante actual
    (más antigua primero). `tope` = nº de lecturas recientes a resumir (None = todas)."""
    historial = serie if not tope else serie[-tope:]
    valores = [v for _, v in historial]
    if not valores:
        return None
    ts_act, actual = historial[-1]
    base = [v for _, v in serie[:BASELINE_N]]
    sigma_base = pstdev(base) if len(base) > 1 else 0.0
    nivel_clin, etiqueta = ref.clasificar(variable, actual)

    devs, rep = _desv_variable(usuario, variable)
    por_ts = {_norm(d["timestamp"]): d for d in devs}
    desde = _norm(historial[0][0])
    en_ventana = [d for t, d in por_ts.items() if desde <= t <= _norm(ts_act)]
    d_act = por_ts.get(_norm(ts_act))
    if d_act:
        estado_modelo = d_act["status"]
        esperado = {"valor": d_act["predicted_value"], **d_act["expected_range"]}
    else:
        estado_modelo = "NORMAL" if rep else "SIN_MODELO"
        esperado = None

    pend = pendiente(valores[-min(len(valores), 12):])
    ref_escala = pstdev(valores) or 1.0
    if abs(pend) < UMBRAL_TENDENCIA * ref_escala:
        tendencia = "estable"
    else:
        tendencia = "ascendente" if pend > 0 else "descendente"

    base_nivel = ref.clasificar(variable, mean(base))[0] if base else ref.NORMAL
    der = deriva(variable, serie)
    return {
        "variable": variable, "unidad": UNIDADES.get(variable),
        "lecturas": len(valores), "desde": historial[0][0], "hasta": ts_act,
        "actual": actual, "minimo": min(valores), "maximo": max(valores),
        "media": round(mean(valores), 2), "desviacion": round(pstdev(valores), 2),
        "linea_base": round(mean(base), 2) if base else None,
        "diferencia_base": round(actual - mean(base), 2) if base else None,
        "z_base": round((actual - mean(base)) / sigma_base, 2) if base and sigma_base > 1e-6 else None,
        "tendencia": tendencia, "pendiente_por_lectura": round(pend, 3),
        "esperado_personal": esperado, "estado_modelo": estado_modelo,
        "modelo": rep["metadata"]["model_name"] if rep else None,
        "advertencias_ventana": sum(d["status"] == "ADVERTENCIA" for d in en_ventana),
        "anomalias_ventana": sum(d["status"] == "ANOMALIA" for d in en_ventana),
        "nivel_clinico": nivel_clin, "interpretacion_clinica": etiqueta,
        "codigo_nivel_clinico": codigos.NIVEL_CLINICO[nivel_clin],
        "codigo_estado_modelo": codigos.ESTADO_MODELO.get(estado_modelo, 3000),
        "codigo_tendencia": codigos.TENDENCIA[tendencia],
        "deriva": der,
        "linea_base_confiable": ref.ORDEN[base_nivel] < ref.ORDEN[ref.ALERTA],
    }


def persistente(usuario, variable, ts_actual, n=PERSISTENCIA, series_ts=None):
    """True si las últimas `n` lecturas (hasta ts_actual) están todas desviadas en el modelo personal."""
    devs, _ = _desv_variable(usuario, variable)
    if not series_ts:
        return False
    por_ts = {_norm(d["timestamp"]) for d in devs}
    ult = [_norm(t) for t in series_ts if _norm(t) <= _norm(ts_actual)][-n:]
    return len(ult) == n and all(t in por_ts for t in ult)


def derivadas(actual):
    """Magnitudes derivadas con los últimos valores {variable: valor}."""
    out = {}
    s, d, p = actual.get("presion_sistolica"), actual.get("presion_diastolica"), actual.get("pulso")
    if s is not None and d is not None:
        out["presion_pulso"] = round(ref.presion_pulso(s, d), 1)
        out["presion_media"] = round(ref.presion_media(s, d), 1)
    if s is not None and p is not None:
        out["indice_choque"] = round(ref.indice_choque(p, s), 2)
    return out


def patrones(actual, estados):
    """Co-ocurrencias de varias variables. `estados` = {variable: estado_modelo}. Lista de eventos."""
    out = []
    desv = {v for v, e in estados.items() if e in ("ADVERTENCIA", "ANOMALIA")}
    sp = actual.get("spo2")
    if sp is not None and sp < U["PATRON_SPO2_MAX"] and "pulso" in desv:
        out.append(codigos.evento(5004, "Saturación baja con pulso fuera de lo habitual: posible compromiso respiratorio."))
    if {"presion_sistolica", "pulso"} <= desv:
        out.append(codigos.evento(5007, "Presión sistólica y pulso desviados a la vez: posible alteración circulatoria."))
    der = derivadas(actual)
    if der.get("indice_choque", 0) > U["INDICE_CHOQUE_MAX"]:
        out.append(codigos.evento(5008, f"Índice de choque elevado ({der['indice_choque']})."))
    if "presion_pulso" in der and not U["PRESION_PULSO_MIN"] <= der["presion_pulso"] <= U["PRESION_PULSO_MAX"]:
        out.append(codigos.evento(5009, f"Presión de pulso fuera de rango ({der['presion_pulso']} mmHg)."))
    if len(desv) >= U["PATRON_MIN_VARIABLES"]:
        out.append(codigos.evento(5011, "Tres o más variables se desvían de su patrón personal simultáneamente."))
    return out


def resumen_global(usuario, series_por_var, tope=None, variables=None):
    """Resumen de las variables pedidas (o todas) de un usuario, más derivadas y patrones.
    `series_por_var` = {variable: [(ts, valor), ...]} hasta el instante actual."""
    vars_ = [v for v in (variables or sorted(series_por_var)) if v in series_por_var]
    medidas = {v: resumen_medida(usuario, v, series_por_var[v], tope) for v in vars_}
    actual = {v: s[-1][1] for v, s in series_por_var.items() if s}
    estados = {v: m["estado_modelo"] for v, m in medidas.items() if m}
    return {"usuario": usuario, "medidas": medidas, "derivadas": derivadas(actual),
            "patrones": patrones(actual, estados)}

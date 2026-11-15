"""Notificaciones al cambiar el nivel de alerta de una variable (con deduplicación).

Se generan al cruzar un límite clínico absoluto o al desviarse del modelo personal.
Buffer en memoria + persistencia en data/resultados/notificaciones.json.
"""
import json
import threading

from src import config
from src.salud import codigos, cognitivo, inferencia
from src.salud.umbrales import U
from src.salud import referencias as ref

_lock = threading.Lock()
_lista = []          # [{id, usuario, timestamp, severidad, variable, mensaje}]
_ultimo = {}         # (usuario, variable) -> severidad ya notificada
_procesado = {}      # usuario -> índice de la última lectura procesada
_sin = {}            # (usuario, variable) -> lecturas seguidas sin deriva
REARME = U["DERIVA_REARME_LECTURAS"]          # lecturas sin deriva para volver a avisar
_deriva = {}         # (usuario, variable) -> True si ya se avisó de la deriva vigente
_cog_alerta = {}     # usuario -> True si ya se avisó de la alerta cognitiva sostenida vigente
_cog_deriva = {}     # usuario -> True si ya se avisó de la deriva cognitiva vigente

_MODELO = {"NORMAL": ref.NORMAL, "SIN_MODELO": ref.NORMAL, "ADVERTENCIA": ref.VIGILAR, "ANOMALIA": ref.ALERTA}


def _guardar():
    try:
        config.NOTIFICACIONES.parent.mkdir(parents=True, exist_ok=True)
        config.NOTIFICACIONES.write_text(json.dumps(_lista, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def reiniciar():
    with _lock:
        _lista.clear(), _ultimo.clear(), _procesado.clear(), _deriva.clear(), _sin.clear()
        _cog_alerta.clear(), _cog_deriva.clear()
        _guardar()


def evaluar_lectura(usuario, ts, valores, estados_modelo):
    """Evalúa una lectura {variable: valor}; devuelve las notificaciones nuevas.
    `estados_modelo` = {variable: 'NORMAL'|'ADVERTENCIA'|'ANOMALIA'} del modelo personal."""
    nuevas = []
    with _lock:
        for var, valor in valores.items():
            clin, etiqueta = ref.clasificar(var, valor)
            if clin == ref.VIGILAR and estados_modelo.get(var, "NORMAL") == "NORMAL":
                clin = ref.NORMAL   # fuera de rango "leve" pero normal para esta persona: no se notifica
            sev = ref.mas_grave(clin, _MODELO.get(estados_modelo.get(var, "NORMAL"), ref.NORMAL))
            previo = _ultimo.get((usuario, var), ref.NORMAL)
            _ultimo[(usuario, var)] = sev
            # Notifica solo al empeorar (o al pasar a un nivel más alto); no repite el mismo nivel.
            if ref.ORDEN[sev] > ref.ORDEN[previo] and sev != ref.NORMAL:
                partes = []
                if clin != ref.NORMAL:
                    partes.append(etiqueta)
                if estados_modelo.get(var, "NORMAL") in ("ADVERTENCIA", "ANOMALIA"):
                    partes.append(f"fuera de su patrón personal ({estados_modelo[var].lower()})")
                cod = codigos.NOTIF_SEVERIDAD[sev]
                n = {"id": len(_lista) + 1, "usuario": usuario, "timestamp": ts, "severidad": sev,
                     "codigo": cod, "tipo": codigos.nombre(cod), "variable": var, "mensaje": f"{var} = {valor}: " + "; ".join(partes)}
                _lista.append(n)
                nuevas.append(n)
        if nuevas:
            _guardar()
    return nuevas


def evaluar_deriva(usuario, ts, var, serie):
    """Avisa una vez cuando aparece una deriva lenta; se rearma al desaparecer."""
    d = inferencia.deriva(var, serie)
    clave = (usuario, var)
    if not d["detectada"]:
        # histéresis: se rearma solo tras REARME lecturas seguidas sin deriva
        if _deriva.get(clave, 0) > 0:
            _sin[clave] = _sin.get(clave, 0) + 1
            if _sin[clave] >= REARME:
                _deriva[clave], _sin[clave] = 0, 0
        return []
    _sin[clave] = 0
    if _deriva.get(clave):
        return []
    _deriva[clave] = 1
    with _lock:
        n = {"id": len(_lista) + 1, "usuario": usuario, "timestamp": ts, "severidad": ref.VIGILAR,
             "codigo": 6020, "tipo": codigos.nombre(6020), "variable": var,
             "mensaje": f"{var}: deriva lenta {d['sentido']} de {d['cambio']} (respecto a {d['referencia']})"}
        _lista.append(n)
        _guardar()
    return [n]


def sincronizar(usuario, serie, hasta):
    """Procesa las lecturas de `serie` [(ts, {var: valor})] aún no vistas hasta el índice `hasta`.
    Devuelve las notificaciones nuevas."""
    nuevas = []
    ini = _procesado.get(usuario, -1) + 1
    if hasta < ini:
        return nuevas
    est_por_var = {}
    for var in config.VARIABLES_ANALIZADAS:
        devs, _ = inferencia._desv_variable(usuario, var)
        est_por_var[var] = {inferencia._norm(d["timestamp"]): d["status"] for d in devs}
    acum = {}
    for i in range(0, hasta + 1):
        ts, valores = serie[i]
        for v, x in valores.items():
            acum.setdefault(v, []).append((ts, x))
        if i < ini:
            continue
        estados = {v: est_por_var.get(v, {}).get(inferencia._norm(ts), "NORMAL") for v in valores}
        nuevas += evaluar_lectura(usuario, ts, valores, estados)
        for v in valores:
            if v in config.VARIABLES_ANALIZADAS:
                nuevas += evaluar_deriva(usuario, ts, v, acum[v])
    _procesado[usuario] = hasta
    return nuevas


def sincronizar_sueno(usuario, noches, hasta):
    """Como `sincronizar`, pero para las noches [(fecha, {variable_de_sueño: valor})] hasta el índice `hasta`.
    El sueño no tiene modelo personal: avisa por límite clínico (>= ALERTA) y por deriva lenta."""
    nuevas = []
    clave = (usuario, "sueno")
    ini = _procesado.get(clave, -1) + 1
    if hasta < ini:
        return nuevas
    acum = {}
    for i in range(0, hasta + 1):
        ts, valores = noches[i]
        for v, x in valores.items():
            acum.setdefault(v, []).append((ts, x))
        if i < ini:
            continue
        nuevas += evaluar_lectura(usuario, ts, valores, {})
        for v in valores:
            nuevas += evaluar_deriva(usuario, ts, v, acum[v])
    _procesado[clave] = hasta
    return nuevas


def sincronizar_cognitivo(usuario, sesiones):
    """Procesa las sesiones cognitivas aún no vistas. Notifica una vez por ALERTA sostenida (6010) y por deriva (6020);
    se rearma al desaparecer. Un VIGILAR o una ALERTA aislada no notifica (se trata como "repetir la prueba")."""
    nuevas = []
    sesiones = sorted(sesiones, key=cognitivo._fecha)
    clave = (usuario, "cognitivo")
    with _lock:
        ini = _procesado.get(clave, -1) + 1
        for i in range(ini, len(sesiones)):
            ev = cognitivo.evaluar(sesiones[: i + 1])
            ts = sesiones[i]["fecha"]
            if ev["alerta_sostenida"] and not _cog_alerta.get(usuario):
                nuevas.append(_nueva(usuario, ts, ref.ALERTA, 6010, "cognitivo",
                                     f"Rendimiento cognitivo claramente peor que su línea base en {U['COG_PERSISTENCIA_SESIONES']} sesiones seguidas. "
                                     + cognitivo.AVISO))
            _cog_alerta[usuario] = ev["alerta_sostenida"]
            d = ev["deriva"]
            if d["detectada"] and not _cog_deriva.get(usuario):
                nuevas.append(_nueva(usuario, ts, ref.VIGILAR, 6020, "cognitivo",
                                     f"cognitivo: deriva lenta del rendimiento ({', '.join(d['variables'])})"))
            _cog_deriva[usuario] = d["detectada"]
        _procesado[clave] = len(sesiones) - 1
        if nuevas:
            _guardar()
    return nuevas


def _nueva(usuario, ts, severidad, cod, variable, mensaje):
    n = {"id": len(_lista) + 1, "usuario": usuario, "timestamp": ts, "severidad": severidad,
         "codigo": cod, "tipo": codigos.nombre(cod), "variable": variable, "mensaje": mensaje}
    _lista.append(n)
    return n


def listar(usuario=None, desde=0):
    with _lock:
        return [n for n in _lista if n["id"] > desde and (usuario is None or n["usuario"] == usuario)]

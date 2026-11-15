"""Decisión apto / no apto por tripulante (orientativa, no es diagnóstico médico).

Los límites clínicos tienen la última palabra: el modelo personal ("¿es raro para esta persona?")
nunca puede anular un valor clínicamente peligroso. Todos los hallazgos llevan código (docs/CODIGOS.md).
"""
from src.salud import codigos, inferencia
from src.salud import referencias as ref

MODELO_DESVIADO = ("ADVERTENCIA", "ANOMALIA")


def evaluar_aptitud(usuario, series_por_var):
    """series_por_var = {variable: [(ts, valor), ...]} hasta el instante actual."""
    motivos, obs = [], []
    nivel, apto = ref.NORMAL, True
    resumen = inferencia.resumen_global(usuario, series_por_var)

    for var, m in resumen["medidas"].items():
        if not m:
            continue
        serie = series_por_var[var]
        nom = f"{var} {m['actual']} {m['unidad']}"
        clin, etiq = m["nivel_clinico"], m["interpretacion_clinica"]
        nivel = ref.mas_grave(nivel, clin)
        modelo_desv = m["estado_modelo"] in MODELO_DESVIADO

        if clin == ref.CRITICO:
            apto = False
            motivos.append(codigos.evento(5001, f"{nom}: {etiq} (límite crítico)", var))
        elif clin == ref.ALERTA:
            if inferencia.persistencia_clinica(var, serie):
                apto = False
                motivos.append(codigos.evento(5002, f"{nom}: {etiq} sostenida (límite clínico, aunque el modelo la vea normal)"
                                              if not modelo_desv else f"{nom}: {etiq} sostenida", var))
            elif modelo_desv:
                apto = False
                motivos.append(codigos.evento(5003, f"{nom}: {etiq} y fuera de su patrón personal", var))
            else:
                obs.append(codigos.evento(5010, f"{nom}: {etiq} (lectura puntual)", var))
        elif clin == ref.VIGILAR:
            obs.append(codigos.evento(5012, f"{nom}: {etiq}", var))

        if m["estado_modelo"] == "ANOMALIA":
            nivel = ref.mas_grave(nivel, ref.ALERTA)
            if clin != ref.NORMAL:
                apto = False
                motivos.append(codigos.evento(5015, f"{var}: anomalía respecto a su modelo personal y fuera de rango clínico", var))
            else:
                obs.append(codigos.evento(5013, f"{var}: anomalía respecto a su modelo personal (dentro de rango clínico)", var))
        elif m["estado_modelo"] == "ADVERTENCIA":
            nivel = ref.mas_grave(nivel, ref.VIGILAR)
            obs.append(codigos.evento(5014, f"{var}: desviación leve de su patrón personal", var))

        d = m["deriva"]
        if d["detectada"]:
            msg = (f"{var}: deriva lenta {d['sentido']} de {d['cambio']} {m['unidad']} "
                   f"(respecto a {d['referencia']}; umbral {d['umbral']})")
            if clin != ref.NORMAL:       # ya está cambiando Y fuera de lo normal: no apto
                apto = False
                nivel = ref.mas_grave(nivel, ref.ALERTA)
                motivos.append(codigos.evento(5005, msg + ", con el valor ya fuera de rango", var))
            else:
                nivel = ref.mas_grave(nivel, ref.VIGILAR)
                obs.append(codigos.evento(5005, msg, var))

        if not m["linea_base_confiable"]:
            obs.append(codigos.evento(5006, f"{var}: su línea base ya estaba fuera de rango clínico; "
                                            "el modelo personal no es referencia fiable, manda el criterio clínico", var))
            nivel = ref.mas_grave(nivel, ref.VIGILAR)

    for p in resumen["patrones"]:
        if p["codigo"] == 5004:          # compromiso respiratorio: motivo de no apto
            apto = False
            nivel = ref.mas_grave(nivel, ref.ALERTA)
            motivos.append(p)
        else:
            obs.append(p)

    if not apto:
        nivel = ref.mas_grave(nivel, ref.ALERTA)
        codigo = 1011 if nivel == ref.CRITICO else 1010
        rec = ["No apto para actividad exigente: reposo y reevaluación por el médico de vuelo."]
    elif obs:
        codigo, rec = 1002, ["Apto con seguimiento: repetir medición en los próximos minutos."]
    else:
        codigo, rec = 1001, ["Sin hallazgos: continuar con la rutina."]
    return {"usuario": usuario, "apto": apto, "nivel": nivel, "codigo": codigo, "estado": codigos.nombre(codigo),
            "motivos": motivos, "observaciones": obs, "recomendaciones": rec, "derivadas": resumen["derivadas"]}

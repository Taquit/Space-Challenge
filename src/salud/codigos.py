"""Catálogo de códigos de respuesta para el frontend. Documentado en docs/CODIGOS.md.

Familias:  1xxx estado general · 2xxx nivel clínico · 3xxx modelo personal · 4xxx tendencia/deriva
           5xxx hallazgos (motivos/observaciones) · 6xxx notificaciones · 7xxx chat · 9xxx errores
"""
# nombre, descripción
CATALOGO = {
    # --- 1xxx: estado general del tripulante (aptitud) ---
    1001: ("SALUDABLE", "Apto, sin hallazgos."),
    1002: ("APTO_CON_SEGUIMIENTO", "Apto, pero con observaciones que conviene vigilar."),
    1010: ("RIESGO", "No apto: hay un riesgo que requiere reposo y reevaluación."),
    1011: ("CRITICO", "No apto: valor en rango crítico, atención inmediata."),
    # --- 2xxx: nivel clínico de una medida (límite absoluto) ---
    2001: ("CLINICO_NORMAL", "Valor dentro del rango clínico de referencia."),
    2002: ("CLINICO_VIGILAR", "Valor ligeramente fuera del rango."),
    2010: ("CLINICO_ALERTA", "Valor claramente fuera del rango."),
    2011: ("CLINICO_CRITICO", "Valor en rango crítico."),
    # --- 3xxx: modelo personal ---
    3000: ("MODELO_NO_DISPONIBLE", "Sin modelo personal para esta medida."),
    3001: ("MODELO_NORMAL", "Normal para esta persona según su modelo."),
    3002: ("MODELO_ADVERTENCIA", "Desviación leve (≥2σ) de su patrón personal."),
    3010: ("MODELO_ANOMALIA", "Desviación fuerte (≥3σ) de su patrón personal."),
    # --- 4xxx: tendencia y deriva ---
    4001: ("TENDENCIA_ESTABLE", "La medida se mantiene estable."),
    4002: ("TENDENCIA_ASCENDENTE", "La medida sube de forma sostenida."),
    4003: ("TENDENCIA_DESCENDENTE", "La medida baja de forma sostenida."),
    4101: ("SIN_DERIVA", "Sin cambio acumulado relevante."),
    4110: ("DERIVA_LENTA", "Cambio acumulado lento pero relevante, aunque cada lectura parezca normal."),
    # --- 5xxx: hallazgos (motivos de no apto u observaciones) ---
    5001: ("LIMITE_CRITICO", "Medida en rango crítico."),
    5002: ("ALERTA_CLINICA_SOSTENIDA", "Medida en alerta clínica durante varias lecturas seguidas."),
    5003: ("ALERTA_CLINICA_Y_MODELO", "Medida en alerta clínica y fuera de su patrón personal."),
    5004: ("PATRON_RESPIRATORIO", "SpO2 baja junto con pulso fuera de su patrón: posible compromiso respiratorio."),
    5005: ("DERIVA_LENTA_HALLAZGO", "Deriva lenta de la medida (con valor ya fuera de lo normal si es motivo)."),
    5006: ("LINEA_BASE_NO_CONFIABLE", "La línea base ya estaba fuera de rango clínico; manda el criterio clínico."),
    5007: ("PATRON_CIRCULATORIO", "Presión sistólica y pulso desviados a la vez."),
    5008: ("INDICE_CHOQUE_ELEVADO", "Índice de choque (pulso/sistólica) > 0.9."),
    5009: ("PRESION_PULSO_ANORMAL", "Presión de pulso fuera de 25-60 mmHg."),
    5010: ("ALERTA_PUNTUAL", "Una lectura en alerta clínica, aún no sostenida."),
    5011: ("MULTIPLES_DESVIACIONES", "Tres o más variables fuera de su patrón a la vez."),
    5012: ("FUERA_DE_RANGO_LEVE", "Valor ligeramente fuera del rango clínico."),
    5013: ("ANOMALIA_PERSONAL", "Anomalía respecto a su modelo, pero dentro del rango clínico."),
    5014: ("DESVIACION_PERSONAL_LEVE", "Desviación leve de su patrón personal."),
    5015: ("ANOMALIA_Y_FUERA_DE_RANGO", "Anomalía personal y además fuera de rango clínico."),
    # --- 6xxx: notificaciones ---
    6001: ("NOTIF_VIGILAR", "Notificación de vigilancia."),
    6010: ("NOTIF_ALERTA", "Notificación de alerta."),
    6011: ("NOTIF_CRITICO", "Notificación crítica."),
    6020: ("NOTIF_DERIVA", "Notificación por deriva lenta."),
    # --- 7xxx: chat ---
    7001: ("RESPUESTA_OK", "Respuesta del agente generada."),
    # --- 9xxx: errores ---
    9001: ("TRIPULANTE_NO_ENCONTRADO", "El tripulante no existe."),
    9002: ("VARIABLE_DESCONOCIDA", "La medida solicitada no existe."),
    9003: ("LLM_NO_DISPONIBLE", "LM Studio no responde."),
}

NIVEL_CLINICO = {"NORMAL": 2001, "VIGILAR": 2002, "ALERTA": 2010, "CRITICO": 2011}
ESTADO_MODELO = {"SIN_MODELO": 3000, "NORMAL": 3001, "ADVERTENCIA": 3002, "ANOMALIA": 3010}
TENDENCIA = {"estable": 4001, "ascendente": 4002, "descendente": 4003}
NOTIF_SEVERIDAD = {"VIGILAR": 6001, "ALERTA": 6010, "CRITICO": 6011}


def nombre(codigo):
    return CATALOGO[codigo][0]


def evento(codigo, mensaje, variable=None):
    """Hallazgo serializable: {codigo, nombre, mensaje, variable}."""
    return {"codigo": codigo, "nombre": nombre(codigo), "mensaje": mensaje, "variable": variable}


def error(codigo, mensaje=None):
    """Cuerpo de error para HTTPException(detail=...)."""
    return {"codigo": codigo, "nombre": nombre(codigo), "mensaje": mensaje or CATALOGO[codigo][1]}


def catalogo():
    return [{"codigo": c, "nombre": n, "descripcion": d} for c, (n, d) in sorted(CATALOGO.items())]

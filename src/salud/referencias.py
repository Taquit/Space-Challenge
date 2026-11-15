"""Límites clínicos absolutos (adulto en reposo) y magnitudes derivadas.

Son solo una red de seguridad: el criterio normal/anómalo del día a día es el rango
del modelo personal de cada astronauta. Orientativo, no es diagnóstico médico.
"""
NORMAL, VIGILAR, ALERTA, CRITICO = "NORMAL", "VIGILAR", "ALERTA", "CRITICO"
ORDEN = {NORMAL: 0, VIGILAR: 1, ALERTA: 2, CRITICO: 3}

# variable -> [(umbral_inferior, nivel_si_valor<umbral_inferior)...], etc. Se evalúa de más grave a menos.
# Cada regla: (condición, nivel, etiqueta)
_REGLAS = {
    "pulso": [
        (lambda v: v < 40, CRITICO, "bradicardia severa"), (lambda v: v > 130, CRITICO, "taquicardia severa"),
        (lambda v: v < 50, ALERTA, "bradicardia"), (lambda v: v > 110, ALERTA, "taquicardia"),
        (lambda v: v < 60, VIGILAR, "pulso bajo"), (lambda v: v > 100, VIGILAR, "pulso elevado"),
    ],
    "spo2": [
        (lambda v: v < 90, CRITICO, "hipoxemia severa"),
        (lambda v: v < 92, ALERTA, "hipoxemia"),
        (lambda v: v < 95, VIGILAR, "saturación baja"),
    ],
    "presion_sistolica": [
        (lambda v: v < 80, CRITICO, "hipotensión severa"), (lambda v: v >= 180, CRITICO, "crisis hipertensiva"),
        (lambda v: v < 90, ALERTA, "hipotensión"), (lambda v: v >= 140, ALERTA, "hipertensión"),
        (lambda v: v >= 130, VIGILAR, "presión sistólica elevada"),
    ],
    "presion_diastolica": [
        (lambda v: v < 50, CRITICO, "hipotensión diastólica severa"), (lambda v: v >= 120, CRITICO, "crisis hipertensiva"),
        (lambda v: v < 60, ALERTA, "hipotensión diastólica"), (lambda v: v >= 90, ALERTA, "hipertensión diastólica"),
        (lambda v: v >= 80, VIGILAR, "presión diastólica elevada"),
    ],
}


def clasificar(variable, valor):
    """(nivel, etiqueta) del valor según el límite clínico absoluto."""
    for cond, nivel, etiqueta in _REGLAS.get(variable, []):
        if cond(valor):
            return nivel, etiqueta
    return NORMAL, "dentro del rango"


def mas_grave(*niveles):
    return max(niveles, key=ORDEN.__getitem__, default=NORMAL)


def presion_pulso(sistolica, diastolica):
    return sistolica - diastolica


def presion_media(sistolica, diastolica):
    return diastolica + (sistolica - diastolica) / 3


def indice_choque(pulso, sistolica):
    return pulso / sistolica

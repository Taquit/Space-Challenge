"""Límites clínicos absolutos (adulto en reposo) y magnitudes derivadas.

Son solo una red de seguridad: el criterio normal/anómalo del día a día es el rango
del modelo personal de cada astronauta. Orientativo, no es diagnóstico médico.
"""
from src.salud.umbrales import U

NORMAL, VIGILAR, ALERTA, CRITICO = "NORMAL", "VIGILAR", "ALERTA", "CRITICO"
ORDEN = {NORMAL: 0, VIGILAR: 1, ALERTA: 2, CRITICO: 3}

# Umbrales en umbrales.env (cargados en src/salud/umbrales.py). Se evalúa de más grave a menos grave.
_REGLAS = {
    "pulso": [
        (lambda v: v < U["PULSO_CRITICO_MIN"], CRITICO, "bradicardia severa"), (lambda v: v > U["PULSO_CRITICO_MAX"], CRITICO, "taquicardia severa"),
        (lambda v: v < U["PULSO_ALERTA_MIN"], ALERTA, "bradicardia"), (lambda v: v > U["PULSO_ALERTA_MAX"], ALERTA, "taquicardia"),
        (lambda v: v < U["PULSO_VIGILAR_MIN"], VIGILAR, "pulso bajo"), (lambda v: v > U["PULSO_VIGILAR_MAX"], VIGILAR, "pulso elevado"),
    ],
    "spo2": [
        (lambda v: v < U["SPO2_CRITICO_MIN"], CRITICO, "hipoxemia severa"),
        (lambda v: v < U["SPO2_ALERTA_MIN"], ALERTA, "hipoxemia"),
        (lambda v: v < U["SPO2_VIGILAR_MIN"], VIGILAR, "saturación baja"),
    ],
    "presion_sistolica": [
        (lambda v: v < U["SISTOLICA_CRITICO_MIN"], CRITICO, "hipotensión severa"), (lambda v: v >= U["SISTOLICA_CRITICO_MAX"], CRITICO, "crisis hipertensiva"),
        (lambda v: v < U["SISTOLICA_ALERTA_MIN"], ALERTA, "hipotensión"), (lambda v: v >= U["SISTOLICA_ALERTA_MAX"], ALERTA, "hipertensión"),
        (lambda v: v >= U["SISTOLICA_VIGILAR_MAX"], VIGILAR, "presión sistólica elevada"),
    ],
    "presion_diastolica": [
        (lambda v: v < U["DIASTOLICA_CRITICO_MIN"], CRITICO, "hipotensión diastólica severa"), (lambda v: v >= U["DIASTOLICA_CRITICO_MAX"], CRITICO, "crisis hipertensiva"),
        (lambda v: v < U["DIASTOLICA_ALERTA_MIN"], ALERTA, "hipotensión diastólica"), (lambda v: v >= U["DIASTOLICA_ALERTA_MAX"], ALERTA, "hipertensión diastólica"),
        (lambda v: v >= U["DIASTOLICA_VIGILAR_MAX"], VIGILAR, "presión diastólica elevada"),
    ],
    # Sueño (una lectura = una noche)
    "sueno_eficiencia": [
        (lambda v: v < U["SUENO_EFICIENCIA_CRITICO_MIN"], CRITICO, "eficiencia de sueño muy baja"),
        (lambda v: v < U["SUENO_EFICIENCIA_ALERTA_MIN"], ALERTA, "eficiencia de sueño baja"),
        (lambda v: v < U["SUENO_EFICIENCIA_VIGILAR_MIN"], VIGILAR, "eficiencia de sueño reducida"),
    ],
    "sueno_duracion": [
        (lambda v: v < U["SUENO_DURACION_CRITICO_MIN"], CRITICO, "privación severa de sueño"),
        (lambda v: v < U["SUENO_DURACION_ALERTA_MIN"], ALERTA, "sueño insuficiente"),
        (lambda v: v < U["SUENO_DURACION_VIGILAR_MIN"], VIGILAR, "sueño algo corto"),
    ],
    "sueno_latencia": [
        (lambda v: v > U["SUENO_LATENCIA_CRITICO_MAX"], CRITICO, "latencia de sueño muy larga"),
        (lambda v: v > U["SUENO_LATENCIA_ALERTA_MAX"], ALERTA, "latencia de sueño larga"),
        (lambda v: v > U["SUENO_LATENCIA_VIGILAR_MAX"], VIGILAR, "latencia de sueño algo larga"),
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

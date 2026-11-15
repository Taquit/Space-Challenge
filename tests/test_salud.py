from src.salud import aptitud, inferencia, notificaciones
from src.salud import referencias as ref


def test_clasificar_limites():
    assert ref.clasificar("spo2", 91.9)[0] == ref.ALERTA
    assert ref.clasificar("spo2", 92)[0] == ref.VIGILAR
    assert ref.clasificar("spo2", 95)[0] == ref.NORMAL
    assert ref.clasificar("pulso", 120)[0] == ref.ALERTA
    assert ref.clasificar("presion_sistolica", 135)[0] == ref.VIGILAR


def test_derivadas():
    d = inferencia.derivadas({"presion_sistolica": 120, "presion_diastolica": 80, "pulso": 60})
    assert d == {"presion_pulso": 40, "presion_media": 93.3, "indice_choque": 0.5}


def _series(**kw):
    return {v: [(f"2026-11-01T00:{i:02d}:00", x) for i, x in enumerate(vals)] for v, vals in kw.items()}


def test_apto_y_no_apto():
    ok = _series(pulso=[70] * 20, spo2=[97] * 20, presion_sistolica=[115] * 20, presion_diastolica=[75] * 20)
    assert aptitud.evaluar_aptitud("__nadie__", ok)["apto"] is True
    mal = _series(pulso=[70] * 20, spo2=[97] * 19 + [88], presion_sistolica=[115] * 20, presion_diastolica=[75] * 20)
    r = aptitud.evaluar_aptitud("__nadie__", mal)
    assert r["apto"] is False and r["nivel"] == ref.CRITICO


def test_notificaciones_sin_duplicados():
    notificaciones.reiniciar()
    n1 = notificaciones.evaluar_lectura("t", "ts1", {"spo2": 93}, {"spo2": "ADVERTENCIA"})
    n2 = notificaciones.evaluar_lectura("t", "ts2", {"spo2": 93}, {"spo2": "ADVERTENCIA"})
    n3 = notificaciones.evaluar_lectura("t", "ts3", {"spo2": 90.5}, {})
    assert notificaciones.evaluar_lectura("t", "ts4", {"pulso": 58}, {}) == []   # leve y normal para la persona
    assert len(n1) == 1 and n2 == [] and n3[0]["severidad"] == ref.ALERTA
    notificaciones.reiniciar()


def _bajando(ini, fin, n):
    return [round(ini + (fin - ini) * i / (n - 1), 2) for i in range(n)]


def test_deriva_lenta_detectada_y_sin_deriva():
    d = inferencia.deriva("spo2", _series(spo2=_bajando(97, 93, 60))["spo2"])
    assert d["detectada"] and d["codigo"] == 4110 and d["sentido"] == "descendente"
    assert inferencia.deriva("spo2", _series(spo2=[97] * 60)["spo2"])["codigo"] == 4101


def test_limite_clinico_manda_sobre_modelo_normal():
    # Caída lenta hasta 91 (alerta clínica): el modelo (inexistente aquí) no puede anular el límite
    s = _series(pulso=[70] * 60, spo2=_bajando(97, 91, 60), presion_sistolica=[115] * 60, presion_diastolica=[75] * 60)
    r = aptitud.evaluar_aptitud("__nadie__", s)
    assert r["apto"] is False and r["codigo"] == 1010
    assert {5002, 5005} & {m["codigo"] for m in r["motivos"]}


def test_codigos_estado_y_linea_base():
    ok = _series(pulso=[70] * 20, spo2=[97] * 20, presion_sistolica=[115] * 20, presion_diastolica=[75] * 20)
    assert aptitud.evaluar_aptitud("__nadie__", ok)["codigo"] == 1001
    crit = _series(pulso=[70] * 20, spo2=[97] * 19 + [88], presion_sistolica=[115] * 20, presion_diastolica=[75] * 20)
    assert aptitud.evaluar_aptitud("__nadie__", crit)["codigo"] == 1011
    mala_base = _series(pulso=[70] * 20, spo2=[91] * 20, presion_sistolica=[115] * 20, presion_diastolica=[75] * 20)
    r = aptitud.evaluar_aptitud("__nadie__", mala_base)
    assert 5006 in {o["codigo"] for o in r["observaciones"]}
    assert r["apto"] is False      # sostenido en alerta clínica aunque "siempre estuvo así"

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


def test_umbrales_cargan_del_archivo_y_entorno(tmp_path, monkeypatch):
    from src.salud import umbrales
    assert umbrales.U["SPO2_ALERTA_MIN"] == 92          # coincide con umbrales.env
    monkeypatch.setenv("SPO2_ALERTA_MIN", "94")
    assert umbrales.cargar()["SPO2_ALERTA_MIN"] == 94   # el entorno tiene prioridad
    monkeypatch.setenv("SPO2_ALERTA_MIN", "abc")
    import pytest
    with pytest.raises(ValueError):
        umbrales.cargar()


# ---- Sueño ----
def test_clasificar_sueno():
    assert ref.clasificar("sueno_eficiencia", 92)[0] == ref.NORMAL
    assert ref.clasificar("sueno_eficiencia", 80)[0] == ref.VIGILAR
    assert ref.clasificar("sueno_eficiencia", 70)[0] == ref.ALERTA
    assert ref.clasificar("sueno_eficiencia", 52.5)[0] == ref.CRITICO
    assert ref.clasificar("sueno_duracion", 5.5)[0] == ref.ALERTA
    assert ref.clasificar("sueno_latencia", 30)[0] == ref.NORMAL      # el máximo es ">"
    assert ref.clasificar("sueno_latencia", 100)[0] == ref.CRITICO


def _noches(**kw):
    return {v: [(f"2004-09-{i + 1:02d}", x) for i, x in enumerate(vals)] for v, vals in kw.items()}


def test_sueno_deficiente_no_declara_no_apto_pero_avisa():
    vit = _series(pulso=[70] * 20, spo2=[97] * 20, presion_sistolica=[115] * 20, presion_diastolica=[75] * 20)
    s = {**vit, **_noches(sueno_eficiencia=[90] * 15 + [60, 60, 60], sueno_duracion=[7.5] * 15 + [4.5] * 3)}
    r = aptitud.evaluar_aptitud("__nadie__", s)
    assert r["apto"] is True                       # el sueño solo observa
    assert {5016, 5017} <= {o["codigo"] for o in r["observaciones"]}
    assert r["codigo"] == 1002


def test_sueno_sostenido_requiere_varias_noches():
    una = _noches(sueno_eficiencia=[90] * 17 + [60])
    assert inferencia.patron_sueno(una) == []
    tres = _noches(sueno_eficiencia=[90] * 15 + [60, 60, 60])
    assert inferencia.patron_sueno(tres)[0]["codigo"] == 5017


def test_resumen_sueno_sin_modelo_ni_datos_suficientes():
    r = inferencia.resumen_medida("__nadie__", "sueno_eficiencia", _noches(sueno_eficiencia=[90, 85, 70])["sueno_eficiencia"])
    assert r["estado_modelo"] == "SIN_MODELO" and r["unidad"] == "%" and r["deriva"]["detectada"] is False


def test_notificacion_sueno_por_limite_clinico():
    notificaciones.reiniciar()
    noches = [(f"2004-09-{i + 1:02d}", {"sueno_eficiencia": e}) for i, e in enumerate([92, 90, 58])]
    n = notificaciones.sincronizar_sueno("__s__", noches, 2)
    assert len(n) == 1 and n[0]["variable"] == "sueno_eficiencia" and n[0]["severidad"] == ref.CRITICO
    assert notificaciones.sincronizar_sueno("__s__", noches, 2) == []      # no repite
    notificaciones.reiniciar()


def test_importador_promedia_duplicados_y_mapea(tmp_path):
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("imp", Path(__file__).resolve().parent.parent / "scripts" / "importar_sueno.py")
    imp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(imp)
    csv_ = tmp_path / "s.csv"
    csv_.write_text("﻿ID,Subject,Date,Test_Phase,BR_Day,Record Number,Sleep latency,Sleep duration,Sleep efficiency,Comments\n"
                    "1,C1G0003,9/10/2004,IN_TEST,2,1,0:10,7:30,90,\n"
                    "2,C1G0003,9/10/2004,IN_TEST,2,2,0:20,6:30,80,Ambien 5mg\n"
                    "3,XXXX,9/10/2004,IN_TEST,2,3,0:20,6:30,80,\n", encoding="utf-8")
    out = imp.convertir(csv_)
    assert len(out) == 1 and out[0]["usuario"] == "astro_1" and out[0]["timestamp"] == "2004-09-10"
    assert out[0]["valores"] == {"sueno_latencia": 15.0, "sueno_duracion": 7.0, "sueno_eficiencia": 85.0}
    assert out[0]["medicacion"] == "Ambien 5mg"


def test_monitor_sueno_y_tripulante_sin_sueno():
    from src.datos.salud import Monitor
    from src import config
    m = Monitor(seg_por_lectura=1000)             # reloj lento: solo la primera lectura/noche
    assert m.noches_disponibles("astro_1") > 0 and m.noches_disponibles("astro_3") == 0
    e = m.estado("astro_3", 10)
    assert e["sueno"] == [] and "sueno_eficiencia" not in e["actual"]
    e1 = m.estado("astro_1", 10)
    assert len(e1["sueno"]) == 1 and e1["actual"]["sueno_eficiencia"]["unidad"] == "%"
    assert set(config.VARIABLES_SUENO) <= set(m.variables("astro_1"))

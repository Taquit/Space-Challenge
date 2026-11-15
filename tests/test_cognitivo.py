import itertools
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.datos.cognitivo import DatosCognitivo
from src.salud import aptitud, cognitivo, notificaciones
from src.salud import referencias as ref
from src.salud.umbrales import U

T0 = datetime(2026, 9, 6, 9, 30, tzinfo=timezone(timedelta(hours=-6)))


def ses(i, rt=280.0, lapsos=1, tput=0.47, mx=8, fam=False):
    return {"id": i, "fecha": (T0 + timedelta(days=7 * i)).isoformat(), "forma": "A", "semilla": i, "familiarizacion": fam,
            "pruebas": {"pvt": {"rt_media_ms": rt, "rt_mediana_ms": rt - 5, "lapsos": lapsos, "falsos_inicios": 0, "n_estimulos": 24},
                        "dsst": {"correctas": 42, "intentos": 44, "precision": 0.95, "throughput": tput, "rt_media_ms": 2000.0},
                        "matrix": {"correctas": mx, "intentos": 12, "precision": mx / 12, "tiempo_total_s": 140.0, "throughput": mx / 140}},
            "contexto": {"comentario": ""}}


def base():
    """Familiarización (peor, se descarta) + 3 sesiones de línea base con algo de variación."""
    return [ses(0, rt=400, lapsos=6, tput=0.3, mx=3, fam=True),
            ses(1, rt=270), ses(2, rt=280, tput=0.48), ses(3, rt=290, lapsos=2, tput=0.46, mx=9)]


MALA = dict(rt=400, lapsos=8, tput=0.30, mx=3)


def test_familiarizacion_excluida_y_sin_linea_base():
    ev = cognitivo.evaluar(base()[:3])      # familiarización + 2 de base: faltan sesiones
    assert ev["estado"] == "SIN_LINEA_BASE" and ev["codigo_nivel"] == 8000 and ev["sesiones_validas"] == 2
    ev = cognitivo.evaluar(base())
    assert ev["linea_base_completa"] and ev["linea_base"]["cog_pvt_rt"]["media"] == 280.0   # no entra la de rt=400
    assert ev["estado"] == "NORMAL" and ev["codigo_nivel"] == 8001


def test_z_signo_correcto():
    assert cognitivo.z_deterioro(300, 280, 10, "sube") == 2.0
    assert cognitivo.z_deterioro(260, 280, 10, "sube") == -2.0
    assert cognitivo.z_deterioro(0.40, 0.48, 0.04, "baja") == pytest.approx(2.0)
    assert cognitivo.z_deterioro(0.56, 0.48, 0.04, "baja") == pytest.approx(-2.0)
    ev = cognitivo.evaluar(base() + [ses(4, **MALA)])       # todo peor: todas las z positivas
    assert all(m["z"] > 0 for m in ev["ultima"]["metricas"].values())
    ev = cognitivo.evaluar(base() + [ses(4, rt=250, lapsos=0, tput=0.55, mx=11)])   # todo mejor: z negativas, NORMAL
    assert all(m["z"] < 0 for m in ev["ultima"]["metricas"].values()) and ev["estado"] == "NORMAL"


def test_piso_de_desviacion():
    iguales = [ses(0, fam=True)] + [ses(i, lapsos=0) for i in (1, 2, 3)]    # desviación 0 en todo
    ev = cognitivo.evaluar(iguales + [ses(4, rt=300, lapsos=3)])
    for m in ev["ultima"]["metricas"].values():
        assert abs(m["z"]) < 1000
    assert ev["linea_base"]["cog_pvt_rt"]["sd"] == 0 and ev["linea_base"]["cog_pvt_rt"]["sd_efectiva"] > 0
    assert ev["linea_base"]["cog_pvt_lapsos"]["sd_efectiva"] >= U["COG_SD_MIN_ABS_CONTEO"]


def test_persistencia_y_notificaciones():
    notificaciones.reiniciar()
    aislada = base() + [ses(4, **MALA)]
    assert not cognitivo.evaluar(aislada)["alerta_sostenida"]
    assert notificaciones.sincronizar_cognitivo("u_cog", aislada) == []          # una ALERTA aislada: repetir, no notificar
    seguidas = aislada + [ses(5, **MALA)]
    assert cognitivo.evaluar(seguidas)["alerta_sostenida"]
    n = notificaciones.sincronizar_cognitivo("u_cog", seguidas)
    assert [x["codigo"] for x in n if x["variable"] == "cognitivo"][0] == 6010
    assert notificaciones.sincronizar_cognitivo("u_cog", seguidas) == []         # sin duplicados
    notificaciones.reiniciar()


def test_vigilar_no_notifica():
    notificaciones.reiniciar()
    s = base() + [ses(4, rt=298)]                # z de rt ~ 1.8 con sd_ef 14: VIGILAR/ALERTA aislada
    assert notificaciones.sincronizar_cognitivo("u_vig", s) == []
    notificaciones.reiniciar()


def test_deriva_gradual_si_y_atipica_aislada_no():
    gradual = base() + [ses(4 + k, rt=285 + 6 * k, lapsos=1 + k // 2, tput=0.47 - 0.01 * k, mx=8) for k in range(4)]
    d = cognitivo.evaluar(gradual)["deriva"]
    assert d["detectada"] and d["codigo"] == 4110
    aislada = base() + [ses(4), ses(5), ses(6, **MALA), ses(7)]
    d = cognitivo.evaluar(aislada)["deriva"]
    assert not d["detectada"] and d["codigo"] == 4101


def _series(**kw):
    return {v: [(f"2026-11-01T00:{i:02d}:00", x) for i, x in enumerate(vals)] for v, vals in kw.items()}


def test_aptitud_sin_sesiones_es_identica():
    s = _series(pulso=[70] * 20, spo2=[97] * 20, presion_sistolica=[115] * 20, presion_diastolica=[75] * 20)
    a = aptitud.evaluar_aptitud("__nadie__", s)
    assert a == aptitud.evaluar_aptitud("__nadie__", s, None) == aptitud.evaluar_aptitud("__nadie__", s, [])
    assert "cognitivo" not in a and a["codigo"] == 1001


def test_cognitivo_observa_y_pasa_a_seguimiento():
    s = _series(pulso=[70] * 20, spo2=[97] * 20, presion_sistolica=[115] * 20, presion_diastolica=[75] * 20)
    a = aptitud.evaluar_aptitud("__nadie__", s, base() + [ses(4, **MALA)])
    assert a["apto"] is True and a["codigo"] == 1002 and a["nivel"] == ref.VIGILAR
    assert 5018 in {o["codigo"] for o in a["observaciones"]} and a["motivos"] == []
    assert a["cognitivo"]["codigo_nivel"] == 8010


def test_patrones_sueno_y_fisiologia():
    ev = cognitivo.bloque(base() + [ses(4, **MALA)], {"patrones": [{"codigo": 5017}], "medidas": {
        "pulso": {"variable": "pulso", "nivel_clinico": "VIGILAR", "estado_modelo": "NORMAL"}}})
    assert {5018, 5019, 5020} <= {o["codigo"] for o in ev["observaciones"]}
    ev = cognitivo.bloque(base() + [ses(4)], {"patrones": [{"codigo": 5017}], "medidas": {}})
    assert ev["observaciones"] == []      # sin caída cognitiva no hay patrón


def test_nunca_no_apto():
    """Ninguna combinación de entradas cognitivas produce 1010 o 1011 con signos vitales sanos."""
    s = _series(pulso=[70] * 20, spo2=[97] * 20, presion_sistolica=[115] * 20, presion_diastolica=[75] * 20)
    casos = itertools.product([250, 280, 400, 900], [0, 3, 30], [0.5, 0.2, 0.0], [0, 8, 12])
    for rt, lap, tp, mx in casos:
        for n in (1, 2, 3, 6):
            sesiones = base() + [ses(4 + k, rt=rt, lapsos=lap, tput=tp, mx=mx) for k in range(n)]
            a = aptitud.evaluar_aptitud("__nadie__", s, sesiones)
            assert a["apto"] is True and a["codigo"] in (1001, 1002)


# ---- Datos y API ----
@pytest.fixture
def api(tmp_path, monkeypatch):
    from src.api import salud as api_salud
    monkeypatch.setattr(api_salud, "datos_cognitivo", DatosCognitivo(tmp_path / "cog.json"))
    notificaciones.reiniciar()
    app = FastAPI()
    app.include_router(api_salud.router)
    yield TestClient(app), tmp_path
    notificaciones.reiniciar()


def test_api_ciclo_completo(api):
    c, tmp = api
    u = c.get("/tripulantes").json()[0]["id"]
    assert c.get(f"/tripulantes/{u}/cognitivo/resumen").json()["codigo_nivel"] == 8000
    for s in base() + [ses(4, **MALA), ses(5, **MALA)]:
        s = {k: v for k, v in s.items() if k != "id"}
        r = c.post(f"/tripulantes/{u}/cognitivo", json=s)
        assert r.status_code == 201
    assert r.json()["codigo_nivel"] == 8010 and any(n["codigo"] == 6010 for n in r.json()["notificaciones"])
    h = c.get(f"/tripulantes/{u}/cognitivo").json()
    assert len(h["sesiones"]) == 6 and h["sesiones"][-1]["evaluacion"]["nivel"] == "ALERTA"
    assert (tmp / "cog.json").exists()
    r = c.get(f"/tripulantes/{u}/aptitud").json()
    assert r["cognitivo"]["codigo_nivel"] == 8010 and r["codigo"] in (1002, 1010, 1011)
    assert "cognitivo" in c.get(f"/tripulantes/{u}/resumen").json()
    assert any(n["variable"] == "cognitivo" for n in c.get(f"/tripulantes/{u}/notificaciones").json())


def test_api_errores(api):
    c, _ = api
    u = c.get("/tripulantes").json()[0]["id"]
    r = c.post(f"/tripulantes/{u}/cognitivo", json={"fecha": "ayer", "pruebas": {}})
    assert r.status_code == 422 and r.json()["detail"]["codigo"] == 9004
    r = c.post(f"/tripulantes/{u}/cognitivo", json={"fecha": T0.isoformat(), "pruebas": {"pvt": {"rt_media_ms": -1}}})
    assert r.json()["detail"]["codigo"] == 9004
    r = c.post("/tripulantes/__nadie__/cognitivo", json=base()[1])
    assert r.status_code == 404 and r.json()["detail"]["codigo"] == 9001
    assert c.get("/tripulantes/__nadie__/cognitivo").json()["detail"]["codigo"] == 9001


def test_simulador_cumple_aceptacion():
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("sim", Path(__file__).parent.parent / "scripts" / "simular_cognitivo.py")
    sim = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sim)
    datos = sim.generar()
    ev = {u: cognitivo.evaluar(s) for u, s in datos.items()}
    assert ev["astro_1"]["codigo_nivel"] == 8001 and not ev["astro_1"]["deriva"]["detectada"]
    assert ev["astro_2"]["codigo_nivel"] in (8002, 8010)
    assert ev["astro_3"]["deriva"]["codigo"] == 4110

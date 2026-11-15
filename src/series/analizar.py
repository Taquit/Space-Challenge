"""Puente entre data/fisiologico.json y el modelo One-Step-Ahead de NasaSpaceApps-Model.

Convierte el JSON (formato largo: usuario/timestamp/variable/valor) al formato que
espera el modelo, predice cada medición con las anteriores y escribe un JSON de
desviaciones (ADVERTENCIA / ANOMALIA) con el esquema de `json_generator`.

Cada usuario tiene su propio modelo por variable (models/series/usuarios/<usuario>_<variable>.joblib),
entrenado solo con sus datos. Salida: {usuario: {variable: reporte}}.

Uso:  python -m src.series.analizar [--usuario astro_1] [--entrada ruta.json] [--entrenar]
(el reentrenamiento es automático cada config.REENTRENAR_CADA mediciones nuevas; --entrenar lo fuerza)
"""
import argparse
import json
import datetime
import sys
import warnings

import joblib
import pandas as pd

from src import config
from src.datos.salud import UNIDADES
from src.series import anomaly_detection, features, json_generator, models

WARMUP = 15              # mismas mediciones mínimas que predict_one_step_ahead.py
BASELINE_N = 15          # mediciones iniciales del usuario que fijan su línea base
FUENTE = "data/fisiologico.json"


def cargar_modelo(ruta=config.MODELO_SERIES):
    """Carga el pipeline guardado. Se pickleó con los módulos `src.features`,
    `src.models` y `src.anomaly_detection`; aquí viven en `src.series`."""
    sys.modules.setdefault("src.features", features)
    sys.modules.setdefault("src.models", models)
    sys.modules.setdefault("src.anomaly_detection", anomaly_detection)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return joblib.load(ruta)


def cargar_json(ruta=config.FISIOLOGICO):
    """JSON largo -> DataFrame ancho (una fila por timestamp) por usuario, con las columnas del modelo."""
    df = pd.read_json(ruta)
    if df.empty:
        return df
    df["columna"] = df["variable"].map(config.VARIABLES_MODELO)
    df = df.dropna(subset=["columna"])
    ancho = (df.pivot_table(index=["usuario", "timestamp"], columns="columna", values="valor")
               .reset_index().sort_values(["usuario", "timestamp"]))
    return ancho


COLS_ENTRADA = features.PHYSIO_TARGETS + ["spo2"]   # columnas que usan como entrada los modelos personales


def preparar(ancho, usuario, pipeline_global, cols=None):
    """DataFrame de un usuario listo para el modelo. Se usan las variables como entrada;
    las que el JSON no trae se rellenan con la mediana de entrenamiento global (constante)."""
    fe = pipeline_global["feature_engineer"]
    cols = cols or fe.target_cols
    df = ancho[ancho["usuario"] == usuario].reset_index(drop=True)
    global_med = pd.DataFrame(fe.subject_baselines).T.median()
    for c in cols:
        if c not in df.columns:
            df[c] = global_med[c]
    df[cols] = df[cols].ffill().bfill()
    df["subject_id"] = usuario
    df["signal_quality"] = "GOOD"
    return df


def ruta_modelo_usuario(usuario, variable="pulso"):
    return config.MODELOS_USUARIO / f"{usuario}_{variable}.joblib"


def entrenar_usuario(pipeline_global, ancho, usuario, variable="pulso"):
    """Entrena un modelo SOLO con los datos de `usuario` para `variable` (70% entrena el predictor
    y el escalador; el 30% restante calibra el detector de anomalías). Devuelve el pipeline o None."""
    target = config.VARIABLES_ANALIZADAS[variable]
    if target not in ancho.columns:
        return None
    df = preparar(ancho, usuario, pipeline_global, COLS_ENTRADA)
    if len(df) < config.MIN_ENTRENAMIENTO:
        return None
    corte = int(len(df) * 0.7)
    train, val = df.iloc[:corte].reset_index(drop=True), df.iloc[corte:].reset_index(drop=True)

    fe = features.FeatureEngineer(target_cols=COLS_ENTRADA)
    fe.fit(train)
    cols = [f"{c}_scaled" for c in fe.feature_names]
    ftr, fva = fe.transform(train), fe.transform(val)
    modelo = type(pipeline_global["model"])()          # misma familia que el modelo ganador
    modelo.fit(ftr[cols].values, ftr[f"{target}_target"].values)

    ad = anomaly_detection.AnomalyDetector(target_variable=target, unit=UNIDADES[variable])
    ad.fit(fva[f"{target}_target"].values, modelo.predict(fva[cols].values), fva[cols].values, fva["subject_id"].values)

    pipe = dict(pipeline_global, model=modelo, feature_engineer=fe, anomaly_detector=ad, target_col=target,
                variable=variable, model_name=f"{pipeline_global['model_name']} (personalizado)",
                n_entrenamiento=len(train), n_total=len(df))
    config.MODELOS_USUARIO.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipe, ruta_modelo_usuario(usuario, variable))
    return pipe


def analizar_usuario(pipeline, ancho, usuario, personalizado=False):
    modelo, fe, ad = pipeline["model"], pipeline["feature_engineer"], pipeline["anomaly_detector"]
    target = pipeline["target_col"]
    df = preparar(ancho, usuario, pipeline, COLS_ENTRADA if personalizado else None)
    if target not in ancho.columns or len(df) <= WARMUP:
        return None

    if not personalizado:
        # Modelo global: línea base = mediana de las primeras mediciones del propio usuario.
        fe.subject_baselines[usuario] = df[fe.target_cols].head(BASELINE_N).median().to_dict()
    feat = fe.transform(df, subject_id=usuario)
    cols = [f"{c}_scaled" for c in fe.feature_names]

    normal = adv = anom = 0
    desv = []
    for i in range(WARMUP, len(df)):
        x = feat.iloc[[i]][cols].values
        rec = ad.evaluate_measurement(
            actual_value=float(df.loc[i, target]), predicted_value=float(modelo.predict(x)[0]),
            timestamp=str(df.loc[i, "timestamp"]), subject_id=usuario,
            model_name=pipeline["model_name"], signal_quality="GOOD",
            history_len=i, feature_vec=x[0])
        if rec is None:
            normal += 1
        else:
            anom += rec["status"] == "ANOMALIA"
            adv += rec["status"] != "ANOMALIA"
            desv.append(rec)
    return dict(total=len(df) - WARMUP, normal=normal, adv=adv, anom=anom, desv=desv)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--entrada", default=str(config.FISIOLOGICO))
    ap.add_argument("--usuario", help="por defecto, todos los usuarios")
    ap.add_argument("--entrenar", action="store_true",
                    help="fuerza el reentrenamiento (normalmente es automático al llegar datos nuevos)")
    args = ap.parse_args()

    pipeline = cargar_modelo()
    ancho = cargar_json(args.entrada)
    usuarios = [args.usuario] if args.usuario else sorted(ancho["usuario"].unique()) if len(ancho) else []
    config.DESVIACIONES.parent.mkdir(parents=True, exist_ok=True)
    salida = {}
    for u in usuarios:
        n = int((ancho["usuario"] == u).sum())
        for variable in config.VARIABLES_ANALIZADAS:
            ruta = ruta_modelo_usuario(u, variable)
            pipe_u = cargar_modelo(ruta) if ruta.exists() else None
            nuevas = n - (pipe_u["n_total"] if pipe_u else 0)
            # Reentrena si se fuerza, si aún no hay modelo propio o si llegaron suficientes datos nuevos.
            if args.entrenar or pipe_u is None or nuevas >= config.REENTRENAR_CADA:
                nuevo = entrenar_usuario(pipeline, ancho, u, variable)
                if nuevo:
                    pipe_u = nuevo
                    print(f"{u}/{variable}: modelo personal (re)entrenado con {n} mediciones")
                elif pipe_u is None:
                    print(f"{u}/{variable}: pocos datos para entrenar (<{config.MIN_ENTRENAMIENTO}); se omite")
            if pipe_u is None:
                continue
            r = analizar_usuario(pipe_u, ancho, u, personalizado=True)
            if r is None:
                print(f"{u}/{variable}: faltan datos (se necesitan más de {WARMUP} mediciones).")
                continue
            texto = json_generator.build_and_validate_json_output(
                model_name=pipe_u["model_name"], subject_id=u, data_source=FUENTE,
                signal_quality="GOOD", generated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                total_analyzed=r["total"], normal_count=r["normal"], warning_count=r["adv"],
                anomalous_count=r["anom"], deviations_list=r["desv"], output_path=None)
            salida.setdefault(u, {})[variable] = json.loads(texto)
            print(f"{u}/{variable}: {r['total']} analizadas, {r['adv']} advertencias, {r['anom']} anomalías")
    config.DESVIACIONES.write_text(json.dumps(salida, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Resultado en {config.DESVIACIONES}")


if __name__ == "__main__":
    main()

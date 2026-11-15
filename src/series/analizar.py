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

WARMUP = 15
BASELINE_N = 15
FUENTE = "data/fisiologico.json"


def cargar_modelo(ruta=config.MODELO_SERIES):
    sys.modules.setdefault("src.features", features)
    sys.modules.setdefault("src.models", models)
    sys.modules.setdefault("src.anomaly_detection", anomaly_detection)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return joblib.load(ruta)


def cargar_json(ruta=config.FISIOLOGICO):
    df = pd.read_json(ruta)
    if df.empty:
        return df
    df["columna"] = df["variable"].map(config.VARIABLES_MODELO)
    df = df.dropna(subset=["columna"])
    pivot = (df.pivot_table(index=["usuario", "timestamp"], columns="columna", values="valor")
               .reset_index().sort_values(["usuario", "timestamp"]))
    return pivot


COLS_ENTRADA = features.PHYSIO_TARGETS + ["spo2"]


def preparar(ancho, usuario, pipeline_global, cols=None):
    fe = pipeline_global["feature_engineer"]
    c_list = cols or fe.target_cols
    sub_df = ancho[ancho["usuario"] == usuario].reset_index(drop=True)
    med = pd.DataFrame(fe.subject_baselines).T.median()
    for c in c_list:
        if c not in sub_df.columns:
            sub_df[c] = med[c]
    sub_df[c_list] = sub_df[c_list].ffill().bfill()
    sub_df["subject_id"] = usuario
    sub_df["signal_quality"] = "GOOD"
    return sub_df


def ruta_modelo_usuario(usuario, variable="pulso"):
    return config.MODELOS_USUARIO / f"{usuario}_{variable}.joblib"


def entrenar_usuario(pipeline_global, ancho, usuario, variable="pulso"):
    target = config.VARIABLES_ANALIZADAS[variable]
    if target not in ancho.columns:
        return None
    c_var = [target]
    df = preparar(ancho, usuario, pipeline_global, c_var)
    if len(df) < config.MIN_ENTRENAMIENTO:
        return None
    split = int(len(df) * 0.7)
    d_train, d_val = df.iloc[:split].reset_index(drop=True), df.iloc[split:].reset_index(drop=True)

    fe = features.FeatureEngineer(target_cols=c_var)
    fe.fit(d_train)
    col_names = [f"{c}_scaled" for c in fe.feature_names]
    f_tr, f_val = fe.transform(d_train), fe.transform(d_val)
    mod = type(pipeline_global["model"])()
    mod.fit(f_tr[col_names].values, f_tr[f"{target}_target"].values)

    det = anomaly_detection.AnomalyDetector(target_variable=target, unit=UNIDADES[variable])
    det.fit(f_val[f"{target}_target"].values, mod.predict(f_val[col_names].values), f_val[col_names].values, f_val["subject_id"].values)

    pipe = dict(pipeline_global, model=mod, feature_engineer=fe, anomaly_detector=det, target_col=target,
                variable=variable, model_name=f"{pipeline_global['model_name']} (personalizado)",
                n_entrenamiento=len(d_train), n_total=len(df))
    config.MODELOS_USUARIO.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipe, ruta_modelo_usuario(usuario, variable))
    return pipe


def analizar_usuario(pipeline, ancho, usuario, personalizado=False):
    mod, fe, det = pipeline["model"], pipeline["feature_engineer"], pipeline["anomaly_detector"]
    target = pipeline["target_col"]
    c_var = getattr(fe, "target_cols", [target])
    df = preparar(ancho, usuario, pipeline, c_var if personalizado else None)
    if target not in ancho.columns or len(df) <= WARMUP:
        return None

    if not personalizado:
        fe.subject_baselines[usuario] = df[fe.target_cols].head(BASELINE_N).median().to_dict()
    feat = fe.transform(df, subject_id=usuario)
    col_names = [f"{c}_scaled" for c in fe.feature_names]

    ok_cnt = adv_cnt = anom_cnt = 0
    desv = []
    for i in range(WARMUP, len(df)):
        x_val = feat.iloc[[i]][col_names].values
        val_real = float(df.loc[i, target])
        val_pred = float(mod.predict(x_val)[0])
        rec = det.evaluate_measurement(
            actual_value=val_real, predicted_value=val_pred,
            timestamp=str(df.loc[i, "timestamp"]), subject_id=usuario,
            model_name=pipeline["model_name"], signal_quality="GOOD",
            history_len=i, feature_vec=x_val[0])
        if rec is None:
            ok_cnt += 1
        else:
            anom_cnt += (rec["status"] == "ANOMALIA")
            adv_cnt += (rec["status"] != "ANOMALIA")
            desv.append(rec)
    return dict(total=len(df) - WARMUP, normal=ok_cnt, adv=adv_cnt, anom=anom_cnt, desv=desv)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--entrada", default=str(config.FISIOLOGICO))
    p.add_argument("--usuario", help="filtrar por usuario")
    p.add_argument("--entrenar", action="store_true", help="forzar reentrenamiento")
    args = p.parse_args()

    pipe_base = cargar_modelo()
    df_ancho = cargar_json(args.entrada)
    usrs = [args.usuario] if args.usuario else sorted(df_ancho["usuario"].unique()) if len(df_ancho) else []
    config.DESVIACIONES.parent.mkdir(parents=True, exist_ok=True)
    res = {}
    for u in usrs:
        n_filas = int((df_ancho["usuario"] == u).sum())
        for v in config.VARIABLES_ANALIZADAS:
            r_mod = ruta_modelo_usuario(u, v)
            m_usr = cargar_modelo(r_mod) if r_mod.exists() else None
            nuevos_datos = n_filas - (m_usr["n_total"] if m_usr else 0)
            if args.entrenar or m_usr is None or nuevos_datos >= config.REENTRENAR_CADA:
                nuevo = entrenar_usuario(pipe_base, df_ancho, u, v)
                if nuevo:
                    m_usr = nuevo
                    print(f"{u}/{v}: modelo reentrenado ({n_filas} filas)")
                elif m_usr is None:
                    print(f"{u}/{v}: faltan datos para entrenar (<{config.MIN_ENTRENAMIENTO})")
            if m_usr is None:
                continue
            out = analizar_usuario(m_usr, df_ancho, u, personalizado=True)
            if out is None:
                print(f"{u}/{v}: faltan datos (se ocupan >{WARMUP})")
                continue
            js = json_generator.build_and_validate_json_output(
                model_name=m_usr["model_name"], subject_id=u, data_source=FUENTE,
                signal_quality="GOOD", generated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                total_analyzed=out["total"], normal_count=out["normal"], warning_count=out["adv"],
                anomalous_count=out["anom"], deviations_list=out["desv"], output_path=None)
            res.setdefault(u, {})[v] = json.loads(js)
            print(f"{u}/{v}: {out['total']} analizadas, {out['adv']} adv, {out['anom']} anom")
    config.DESVIACIONES.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Listo -> {config.DESVIACIONES}")


if __name__ == "__main__":
    main()

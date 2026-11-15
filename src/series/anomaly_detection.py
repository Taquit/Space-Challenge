import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor

from src.salud.umbrales import U


class AnomalyDetector:
    def __init__(self, target_variable="heart_rate", unit="bpm"):
        self.target_variable = target_variable
        self.unit = unit
        self.mean_residual = 0.0
        self.std_residual = 1.0
        self.residual_history = []
        self.subject_baselines = {}
        self.iso_forest = IsolationForest(contamination=0.03, random_state=42)
        self.lof = LocalOutlierFactor(n_neighbors=20, contamination=0.03, novelty=True)
        self.is_fitted = False

    def fit(self, y_true: np.ndarray, y_pred: np.ndarray, X_features: np.ndarray = None, subject_ids: np.ndarray = None):
        res = y_true - y_pred
        self.mean_residual = float(np.mean(res))
        self.std_residual = float(np.std(res))
        if self.std_residual < 1e-4:
            self.std_residual = 1.0
            
        self.residual_history = res.tolist()

        if subject_ids is not None:
            for s in np.unique(subject_ids):
                mask = (subject_ids == s)
                sy = y_true[mask]
                sr = res[mask]
                self.subject_baselines[s] = {
                    'median': float(np.median(sy)),
                    'std': float(np.std(sy)),
                    'res_mean': float(np.mean(sr)),
                    'res_std': float(np.std(sr)) if np.std(sr) > 1e-4 else self.std_residual
                }

        if X_features is not None:
            comb = np.hstack([X_features, res.reshape(-1, 1)])
            self.iso_forest.fit(comb)
            self.lof.fit(comb)

        self.is_fitted = True
        return self

    def evaluate_measurement(
        self,
        actual_value: float,
        predicted_value: float,
        timestamp: str,
        subject_id: str,
        model_name: str,
        signal_quality: str = "GOOD",
        history_len: int = 100,
        feature_vec: np.ndarray = None
    ) -> dict:
        if history_len < 10 or signal_quality == "DEGRADED":
            return None

        err = abs(actual_value - predicted_value)
        
        if subject_id in self.subject_baselines:
            sb = self.subject_baselines[subject_id]
            sigma = sb['res_std']
            mu = sb['res_mean']
        else:
            sigma = self.std_residual
            mu = self.mean_residual

        z = ((actual_value - predicted_value) - mu) / sigma
        az = abs(z)

        low = round(float(predicted_value - 2.0 * sigma), 2)
        upp = round(float(predicted_value + 2.0 * sigma), 2)

        dev_pct = round(float((err / abs(predicted_value)) * 100.0), 2) if abs(predicted_value) > 1e-3 else None

        iso_anom = False
        if feature_vec is not None and self.is_fitted:
            comb_step = np.hstack([feature_vec.reshape(1, -1), np.array([[actual_value - predicted_value]])])
            if self.iso_forest.predict(comb_step)[0] == -1:
                iso_anom = True

        if az >= U["MODELO_Z_ANOMALIA"] or (az >= U["MODELO_Z_ANOMALIA_ISO"] and iso_anom):
            stat = "ANOMALIA"
            conf = round(min(0.99, 0.85 + (az - 3.0) * 0.04), 2)
            msg = "El valor observado supera el intervalo de predicción individual con significancia estadística mayor a 3 sigmas."
        elif az >= U["MODELO_Z_ADVERTENCIA"]:
            stat = "ADVERTENCIA"
            conf = round(min(0.90, 0.70 + (az - 2.0) * 0.15), 2)
            msg = "Desviación relevante respecto a la línea base e intervalo de pronóstico del participante que requiere seguimiento."
        else:
            stat = "NORMAL"

        if stat == "NORMAL":
            return None

        dev_t = "ABOVE_EXPECTED" if actual_value > predicted_value else "BELOW_EXPECTED"

        return {
            "timestamp": timestamp,
            "variable": self.target_variable,
            "unit": self.unit,
            "actual_value": round(float(actual_value), 2),
            "predicted_value": round(float(predicted_value), 2),
            "expected_range": {
                "lower": low,
                "upper": upp
            },
            "absolute_error": round(float(err), 2),
            "standardized_residual": round(float(z), 2),
            "deviation_percentage": dev_pct,
            "status": stat,
            "deviation_type": dev_t,
            "confidence": conf,
            "explanation": msg,
            "model_name": model_name
        }

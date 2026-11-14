"""
Módulo de Detección de Anomalías y Clasificación de Desviaciones Fisiológicas
=============================================================================
Implementa métodos basados en residuos, intervalos de predicción,
detección no supervisada (Isolation Forest, Local Outlier Factor) y
umbrales adaptativos personalizados por participante.
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor


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
        """
        Ajusta la distribución de residuos y detectores multidimensionales
        con datos de entrenamiento y validación.
        """
        residuals = y_true - y_pred
        self.mean_residual = float(np.mean(residuals))
        self.std_residual = float(np.std(residuals))
        if self.std_residual < 1e-4:
            self.std_residual = 1.0
            
        self.residual_history = residuals.tolist()

        # Ajuste de línea base individual por participante
        if subject_ids is not None:
            unique_subjects = np.unique(subject_ids)
            for sid in unique_subjects:
                mask = (subject_ids == sid)
                subj_y = y_true[mask]
                subj_res = residuals[mask]
                self.subject_baselines[sid] = {
                    'median': float(np.median(subj_y)),
                    'std': float(np.std(subj_y)),
                    'res_mean': float(np.mean(subj_res)),
                    'res_std': float(np.std(subj_res)) if np.std(subj_res) > 1e-4 else self.std_residual
                }

        # Ajuste de Isolation Forest y LOF sobre espacio de residuos y características
        if X_features is not None:
            # Matriz combinada: features clave + residuo
            combined = np.hstack([X_features, residuals.reshape(-1, 1)])
            self.iso_forest.fit(combined)
            self.lof.fit(combined)

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
        """
        Evalúa una única medición One-Step-Ahead y clasifica su desviación.
        Retorna None si la medición es NORMAL, o un diccionario estructurado si es ADVERTENCIA o ANOMALIA.
        """
        # Exigir suficientes observaciones válidas y descartar si la calidad de señal está degradada
        if history_len < 10 or signal_quality == "DEGRADED":
            return None

        abs_error = abs(actual_value - predicted_value)
        
        # Parámetros individuales del participante o globales
        if subject_id in self.subject_baselines:
            sb = self.subject_baselines[subject_id]
            sigma = sb['res_std']
            mu = sb['res_mean']
        else:
            sigma = self.std_residual
            mu = self.mean_residual

        # Residuo estandarizado (Z-score)
        std_residual = ( (actual_value - predicted_value) - mu ) / sigma
        abs_z = abs(std_residual)

        # Intervalo de predicción individual
        k_interval = 2.0  # ~95.45% de cobertura
        expected_lower = round(float(predicted_value - k_interval * sigma), 2)
        expected_upper = round(float(predicted_value + k_interval * sigma), 2)

        # Error porcentual (cuando el valor predicho no es nulo)
        if abs(predicted_value) > 1e-3:
            dev_percentage = round(float((abs_error / abs(predicted_value)) * 100.0), 2)
        else:
            dev_percentage = None

        # Evaluación multidimensional complementaria si hay feature_vec
        iso_anomaly = False
        if feature_vec is not None and self.is_fitted:
            comb_step = np.hstack([feature_vec.reshape(1, -1), np.array([[actual_value - predicted_value]])])
            if self.iso_forest.predict(comb_step)[0] == -1:
                iso_anomaly = True

        # Clasificación del estado
        if abs_z >= 3.0 or (abs_z >= 2.5 and iso_anomaly):
            status = "ANOMALIA"
            confidence = round(min(0.99, 0.85 + (abs_z - 3.0) * 0.04), 2)
            explanation = "El valor observado supera el intervalo de predicción individual con significancia estadística mayor a 3 sigmas."
        elif abs_z >= 2.0:
            status = "ADVERTENCIA"
            confidence = round(min(0.90, 0.70 + (abs_z - 2.0) * 0.15), 2)
            explanation = "Desviación relevante respecto a la línea base e intervalo de pronóstico del participante que requiere seguimiento."
        else:
            status = "NORMAL"

        if status == "NORMAL":
            return None

        deviation_type = "ABOVE_EXPECTED" if actual_value > predicted_value else "BELOW_EXPECTED"

        return {
            "timestamp": timestamp,
            "variable": self.target_variable,
            "unit": self.unit,
            "actual_value": round(float(actual_value), 2),
            "predicted_value": round(float(predicted_value), 2),
            "expected_range": {
                "lower": expected_lower,
                "upper": expected_upper
            },
            "absolute_error": round(float(abs_error), 2),
            "standardized_residual": round(float(std_residual), 2),
            "deviation_percentage": dev_percentage,
            "status": status,
            "deviation_type": deviation_type,
            "confidence": confidence,
            "explanation": explanation,
            "model_name": model_name
        }

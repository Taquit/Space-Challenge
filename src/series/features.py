"""
Módulo de Ingeniería de Características Temporales (Feature Engineering)
========================================================================
Construye variables de rezago (lags), estadísticas móviles (media, std, min, max, tendencia)
y línea base individual de cada participante sin data leakage.
"""

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

PHYSIO_TARGETS = ['heart_rate', 'systolic_bp', 'diastolic_bp', 'actigraphy_activity']

class FeatureEngineer:
    def __init__(self, target_cols=None, lags=(1, 2, 3, 5), windows=(5, 15)):
        self.target_cols = target_cols or PHYSIO_TARGETS
        self.lags = lags
        self.windows = windows
        self.scalers = {}
        self.feature_names = []
        self.is_fitted = False
        self.subject_baselines = {}

    def _compute_raw_features(self, df: pd.DataFrame, subject_id: str = None) -> pd.DataFrame:
        """
        Calcula lags y estadísticas rodantes causales sobre una serie temporal ordenada.
        """
        feats = pd.DataFrame(index=df.index)
        
        # Copiar metadatos esenciales
        for meta_col in ['timestamp', 'time_sec', 'subject_id', 'condition', 'signal_quality', 'event']:
            if meta_col in df.columns:
                feats[meta_col] = df[meta_col]

        for col in self.target_cols:
            if col not in df.columns:
                continue
                
            val_series = df[col]
            feats[f"{col}_target"] = val_series.values
            
            # Lags causales
            for lag in self.lags:
                feats[f"{col}_lag_{lag}"] = val_series.shift(lag)
                
            # Estadísticas móviles causales (shift(1) para no incluir el valor t en la predicción de t)
            shifted = val_series.shift(1)
            for w in self.windows:
                rolling = shifted.rolling(window=w, min_periods=1)
                feats[f"{col}_roll_mean_{w}"] = rolling.mean()
                feats[f"{col}_roll_std_{w}"] = rolling.std().fillna(0.0)
                feats[f"{col}_roll_min_{w}"] = rolling.min()
                feats[f"{col}_roll_max_{w}"] = rolling.max()
                
            # Tendencia causal (diferencia entre lag_1 y lag_5 dividida por el tiempo)
            feats[f"{col}_trend_5"] = (val_series.shift(1) - val_series.shift(5)).fillna(0.0) / 4.0

            # Línea base del participante si está calculada
            if subject_id and subject_id in self.subject_baselines:
                base = self.subject_baselines[subject_id].get(col, val_series.iloc[0])
                feats[f"{col}_baseline_diff"] = val_series.shift(1) - base
            else:
                feats[f"{col}_baseline_diff"] = 0.0

        return feats

    def fit(self, train_df: pd.DataFrame):
        """
        Ajusta estadísticas y escaladores exclusivamente con el conjunto de entrenamiento.
        """
        # Calcular línea base individual por participante en el conjunto de entrenamiento
        for sid, grp in train_df.groupby('subject_id'):
            self.subject_baselines[sid] = {
                col: grp[col].median() for col in self.target_cols if col in grp.columns
            }

        # Generar características
        feature_dfs = []
        for sid, grp in train_df.groupby('subject_id'):
            grp_feats = self._compute_raw_features(grp, subject_id=sid)
            feature_dfs.append(grp_feats)
            
        concat_feats = pd.concat(feature_dfs, ignore_index=True)
        # Descartar filas con NaN iniciales causados por los lags
        clean_feats = concat_feats.dropna().reset_index(drop=True)
        
        feature_cols = [c for c in clean_feats.columns if ('_lag_' in c or '_roll_' in c or '_trend_' in c or '_baseline_diff' in c)]
        self.feature_names = feature_cols
        
        # Ajustar escalador
        self.scaler = StandardScaler()
        self.scaler.fit(clean_feats[feature_cols])
        self.is_fitted = True
        return self

    def transform(self, df: pd.DataFrame, subject_id: str = None) -> pd.DataFrame:
        """
        Aplica transformaciones usando los parámetros aprendidos en entrenamiento.
        """
        if not self.is_fitted:
            raise ValueError("FeatureEngineer debe ser ajustado con fit() antes de transform().")
            
        sid = subject_id or (df['subject_id'].iloc[0] if 'subject_id' in df.columns else None)
        feats = self._compute_raw_features(df, subject_id=sid)
        
        # Si aún hay NaNs debido a lags en los primeros segundos, rellenar con bfill causal de entrenamiento
        for c in self.feature_names:
            if c in feats.columns:
                feats[c] = feats[c].bfill().ffill().fillna(0.0)

        # Aplicar escala
        scaled_vals = self.scaler.transform(feats[self.feature_names])
        scaled_df = pd.DataFrame(scaled_vals, columns=[f"{c}_scaled" for c in self.feature_names], index=feats.index)
        
        # Concatenar metadatos y targets
        result = pd.concat([feats, scaled_df], axis=1)
        return result

    def get_feature_vector_for_step(self, history_df: pd.DataFrame, subject_id: str = None) -> np.ndarray:
        """
        Genera el vector de características para una predicción One-Step-Ahead a partir de la historia reciente.
        """
        feats = self._compute_raw_features(history_df, subject_id=subject_id)
        last_row = feats.iloc[[-1]]
        for c in self.feature_names:
            if c not in last_row.columns or pd.isna(last_row[c].values[0]):
                last_row[c] = 0.0
        X_scaled = self.scaler.transform(last_row[self.feature_names])
        return X_scaled

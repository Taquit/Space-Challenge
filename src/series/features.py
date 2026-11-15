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
        out = pd.DataFrame(index=df.index)
        
        for c in ['timestamp', 'time_sec', 'subject_id', 'condition', 'signal_quality', 'event']:
            if c in df.columns:
                out[c] = df[c]

        for col in self.target_cols:
            if col not in df.columns:
                continue
                
            s = df[col]
            out[f"{col}_target"] = s.values
            
            for lag in self.lags:
                out[f"{col}_lag_{lag}"] = s.shift(lag)
                
            sh = s.shift(1)
            for w in self.windows:
                r = sh.rolling(window=w, min_periods=1)
                out[f"{col}_roll_mean_{w}"] = r.mean()
                out[f"{col}_roll_std_{w}"] = r.std().fillna(0.0)
                out[f"{col}_roll_min_{w}"] = r.min()
                out[f"{col}_roll_max_{w}"] = r.max()
                
            out[f"{col}_trend_5"] = (s.shift(1) - s.shift(5)).fillna(0.0) / 4.0

            if subject_id and subject_id in self.subject_baselines:
                base = self.subject_baselines[subject_id].get(col, s.iloc[0])
                out[f"{col}_baseline_diff"] = s.shift(1) - base
            else:
                out[f"{col}_baseline_diff"] = 0.0

        return out

    def fit(self, train_df: pd.DataFrame):
        for sid, grp in train_df.groupby('subject_id'):
            self.subject_baselines[sid] = {
                col: grp[col].median() for col in self.target_cols if col in grp.columns
            }

        f_dfs = []
        for sid, grp in train_df.groupby('subject_id'):
            f_dfs.append(self._compute_raw_features(grp, subject_id=sid))
            
        full = pd.concat(f_dfs, ignore_index=True)
        clean = full.dropna().reset_index(drop=True)
        
        f_cols = [c for c in clean.columns if ('_lag_' in c or '_roll_' in c or '_trend_' in c or '_baseline_diff' in c)]
        self.feature_names = f_cols
        
        self.scaler = StandardScaler()
        self.scaler.fit(clean[f_cols])
        self.is_fitted = True
        return self

    def transform(self, df: pd.DataFrame, subject_id: str = None) -> pd.DataFrame:
        if not self.is_fitted:
            raise ValueError("FeatureEngineer debe ser ajustado con fit() antes de transform().")
            
        sid = subject_id or (df['subject_id'].iloc[0] if 'subject_id' in df.columns else None)
        feats = self._compute_raw_features(df, subject_id=sid)
        
        for c in self.feature_names:
            if c in feats.columns:
                feats[c] = feats[c].bfill().ffill().fillna(0.0)

        scaled = self.scaler.transform(feats[self.feature_names])
        scaled_df = pd.DataFrame(scaled, columns=[f"{c}_scaled" for c in self.feature_names], index=feats.index)
        return pd.concat([feats, scaled_df], axis=1)

    def get_feature_vector_for_step(self, history_df: pd.DataFrame, subject_id: str = None) -> np.ndarray:
        feats = self._compute_raw_features(history_df, subject_id=subject_id)
        row = feats.iloc[[-1]]
        for c in self.feature_names:
            if c not in row.columns or pd.isna(row[c].values[0]):
                row[c] = 0.0
        return self.scaler.transform(row[self.feature_names])

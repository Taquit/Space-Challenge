"""
Módulo de Modelos Predictivos Fisiológicos One-Step-Ahead
=========================================================
Implementa modelos estadísticos, Machine Learning y Deep Learning
para la predicción de variables fisiológicas vitales de astronautas.

Modelos implementados:
1. Exponential Smoothing (Holt-Winters lineal)
2. ARIMA (Autoregressive Integrated Moving Average)
3. Random Forest Regressor
4. Gradient Boosting / LightGBM (HistGradientBoostingRegressor)
5. Support Vector Regression (SVR)
6. LSTM (Long Short-Term Memory Neural Network - PyTorch)
7. GRU (Gated Recurrent Unit Neural Network - PyTorch)
"""

import numpy as np
import scipy.optimize
from sklearn.ensemble import RandomForestRegressor, HistGradientBoostingRegressor
from sklearn.svm import SVR
import torch
import torch.nn as nn
from torch.utils.data import TensorDataset, DataLoader

# Fijar semillas para reproducibilidad
np.random.seed(42)
torch.manual_seed(42)
if torch.cuda.is_available():
    torch.cuda.manual_seed_all(42)


class BasePhysioPredictor:
    def fit(self, X: np.ndarray, y: np.ndarray):
        raise NotImplementedError
        
    def predict(self, X: np.ndarray) -> np.ndarray:
        raise NotImplementedError


# =====================================================================
# 1. MODELO ESTADÍSTICO: Exponential Smoothing (Holt's Linear)
# =====================================================================
class ExponentialSmoothingModel(BasePhysioPredictor):
    """
    Suavizamiento exponencial lineal de Holt con optimización de parámetros alfa y beta.
    """
    def __init__(self, alpha=None, beta=None):
        self.alpha = alpha
        self.beta = beta
        self.level_ = None
        self.trend_ = None
        self.last_y_ = None

    def fit(self, X: np.ndarray, y: np.ndarray):
        y_series = np.asarray(y, dtype=float)
        
        def sse(params):
            a, b = params
            lvl = y_series[0]
            trd = y_series[1] - y_series[0] if len(y_series) > 1 else 0.0
            errs = []
            for val in y_series[1:]:
                pred = lvl + trd
                errs.append((val - pred)**2)
                new_lvl = a * val + (1.0 - a) * (lvl + trd)
                new_trd = b * (new_lvl - lvl) + (1.0 - b) * trd
                lvl, trd = new_lvl, new_trd
            return np.mean(errs)

        if self.alpha is None or self.beta is None:
            res = scipy.optimize.minimize(
                sse, x0=[0.5, 0.1], bounds=[(0.01, 0.99), (0.001, 0.5)], method='L-BFGS-B'
            )
            self.alpha, self.beta = res.x
            
        # Calcular estado final
        lvl = y_series[0]
        trd = y_series[1] - y_series[0] if len(y_series) > 1 else 0.0
        for val in y_series[1:]:
            new_lvl = self.alpha * val + (1.0 - self.alpha) * (lvl + trd)
            new_trd = self.beta * (new_lvl - lvl) + (1.0 - self.beta) * trd
            lvl, trd = new_lvl, new_trd
            
        self.level_ = lvl
        self.trend_ = trd
        self.last_y_ = y_series[-1]
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        # Para features tabulares, el primer lag es la observación t previa
        # Si X contiene features, utilizamos el primer feature (lag_1) como base
        preds = []
        lvl = self.level_
        trd = self.trend_
        
        # Pronóstico recursivo one-step sobre el batch
        for row in X:
            pred = lvl + trd
            preds.append(pred)
            # Actualizar con lag_1 si está disponible
            val = row[0]
            new_lvl = self.alpha * val + (1.0 - self.alpha) * (lvl + trd)
            new_trd = self.beta * (new_lvl - lvl) + (1.0 - self.beta) * trd
            lvl, trd = new_lvl, new_trd
            
        return np.array(preds)


# =====================================================================
# 2. MODELO ESTADÍSTICO: ARIMA (Autoregressive Integrated Moving Average)
# =====================================================================
class ARIMAModel(BasePhysioPredictor):
    """
    ARIMA(p, d, q) con orden autoregresivo y diferenciación para series fisiológicas.
    """
    def __init__(self, p=3, d=1):
        self.p = p
        self.d = d
        self.phi = None
        self.intercept = 0.0

    def fit(self, X: np.ndarray, y: np.ndarray):
        y_series = np.asarray(y, dtype=float)
        # Diferenciación d=1
        if self.d == 1:
            diff_y = np.diff(y_series)
        else:
            diff_y = y_series
            
        # Construcción de matriz AR(p)
        N = len(diff_y)
        if N <= self.p + 2:
            self.phi = np.zeros(self.p)
            return self
            
        X_ar = []
        y_ar = []
        for i in range(self.p, N):
            X_ar.append(diff_y[i - self.p:i][::-1])
            y_ar.append(diff_y[i])
            
        X_ar = np.array(X_ar)
        y_ar = np.array(y_ar)
        
        # Ajuste mínimos cuadrados regulares (Ridge)
        reg = 1e-4 * np.eye(self.p)
        self.phi = np.linalg.solve(X_ar.T @ X_ar + reg, X_ar.T @ y_ar)
        self.intercept = np.mean(y_ar - X_ar @ self.phi)
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        # Utiliza los lags presentes en las primeras p columnas de X
        preds = []
        for row in X:
            # Reconstruir valor diferenciado y sumar lag_1
            lags = row[:self.p]
            lag_1 = row[0]
            if len(lags) >= self.p:
                diff_lags = np.diff(np.insert(lags, 0, lag_1))[:self.p]
                pred_diff = self.intercept + np.dot(self.phi, diff_lags)
                preds.append(lag_1 + pred_diff)
            else:
                preds.append(lag_1)
        return np.array(preds)


# =====================================================================
# 3. MACHINE LEARNING: Random Forest Regressor
# =====================================================================
class RandomForestModel(BasePhysioPredictor):
    def __init__(self, n_estimators=100, max_depth=12, random_state=42):
        self.model = RandomForestRegressor(
            n_estimators=n_estimators,
            max_depth=max_depth,
            random_state=random_state,
            n_jobs=1
        )

    def fit(self, X: np.ndarray, y: np.ndarray):
        self.model.fit(X, y)
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        return self.model.predict(X)


# =====================================================================
# 4. MACHINE LEARNING: Gradient Boosting / LightGBM
# =====================================================================
class GradientBoostingModel(BasePhysioPredictor):
    """
    HistGradientBoostingRegressor: Algoritmo de árbol de boosting por histogramas
    equivalente e interoperable con LightGBM.
    """
    def __init__(self, max_iter=120, max_depth=6, learning_rate=0.07, random_state=42):
        self.model = HistGradientBoostingRegressor(
            max_iter=max_iter,
            max_depth=max_depth,
            learning_rate=learning_rate,
            random_state=random_state,
            early_stopping=True
        )

    def fit(self, X: np.ndarray, y: np.ndarray):
        self.model.fit(X, y)
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        return self.model.predict(X)


# =====================================================================
# 5. MACHINE LEARNING: Support Vector Regression (SVR)
# =====================================================================
class SVRModel(BasePhysioPredictor):
    def __init__(self, C=10.0, epsilon=0.1, kernel='rbf'):
        self.model = SVR(C=C, epsilon=epsilon, kernel=kernel)

    def fit(self, X: np.ndarray, y: np.ndarray):
        self.model.fit(X, y)
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        return self.model.predict(X)


# =====================================================================
# 6. DEEP LEARNING: LSTM (PyTorch)
# =====================================================================
class _LSTMNet(nn.Module):
    def __init__(self, input_dim, hidden_dim=32, num_layers=2, dropout=0.1):
        super().__init__()
        self.lstm = nn.LSTM(
            input_dim, hidden_dim, num_layers=num_layers,
            batch_first=True, dropout=dropout if num_layers > 1 else 0.0
        )
        self.fc = nn.Sequential(
            nn.Linear(hidden_dim, 16),
            nn.ReLU(),
            nn.Linear(16, 1)
        )

    def forward(self, x):
        # x shape: (batch_size, seq_len=1, input_dim)
        out, _ = self.lstm(x)
        out = self.fc(out[:, -1, :])
        return out.squeeze(-1)


class LSTMModel(BasePhysioPredictor):
    def __init__(self, hidden_dim=32, num_layers=2, epochs=25, lr=0.005, batch_size=64):
        self.hidden_dim = hidden_dim
        self.num_layers = num_layers
        self.epochs = epochs
        self.lr = lr
        self.batch_size = batch_size
        self.net = None
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    def fit(self, X: np.ndarray, y: np.ndarray):
        input_dim = X.shape[1]
        self.net = _LSTMNet(input_dim, self.hidden_dim, self.num_layers).to(self.device)
        
        X_t = torch.tensor(X[:, np.newaxis, :], dtype=torch.float32)
        y_t = torch.tensor(y, dtype=torch.float32)
        dataset = TensorDataset(X_t, y_t)
        loader = DataLoader(dataset, batch_size=self.batch_size, shuffle=True)
        
        criterion = nn.MSELoss()
        optimizer = torch.optim.AdamW(self.net.parameters(), lr=self.lr, weight_decay=1e-4)
        
        self.net.train()
        for epoch in range(self.epochs):
            for batch_x, batch_y in loader:
                batch_x, batch_y = batch_x.to(self.device), batch_y.to(self.device)
                optimizer.zero_grad()
                pred = self.net(batch_x)
                loss = criterion(pred, batch_y)
                loss.backward()
                optimizer.step()
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        self.net.eval()
        with torch.no_grad():
            X_t = torch.tensor(X[:, np.newaxis, :], dtype=torch.float32).to(self.device)
            preds = self.net(X_t).cpu().numpy()
        return preds


# =====================================================================
# 7. DEEP LEARNING: GRU (PyTorch)
# =====================================================================
class _GRUNet(nn.Module):
    def __init__(self, input_dim, hidden_dim=32, num_layers=2, dropout=0.1):
        super().__init__()
        self.gru = nn.GRU(
            input_dim, hidden_dim, num_layers=num_layers,
            batch_first=True, dropout=dropout if num_layers > 1 else 0.0
        )
        self.fc = nn.Sequential(
            nn.Linear(hidden_dim, 16),
            nn.ReLU(),
            nn.Linear(16, 1)
        )

    def forward(self, x):
        out, _ = self.gru(x)
        out = self.fc(out[:, -1, :])
        return out.squeeze(-1)


class GRUModel(BasePhysioPredictor):
    def __init__(self, hidden_dim=32, num_layers=2, epochs=25, lr=0.005, batch_size=64):
        self.hidden_dim = hidden_dim
        self.num_layers = num_layers
        self.epochs = epochs
        self.lr = lr
        self.batch_size = batch_size
        self.net = None
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    def fit(self, X: np.ndarray, y: np.ndarray):
        input_dim = X.shape[1]
        self.net = _GRUNet(input_dim, self.hidden_dim, self.num_layers).to(self.device)
        
        X_t = torch.tensor(X[:, np.newaxis, :], dtype=torch.float32)
        y_t = torch.tensor(y, dtype=torch.float32)
        dataset = TensorDataset(X_t, y_t)
        loader = DataLoader(dataset, batch_size=self.batch_size, shuffle=True)
        
        criterion = nn.MSELoss()
        optimizer = torch.optim.AdamW(self.net.parameters(), lr=self.lr, weight_decay=1e-4)
        
        self.net.train()
        for epoch in range(self.epochs):
            for batch_x, batch_y in loader:
                batch_x, batch_y = batch_x.to(self.device), batch_y.to(self.device)
                optimizer.zero_grad()
                pred = self.net(batch_x)
                loss = criterion(pred, batch_y)
                loss.backward()
                optimizer.step()
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        self.net.eval()
        with torch.no_grad():
            X_t = torch.tensor(X[:, np.newaxis, :], dtype=torch.float32).to(self.device)
            preds = self.net(X_t).cpu().numpy()
        return preds

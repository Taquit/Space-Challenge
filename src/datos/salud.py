"""Acceso a los datos fisiológicos de data/fisiologico.json.

El JSON está en formato largo (usuario, timestamp, variable, valor). Aquí se
agrupa por tripulante y por instante: {"pulso": 71.2, "spo2": 97.5, ...}.

"Tiempo real": el archivo es un día completo ya grabado, así que el Monitor lo
reproduce como una transmisión en vivo. Un reloj simulado avanza una lectura
cada SIM_SEGUNDOS_POR_LECTURA segundos desde que arranca el servidor. Cuando
exista un sensor real, basta con reemplazar `Monitor.indice_actual()`.
"""
import json
import time
from collections import defaultdict

from src import config

UNIDADES = {
    "pulso": "bpm",
    "spo2": "%",
    "presion_sistolica": "mmHg",
    "presion_diastolica": "mmHg",
}


class Monitor:
    def __init__(self, ruta=config.DATOS_FISIOLOGICOS, seg_por_lectura=config.SIM_SEGUNDOS_POR_LECTURA):
        crudo = json.loads(ruta.read_text(encoding="utf-8"))
        por_usuario = defaultdict(lambda: defaultdict(dict))
        for r in crudo:
            por_usuario[r["usuario"]][r["timestamp"]][r["variable"]] = r["valor"]
        # {usuario: [(timestamp, {variable: valor}), ...]} ordenado por tiempo
        self.series = {u: sorted(ts.items()) for u, ts in por_usuario.items()}
        self.seg = seg_por_lectura
        self.t0 = time.monotonic()

    def reiniciar(self):
        self.t0 = time.monotonic()

    def tripulantes(self):
        return sorted(self.series)

    def variables(self, usuario):
        return sorted({v for _, vals in self.series[usuario] for v in vals})

    def indice_actual(self, usuario):
        """Índice de la última lectura 'ya ocurrida' según el reloj simulado."""
        n = len(self.series[usuario])
        return min(int((time.monotonic() - self.t0) / self.seg), n - 1)

    def series_por_variable(self, usuario, hasta=None):
        """{variable: [(timestamp, valor), ...]} hasta el instante actual (más antiguo primero)."""
        i = self.indice_actual(usuario) if hasta is None else hasta
        out = defaultdict(list)
        for ts, vals in self.series[usuario][: i + 1]:
            for var, v in vals.items():
                out[var].append((ts, v))
        return dict(out)

    def lectura(self, usuario, i):
        ts, valores = self.series[usuario][i]
        return {"timestamp": ts, "valores": valores}

    def estado(self, usuario, limite):
        """Última lectura por variable + las últimas `limite` lecturas."""
        i = self.indice_actual(usuario)
        serie = self.series[usuario]
        actual = {}
        for ts, vals in serie[: i + 1]:       # el valor más reciente de cada variable
            for var, v in vals.items():
                actual[var] = {"valor": v, "unidad": UNIDADES.get(var), "timestamp": ts}
        desde = max(0, i + 1 - limite)
        return {
            "usuario": usuario,
            "timestamp_actual": serie[i][0],
            "actual": actual,
            "historial": [self.lectura(usuario, j) for j in range(desde, i + 1)],
            "simulado": True,
        }

"""Acceso a los datos fisiológicos de data/fisiologico.json.

El JSON está en formato largo (usuario, timestamp, variable, valor). Aquí se
agrupa por tripulante y por instante: {"pulso": 71.2, "spo2": 97.5, ...}.

"Tiempo real": el archivo es un día completo ya grabado, así que el Monitor lo
reproduce como una transmisión en vivo. Un reloj simulado avanza una lectura
cada SIM_SEGUNDOS_POR_LECTURA segundos desde que arranca el servidor.

Sueño: data/sueno.json (scripts/importar_sueno.py) es un resumen por NOCHE (latencia,
duración, eficiencia). Se reproduce con el mismo reloj pero con su propio índice: cada
SIM_SEGUNDOS_POR_LECTURA segundos "ocurre" una noche nueva. Un tripulante sin datos de
sueño simplemente no tiene esas variables. Cuando
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
    "sueno_latencia": "min",
    "sueno_duracion": "h",
    "sueno_eficiencia": "%",
}


class Monitor:
    def __init__(self, ruta=config.DATOS_FISIOLOGICOS, seg_por_lectura=config.SIM_SEGUNDOS_POR_LECTURA,
                 ruta_sueno=config.DATOS_SUENO):
        crudo = json.loads(ruta.read_text(encoding="utf-8"))
        por_usuario = defaultdict(lambda: defaultdict(dict))
        for r in crudo:
            por_usuario[r["usuario"]][r["timestamp"]][r["variable"]] = r["valor"]
        # {usuario: [(timestamp, {variable: valor}), ...]} ordenado por tiempo
        self.series = {u: sorted(ts.items()) for u, ts in por_usuario.items()}
        # {usuario: [{"timestamp", "fase", "medicacion", "valores"}, ...]} ordenado por fecha
        self.sueno = defaultdict(list)
        if ruta_sueno and ruta_sueno.exists():
            for n in json.loads(ruta_sueno.read_text(encoding="utf-8")):
                self.sueno[n["usuario"]].append(n)
            for noches in self.sueno.values():
                noches.sort(key=lambda n: n["timestamp"])
        self.seg = seg_por_lectura
        self.t0 = time.monotonic()

    def reiniciar(self):
        self.t0 = time.monotonic()

    def tripulantes(self):
        return sorted(set(self.series) | set(self.sueno))

    def existe(self, usuario):
        return usuario in self.series or usuario in self.sueno

    def variables(self, usuario):
        vars_ = {v for _, vals in self.series.get(usuario, []) for v in vals}
        vars_ |= {v for n in self.sueno.get(usuario, []) for v in n["valores"]}
        return sorted(vars_)

    def lecturas_disponibles(self, usuario):
        return len(self.series.get(usuario, []))

    def noches_disponibles(self, usuario):
        return len(self.sueno.get(usuario, []))

    def indice_sueno(self, usuario):
        """Índice de la última noche 'ya ocurrida' (-1 si el tripulante no tiene sueño o aún no hay ninguna)."""
        n = len(self.sueno.get(usuario, []))
        return min(int((time.monotonic() - self.t0) / self.seg), n - 1) if n else -1

    def noche(self, usuario, i):
        n = self.sueno[usuario][i]
        return {"timestamp": n["timestamp"], "valores": n["valores"],
                "fase": n.get("fase"), "medicacion": n.get("medicacion")}

    def serie_sueno(self, usuario, hasta=None):
        """[(fecha, {variable: valor})] de las noches ya ocurridas (para notificaciones)."""
        i = self.indice_sueno(usuario) if hasta is None else hasta
        return [(n["timestamp"], n["valores"]) for n in self.sueno.get(usuario, [])[: i + 1]]

    def indice_actual(self, usuario):
        """Índice de la última lectura 'ya ocurrida' según el reloj simulado."""
        n = len(self.series[usuario])
        return min(int((time.monotonic() - self.t0) / self.seg), n - 1)

    def series_por_variable(self, usuario, hasta=None):
        """{variable: [(timestamp, valor), ...]} hasta el instante actual (más antiguo primero)."""
        out = defaultdict(list)
        if usuario in self.series:
            i = self.indice_actual(usuario) if hasta is None else hasta
            for ts, vals in self.series[usuario][: i + 1]:
                for var, v in vals.items():
                    out[var].append((ts, v))
        for ts, vals in self.serie_sueno(usuario):
            for var, v in vals.items():
                out[var].append((ts, v))
        return dict(out)

    def lectura(self, usuario, i):
        ts, valores = self.series[usuario][i]
        return {"timestamp": ts, "valores": valores}

    def estado(self, usuario, limite):
        """Última lectura por variable + las últimas `limite` lecturas."""
        serie = self.series.get(usuario, [])
        i = self.indice_actual(usuario) if serie else -1
        actual = {}
        for ts, vals in serie[: i + 1]:       # el valor más reciente de cada variable
            for var, v in vals.items():
                actual[var] = {"valor": v, "unidad": UNIDADES.get(var), "timestamp": ts}
        desde = max(0, i + 1 - limite)
        k = self.indice_sueno(usuario)
        for ts, vals in self.serie_sueno(usuario, k):   # la última noche de cada variable de sueño
            for var, v in vals.items():
                actual[var] = {"valor": v, "unidad": UNIDADES.get(var), "timestamp": ts}
        desde_s = max(0, k + 1 - limite)
        return {
            "usuario": usuario,
            "timestamp_actual": serie[i][0] if serie else (self.sueno[usuario][k]["timestamp"] if k >= 0 else None),
            "actual": actual,
            "historial": [self.lectura(usuario, j) for j in range(desde, i + 1)],
            "sueno": [self.noche(usuario, j) for j in range(desde_s, k + 1)],
            "simulado": True,
        }

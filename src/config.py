"""Configuración central del RAG."""
import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def _ruta(var, defecto):
    """Ruta configurable por variable de entorno (relativa a la raíz del proyecto o absoluta)."""
    v = os.environ.get(var)
    return (RAIZ / v) if v else defecto
PDFS_DIR = RAIZ / "data" / "pdfs"
INDICE = RAIZ / "data" / "indices" / "indice.faiss"
CHUNKS = RAIZ / "data" / "indices" / "chunks.json"
MODELO_EMB = str(RAIZ / "models" / "bge-m3")

DATOS_FISIOLOGICOS = _ruta("DATOS_FISIOLOGICOS", RAIZ / "data" / "fisiologico.json")   # lo que lee la API
REPORTE = RAIZ / "data" / "indices" / "report.md"   # reporte de calidad del chunking

# Chunking (src/rag/prepare_chunks.py). Los tokens se estiman como palabras x 1.3
MAX_TOKENS = 400          # tamaño máximo de un fragmento
MIN_TOKENS = 60           # unidades menores se unen con la siguiente
FLAG_MIN = 25             # fragmentos menores a esto se marcan en el reporte
OVERLAP_ORACIONES = 1     # oraciones compartidas entre fragmentos consecutivos
SEMILLA = 7               # muestras aleatorias del reporte
TOP_K = 5            # fragmentos que se pasan al LLM

LMSTUDIO_URL = "http://localhost:1234/v1"
MODELO_LLM = None    # None = usa el primer modelo cargado en LM Studio
TEMPERATURA = 0.2
RAZONAMIENTO = "none"   # LM Studio: "none" apaga el razonamiento de Qwen3.5 (mucho más rápido en CPU)
MAX_TOKENS_RESPUESTA = 300

# --- Parte 2: series de tiempo (modelo de NasaSpaceApps-Model) ---
FISIOLOGICO = _ruta("DATOS_FISIOLOGICOS", RAIZ / "data" / "fisiologico.json")   # lo que lee analizar (misma variable)
MODELO_SERIES = RAIZ / "models" / "series" / "best_model.joblib"
DESVIACIONES = RAIZ / "data" / "resultados" / "deviations.json"   # salida de src.series.analizar
# Nombre de variable en fisiologico.json -> columna que espera el modelo
VARIABLES_MODELO = {
    "pulso": "heart_rate",
    "presion_sistolica": "systolic_bp",
    "presion_diastolica": "diastolic_bp",
    "actividad": "actigraphy_activity",
    "spo2": "spo2",
}
# Variables con modelo personal (una por usuario y variable) y su columna del modelo
VARIABLES_ANALIZADAS = {
    "pulso": "heart_rate",
    "spo2": "spo2",
    "presion_sistolica": "systolic_bp",
    "presion_diastolica": "diastolic_bp",
}
# Sueño: resumen por noche (data/sueno.json, ver scripts/importar_sueno.py). Sin modelo personal.
DATOS_SUENO = _ruta("DATOS_SUENO", RAIZ / "data" / "sueno.json")
# Cognitivo: sesiones de pruebas (PVT, DSST, Matrix) en data/cognitivo.json. Ver docs/COGNITIVO.md.
DATOS_COGNITIVO = _ruta("DATOS_COGNITIVO", RAIZ / "data" / "cognitivo.json")
VARIABLES_SUENO = ("sueno_latencia", "sueno_duracion", "sueno_eficiencia")
MODELOS_USUARIO = RAIZ / "models" / "series" / "usuarios"   # un modelo por usuario y variable: <usuario>_<variable>.joblib
NOTIFICACIONES = RAIZ / "data" / "resultados" / "notificaciones.json"
MIN_ENTRENAMIENTO = 60   # mediciones mínimas del usuario para entrenar su propio modelo


# API (FastAPI)
API_HOST = "127.0.0.1"   # "0.0.0.0" para exponerla en la red local
API_PORT = 8000
# Orígenes del front permitidos por CORS (agrega el de tu front si es otro)
CORS_ORIGENES = ["http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:5173",
                 "http://localhost:8000", "http://127.0.0.1:8000"]
# Front estático (index.html) que la API sirve en "/". Configurable con ORBITAL_FRONT_DIR.
FRONT_DIR = _ruta("ORBITAL_FRONT_DIR", RAIZ / "front" / "Space-Challenge-Front-main")
REENTRENAR_CADA = 30   # mediciones nuevas (filas por usuario) tras las cuales se reentrena solo

# Datos de salud "en tiempo real" (reproducción simulada de fisiologico.json)
SIM_SEGUNDOS_POR_LECTURA = 2.0   # cada cuántos segundos "ocurre" una lectura nueva

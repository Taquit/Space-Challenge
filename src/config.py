"""Configuración central del RAG."""
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PDFS_DIR = RAIZ / "data" / "pdfs"
INDICE = RAIZ / "data" / "indices" / "indice.faiss"
CHUNKS = RAIZ / "data" / "indices" / "chunks.json"
MODELO_EMB = str(RAIZ / "models" / "bge-m3")

DATOS_FISIOLOGICOS = RAIZ / "data" / "fisiologico.json"
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
MAX_TOKENS_RESPUESTA = 150

# --- Parte 2: series de tiempo (modelo de NasaSpaceApps-Model) ---
FISIOLOGICO = RAIZ / "data" / "fisiologico.json"
MODELO_SERIES = RAIZ / "models" / "series" / "best_model.joblib"
DESVIACIONES = RAIZ / "data" / "resultados" / "deviations.json"   # salida de src.series.analizar
# Nombre de variable en fisiologico.json -> columna que espera el modelo
VARIABLES_MODELO = {
    "pulso": "heart_rate",
    "presion_sistolica": "systolic_bp",
    "presion_diastolica": "diastolic_bp",
    "actividad": "actigraphy_activity",
}
MODELOS_USUARIO = RAIZ / "models" / "series" / "usuarios"   # un modelo por usuario: <usuario>.joblib
MIN_ENTRENAMIENTO = 60   # mediciones mínimas del usuario para entrenar su propio modelo


# API (FastAPI)
API_HOST = "127.0.0.1"   # "0.0.0.0" para exponerla en la red local
API_PORT = 8000
# Orígenes del front permitidos por CORS (agrega el de tu front si es otro)
CORS_ORIGENES = ["http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:5173"]
REENTRENAR_CADA = 30   # mediciones nuevas (filas por usuario) tras las cuales se reentrena solo

# Datos de salud "en tiempo real" (reproducción simulada de fisiologico.json)
SIM_SEGUNDOS_POR_LECTURA = 2.0   # cada cuántos segundos "ocurre" una lectura nueva

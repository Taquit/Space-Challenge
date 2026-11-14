"""Descarga los pesos de los modelos. Correr UNA vez, con internet."""
from pathlib import Path
from huggingface_hub import snapshot_download

RAIZ = Path(__file__).resolve().parent.parent   # scripts/ -> raíz del proyecto
MODELS = RAIZ / "models"

MODELOS = {
    "BAAI/bge-m3": {"ignore_patterns": ["onnx/*", "imgs/*", "*.onnx", "*.onnx_data"]},
    "amazon/chronos-2": {},
}

for repo, opciones in MODELOS.items():
    destino = MODELS / repo.split("/")[1]
    if (destino / "config.json").exists():
        print(f"Ya existe: {destino}")
        continue
    print(f"Descargando {repo} ...")
    snapshot_download(repo, local_dir=destino, **opciones)
    print(f"Listo: {destino}")
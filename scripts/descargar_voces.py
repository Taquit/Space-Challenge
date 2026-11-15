"""Descarga las voces de Piper que usa Orbi (models/voz/). Correr UNA vez, con internet.

    python scripts/descargar_voces.py            # descarga las que falten
    python scripts/descargar_voces.py --probar   # además genera models/voz/prueba_<idioma>.wav para escucharlas

Requiere `pip install piper-tts huggingface_hub` (incluidos en requirements.txt).
Las voces se definen en src/config.py (VOCES): español de México y inglés de EE. UU.
"""
import argparse
import shutil
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent   # scripts/ -> raíz del proyecto
sys.path.insert(0, str(RAIZ))

from huggingface_hub import hf_hub_download   # noqa: E402

from src import config, voz   # noqa: E402

REPO = "rhasspy/piper-voices"
FRASES = {
    "es": "Hola, soy Orbi. Tus signos vitales se ven muy bien hoy; sigue así.",
    "en": "Hi, I'm Orbi. Your vital signs look great today; keep it up.",
}


def descargar(idioma, ruta):
    destino = config.VOZ_DIR
    destino.mkdir(parents=True, exist_ok=True)
    nombre = Path(ruta).name
    archivos = [(f"{ruta}.onnx", f"{nombre}.onnx"), (f"{ruta}.onnx.json", f"{nombre}.onnx.json"),
                (f"{Path(ruta).parent}/MODEL_CARD", f"{nombre}.MODEL_CARD")]
    for remoto, local in archivos:
        final = destino / local
        if final.exists():
            continue
        print(f"  {remoto} ...")
        tmp = hf_hub_download(REPO, remoto)       # va a la caché de Hugging Face
        shutil.copyfile(tmp, final)               # y se copia con nombre plano a models/voz/


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probar", action="store_true", help="genera un WAV de prueba por voz")
    args = ap.parse_args()

    for idioma, ruta in config.VOCES.items():
        if voz.disponible(idioma):
            print(f"[{idioma}] ya existe: {voz.ruta_modelo(idioma).name}")
        else:
            print(f"[{idioma}] descargando {Path(ruta).name} ...")
            descargar(idioma, ruta)
            print(f"[{idioma}] listo: {voz.ruta_modelo(idioma)}")
        if args.probar:
            wav = config.VOZ_DIR / f"prueba_{idioma}.wav"
            wav.write_bytes(voz.sintetizar(FRASES[idioma], idioma))
            print(f"[{idioma}] prueba: {wav}")


if __name__ == "__main__":
    main()

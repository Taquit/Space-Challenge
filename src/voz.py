"""Voz de Orbi con Piper (TTS neuronal local, sin internet).

Las voces (.onnx + .onnx.json) viven en models/voz/ y se descargan una vez con:

    python scripts/descargar_voces.py

Cada voz se carga la primera vez que se pide y queda en memoria.
"""
import io
import threading
import wave
from pathlib import Path

from src import config

_voces = {}
_candado = threading.Lock()   # Piper en CPU: una síntesis a la vez


def ruta_modelo(idioma):
    return config.VOZ_DIR / (Path(config.VOCES[idioma]).name + ".onnx")


def disponible(idioma):
    m = ruta_modelo(idioma)
    return m.exists() and Path(str(m) + ".json").exists()


def _voz(idioma):
    if idioma not in _voces:
        from piper import PiperVoice   # import perezoso: la API arranca aunque piper-tts no esté instalado
        _voces[idioma] = PiperVoice.load(ruta_modelo(idioma))
    return _voces[idioma]


def sintetizar(texto, idioma="es"):
    """WAV (bytes) con `texto` dicho por la voz de `idioma`. FileNotFoundError si la voz no está instalada."""
    if idioma not in config.VOCES or not disponible(idioma):
        raise FileNotFoundError(f"Voz '{idioma}' no instalada en {config.VOZ_DIR}")
    from piper import SynthesisConfig
    buf = io.BytesIO()
    with _candado:
        voz = _voz(idioma)
        with wave.open(buf, "wb") as w:
            voz.synthesize_wav(texto, w, syn_config=SynthesisConfig(length_scale=config.VOZ_VELOCIDAD))
    return buf.getvalue()

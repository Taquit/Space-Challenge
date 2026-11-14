import json


def sse(evento, datos):
    """Formatea un evento Server-Sent Events."""
    return f"event: {evento}\ndata: {json.dumps(datos, ensure_ascii=False)}\n\n"

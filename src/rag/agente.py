"""Agente RAG en Python puro. Requiere LM Studio con el servidor local activo."""
import json
import os

os.environ["HF_HUB_OFFLINE"] = "1"

import faiss
from openai import OpenAI
from sentence_transformers import SentenceTransformer

from src import config

emb = SentenceTransformer(config.MODELO_EMB, device="cpu")
indice = faiss.read_index(str(config.INDICE))
chunks = json.loads(config.CHUNKS.read_text(encoding="utf-8"))
client = OpenAI(base_url=config.LMSTUDIO_URL, api_key="lm-studio")


def modelo_llm():
    return config.MODELO_LLM or client.models.list().data[0].id


SYSTEM = (
    "Eres un asistente técnico. Responde SOLO con base en los fragmentos de "
    "documentación que se te dan. Sé muy conciso: una o dos oraciones, solo el dato "
    "pedido, sin contexto extra ni repetir la pregunta. Termina con la cita entre "
    "corchetes, por ejemplo [archivo.pdf, pág. 3]. Si la respuesta no está en los "
    "fragmentos, responde: 'No está en la documentación.' Responde en español."
)


def estado_fisiologico(max_desv=5):
    """Resumen de data/resultados/deviations.json (generado por `python -m src.series.analizar`)."""
    if not config.DESVIACIONES.exists():
        return ""
    lineas = []
    for usuario, r in json.loads(config.DESVIACIONES.read_text(encoding="utf-8")).items():
        s = r["summary"]
        lineas.append(f"- {usuario}: estado {s['overall_status']}, {s['total_measurements_analyzed']} mediciones, "
                      f"{s['warning_measurements']} advertencias, {s['anomalous_measurements']} anomalías.")
        for d in sorted(r["deviations"], key=lambda d: -abs(d["standardized_residual"]))[:max_desv]:
            lineas.append(f"  · {d['timestamp']} {d['variable']}={d['actual_value']} {d['unit']} "
                          f"(esperado {d['expected_range']['lower']}-{d['expected_range']['upper']}, {d['status']})")
    return "\n".join(lineas)


def buscar(consulta, k=config.TOP_K):
    """Devuelve los k fragmentos más parecidos a la consulta."""
    q = emb.encode([consulta], normalize_embeddings=True).astype("float32")
    _, ids = indice.search(q, k)
    return [chunks[i] for i in ids[0] if i >= 0]


def pags(f):
    fin = f.get("pagina_fin", f["pagina"])
    return str(f["pagina"]) if fin == f["pagina"] else f"{f['pagina']}-{fin}"


def formatear(frags):
    return "\n\n".join(f"[{f['archivo']}, pág. {pags(f)}]\n{f['texto']}" for f in frags)


def preparar(pregunta, k=config.TOP_K):
    """Recuperación SIEMPRE obligatoria: no dependemos de que el modelo decida buscar.
    Devuelve (mensajes para el LLM, fragmentos usados)."""
    frags = buscar(pregunta, k)
    msgs = [
        {"role": "system", "content": SYSTEM},
        {"role": "user",
         "content": f"Fragmentos:\n{formatear(frags)}\n\nPregunta: {pregunta}"},
    ]
    return msgs, frags


def fuentes_de(frags):
    """Fuentes únicas como lista de dicts, listas para serializar a JSON."""
    vistas = {(f["archivo"], pags(f)) for f in frags}
    return [{"archivo": a, "paginas": p} for a, p in sorted(vistas)]


def generar(msgs):
    """Genera la respuesta del LLM token por token."""
    stream = client.chat.completions.create(
        model=modelo_llm(), messages=msgs, temperature=config.TEMPERATURA,
        max_tokens=config.MAX_TOKENS_RESPUESTA, stream=True,
        extra_body={"reasoning_effort": config.RAZONAMIENTO},
    )
    for ev in stream:
        if ev.choices and ev.choices[0].delta.content:
            yield ev.choices[0].delta.content


def preguntar(pregunta, k=config.TOP_K):
    """Respuesta completa. Devuelve (texto, fuentes)."""
    msgs, frags = preparar(pregunta, k)
    return "".join(generar(msgs)), fuentes_de(frags)


if __name__ == "__main__":
    print("Agente listo. Escribe tu pregunta ('salir' para terminar).")
    while True:
        p = input("\n> ").strip()
        if p.lower() in {"salir", "exit", "q"}:
            break
        if not p:
            continue
        print()
        msgs, frags = preparar(p)
        for t in generar(msgs):
            print(t, end="", flush=True)   # se muestra mientras se genera
        print("\n\nFuentes consultadas:",
              ", ".join(f"{f['archivo']} p.{f['paginas']}" for f in fuentes_de(frags)))

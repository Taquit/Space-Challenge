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

SYSTEM_FISIO = (
    "\n\nIMPORTANTE: quien te escribe ES el tripulante descrito en 'Datos del tripulante' (habla de 'mis', 'yo', "
    "'mi salud'...). Para preguntas personales (quién soy, mis signos vitales, cómo estoy, mi sueño, mi aptitud) "
    "responde con ESOS datos aunque no estén en los fragmentos; nunca digas 'No está en la documentación' para "
    "ellas. Dirígete a él de tú y menciona su identificador. Cita solo las "
    "cifras dadas, no inventes valores, indica si es APTO o NO APTO y aclara que es orientativo. "
    "Si hay resultados cognitivos, cita solo sus cifras, di que son orientativos y que una sesión atípica "
    "puede deberse a fatiga, distracción o poco esfuerzo; nunca los uses para declarar no apto. "
    "Si la respuesta sale solo de esos datos, termina con [Datos del tripulante] en lugar de citar un PDF."
)


def estado_fisiologico(usuario=None, variables=None, series=None, medicacion=None, sesiones_cog=None):
    if not usuario or not (series or sesiones_cog):
        return ""
    from src.salud import aptitud, inferencia
    res = inferencia.resumen_global(usuario, series, variables=variables)
    apt = aptitud.evaluar_aptitud(usuario, series, sesiones_cog)
    txt = [f"Tripulante {usuario} (cada tripulante tiene su propio modelo entrenado con sus datos):"]
    for v, m in res["medidas"].items():
        esp = m["esperado_personal"]
        esp_txt = f", esperado personal {esp['lower']}-{esp['upper']}" if esp else ""
        txt.append(f"- {v}: actual {m['actual']} {m['unidad']}{esp_txt}; media {m['media']}, mín {m['minimo']}, "
                   f"máx {m['maximo']}, tendencia {m['tendencia']}; estado del modelo personal {m['estado_modelo']}; "
                   f"clínico {m['nivel_clinico']} ({m['interpretacion_clinica']})"
                   + (f"; deriva lenta {m['deriva']['sentido']} de {m['deriva']['cambio']}" if m['deriva']['detectada'] else "") + ".")
    if medicacion:
        txt.append("- Medicación para dormir registrada: " + "; ".join(f"{f}: {m}" for f, m in medicacion[-5:]) + ".")
    for p in res["patrones"]:
        txt.append(f"- Patrón: {p['mensaje']}")
    if apt.get("cognitivo"):
        from src.salud import cognitivo
        txt += cognitivo.texto_chat(apt["cognitivo"])
    txt.append(f"Aptitud: {'APTO' if apt['apto'] else 'NO APTO'} (nivel {apt['nivel']}). "
               + " ".join([e["mensaje"] for e in apt["motivos"] + apt["observaciones"]] + apt["recomendaciones"]))
    return "\n".join(txt)


def buscar(consulta, k=config.TOP_K):
    vec = emb.encode([consulta], normalize_embeddings=True).astype("float32")
    _, ids = indice.search(vec, k)
    return [chunks[i] for i in ids[0] if i >= 0]


def pags(f):
    fin = f.get("pagina_fin", f["pagina"])
    return str(f["pagina"]) if fin == f["pagina"] else f"{f['pagina']}-{fin}"


def formatear(frags):
    return "\n\n".join(f"[{f['archivo']}, pág. {pags(f)}]\n{f['texto']}" for f in frags)


def preparar(pregunta, k=config.TOP_K, contexto_fisio=""):
    docs = buscar(pregunta, k)
    extra = f"\n\nDatos del tripulante que pregunta (calculados por el sistema):\n{contexto_fisio}" if contexto_fisio else ""
    m = [
        {"role": "system", "content": SYSTEM + (SYSTEM_FISIO if contexto_fisio else "")},
        {"role": "user", "content": f"Fragmentos:\n{formatear(docs)}{extra}\n\nPregunta: {pregunta}"},
    ]
    return m, docs


def fuentes_de(frags):
    vistas = {(f["archivo"], pags(f)) for f in frags}
    return [{"archivo": a, "paginas": p} for a, p in sorted(vistas)]


def generar(msgs):
    stream = client.chat.completions.create(
        model=modelo_llm(), messages=msgs, temperature=config.TEMPERATURA,
        max_tokens=config.MAX_TOKENS_RESPUESTA, stream=True,
        extra_body={"reasoning_effort": config.RAZONAMIENTO},
    )
    for ev in stream:
        if ev.choices and ev.choices[0].delta.content:
            yield ev.choices[0].delta.content


def preguntar(pregunta, k=config.TOP_K, contexto_fisio=""):
    m, docs = preparar(pregunta, k, contexto_fisio)
    return "".join(generar(m)), fuentes_de(docs)


if __name__ == "__main__":
    print("Agente listo. Escribe tu pregunta ('salir' para terminar).")
    while True:
        p = input("\n> ").strip()
        if p.lower() in {"salir", "exit", "q"}:
            break
        if not p:
            continue
        print()
        m, docs = preparar(p)
        for t in generar(m):
            print(t, end="", flush=True)
        print("\n\nFuentes consultadas:",
              ", ".join(f"{f['archivo']} p.{f['paginas']}" for f in fuentes_de(docs)))

"""Backend FastAPI. Arrancar desde la raíz del proyecto:

    python -m src.api.main
    # o: uvicorn src.api.main:app --host 127.0.0.1 --port 8000

Documentación interactiva: http://localhost:8000/docs
"""
import json
import threading
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from openai import APIConnectionError
from pydantic import BaseModel, Field

from src import config
from src.api.salud import router as router_salud
from src.api.sse import sse

estado = {}                 # agente cargado en el arranque
candado = threading.Lock()  # una consulta a la vez: modelo local en CPU


@asynccontextmanager
async def lifespan(app):
    # Se importa aquí: carga BGE-M3 y el índice una sola vez al arrancar.
    from src.rag import agente
    estado["agente"] = agente
    yield
    estado.clear()


app = FastAPI(
    title="Space Challenge API",
    description="Consulta de documentación técnica (RAG) para el monitoreo de salud de astronautas.",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(router_salud)
app.add_middleware(
    CORSMiddleware, allow_origins=config.CORS_ORIGENES,
    allow_methods=["*"], allow_headers=["*"],
)


class Pregunta(BaseModel):
    pregunta: str = Field(..., min_length=2, max_length=1000,
                          examples=["¿Cuál es el límite de dosis de radiación en toda la carrera?"])
    top_k: int = Field(config.TOP_K, ge=1, le=10, description="Fragmentos que se pasan al LLM")


class Fuente(BaseModel):
    archivo: str
    paginas: str = Field(..., description="Página o rango, p. ej. '39' o '39-40'")


class Respuesta(BaseModel):
    respuesta: str
    fuentes: list[Fuente]


class Salud(BaseModel):
    estado: str
    fragmentos_indexados: int
    llm_disponible: bool
    modelo_llm: str | None = None


@app.get("/salud", response_model=Salud, tags=["Sistema"])
def salud():
    """Estado del servicio: índice cargado y LM Studio disponible."""
    ag = estado["agente"]
    try:
        modelo = ag.modelo_llm()
        return Salud(estado="ok", fragmentos_indexados=len(ag.chunks),
                     llm_disponible=True, modelo_llm=modelo)
    except Exception:
        return Salud(estado="degradado", fragmentos_indexados=len(ag.chunks),
                     llm_disponible=False)


@app.post("/preguntar", response_model=Respuesta, tags=["RAG"])
def preguntar(body: Pregunta):
    """Respuesta completa con sus fuentes. Puede tardar (el LLM corre en CPU);
    para mostrar texto mientras se genera usa `/preguntar/stream`."""
    ag = estado["agente"]
    try:
        with candado:
            texto, fuentes = ag.preguntar(body.pregunta, body.top_k)
    except APIConnectionError:
        raise HTTPException(503, "LM Studio no responde. Activa el servidor (lms server start).")
    return Respuesta(respuesta=texto, fuentes=fuentes)


@app.post("/preguntar/stream", tags=["RAG"],
          responses={200: {"content": {"text/event-stream": {}}}})
def preguntar_stream(body: Pregunta):
    """Respuesta en streaming (Server-Sent Events). Eventos, en orden:

    - `fuentes`: lista de fuentes, llega primero.
    - `token`: fragmento de texto de la respuesta (varios).
    - `fin`: la respuesta terminó.
    - `error`: falló la generación.
    """
    ag = estado["agente"]

    def eventos():
        with candado:
            try:
                msgs, frags = ag.preparar(body.pregunta, body.top_k)
                yield sse("fuentes", ag.fuentes_de(frags))
                for t in ag.generar(msgs):
                    yield sse("token", t)
                yield sse("fin", "")
            except APIConnectionError:
                yield sse("error", "LM Studio no responde. Activa el servidor (lms server start).")

    return StreamingResponse(eventos(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


if __name__ == "__main__":
    uvicorn.run(app, host=config.API_HOST, port=config.API_PORT)

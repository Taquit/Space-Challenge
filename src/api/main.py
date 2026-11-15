"""Backend FastAPI. Arrancar desde la raíz del proyecto:

    python -m src.api.main
    # o: uvicorn src.api.main:app --host 127.0.0.1 --port 8000

Documentación interactiva: http://localhost:8000/docs
"""
import asyncio
import json
import threading
import time
from contextlib import asynccontextmanager
from typing import Literal

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from openai import APIConnectionError
from pydantic import BaseModel, Field

from src import config, voz
from src.api.salud import datos_cognitivo as router_datos_cognitivo
from src.api.salud import monitor as router_salud_monitor
from src.api.salud import router as router_salud
from src.api.sse import sse
from src.salud import codigos

estado = {}                 # agente cargado en el arranque
candado = threading.Lock()  # una consulta a la vez: modelo local en CPU
candado_voz = asyncio.Lock()  # una síntesis de Piper a la vez


@asynccontextmanager
async def lifespan(app):
    # Se importa aquí: carga BGE-M3 y el índice una sola vez al arrancar.
    from src.rag import agente
    estado["agente"] = agente
    # Precarga las voces de Piper: el primer aviso hablado no espera a que se cargue el modelo.
    for idioma in config.VOCES:
        try:
            voz.sintetizar(".", idioma)
        except Exception:
            pass   # sin voz instalada: el front usa la del navegador
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
    usuario: str | None = Field(None, description="Tripulante sobre el que se pregunta (activa el resumen y la aptitud)")
    variables: list[str] | None = Field(None, description="Medidas seleccionadas (p. ej. ['pulso']); vacío = todas")
    idioma: Literal["es", "en"] = Field("es", description="Idioma de la respuesta")


def contexto_fisio(body):
    """Texto de contexto fisiológico si la pregunta indica un tripulante; 404 si no existe."""
    if not body.usuario:
        return ""
    if not router_salud_monitor.existe(body.usuario):
        raise HTTPException(404, codigos.error(9001, f"Tripulante '{body.usuario}' no encontrado"))
    series = router_salud_monitor.series_por_variable(body.usuario)
    k = router_salud_monitor.indice_sueno(body.usuario)
    meds = [(n["timestamp"], n["medicacion"]) for n in router_salud_monitor.sueno.get(body.usuario, [])[: k + 1] if n.get("medicacion")]
    return estado["agente"].estado_fisiologico(body.usuario, body.variables, series, meds,
                                                router_datos_cognitivo.sesiones(body.usuario))


class Fuente(BaseModel):
    archivo: str
    paginas: str = Field(..., description="Página o rango, p. ej. '39' o '39-40'")


class Respuesta(BaseModel):
    codigo: int = Field(7001, description="7001 = respuesta generada (ver docs/CODIGOS.md)")
    respuesta: str
    fuentes: list[Fuente]


class Salud(BaseModel):
    estado: str
    fragmentos_indexados: int
    llm_disponible: bool
    modelo_llm: str | None = None


_llm = {"t": -1e9, "modelo": None}   # último chequeo de LM Studio (se reutiliza unos segundos)
_LLM_CACHE_S = 5


def _modelo_llm(ag):
    """Modelo cargado en LM Studio o None. Rápido: timeout corto, sin reintentos y cacheado,
    para que /salud responda al instante aunque LM Studio esté ocupado generando o apagado."""
    if time.monotonic() - _llm["t"] > _LLM_CACHE_S:
        try:
            cli = ag.client.with_options(timeout=1.5, max_retries=0)
            modelo = config.MODELO_LLM or cli.models.list().data[0].id
        except Exception:
            modelo = None
        _llm.update(t=time.monotonic(), modelo=modelo)
    return _llm["modelo"]


@app.get("/salud", response_model=Salud, tags=["Sistema"])
def salud():
    """Estado del servicio: índice cargado y LM Studio disponible."""
    ag = estado["agente"]
    modelo = _modelo_llm(ag)
    if modelo:
        return Salud(estado="ok", fragmentos_indexados=len(ag.chunks),
                     llm_disponible=True, modelo_llm=modelo)
    return Salud(estado="degradado", fragmentos_indexados=len(ag.chunks),
                 llm_disponible=False)


@app.post("/preguntar", response_model=Respuesta, tags=["RAG"])
def preguntar(body: Pregunta):
    """Respuesta completa con sus fuentes. Puede tardar (el LLM corre en CPU);
    para mostrar texto mientras se genera usa `/preguntar/stream`."""
    ag = estado["agente"]
    try:
        with candado:
            texto, fuentes = ag.preguntar(body.pregunta, body.top_k, contexto_fisio(body), body.idioma)
    except APIConnectionError:
        raise HTTPException(503, codigos.error(9003, "LM Studio no responde. Activa el servidor (lms server start)."))
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
    ctx = contexto_fisio(body)

    def eventos():
        with candado:
            try:
                msgs, frags = ag.preparar(body.pregunta, body.top_k, ctx, body.idioma)
                yield sse("fuentes", ag.fuentes_de(frags))
                for t in ag.generar(msgs):
                    yield sse("token", t)
                yield sse("fin", "")
            except APIConnectionError:
                yield sse("error", "LM Studio no responde. Activa el servidor (lms server start).")

    return StreamingResponse(eventos(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


class Voz(BaseModel):
    texto: str = Field(..., min_length=1, max_length=2000, examples=["Hola, soy Orbi. Tus signos vitales se ven bien."])
    idioma: Literal["es", "en"] = Field("es", description="es = español de México, en = inglés")


@app.post("/voz", tags=["Voz"], response_class=Response,
          responses={200: {"content": {"audio/wav": {}}}, 503: {"description": "Voz no instalada (código 9005)"}})
async def hablar(body: Voz, request: Request):
    """Texto a voz con Piper (local, sin internet). Devuelve un WAV para reproducir en el front."""
    try:
        async with candado_voz:   # Piper sintetiza una frase a la vez: las demás esperan aquí, sin ocupar hilos
            if await request.is_disconnected():   # el front ya la canceló (callar/interrumpir): no se sintetiza
                return Response(status_code=204)
            audio = await run_in_threadpool(voz.sintetizar, body.texto, body.idioma)
    except (FileNotFoundError, ImportError):
        raise HTTPException(503, codigos.error(9005, f"Voz '{body.idioma}' no instalada. Ejecuta: python scripts/descargar_voces.py"))
    return Response(audio, media_type="audio/wav", headers={"Cache-Control": "no-store"})


# Front estático de ORBITAL (carpeta con index.html), servido en "/" desde el mismo origen: sin CORS.
# Se monta DESPUÉS de todas las rutas de la API para no taparlas (/docs, /salud, /tripulantes, /preguntar siguen igual).
if config.FRONT_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(config.FRONT_DIR), html=True), name="front")


if __name__ == "__main__":
    uvicorn.run(app, host=config.API_HOST, port=config.API_PORT)

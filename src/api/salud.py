"""Endpoints de datos de salud de los tripulantes."""
import asyncio

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.api.sse import sse
from src.datos.salud import Monitor

router = APIRouter(prefix="/tripulantes", tags=["Salud en tiempo real"])
monitor = Monitor()


class Medicion(BaseModel):
    valor: float
    unidad: str | None = None
    timestamp: str


class Lectura(BaseModel):
    timestamp: str
    valores: dict[str, float] = Field(..., examples=[{"pulso": 71.2, "spo2": 97.5}])


class EstadoSalud(BaseModel):
    usuario: str
    timestamp_actual: str
    actual: dict[str, Medicion] = Field(..., description="Último valor de cada variable")
    historial: list[Lectura] = Field(..., description="Lecturas hasta ahora, de la más antigua a la más reciente")
    simulado: bool = Field(..., description="true: reproducción de datos grabados, no un sensor real")


class Tripulante(BaseModel):
    id: str
    variables: list[str]
    lecturas_disponibles: int


def _existe(usuario):
    if usuario not in monitor.series:
        raise HTTPException(404, f"Tripulante '{usuario}' no encontrado")


@router.get("", response_model=list[Tripulante])
def listar():
    """Tripulantes con datos y las variables que se miden de cada uno."""
    return [Tripulante(id=u, variables=monitor.variables(u),
                       lecturas_disponibles=len(monitor.series[u]))
            for u in monitor.tripulantes()]


@router.get("/{usuario}/salud", response_model=EstadoSalud)
def salud(usuario: str, limite: int = Query(60, ge=1, le=10000,
                                            description="Cuántas lecturas recientes incluir en el historial")):
    """Foto actual: último valor de cada variable más el historial reciente."""
    _existe(usuario)
    return monitor.estado(usuario, limite)


@router.get("/{usuario}/salud/stream", responses={200: {"content": {"text/event-stream": {}}}})
async def salud_stream(usuario: str, request: Request,
                       limite: int = Query(60, ge=1, le=10000)):
    """Datos en vivo (Server-Sent Events). Eventos:

    - `snapshot`: estado inicial (mismo contenido que `GET /tripulantes/{id}/salud`).
    - `lectura`: una lectura nueva `{timestamp, valores}`, cada vez que "ocurre" una.
    - `fin`: ya no hay más datos (terminó la reproducción).
    - `: ping`: comentario de keep-alive, el front puede ignorarlo.
    """
    _existe(usuario)

    async def eventos():
        estado = monitor.estado(usuario, limite)
        yield sse("snapshot", estado)
        i = monitor.indice_actual(usuario)
        ultimo = len(monitor.series[usuario]) - 1
        pings = 0
        while i < ultimo:
            if await request.is_disconnected():
                return
            await asyncio.sleep(0.5)
            actual = monitor.indice_actual(usuario)
            if actual == i:
                pings += 1
                if pings % 20 == 0:
                    yield ": ping\n\n"
                continue
            for j in range(i + 1, actual + 1):   # no se pierde ninguna lectura
                yield sse("lectura", monitor.lectura(usuario, j))
            i = actual
        yield sse("fin", "")

    return StreamingResponse(eventos(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/reiniciar-simulacion", status_code=204)
def reiniciar():
    """Reinicia la reproducción desde el inicio del día (útil para demos)."""
    monitor.reiniciar()

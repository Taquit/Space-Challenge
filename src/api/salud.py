"""Endpoints de datos de salud de los tripulantes."""
import asyncio

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.api.sse import sse
from src.datos.salud import Monitor
from src.salud import aptitud as apt
from src.salud import codigos
from src.salud import inferencia, notificaciones

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


class Evento(BaseModel):
    codigo: int = Field(..., description="Ver docs/CODIGOS.md (familia 5xxx)")
    nombre: str
    mensaje: str
    variable: str | None = None


class Notificacion(BaseModel):
    id: int
    codigo: int = Field(..., description="6001 vigilar, 6010 alerta, 6011 crítico, 6020 deriva lenta")
    tipo: str
    usuario: str
    timestamp: str
    severidad: str = Field(..., description="VIGILAR | ALERTA | CRITICO")
    variable: str
    mensaje: str


class Aptitud(BaseModel):
    usuario: str
    apto: bool
    codigo: int = Field(..., description="1001 saludable, 1002 apto con seguimiento, 1010 riesgo, 1011 crítico")
    estado: str
    nivel: str = Field(..., description="NORMAL | VIGILAR | ALERTA | CRITICO")
    motivos: list[Evento] = Field(..., description="Razones por las que NO es apto (vacío si es apto)")
    observaciones: list[Evento]
    recomendaciones: list[str]
    derivadas: dict[str, float]


class Tripulante(BaseModel):
    id: str
    variables: list[str]
    lecturas_disponibles: int


def _existe(usuario):
    if usuario not in monitor.series:
        raise HTTPException(404, codigos.error(9001, f"Tripulante '{usuario}' no encontrado"))


@router.get("/codigos", tags=["Códigos"])
def lista_codigos():
    """Catálogo de códigos de respuesta (el mismo de docs/CODIGOS.md)."""
    return codigos.catalogo()


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


@router.get("/{usuario}/resumen")
def resumen(usuario: str,
            variables: str | None = Query(None, description="Medidas separadas por coma (p. ej. pulso,spo2). Vacío = todas"),
            limite: int | None = Query(None, ge=2, le=10000, description="Últimas N lecturas a resumir (vacío = todo lo transcurrido)")):
    """Resumen de la(s) medida(s) seleccionada(s): estadísticas, tendencia, valor actual frente al
    rango esperado por el modelo personal del tripulante, interpretación clínica, derivadas y patrones."""
    _existe(usuario)
    pedidas = [v.strip() for v in variables.split(",") if v.strip()] if variables else None
    series = monitor.series_por_variable(usuario)
    desconocidas = [v for v in (pedidas or []) if v not in series]
    if desconocidas:
        raise HTTPException(404, codigos.error(9002, f"Variable(s) desconocida(s): {', '.join(desconocidas)}"))
    return inferencia.resumen_global(usuario, series, limite, pedidas)


@router.get("/{usuario}/aptitud", response_model=Aptitud)
def aptitud(usuario: str):
    """¿Apto o no apto (saludable)? Combina límites clínicos y el modelo personal. Orientativo."""
    _existe(usuario)
    return apt.evaluar_aptitud(usuario, monitor.series_por_variable(usuario))


@router.get("/{usuario}/notificaciones", response_model=list[Notificacion])
def notificaciones_usuario(usuario: str, desde: int = Query(0, ge=0, description="Solo las de id mayor a este")):
    """Notificaciones generadas hasta ahora (alertas al empeorar el estado de una medida)."""
    _existe(usuario)
    notificaciones.sincronizar(usuario, monitor.series[usuario], monitor.indice_actual(usuario))
    return notificaciones.listar(usuario, desde)


@router.get("/{usuario}/salud/stream", responses={200: {"content": {"text/event-stream": {}}}})
async def salud_stream(usuario: str, request: Request,
                       limite: int = Query(60, ge=1, le=10000)):
    """Datos en vivo (Server-Sent Events). Eventos:

    - `snapshot`: estado inicial (mismo contenido que `GET /tripulantes/{id}/salud`).
    - `lectura`: una lectura nueva `{timestamp, valores}`, cada vez que "ocurre" una.
    - `notificacion`: alerta nueva `{id, usuario, timestamp, severidad, variable, mensaje}`.
    - `fin`: ya no hay más datos (terminó la reproducción).
    - `: ping`: comentario de keep-alive, el front puede ignorarlo.
    """
    _existe(usuario)

    async def eventos():
        estado = monitor.estado(usuario, limite)
        yield sse("snapshot", estado)
        i = monitor.indice_actual(usuario)
        for n in notificaciones.sincronizar(usuario, monitor.series[usuario], i):
            yield sse("notificacion", n)
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
            for n in notificaciones.sincronizar(usuario, monitor.series[usuario], actual):
                yield sse("notificacion", n)
            i = actual
        yield sse("fin", "")

    return StreamingResponse(eventos(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/reiniciar-simulacion", status_code=204)
def reiniciar():
    """Reinicia la reproducción desde el inicio del día (útil para demos)."""
    monitor.reiniciar()
    notificaciones.reiniciar()

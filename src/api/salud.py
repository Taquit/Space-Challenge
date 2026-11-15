"""Endpoints de datos de salud de los tripulantes."""
import asyncio

from fastapi import APIRouter, Body, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.api.sse import sse
from src.datos.cognitivo import DatosCognitivo
from src.datos.salud import Monitor
from src.salud import aptitud as apt
from src.salud import codigos, cognitivo
from src.salud import inferencia, notificaciones

router = APIRouter(prefix="/tripulantes", tags=["Salud en tiempo real"])
monitor = Monitor()
datos_cognitivo = DatosCognitivo()


class Medicion(BaseModel):
    valor: float
    unidad: str | None = None
    timestamp: str


class Lectura(BaseModel):
    timestamp: str
    valores: dict[str, float] = Field(..., examples=[{"pulso": 71.2, "spo2": 97.5}])


class Noche(BaseModel):
    timestamp: str = Field(..., description="Fecha de la noche (YYYY-MM-DD)")
    valores: dict[str, float] = Field(..., examples=[{"sueno_latencia": 14, "sueno_duracion": 7.73, "sueno_eficiencia": 92.1}])
    fase: str | None = Field(None, description="Fase del estudio (PRE_TEST, IN_TEST, POST_TEST)")
    medicacion: str | None = Field(None, description="Medicación para dormir registrada esa noche")


class EstadoSalud(BaseModel):
    usuario: str
    timestamp_actual: str | None = Field(None, description="Instante de la última lectura de signos vitales (o noche, si solo hay sueño)")
    actual: dict[str, Medicion] = Field(..., description="Último valor de cada variable")
    historial: list[Lectura] = Field(..., description="Lecturas hasta ahora, de la más antigua a la más reciente")
    sueno: list[Noche] = Field(default_factory=list, description="Noches de sueño transcurridas (vacío si el tripulante no tiene datos de sueño)")
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
    cognitivo: dict | None = Field(None, description="Bloque cognitivo (solo si el tripulante tiene sesiones). Ver docs/COGNITIVO.md")


class Tripulante(BaseModel):
    id: str
    variables: list[str]
    lecturas_disponibles: int
    noches_disponibles: int = Field(0, description="Noches de sueño disponibles (0 = sin datos de sueño)")


def _existe(usuario):
    if not monitor.existe(usuario):
        raise HTTPException(404, codigos.error(9001, f"Tripulante '{usuario}' no encontrado"))


def _sincronizar(usuario):
    """Procesa lecturas y noches nuevas; devuelve las notificaciones generadas."""
    nuevas = []
    if usuario in monitor.series:
        nuevas += notificaciones.sincronizar(usuario, monitor.series[usuario], monitor.indice_actual(usuario))
    k = monitor.indice_sueno(usuario)
    if k >= 0:
        nuevas += notificaciones.sincronizar_sueno(usuario, monitor.serie_sueno(usuario, k), k)
    sesiones = datos_cognitivo.sesiones(usuario)
    if sesiones:
        nuevas += notificaciones.sincronizar_cognitivo(usuario, sesiones)
    return nuevas


def _bloque_cognitivo(usuario, resumen=None):
    """Bloque cognitivo del usuario o None si no tiene sesiones. `resumen` = resumen_global completo (opcional)."""
    sesiones = datos_cognitivo.sesiones(usuario)
    if not sesiones:
        return None
    if resumen is None:
        resumen = inferencia.resumen_global(usuario, monitor.series_por_variable(usuario))
    return cognitivo.bloque(sesiones, resumen)


@router.get("/codigos", tags=["Códigos"])
def lista_codigos():
    """Catálogo de códigos de respuesta (el mismo de docs/CODIGOS.md)."""
    return codigos.catalogo()


@router.get("", response_model=list[Tripulante])
def listar():
    """Tripulantes con datos y las variables que se miden de cada uno."""
    return [Tripulante(id=u, variables=monitor.variables(u),
                       lecturas_disponibles=monitor.lecturas_disponibles(u),
                       noches_disponibles=monitor.noches_disponibles(u))
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
    res = inferencia.resumen_global(usuario, series, limite, pedidas)
    bloque = _bloque_cognitivo(usuario, res if not pedidas and not limite else None)
    if bloque:
        res["cognitivo"] = bloque
    return res


@router.get("/{usuario}/aptitud", response_model=Aptitud)
def aptitud(usuario: str):
    """¿Apto o no apto (saludable)? Combina límites clínicos y el modelo personal. Orientativo."""
    _existe(usuario)
    return apt.evaluar_aptitud(usuario, monitor.series_por_variable(usuario), datos_cognitivo.sesiones(usuario))


@router.post("/{usuario}/cognitivo", status_code=201, tags=["Cognitivo"])
def guardar_sesion_cognitiva(usuario: str, sesion: dict = Body(..., description="Sesión de pruebas (ver `SesionCognitiva` en el esquema)")):
    """Guarda una sesión de pruebas cognitivas (PVT, DSST, Matrix) y devuelve la sesión con su `id` y el estado
    cognitivo resultante. Sesión que no cumple el esquema: 422 con código 9004."""
    _existe(usuario)
    try:
        guardada = datos_cognitivo.agregar(usuario, sesion)
    except ValueError as e:
        raise HTTPException(422, codigos.error(9004, f"Sesión cognitiva inválida: {e}"))
    nuevas = _sincronizar(usuario)
    ev = cognitivo.evaluar(datos_cognitivo.sesiones(usuario))
    return {"sesion": guardada, "estado": ev["estado"], "codigo_nivel": ev["codigo_nivel"],
            "notificaciones": nuevas, "orientativo": cognitivo.AVISO}


@router.get("/{usuario}/cognitivo", tags=["Cognitivo"])
def historial_cognitivo(usuario: str):
    """Historial de sesiones cognitivas, cada una con su evaluación frente a la línea base (las de familiarización
    y las de línea base no se evalúan)."""
    _existe(usuario)
    sesiones = datos_cognitivo.sesiones(usuario)
    ev = cognitivo.evaluar(sesiones)
    por_id = {e["id"]: e for e in ev["evaluacion"]}
    return {"usuario": usuario, "estado": ev["estado"], "codigo_nivel": ev["codigo_nivel"], "orientativo": cognitivo.AVISO,
            "sesiones": [{**s, "evaluacion": por_id.get(s.get("id"))} for s in sesiones]}


@router.get("/{usuario}/cognitivo/resumen", tags=["Cognitivo"])
def resumen_cognitivo(usuario: str):
    """Línea base, estado, deriva y observaciones cognitivas. Orientativo, no es diagnóstico médico."""
    _existe(usuario)
    return {"usuario": usuario, **cognitivo.bloque(datos_cognitivo.sesiones(usuario),
                                                    inferencia.resumen_global(usuario, monitor.series_por_variable(usuario)))}


@router.get("/{usuario}/notificaciones", response_model=list[Notificacion])
def notificaciones_usuario(usuario: str, desde: int = Query(0, ge=0, description="Solo las de id mayor a este")):
    """Notificaciones generadas hasta ahora (alertas al empeorar el estado de una medida)."""
    _existe(usuario)
    _sincronizar(usuario)
    return notificaciones.listar(usuario, desde)


@router.get("/{usuario}/salud/stream", responses={200: {"content": {"text/event-stream": {}}}})
async def salud_stream(usuario: str, request: Request,
                       limite: int = Query(60, ge=1, le=10000)):
    """Datos en vivo (Server-Sent Events). Eventos:

    - `snapshot`: estado inicial (mismo contenido que `GET /tripulantes/{id}/salud`).
    - `lectura`: una lectura nueva `{timestamp, valores}`, cada vez que "ocurre" una.
    - `sueno`: una noche nueva `{timestamp, valores, fase, medicacion}` (solo tripulantes con datos de sueño).
    - `notificacion`: alerta nueva `{id, usuario, timestamp, severidad, variable, mensaje}`.
    - `fin`: ya no hay más datos (terminaron las lecturas y las noches).
    - `: ping`: comentario de keep-alive, el front puede ignorarlo.
    """
    _existe(usuario)

    async def eventos():
        estado = monitor.estado(usuario, limite)
        yield sse("snapshot", estado)
        i = monitor.indice_actual(usuario) if usuario in monitor.series else -1
        k = monitor.indice_sueno(usuario)
        for n in _sincronizar(usuario):
            yield sse("notificacion", n)
        ultimo = monitor.lecturas_disponibles(usuario) - 1
        ultima_noche = monitor.noches_disponibles(usuario) - 1
        pings = 0
        while i < ultimo or k < ultima_noche:
            if await request.is_disconnected():
                return
            await asyncio.sleep(0.5)
            actual = monitor.indice_actual(usuario) if ultimo >= 0 else -1
            noche = monitor.indice_sueno(usuario)
            if actual == i and noche == k:
                pings += 1
                if pings % 20 == 0:
                    yield ": ping\n\n"
                continue
            for j in range(i + 1, actual + 1):   # no se pierde ninguna lectura
                yield sse("lectura", monitor.lectura(usuario, j))
            for j in range(k + 1, noche + 1):    # ni ninguna noche
                yield sse("sueno", monitor.noche(usuario, j))
            i, k = actual, noche
            for n in _sincronizar(usuario):
                yield sse("notificacion", n)
        yield sse("fin", "")

    return StreamingResponse(eventos(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/reiniciar-simulacion", status_code=204)
def reiniciar():
    """Reinicia la reproducción desde el inicio del día (útil para demos)."""
    monitor.reiniciar()
    notificaciones.reiniciar()

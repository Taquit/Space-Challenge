"""Sesiones de pruebas cognitivas (PVT, DSST, Matrix) en data/cognitivo.json. Ver docs/COGNITIVO.md.

Formato (como data/sueno.json, pero agrupado por usuario): [{"usuario": ..., "sesiones": [{...}, ...]}].
Se guardan siempre las métricas crudas; las inferencias se recalculan al leer (src/salud/cognitivo.py).
"""
import json
import threading
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src import config


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PVT(_Base):
    rt_media_ms: float = Field(..., gt=0)
    rt_mediana_ms: float = Field(..., gt=0)
    lapsos: int = Field(..., ge=0)
    falsos_inicios: int = Field(0, ge=0)
    n_estimulos: int = Field(..., ge=1)


class DSST(_Base):
    correctas: int = Field(..., ge=0)
    intentos: int = Field(..., ge=0)
    precision: float = Field(..., ge=0, le=1)
    throughput: float = Field(..., ge=0, description="Correctas por segundo")
    rt_media_ms: float = Field(..., ge=0)

    @model_validator(mode="after")
    def _coherente(self):
        if self.correctas > self.intentos:
            raise ValueError("correctas no puede superar a intentos")
        return self


class Matrix(_Base):
    correctas: int = Field(..., ge=0, le=12)
    intentos: int = Field(..., ge=0, le=12)
    precision: float = Field(..., ge=0, le=1)
    tiempo_total_s: float = Field(..., ge=0)
    throughput: float = Field(..., ge=0, description="Correctas por segundo")

    @model_validator(mode="after")
    def _coherente(self):
        if self.correctas > self.intentos:
            raise ValueError("correctas no puede superar a intentos")
        return self


class Pruebas(_Base):
    pvt: PVT | None = None
    dsst: DSST | None = None
    matrix: Matrix | None = None

    @model_validator(mode="after")
    def _alguna(self):
        if not (self.pvt or self.dsst or self.matrix):
            raise ValueError("la sesión debe traer al menos una prueba (pvt, dsst o matrix)")
        return self


class Contexto(_Base):
    comentario: str = Field("", max_length=500)


class SesionCognitiva(_Base):
    id: int | None = Field(None, ge=1, description="Lo asigna el servidor si no viene")
    fecha: str = Field(..., description="ISO 8601 con zona horaria, p. ej. 2026-11-15T09:30:00-06:00")
    forma: str = Field("A", min_length=1, max_length=8, description="Forma alternativa de las pruebas")
    semilla: int = Field(0, description="Semilla del generador de estímulos")
    familiarizacion: bool = Field(False, description="true = sesión de práctica, se descarta de la línea base")
    pruebas: Pruebas
    contexto: Contexto = Field(default_factory=Contexto)

    @field_validator("fecha")
    @classmethod
    def _fecha_iso(cls, v):
        try:
            datetime.fromisoformat(v)
        except ValueError:
            raise ValueError("fecha debe estar en formato ISO 8601")
        return v


def validar(sesion):
    """Devuelve la sesión validada como dict (sin campos vacíos); ValueError con el detalle si no cumple el esquema."""
    try:
        return SesionCognitiva.model_validate(sesion).model_dump(exclude_none=True)
    except Exception as e:                      # ValidationError de pydantic
        raise ValueError(str(e)) from e


class DatosCognitivo:
    def __init__(self, ruta=None):
        self.ruta = ruta if ruta is not None else config.DATOS_COGNITIVO
        self._lock = threading.Lock()
        self._por_usuario = {}
        self._cargar()

    def _cargar(self):
        self._por_usuario = {}
        try:
            crudo = json.loads(self.ruta.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        for r in crudo:
            self._por_usuario[r["usuario"]] = list(r.get("sesiones", []))

    def _guardar(self):
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        crudo = [{"usuario": u, "sesiones": s} for u, s in sorted(self._por_usuario.items())]
        self.ruta.write_text(json.dumps(crudo, indent=2, ensure_ascii=False), encoding="utf-8")

    def sesiones(self, usuario):
        """Copia de las sesiones del usuario ordenadas por fecha (más antigua primero)."""
        with self._lock:
            return sorted(self._por_usuario.get(usuario, []), key=lambda s: datetime.fromisoformat(s["fecha"]).timestamp())

    def agregar(self, usuario, sesion):
        """Valida y guarda una sesión. Devuelve la sesión guardada (con `id`). ValueError si es inválida."""
        s = validar(sesion)
        with self._lock:
            lista = self._por_usuario.setdefault(usuario, [])
            usados = {x["id"] for x in lista if "id" in x}
            if s.get("id") in usados:
                raise ValueError(f"ya existe una sesión con id {s['id']}")
            if s.get("id") is None:
                s["id"] = max(usados, default=0) + 1
            lista.append(s)
            self._guardar()
        return s

    def reemplazar_todo(self, por_usuario):
        """{usuario: [sesion, ...]}: sustituye el contenido (lo usa scripts/simular_cognitivo.py)."""
        with self._lock:
            self._por_usuario = {u: [validar(s) for s in ses] for u, ses in por_usuario.items()}
            self._guardar()

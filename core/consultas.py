"""
Panel "Consulta ejecutada" y Bitácora.

Cada petición HTTP abre un registro propio (contextvars) donde los
envoltorios de PostgreSQL (core/bd/pg.py) y MongoDB (core/bd/mongo.py)
anotan cada sentencia: motor, texto, parámetros, tiempo, resultado o
error del motor. El middleware muestra ese registro al final de la
página; si la acción termina en redirección, lo guarda en memoria y lo
recupera en la página siguiente mediante una cookie de un solo uso.

La Bitácora conserva las últimas 50 operaciones en memoria del proceso
(gunicorn corre con un solo proceso para que sea consistente).
"""
from __future__ import annotations

import contextvars
import threading
import uuid
from collections import OrderedDict, deque
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime

from django.utils import timezone

MOTOR_PG = "PostgreSQL"
MOTOR_MONGO = "MongoDB"


@dataclass
class Consulta:
    motor: str
    operacion: str
    sentencia: str
    parametros: str | None = None
    sentencia_final: str | None = None
    tiempo_ms: float = 0.0
    resultado: str | None = None
    error: str | None = None
    momento: datetime = field(default_factory=timezone.now)
    ruta: str = ""
    accion: str = ""

    def como_dict(self) -> dict:
        datos = asdict(self)
        datos["momento"] = timezone.localtime(self.momento).strftime("%d/%m/%Y %H:%M:%S")
        return datos


@dataclass
class EstadoPeticion:
    ruta: str = ""
    metodo: str = ""
    accion: str = ""
    consultas: list[Consulta] = field(default_factory=list)


_estado: contextvars.ContextVar[EstadoPeticion | None] = contextvars.ContextVar(
    "pescapp_estado_peticion", default=None
)
_silencio: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "pescapp_silencio", default=False
)

BITACORA: deque[Consulta] = deque(maxlen=50)
_ACCIONES: "OrderedDict[str, dict]" = OrderedDict()
_MAX_ACCIONES = 200
_candado = threading.Lock()


# ---------------------------------------------------------------------
# Ciclo de vida por petición
# ---------------------------------------------------------------------
def iniciar(ruta: str = "", metodo: str = "") -> contextvars.Token:
    return _estado.set(EstadoPeticion(ruta=ruta, metodo=metodo))


def finalizar(token: contextvars.Token) -> None:
    _estado.reset(token)


def estado_actual() -> EstadoPeticion | None:
    return _estado.get()


def establecer_accion(titulo: str) -> None:
    """Título legible de la acción (aparece en el panel y la bitácora)."""
    estado = _estado.get()
    if estado is not None:
        estado.accion = titulo
        for c in estado.consultas:
            c.accion = c.accion or titulo


def consultas_actuales() -> list[Consulta]:
    estado = _estado.get()
    return estado.consultas if estado is not None else []


@contextmanager
def silenciado():
    """Suspende el registro (semilla, lecturas de infraestructura)."""
    token = _silencio.set(True)
    try:
        yield
    finally:
        _silencio.reset(token)


# ---------------------------------------------------------------------
# Registro de una sentencia o comando
# ---------------------------------------------------------------------
def registrar(
    motor: str,
    operacion: str,
    sentencia: str,
    *,
    parametros: str | None = None,
    sentencia_final: str | None = None,
    tiempo_ms: float = 0.0,
    resultado: str | None = None,
    error: str | None = None,
) -> None:
    if _silencio.get():
        return
    estado = _estado.get()
    consulta = Consulta(
        motor=motor,
        operacion=operacion,
        sentencia=sentencia,
        parametros=parametros,
        sentencia_final=sentencia_final,
        tiempo_ms=round(tiempo_ms, 2),
        resultado=resultado,
        error=error,
        ruta=f"{estado.metodo} {estado.ruta}".strip() if estado else "consola",
        accion=estado.accion if estado else "",
    )
    if estado is not None:
        estado.consultas.append(consulta)
    with _candado:
        BITACORA.appendleft(consulta)


# ---------------------------------------------------------------------
# Acción previa (patrón POST -> redirección -> GET)
# ---------------------------------------------------------------------
def guardar_accion(estado: EstadoPeticion) -> str:
    id_accion = uuid.uuid4().hex[:12]
    with _candado:
        _ACCIONES[id_accion] = {
            "titulo": estado.accion or f"{estado.metodo} {estado.ruta}",
            "consultas": list(estado.consultas),
        }
        while len(_ACCIONES) > _MAX_ACCIONES:
            _ACCIONES.popitem(last=False)
    return id_accion


def recuperar_accion(id_accion: str | None) -> dict | None:
    if not id_accion:
        return None
    with _candado:
        return _ACCIONES.pop(id_accion, None)


def bitacora() -> list[Consulta]:
    with _candado:
        return list(BITACORA)

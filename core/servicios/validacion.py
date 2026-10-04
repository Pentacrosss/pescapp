"""
R3 · Integración MongoDB -> PostgreSQL: validar una recepción.

  1. Lee el documento en MongoDB (registro provisional).
  2. En UNA transacción PostgreSQL:
       INSERT compra (uuid_recepcion = _id, fecha = fecha local de
       capturado_en, estado = pendiente_pago)
       INSERT detalle_compra por línea (subtotal = ROUND(peso × precio, 2))
       UPDATE compra.total = Σ subtotales
  3. COMMIT. Si algo falla: ROLLBACK y la contabilidad no cambia.
  4. Marca el documento como validada con id_compra y validado_en.

Quien impide contabilizar dos veces es PostgreSQL (uuid_recepcion
UNIQUE), no la aplicación: "Forzar revalidación" lo demuestra.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from django.db import DatabaseError, IntegrityError
from pymongo.errors import PyMongoError

from core.bd import mongo, pg
from core.repositorios import compras_repo, recepciones_repo
from core.utilidades import a_decimal, fecha_local

RESTRICCION_UUID = "compra_uuid_recepcion_key"


@dataclass
class ResultadoValidacion:
    ok: bool
    mensaje: str
    nivel: str = "success"  # success | warning | danger
    id_compra: int | None = None
    total: Decimal | None = None
    error_motor: str | None = None
    reconciliada: bool = False


# =====================================================================
# R3 · Validación transaccional (todo o nada)
# =====================================================================
def _crear_compra(documento: dict, id_usuario: int) -> tuple[int, Decimal]:
    fecha = fecha_local(documento["capturado_en"])
    with pg.transaccion("R3 · Validación transaccional"):
        id_compra = compras_repo.insertar_compra(
            documento["id_proveedor"], id_usuario, documento["_id"], fecha
        )
        for linea in documento["lineas"]:
            compras_repo.insertar_detalle_compra(
                id_compra,
                linea["id_producto"],
                a_decimal(linea["peso_kg"]),
                a_decimal(linea["precio_kg"]),
            )
        total = compras_repo.recalcular_total_compra(id_compra)
    return id_compra, total


def validar_recepcion(uuid: str, id_usuario: int, *, validado_en: datetime | None = None) -> ResultadoValidacion:
    documento = recepciones_repo.obtener(uuid)
    if documento is None:
        return ResultadoValidacion(False, "La recepción no existe en MongoDB.", "danger")
    if documento["estado"] != "pendiente":
        return ResultadoValidacion(
            False,
            f"La recepción está '{documento['estado']}' en MongoDB: solo se validan pendientes. "
            "Para probar la protección de PostgreSQL use «Forzar revalidación (demo)».",
            "warning",
        )
    return _contabilizar(documento, id_usuario, validado_en)


# =====================================================================
# R3 · Forzar revalidación (demo): salta la verificación de MongoDB e
# intenta crear la compra otra vez. La rechaza el UNIQUE del motor.
# =====================================================================
def forzar_revalidacion(uuid: str, id_usuario: int) -> ResultadoValidacion:
    documento = recepciones_repo.obtener(uuid)
    if documento is None:
        return ResultadoValidacion(False, "La recepción no existe en MongoDB.", "danger")
    if documento["estado"] == "rechazada":
        return ResultadoValidacion(
            False, "Una recepción rechazada no se contabiliza: la contabilidad no se toca.", "warning"
        )
    return _contabilizar(documento, id_usuario, None)


def _contabilizar(documento: dict, id_usuario: int, validado_en: datetime | None) -> ResultadoValidacion:
    uuid = documento["_id"]
    try:
        id_compra, total = _crear_compra(documento, id_usuario)
    except IntegrityError as exc:
        detalle = pg.describir_error(exc)
        if detalle["sqlstate"] == "23505" and detalle["restriccion"] == RESTRICCION_UUID:
            existente = compras_repo.buscar_compra_por_uuid(uuid)
            reconciliada = False
            if existente and documento.get("estado") != "validada":
                r = recepciones_repo.reconciliar_validada(uuid, existente["id_compra"])
                reconciliada = r.modified_count > 0
            mensaje = "Rechazado por PostgreSQL: esta recepción ya fue contabilizada (uuid_recepcion único)."
            if reconciliada:
                mensaje += (
                    f" MongoDB estaba desfasado y se reconcilió a 'validada' "
                    f"(compra #{existente['id_compra']})."
                )
            return ResultadoValidacion(
                False,
                mensaje,
                "warning",
                id_compra=existente["id_compra"] if existente else None,
                error_motor=detalle["texto"],
                reconciliada=reconciliada,
            )
        return ResultadoValidacion(
            False, "Rechazado por PostgreSQL: " + pg.mensaje_motor(exc), "danger", error_motor=detalle["texto"]
        )
    except DatabaseError as exc:
        # p. ej. trigger fn_bloquear_dia_cerrado (fecha con cierre emitido)
        detalle = pg.describir_error(exc)
        return ResultadoValidacion(
            False, "Rechazado por PostgreSQL: " + pg.mensaje_motor(exc), "danger", error_motor=detalle["texto"]
        )

    # COMMIT confirmado en PostgreSQL -> actualizar el registro provisional
    try:
        recepciones_repo.marcar_validada(uuid, id_compra, validado_en)
    except PyMongoError as exc:
        return ResultadoValidacion(
            True,
            f"Compra #{id_compra} creada en PostgreSQL, pero MongoDB no se pudo actualizar "
            f"({mongo.mensaje_motor(exc)}). Al reintentar, el UNIQUE lo detecta y se reconcilia.",
            "warning",
            id_compra=id_compra,
            total=total,
        )
    return ResultadoValidacion(
        True,
        f"Recepción validada: compra #{id_compra} por ${total} creada en una sola transacción "
        "y documento marcado como 'validada' en MongoDB.",
        "success",
        id_compra=id_compra,
        total=total,
    )

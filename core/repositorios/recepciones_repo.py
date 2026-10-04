"""
Repositorio MongoDB · colección recepciones_muelle (R1, R2).

Registro PROVISIONAL del muelle: un documento por recepción, con _id =
UUID generado en el dispositivo. Aquí está el CRUD completo de
recepciones. MongoDB no guarda saldos ni cierres.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import datetime, timezone as dt_timezone

from django.utils import timezone
from pymongo.errors import PyMongoError

from core.bd import mongo
from core.utilidades import a_entero, hoy, rango_utc_del_dia

ESTADOS = ["pendiente", "validada", "rechazada"]


def a_numero(valor):
    """Número para BSON; si no se puede convertir se deja tal cual y el
    validador $jsonSchema del motor lo rechazará."""
    try:
        return float(str(valor).replace(",", "."))
    except (TypeError, ValueError):
        return valor


def _entero_o_valor(valor):
    convertido = a_entero(valor)
    return convertido if convertido is not None else valor


def normalizar_documento(datos: dict) -> dict:
    """JSON enviado por el dispositivo -> documento BSON.

    Solo convierte tipos (texto ISO -> fecha, números). Las reglas las
    aplica el validador $jsonSchema de la colección.
    """
    capturado = datos.get("capturado_en")
    if isinstance(capturado, str):
        try:
            capturado = datetime.fromisoformat(capturado.replace("Z", "+00:00"))
        except ValueError:
            pass
    if isinstance(capturado, datetime) and capturado.tzinfo is None:
        capturado = timezone.make_aware(capturado)
    if isinstance(capturado, datetime):
        capturado = capturado.astimezone(dt_timezone.utc)

    lineas = []
    for linea in datos.get("lineas") or []:
        atributos = linea.get("atributos")
        lineas.append(
            {
                "id_producto": _entero_o_valor(linea.get("id_producto")),
                "especie": str(linea.get("especie") or ""),
                "peso_kg": a_numero(linea.get("peso_kg")),
                "precio_kg": a_numero(linea.get("precio_kg")),
                "atributos": dict(atributos) if isinstance(atributos, dict) else atributos,
            }
        )

    return {
        "_id": str(datos.get("_id") or ""),
        "id_usuario": _entero_o_valor(datos.get("id_usuario")),
        "id_proveedor": _entero_o_valor(datos.get("id_proveedor")),
        "capturado_en": capturado,
        "lineas": lineas,
        "observaciones": (datos.get("observaciones") or "").strip() or None,
    }


# =====================================================================
# CREATE · R1 · Sincronizar una recepción (upsert idempotente por _id)
#   Paso 1: updateOne({_id}, {$setOnInsert: doc}, {upsert: true})
#           -> si no existe la inserta; si existe no cambia nada.
#   Paso 2: solo si ya existía: updateOne({_id, estado: "pendiente"},
#           {$set: ..., $inc: {reenvios: 1}})
#           -> si sigue pendiente la actualiza y cuenta el reenvío;
#              si está validada o rechazada no la toca.
# Reenviar el mismo UUID nunca crea un segundo documento.
# =====================================================================
def sincronizar_recepcion(documento: dict, *, momento: datetime | None = None) -> dict:
    uuid = documento["_id"]
    ahora = momento or timezone.now()
    resultado = {"uuid": uuid, "pasos": [], "error": None}

    resultado["total_antes"] = mongo.count_documents({}, operacion="countDocuments · total antes")

    nuevo = {k: v for k, v in documento.items() if k != "_id"}
    nuevo.update({"estado": "pendiente", "sincronizado_en": ahora, "reenvios": 0})

    try:
        paso1 = mongo.update_one(
            {"_id": uuid},
            {"$setOnInsert": nuevo},
            upsert=True,
            operacion="R1 · upsert idempotente por _id",
        )
        resultado["pasos"].append(_resumen_update("Paso 1 · upsert por _id", paso1))

        if paso1.upserted_id is not None:
            resultado["accion"] = "insertada"
            resultado["mensaje"] = "Recepción nueva: el motor la insertó (upserted_id = UUID)."
        else:
            paso2 = mongo.update_one(
                {"_id": uuid, "estado": "pendiente"},
                {
                    "$set": {
                        "id_proveedor": documento["id_proveedor"],
                        "lineas": documento["lineas"],
                        "observaciones": documento.get("observaciones"),
                        "sincronizado_en": ahora,
                    },
                    "$inc": {"reenvios": 1},
                },
                operacion="R1 · reenvío: actualizar solo si sigue pendiente",
            )
            resultado["pasos"].append(_resumen_update("Paso 2 · reenvío si pendiente", paso2))
            if paso2.matched_count:
                resultado["accion"] = "actualizada"
                resultado["mensaje"] = "Reenvío de una recepción pendiente: se actualizó y se incrementó reenvios. No se duplicó."
            else:
                resultado["accion"] = "sin_cambios"
                resultado["mensaje"] = "La recepción ya está validada o rechazada: el reenvío no la toca."
    except PyMongoError as exc:
        resultado["accion"] = "error"
        resultado["error"] = mongo.describir_error(exc)["texto"]
        resultado["mensaje"] = "Rechazado por MongoDB: " + mongo.mensaje_motor(exc)

    resultado["total_despues"] = mongo.count_documents({}, operacion="countDocuments · total después")
    actual = mongo.find_one(
        {"_id": uuid},
        proyeccion={"estado": 1, "reenvios": 1, "id_compra": 1},
        operacion="findOne · estado final",
    )
    resultado["estado"] = actual.get("estado") if actual else None
    resultado["reenvios"] = actual.get("reenvios") if actual else None
    return resultado


def _resumen_update(paso: str, r) -> dict:
    return {
        "paso": paso,
        "matched_count": r.matched_count,
        "modified_count": r.modified_count,
        "upserted_id": r.upserted_id,
    }


# =====================================================================
# CREATE (demo) · Documento inválido: lo rechaza el validador $jsonSchema
# =====================================================================
def insertar_invalido_demo() -> str:
    documento = {
        "_id": str(uuid_lib.uuid4()),
        "id_usuario": 3,
        "id_proveedor": 1,
        "capturado_en": timezone.now(),
        "estado": "aprobada",  # no está en el enum
        "lineas": [
            {"id_producto": 1, "especie": "Dorado", "peso_kg": -5, "precio_kg": 3.1, "atributos": {}},
        ],
    }
    mongo.insert_one(documento, operacion="CREATE (demo) · documento inválido")
    return documento["_id"]


# =====================================================================
# READ
# =====================================================================
def construir_filtro(
    estado: str | None = None,
    fecha=None,
    id_proveedor: int | None = None,
    especie: str | None = None,
) -> dict:
    filtro: dict = {}
    if estado:
        filtro["estado"] = estado
    if fecha:
        inicio, fin = rango_utc_del_dia(fecha)
        filtro["capturado_en"] = {"$gte": inicio, "$lt": fin}
    if id_proveedor:
        filtro["id_proveedor"] = id_proveedor
    if especie:
        filtro["lineas.especie"] = especie
    return filtro


ORDEN_LISTA = {"capturado_en": -1}


def listar(filtro: dict, limite: int = 200) -> list[dict]:
    return mongo.find(filtro, orden=ORDEN_LISTA, limite=limite, operacion="READ · listar recepciones")


# READ · R1 · Pendientes del día: igualdad en estado + rango en capturado_en
# -> usa el índice { estado: 1, capturado_en: 1 } (IXSCAN)
ORDEN_PENDIENTES = {"capturado_en": 1}


def filtro_pendientes_del_dia(fecha=None) -> dict:
    inicio, fin = rango_utc_del_dia(fecha or hoy())
    return {"estado": "pendiente", "capturado_en": {"$gte": inicio, "$lt": fin}}


def pendientes_del_dia(fecha=None) -> list[dict]:
    return mongo.find(
        filtro_pendientes_del_dia(fecha),
        orden=ORDEN_PENDIENTES,
        operacion="READ · pendientes del día",
    )


def listar_por_estado(estado: str, limite: int = 100) -> list[dict]:
    return mongo.find(
        {"estado": estado},
        orden={"capturado_en": -1},
        limite=limite,
        operacion=f"READ · recepciones {estado}",
    )


def obtener(uuid: str) -> dict | None:
    return mongo.find_one({"_id": uuid}, operacion="READ · detalle de recepción")


def explicar(filtro: dict, orden: dict) -> dict:
    """READ · Plan de consulta (explain) resumido."""
    crudo = mongo.explain_find(filtro, orden, operacion="READ · explain (plan de consulta)")
    resumen = mongo.resumir_plan(crudo)
    resumen["filtro"] = mongo.a_mongosh(filtro, compacto=True)
    resumen["orden"] = mongo.a_mongosh(orden, compacto=True)
    return resumen


def conteo_por_estado() -> dict:
    filas = mongo.aggregate(
        [{"$group": {"_id": "$estado", "total": {"$sum": 1}}}],
        operacion="READ · conteo por estado",
    )
    conteo = {e: 0 for e in ESTADOS}
    for fila in filas:
        conteo[fila["_id"]] = fila["total"]
    conteo["total"] = sum(conteo[e] for e in ESTADOS)
    return conteo


# =====================================================================
# UPDATE · solo recepciones pendientes ($set con filtro estado: pendiente)
# =====================================================================
def corregir_linea(uuid: str, indice: int, peso_kg=None, precio_kg=None):
    cambios = {}
    if peso_kg is not None:
        cambios[f"lineas.{indice}.peso_kg"] = peso_kg
    if precio_kg is not None:
        cambios[f"lineas.{indice}.precio_kg"] = precio_kg
    return mongo.update_one(
        {"_id": uuid, "estado": "pendiente"},
        {"$set": cambios},
        operacion="UPDATE · corregir peso/precio de una línea",
    )


def agregar_atributo(uuid: str, indice: int, clave: str, valor):
    """R2 · Agrega un atributo nuevo a una línea sin cambiar el esquema."""
    return mongo.update_one(
        {"_id": uuid, "estado": "pendiente"},
        {"$set": {f"lineas.{indice}.atributos.{clave}": valor}},
        operacion="UPDATE · R2 · agregar atributo",
    )


def rechazar(uuid: str, motivo: str):
    """UPDATE · Rechazar: cambia el estado en MongoDB; PostgreSQL no se toca."""
    return mongo.update_one(
        {"_id": uuid, "estado": "pendiente"},
        {"$set": {"estado": "rechazada", "motivo_rechazo": motivo}},
        operacion="UPDATE · rechazar recepción",
    )


def marcar_validada(uuid: str, id_compra: int, validado_en: datetime | None = None):
    """UPDATE · R3 · Tras el COMMIT en PostgreSQL: estado validada + id_compra."""
    return mongo.update_one(
        {"_id": uuid, "estado": "pendiente"},
        {"$set": {"estado": "validada", "id_compra": id_compra, "validado_en": validado_en or timezone.now()}},
        operacion="UPDATE · R3 · marcar validada",
    )


def reconciliar_validada(uuid: str, id_compra: int):
    """UPDATE · R3 · PostgreSQL es la fuente oficial: si ya existe la compra
    y MongoDB quedó desfasado, se alinea el estado a validada."""
    return mongo.update_one(
        {"_id": uuid, "estado": {"$ne": "validada"}},
        {"$set": {"estado": "validada", "id_compra": id_compra, "validado_en": timezone.now()}},
        operacion="UPDATE · R3 · reconciliar con PostgreSQL",
    )


def desfasar_demo(uuid: str):
    """UPDATE (demo) · Simula que MongoDB no alcanzó a marcar la recepción
    (la compra ya existe en PostgreSQL pero el documento sigue pendiente)."""
    return mongo.update_one(
        {"_id": uuid, "estado": "validada"},
        {"$set": {"estado": "pendiente"}, "$unset": {"id_compra": "", "validado_en": ""}},
        operacion="UPDATE (demo) · simular desfase MongoDB",
    )


# =====================================================================
# DELETE · solo pendiente o rechazada (captura errónea).
# Una validada ya tiene compra oficial: el filtro impide borrarla.
# =====================================================================
def eliminar(uuid: str):
    return mongo.delete_one(
        {"_id": uuid, "estado": {"$in": ["pendiente", "rechazada"]}},
        operacion="DELETE · eliminar recepción",
    )

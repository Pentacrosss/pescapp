"""
Creación de los esquemas de ambos motores.

- PostgreSQL: ejecuta los scripts de db/postgres (01, 02, 03). No hay
  migraciones de Django: el esquema lo definen los scripts SQL.
- MongoDB: crea la colección recepciones_muelle con su validador
  $jsonSchema y sus dos índices (mismo contenido que
  db/mongo/script_final_mongo.js).
"""
from __future__ import annotations

import time

from django.conf import settings
from django.db import connection, transaction
from django.db.utils import OperationalError

from core.bd import mongo, pg

RUTA_SQL = settings.BASE_DIR / "db" / "postgres"
SCRIPTS_SQL = ["01_schema.sql", "02_triggers.sql", "03_funciones_vistas.sql"]

PATRON_UUID = "^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"

_NUMERO_POSITIVO = {"bsonType": "number", "minimum": 0, "exclusiveMinimum": True}
_ENTERO = {"bsonType": ["int", "long"]}

# ---------------------------------------------------------------------
# Validador $jsonSchema de recepciones_muelle
# "atributos" es un objeto SIN esquema fijo: ahí está la flexibilidad (R2)
# ---------------------------------------------------------------------
VALIDADOR_RECEPCIONES = {
    "$jsonSchema": {
        "bsonType": "object",
        "title": "Recepción en muelle (registro provisional)",
        "required": ["_id", "id_usuario", "id_proveedor", "capturado_en", "estado", "lineas"],
        "properties": {
            "_id": {
                "bsonType": "string",
                "pattern": PATRON_UUID,
                "description": "UUID generado en el dispositivo",
            },
            "id_usuario": _ENTERO,
            "id_proveedor": _ENTERO,
            "capturado_en": {"bsonType": "date"},
            "sincronizado_en": {"bsonType": "date"},
            "estado": {"enum": ["pendiente", "validada", "rechazada"]},
            "lineas": {
                "bsonType": "array",
                "minItems": 1,
                "items": {
                    "bsonType": "object",
                    "required": ["id_producto", "especie", "peso_kg", "precio_kg", "atributos"],
                    "properties": {
                        "id_producto": _ENTERO,
                        "especie": {"bsonType": "string", "minLength": 1},
                        "peso_kg": _NUMERO_POSITIVO,
                        "precio_kg": _NUMERO_POSITIVO,
                        "atributos": {
                            "bsonType": "object",
                            "description": "Atributos propios de cada especie, sin esquema fijo",
                        },
                    },
                },
            },
            "observaciones": {"bsonType": ["string", "null"]},
            "reenvios": {"bsonType": ["int", "long"], "minimum": 0},
            "validado_en": {"bsonType": "date"},
            "id_compra": _ENTERO,
            "motivo_rechazo": {"bsonType": "string"},
        },
    }
}

INDICES_RECEPCIONES = [
    # Pendientes del día: igualdad por estado + rango por capturado_en
    ("estado_1_capturado_en_1", [("estado", 1), ("capturado_en", 1)]),
    # Historial por proveedor, lo más reciente primero
    ("id_proveedor_1_capturado_en_-1", [("id_proveedor", 1), ("capturado_en", -1)]),
]


# ---------------------------------------------------------------------
# PostgreSQL
# ---------------------------------------------------------------------
def aplicar_esquema_postgres() -> None:
    with transaction.atomic():
        for nombre in SCRIPTS_SQL:
            texto = (RUTA_SQL / nombre).read_text(encoding="utf-8")
            pg.ejecutar_script(texto, nombre)


def existe_esquema_postgres() -> bool:
    with connection.cursor() as cur:
        cur.execute("SELECT to_regclass('public.cierre_diario') IS NOT NULL")
        return bool(cur.fetchone()[0])


# ---------------------------------------------------------------------
# MongoDB
# ---------------------------------------------------------------------
def crear_coleccion_mongo() -> None:
    base = mongo.bd()
    base.drop_collection(mongo.COLECCION)
    base.create_collection(
        mongo.COLECCION,
        validator=VALIDADOR_RECEPCIONES,
        validationLevel="strict",
        validationAction="error",
    )
    col = base[mongo.COLECCION]
    for nombre, claves in INDICES_RECEPCIONES:
        col.create_index(claves, name=nombre)


def existe_coleccion_mongo() -> bool:
    return mongo.COLECCION in mongo.bd().list_collection_names()


def info_coleccion() -> dict:
    """Validador e índices tal como los reporta el motor (para la defensa)."""
    respuesta = mongo._ejecutar(
        "listCollections",
        f'db.getCollectionInfos({{ name: "{mongo.COLECCION}" }})',
        lambda: list(mongo.bd().list_collections(filter={"name": mongo.COLECCION})),
        lambda r: f"{len(r)} colección(es)",
    )
    opciones = respuesta[0].get("options", {}) if respuesta else {}
    indices = mongo._ejecutar(
        "getIndexes",
        f"db.{mongo.COLECCION}.getIndexes()",
        lambda: list(mongo.coleccion().list_indexes()),
        lambda r: f"{len(r)} índice(s)",
    )
    return {
        "validador": opciones.get("validator"),
        "nivel": opciones.get("validationLevel"),
        "accion": opciones.get("validationAction"),
        "indices": [{"nombre": i["name"], "claves": dict(i["key"])} for i in indices],
    }


# ---------------------------------------------------------------------
# Espera de servicios (arranque con Docker)
# ---------------------------------------------------------------------
def esperar_bases(segundos: int = 90, salida=print) -> None:
    limite = time.monotonic() + segundos
    while True:
        try:
            connection.ensure_connection()
            break
        except OperationalError as exc:
            if time.monotonic() > limite:
                raise
            salida(f"Esperando PostgreSQL... ({str(exc).splitlines()[0]})")
            time.sleep(2)
    while True:
        try:
            mongo.cliente().admin.command("ping")
            break
        except Exception as exc:  # noqa: BLE001
            if time.monotonic() > limite:
                raise
            salida(f"Esperando MongoDB... ({type(exc).__name__})")
            time.sleep(2)

"""
Acceso a MongoDB con pymongo.

Cada comando se ejecuta a través de estas funciones, que lo anotan en el
panel "Consulta ejecutada" en sintaxis mongosh (JSON) junto con el
resultado devuelto por el motor (matched_count, modified_count,
upserted_id, deleted_count...) o el error del motor.
"""
from __future__ import annotations

import json
import re
import threading
import time
from datetime import datetime, timezone as dt_timezone
from decimal import Decimal

from django.conf import settings
from pymongo import MongoClient
from pymongo.errors import OperationFailure, PyMongoError, WriteError

from core import consultas
from core.consultas import MOTOR_MONGO

COLECCION = "recepciones_muelle"

_cliente: MongoClient | None = None
_candado = threading.Lock()


def cliente() -> MongoClient:
    global _cliente
    if _cliente is None:
        with _candado:
            if _cliente is None:
                _cliente = MongoClient(
                    settings.MONGO_URI,
                    tz_aware=True,
                    serverSelectionTimeoutMS=5000,
                )
    return _cliente


def bd():
    return cliente()[settings.MONGO_DB]


def coleccion():
    return bd()[COLECCION]


# ---------------------------------------------------------------------
# Formato mongosh
# ---------------------------------------------------------------------
_MARCA = "@@ISODATE@@"


def _json_default(obj):
    if isinstance(obj, datetime):
        if obj.tzinfo is None:
            obj = obj.replace(tzinfo=dt_timezone.utc)
        iso = obj.astimezone(dt_timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        return f"{_MARCA}{iso}{_MARCA}"
    if isinstance(obj, Decimal):
        return float(obj)
    return str(obj)


def a_mongosh(obj, compacto: bool = False) -> str:
    """JSON legible con fechas como ISODate("...")."""
    texto = json.dumps(
        obj,
        ensure_ascii=False,
        indent=None if compacto else 2,
        default=_json_default,
    )
    return re.sub(rf'"{_MARCA}(.*?){_MARCA}"', r'ISODate("\1")', texto)


def _arg(obj) -> str:
    """Argumento de comando: compacto si es corto, indentado si es largo."""
    compacto = a_mongosh(obj, compacto=True)
    if len(compacto) <= 90:
        return compacto
    return a_mongosh(obj).replace("\n", "\n  ")


def _comando(metodo: str, *args: str) -> str:
    en_linea = ", ".join(args)
    if "\n" not in en_linea and len(en_linea) <= 90:
        return f"db.{COLECCION}.{metodo}({en_linea})"
    cuerpo = ",\n  ".join(args)
    return f"db.{COLECCION}.{metodo}(\n  {cuerpo}\n)"


# ---------------------------------------------------------------------
# Errores del motor
# ---------------------------------------------------------------------
def _reglas_incumplidas(info, ruta="") -> list[str]:
    """Recorre errInfo del validador $jsonSchema y resume qué regla falló."""
    salida: list[str] = []
    if isinstance(info, dict):
        nombre = info.get("propertyName")
        nueva_ruta = f"{ruta}.{nombre}" if (ruta and nombre) else (nombre or ruta)
        operador = info.get("operatorName")
        hijos = [v for v in info.values() if isinstance(v, (dict, list))]
        if operador and not hijos:
            salida.append(f"{nueva_ruta or '(documento)'}: {operador}")
        for v in hijos:
            salida.extend(_reglas_incumplidas(v, nueva_ruta))
        if operador and hijos and not salida:
            salida.append(f"{nueva_ruta or '(documento)'}: {operador}")
    elif isinstance(info, list):
        for v in info:
            salida.extend(_reglas_incumplidas(v, ruta))
    return salida


def describir_error(exc: BaseException) -> dict:
    if isinstance(exc, (WriteError, OperationFailure)):
        detalles = exc.details or {}
        mensaje = detalles.get("errmsg", str(exc))
        texto = f"{type(exc).__name__} (code {exc.code}): {mensaje}"
        reglas: list[str] = []
        err_info = detalles.get("errInfo")
        if err_info:
            reglas = list(dict.fromkeys(_reglas_incumplidas(err_info)))
            if reglas:
                texto += "\nReglas incumplidas: " + "; ".join(reglas)
            texto += "\nerrInfo: " + a_mongosh(err_info)
        return {"codigo": exc.code, "mensaje": mensaje, "reglas": reglas, "texto": texto}
    return {"codigo": None, "mensaje": str(exc), "reglas": [], "texto": f"{type(exc).__name__}: {exc}"}


def mensaje_motor(exc: BaseException) -> str:
    d = describir_error(exc)
    texto = d["mensaje"]
    if d["reglas"]:
        texto += " · " + "; ".join(d["reglas"][:3])
    return texto


# ---------------------------------------------------------------------
# Ejecución registrada
# ---------------------------------------------------------------------
def _ejecutar(operacion: str, texto: str, fn, resumen):
    inicio = time.perf_counter()
    try:
        respuesta = fn()
    except PyMongoError as exc:
        consultas.registrar(
            MOTOR_MONGO,
            operacion,
            texto,
            tiempo_ms=(time.perf_counter() - inicio) * 1000,
            error=describir_error(exc)["texto"],
        )
        raise
    consultas.registrar(
        MOTOR_MONGO,
        operacion,
        texto,
        tiempo_ms=(time.perf_counter() - inicio) * 1000,
        resultado=resumen(respuesta),
    )
    return respuesta


def _orden_pymongo(orden: dict | None):
    return list(orden.items()) if orden else None


def insert_one(documento: dict, *, operacion: str = "insertOne"):
    return _ejecutar(
        operacion,
        _comando("insertOne", _arg(documento)),
        lambda: coleccion().insert_one(documento),
        lambda r: f"{{ acknowledged: true, inserted_id: {json.dumps(r.inserted_id, default=str)} }}",
    )


def update_one(filtro: dict, cambios: dict, *, upsert: bool = False, operacion: str = "updateOne"):
    args = [_arg(filtro), _arg(cambios)]
    if upsert:
        args.append("{ upsert: true }")
    return _ejecutar(
        operacion,
        _comando("updateOne", *args),
        lambda: coleccion().update_one(filtro, cambios, upsert=upsert),
        lambda r: (
            f"{{ matched_count: {r.matched_count}, modified_count: {r.modified_count}, "
            f"upserted_id: {json.dumps(r.upserted_id, default=str)} }}"
        ),
    )


def delete_one(filtro: dict, *, operacion: str = "deleteOne"):
    return _ejecutar(
        operacion,
        _comando("deleteOne", _arg(filtro)),
        lambda: coleccion().delete_one(filtro),
        lambda r: f"{{ acknowledged: true, deleted_count: {r.deleted_count} }}",
    )


def find(
    filtro: dict,
    *,
    proyeccion: dict | None = None,
    orden: dict | None = None,
    limite: int = 0,
    operacion: str = "find",
) -> list[dict]:
    args = [_arg(filtro)]
    if proyeccion:
        args.append(_arg(proyeccion))
    texto = _comando("find", *args)
    if orden:
        texto += f".sort({a_mongosh(orden, compacto=True)})"
    if limite:
        texto += f".limit({limite})"

    def ejecutar():
        cursor = coleccion().find(filtro, proyeccion)
        if orden:
            cursor = cursor.sort(_orden_pymongo(orden))
        if limite:
            cursor = cursor.limit(limite)
        return list(cursor)

    return _ejecutar(operacion, texto, ejecutar, lambda r: f"{len(r)} documento(s) devuelto(s)")


def find_one(filtro: dict, *, proyeccion: dict | None = None, operacion: str = "findOne"):
    args = [_arg(filtro)]
    if proyeccion:
        args.append(_arg(proyeccion))
    return _ejecutar(
        operacion,
        _comando("findOne", *args),
        lambda: coleccion().find_one(filtro, proyeccion),
        lambda r: "1 documento devuelto" if r else "null (no existe)",
    )


def count_documents(filtro: dict, *, operacion: str = "countDocuments") -> int:
    return _ejecutar(
        operacion,
        _comando("countDocuments", _arg(filtro)),
        lambda: coleccion().count_documents(filtro),
        lambda r: f"{r}",
    )


def aggregate(pipeline: list[dict], *, operacion: str = "aggregate") -> list[dict]:
    return _ejecutar(
        operacion,
        _comando("aggregate", a_mongosh(pipeline).replace("\n", "\n  ")),
        lambda: list(coleccion().aggregate(pipeline)),
        lambda r: f"{len(r)} documento(s) devuelto(s) · {a_mongosh(r, compacto=True)[:300]}",
    )


def explain_find(filtro: dict, orden: dict | None = None, *, operacion: str = "explain") -> dict:
    """Plan de ejecución de un find() con estadísticas (executionStats)."""
    comando = {"find": COLECCION, "filter": filtro}
    if orden:
        comando["sort"] = orden
    texto = _comando("find", _arg(filtro))
    if orden:
        texto += f".sort({a_mongosh(orden, compacto=True)})"
    texto += '.explain("executionStats")'
    return _ejecutar(
        operacion,
        texto,
        lambda: bd().command("explain", comando, verbosity="executionStats"),
        lambda r: "Plan: " + resumir_plan(r)["etapas_texto"],
    )


# ---------------------------------------------------------------------
# Resumen del plan de consulta
# ---------------------------------------------------------------------
def _recorrer_plan(nodo: dict, etapas: list[dict]) -> None:
    if not isinstance(nodo, dict):
        return
    if "queryPlan" in nodo:  # formato del motor SBE (MongoDB 7)
        _recorrer_plan(nodo["queryPlan"], etapas)
        return
    if "stage" in nodo:
        etapas.append(
            {
                "stage": nodo["stage"],
                "indice": nodo.get("indexName"),
                "limites": nodo.get("indexBounds"),
            }
        )
    if "inputStage" in nodo:
        _recorrer_plan(nodo["inputStage"], etapas)
    for hijo in nodo.get("inputStages", []):
        _recorrer_plan(hijo, etapas)


def resumir_plan(explain: dict) -> dict:
    planificador = explain.get("queryPlanner", {})
    etapas: list[dict] = []
    _recorrer_plan(planificador.get("winningPlan", {}), etapas)
    stats = explain.get("executionStats", {})
    indice = next((e["indice"] for e in etapas if e["indice"]), None)
    return {
        "etapas": etapas,
        "etapas_texto": " → ".join(
            e["stage"] + (f" ({e['indice']})" if e["indice"] else "") for e in etapas
        ),
        "usa_indice": any(e["stage"] == "IXSCAN" for e in etapas),
        "indice": indice,
        "limites": next((e["limites"] for e in etapas if e["limites"]), None),
        "n_devueltos": stats.get("nReturned"),
        "claves_examinadas": stats.get("totalKeysExamined"),
        "docs_examinados": stats.get("totalDocsExamined"),
        "tiempo_ms": stats.get("executionTimeMillis"),
        "planes_rechazados": len(planificador.get("rejectedPlans", [])),
    }

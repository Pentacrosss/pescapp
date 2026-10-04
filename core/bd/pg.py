"""
Acceso a PostgreSQL con SQL explícito y parámetros.

Usa la conexión de Django (django.db.connection, psycopg 3). Las 12
tablas de negocio NO usan el ORM: cada repositorio escribe su SQL y lo
ejecuta con estas funciones, que además lo anotan en el panel
"Consulta ejecutada" (sentencia, parámetros, sentencia final enviada,
tiempo, filas o error devuelto por el motor).
"""
from __future__ import annotations

import json
import re
import textwrap
import time
import uuid
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal

import psycopg
from django.db import connection, transaction

from core import consultas
from core.consultas import MOTOR_PG


# ---------------------------------------------------------------------
# Utilidades de formato
# ---------------------------------------------------------------------
def limpiar_sql(sql: str) -> str:
    return textwrap.dedent(sql).strip()


def _a_json(valor):
    if isinstance(valor, Decimal):
        return str(valor)
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()
    if isinstance(valor, uuid.UUID):
        return str(valor)
    return valor


def _formatear_parametros(params) -> str | None:
    if params is None:
        return None
    if isinstance(params, dict):
        datos = {k: _a_json(v) for k, v in params.items()}
    else:
        datos = [_a_json(v) for v in params]
    return json.dumps(datos, ensure_ascii=False, default=str)


def _fila_json(fila: dict) -> str:
    return json.dumps({k: _a_json(v) for k, v in fila.items()}, ensure_ascii=False, default=str)


def _operacion_por_defecto(sql: str) -> str:
    texto = sql.lstrip().upper()
    m = re.match(r"(INSERT INTO|UPDATE|DELETE FROM)\s+(\w+)", texto)
    if m:
        return f"{m.group(1).split()[0]} {m.group(2).lower()}"
    m = re.search(r"\bFROM\s+(\w+)", texto)
    if texto.startswith("SELECT") and m:
        return f"SELECT {m.group(1).lower()}"
    return texto.split()[0] if texto else "SQL"


def _sentencia_final(cursor, sql: str, params) -> str | None:
    """Sentencia tal como se envía al motor (parámetros ya enlazados)."""
    if params is None:
        return None
    try:
        return cursor.cursor.mogrify(sql, params)
    except Exception:  # pragma: no cover - solo informativo
        return None


# ---------------------------------------------------------------------
# Errores del motor
# ---------------------------------------------------------------------
def error_psycopg(exc: BaseException) -> psycopg.Error | None:
    if isinstance(exc, psycopg.Error):
        return exc
    causa = exc.__cause__
    return causa if isinstance(causa, psycopg.Error) else None


def describir_error(exc: BaseException) -> dict:
    """Mensaje real devuelto por PostgreSQL (sqlstate, detalle, contexto)."""
    pe = error_psycopg(exc)
    if pe is not None and pe.diag is not None and pe.diag.message_primary:
        d = pe.diag
        sqlstate = d.sqlstate or pe.sqlstate
        partes = [f"ERROR {sqlstate}: {d.message_primary}"]
        if d.message_detail:
            partes.append(f"DETAIL: {d.message_detail}")
        if d.message_hint:
            partes.append(f"HINT: {d.message_hint}")
        if d.context:
            partes.append(f"CONTEXT: {d.context}")
        return {
            "sqlstate": sqlstate,
            "mensaje": d.message_primary,
            "detalle": d.message_detail,
            "pista": d.message_hint,
            "restriccion": d.constraint_name,
            "texto": "\n".join(partes),
        }
    return {
        "sqlstate": None,
        "mensaje": str(exc),
        "detalle": None,
        "pista": None,
        "restriccion": None,
        "texto": f"{type(exc).__name__}: {exc}",
    }


def mensaje_motor(exc: BaseException) -> str:
    """Una línea con el mensaje del motor, para alertas."""
    d = describir_error(exc)
    texto = d["mensaje"]
    if d["detalle"]:
        texto += f" — {d['detalle']}"
    return texto


# ---------------------------------------------------------------------
# Ejecución registrada
# ---------------------------------------------------------------------
def _ejecutar(sql: str, params, operacion: str | None):
    sql = limpiar_sql(sql)
    operacion = operacion or _operacion_por_defecto(sql)
    with connection.cursor() as cur:
        final = _sentencia_final(cur, sql, params)
        inicio = time.perf_counter()
        try:
            cur.execute(sql, params)
            filas: list[dict] = []
            if cur.description is not None:
                columnas = [c.name for c in cur.description]
                filas = [dict(zip(columnas, f)) for f in cur.fetchall()]
            afectadas = cur.rowcount
        except Exception as exc:
            consultas.registrar(
                MOTOR_PG,
                operacion,
                sql,
                parametros=_formatear_parametros(params),
                sentencia_final=final,
                tiempo_ms=(time.perf_counter() - inicio) * 1000,
                error=describir_error(exc)["texto"],
            )
            raise
        tiempo_ms = (time.perf_counter() - inicio) * 1000

    es_lectura = sql.lstrip().upper().startswith(("SELECT", "WITH"))
    if es_lectura:
        resultado = f"{len(filas)} fila(s) devuelta(s)"
        if len(filas) == 1:
            resultado += f" · {_fila_json(filas[0])}"
    else:
        resultado = f"{afectadas} fila(s) afectada(s)"
        if filas:
            resultado += f" · RETURNING {_fila_json(filas[0])}"
    consultas.registrar(
        MOTOR_PG,
        operacion,
        sql,
        parametros=_formatear_parametros(params),
        sentencia_final=final,
        tiempo_ms=tiempo_ms,
        resultado=resultado,
    )
    return filas, afectadas


def consultar(sql: str, params=None, *, operacion: str | None = None) -> list[dict]:
    """SELECT que devuelve varias filas (lista de diccionarios)."""
    filas, _ = _ejecutar(sql, params, operacion)
    return filas


def consultar_uno(sql: str, params=None, *, operacion: str | None = None) -> dict | None:
    """SELECT o DML con RETURNING que devuelve una fila."""
    filas, _ = _ejecutar(sql, params, operacion)
    return filas[0] if filas else None


def ejecutar(sql: str, params=None, *, operacion: str | None = None) -> int:
    """INSERT/UPDATE/DELETE; devuelve filas afectadas."""
    _, afectadas = _ejecutar(sql, params, operacion)
    return afectadas


def ejecutar_script(texto: str, nombre: str) -> None:
    """Ejecuta un archivo .sql completo (sin parámetros)."""
    inicio = time.perf_counter()
    with connection.cursor() as cur:
        cur.execute(texto)
    consultas.registrar(
        MOTOR_PG,
        f"SCRIPT {nombre}",
        f"\\i {nombre}",
        tiempo_ms=(time.perf_counter() - inicio) * 1000,
        resultado="Script ejecutado",
    )


# ---------------------------------------------------------------------
# Transacciones: todo o nada (transaction.atomic) con BEGIN/COMMIT/
# ROLLBACK visibles en el panel.
# ---------------------------------------------------------------------
@contextmanager
def transaccion(nombre: str):
    consultas.registrar(MOTOR_PG, "BEGIN", f"BEGIN;  -- {nombre}", resultado="Transacción iniciada")
    inicio = time.perf_counter()
    try:
        with transaction.atomic():
            yield
    except Exception as exc:
        consultas.registrar(
            MOTOR_PG,
            "ROLLBACK",
            f"ROLLBACK;  -- {nombre}",
            tiempo_ms=(time.perf_counter() - inicio) * 1000,
            resultado="Transacción revertida: no quedó ningún cambio",
            error=describir_error(exc)["texto"],
        )
        raise
    consultas.registrar(
        MOTOR_PG,
        "COMMIT",
        f"COMMIT;  -- {nombre}",
        tiempo_ms=(time.perf_counter() - inicio) * 1000,
        resultado="Transacción confirmada",
    )

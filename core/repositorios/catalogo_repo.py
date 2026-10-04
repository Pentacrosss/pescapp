"""
Repositorio PostgreSQL · Catálogo.

CRUD completo de producto (SQL explícito con parámetros) y altas/listados
de proveedor y cliente. Las restricciones las hace cumplir el motor:
UNIQUE (id_especie, presentacion) y las claves foráneas de los detalles.
"""
from __future__ import annotations

from core.bd import pg


# =====================================================================
# READ · usuarios y especies
# =====================================================================
def listar_usuarios() -> list[dict]:
    return pg.consultar(
        """
        SELECT id_usuario, nombre, rol, estado
          FROM usuario
         ORDER BY id_usuario
        """,
        operacion="READ usuario",
    )


def listar_especies() -> list[dict]:
    return pg.consultar(
        """
        SELECT id_especie, nombre_comun, categoria
          FROM especie
         ORDER BY nombre_comun
        """,
        operacion="READ especie",
    )


# =====================================================================
# PRODUCTOS · CRUD
# =====================================================================

# ---------------------------------------------------------------------
# CREATE · producto (INSERT ... RETURNING). Si se repite especie +
# presentación, el UNIQUE del motor lo rechaza.
# ---------------------------------------------------------------------
def crear_producto(id_especie: int, presentacion: str, unidad: str) -> dict:
    return pg.consultar_uno(
        """
        INSERT INTO producto (id_especie, presentacion, unidad)
        VALUES (%(id_especie)s, %(presentacion)s, %(unidad)s)
        RETURNING id_producto, id_especie, presentacion, unidad
        """,
        {"id_especie": id_especie, "presentacion": presentacion, "unidad": unidad},
        operacion="CREATE producto",
    )


# ---------------------------------------------------------------------
# READ · productos con su especie y cuántas veces aparecen en compras y
# ventas (JOIN especie + subconsultas sobre los detalles)
# ---------------------------------------------------------------------
def listar_productos() -> list[dict]:
    return pg.consultar(
        """
        SELECT p.id_producto,
               p.id_especie,
               e.nombre_comun AS especie,
               e.categoria,
               p.presentacion,
               p.unidad,
               (SELECT COUNT(*) FROM detalle_compra dc
                 WHERE dc.id_producto = p.id_producto) AS veces_comprado,
               (SELECT COUNT(*) FROM detalle_venta dv
                 WHERE dv.id_producto = p.id_producto) AS veces_vendido
          FROM producto p
          JOIN especie e ON e.id_especie = p.id_especie
         ORDER BY e.nombre_comun, p.presentacion
        """,
        operacion="READ producto JOIN especie",
    )


def obtener_producto(id_producto: int) -> dict | None:
    return pg.consultar_uno(
        """
        SELECT p.id_producto, p.id_especie, e.nombre_comun AS especie,
               p.presentacion, p.unidad
          FROM producto p
          JOIN especie e ON e.id_especie = p.id_especie
         WHERE p.id_producto = %(id_producto)s
        """,
        {"id_producto": id_producto},
        operacion="READ producto (uno)",
    )


# ---------------------------------------------------------------------
# UPDATE · presentación y unidad
# ---------------------------------------------------------------------
def actualizar_producto(id_producto: int, presentacion: str, unidad: str) -> dict | None:
    return pg.consultar_uno(
        """
        UPDATE producto
           SET presentacion = %(presentacion)s,
               unidad       = %(unidad)s
         WHERE id_producto = %(id_producto)s
        RETURNING id_producto, presentacion, unidad
        """,
        {"id_producto": id_producto, "presentacion": presentacion, "unidad": unidad},
        operacion="UPDATE producto",
    )


# ---------------------------------------------------------------------
# DELETE · si el producto está en algún detalle_compra/detalle_venta,
# la clave foránea del motor impide borrarlo.
# ---------------------------------------------------------------------
def eliminar_producto(id_producto: int) -> int:
    return pg.ejecutar(
        """
        DELETE FROM producto
         WHERE id_producto = %(id_producto)s
        """,
        {"id_producto": id_producto},
        operacion="DELETE producto",
    )


# =====================================================================
# PROVEEDORES · listar y crear
# =====================================================================
def listar_proveedores() -> list[dict]:
    return pg.consultar(
        """
        SELECT id_proveedor, nombre, identificacion, telefono
          FROM proveedor
         ORDER BY nombre
        """,
        operacion="READ proveedor",
    )


def crear_proveedor(nombre: str, identificacion: str, telefono: str | None) -> dict:
    return pg.consultar_uno(
        """
        INSERT INTO proveedor (nombre, identificacion, telefono)
        VALUES (%(nombre)s, %(identificacion)s, %(telefono)s)
        RETURNING id_proveedor, nombre
        """,
        {"nombre": nombre, "identificacion": identificacion, "telefono": telefono or None},
        operacion="CREATE proveedor",
    )


# =====================================================================
# CLIENTES · listar y crear
# =====================================================================
def listar_clientes() -> list[dict]:
    return pg.consultar(
        """
        SELECT id_cliente, nombre, identificacion, tipo
          FROM cliente
         ORDER BY nombre
        """,
        operacion="READ cliente",
    )


def crear_cliente(nombre: str, identificacion: str, tipo: str) -> dict:
    return pg.consultar_uno(
        """
        INSERT INTO cliente (nombre, identificacion, tipo)
        VALUES (%(nombre)s, %(identificacion)s, %(tipo)s)
        RETURNING id_cliente, nombre
        """,
        {"nombre": nombre, "identificacion": identificacion, "tipo": tipo},
        operacion="CREATE cliente",
    )


# =====================================================================
# Inicio · conteo de filas de las 12 tablas
# =====================================================================
def conteo_tablas() -> dict:
    return pg.consultar_uno(
        """
        SELECT (SELECT COUNT(*) FROM usuario)        AS usuario,
               (SELECT COUNT(*) FROM proveedor)      AS proveedor,
               (SELECT COUNT(*) FROM cliente)        AS cliente,
               (SELECT COUNT(*) FROM especie)        AS especie,
               (SELECT COUNT(*) FROM producto)       AS producto,
               (SELECT COUNT(*) FROM compra)         AS compra,
               (SELECT COUNT(*) FROM detalle_compra) AS detalle_compra,
               (SELECT COUNT(*) FROM venta)          AS venta,
               (SELECT COUNT(*) FROM detalle_venta)  AS detalle_venta,
               (SELECT COUNT(*) FROM pago)           AS pago,
               (SELECT COUNT(*) FROM cobro)          AS cobro,
               (SELECT COUNT(*) FROM cierre_diario)  AS cierre_diario
        """,
        operacion="READ conteo de las 12 tablas",
    )

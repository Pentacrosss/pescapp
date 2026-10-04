"""
Repositorio PostgreSQL · Compras y pagos a proveedores.

Las compras NO se crean a mano: nacen de una recepción validada
(core/servicios/validacion.py, R3). Aquí están las sentencias que esa
transacción ejecuta y el registro de pagos.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from core.bd import pg


# =====================================================================
# R3 · CREATE compra desde una recepción (se ejecutan DENTRO de
# pg.transaccion; si una falla, ninguna queda).
# =====================================================================
def insertar_compra(id_proveedor: int, id_usuario: int, uuid_recepcion: str, fecha: date) -> int:
    fila = pg.consultar_uno(
        """
        INSERT INTO compra (id_proveedor, id_usuario, uuid_recepcion, fecha, total, estado)
        VALUES (%(id_proveedor)s, %(id_usuario)s, %(uuid_recepcion)s, %(fecha)s, 0, 'pendiente_pago')
        RETURNING id_compra
        """,
        {
            "id_proveedor": id_proveedor,
            "id_usuario": id_usuario,
            "uuid_recepcion": uuid_recepcion,
            "fecha": fecha,
        },
        operacion="R3 · INSERT compra",
    )
    return fila["id_compra"]


def insertar_detalle_compra(id_compra: int, id_producto: int, peso_kg: Decimal, precio_kg: Decimal) -> dict:
    return pg.consultar_uno(
        """
        INSERT INTO detalle_compra (id_compra, id_producto, peso_kg, precio_kg, subtotal)
        VALUES (%(id_compra)s, %(id_producto)s, %(peso_kg)s, %(precio_kg)s,
                ROUND(%(peso_kg)s::numeric * %(precio_kg)s::numeric, 2))
        RETURNING id_det_compra, subtotal
        """,
        {"id_compra": id_compra, "id_producto": id_producto, "peso_kg": peso_kg, "precio_kg": precio_kg},
        operacion="R3 · INSERT detalle_compra",
    )


def recalcular_total_compra(id_compra: int) -> Decimal:
    fila = pg.consultar_uno(
        """
        UPDATE compra
           SET total = (SELECT COALESCE(SUM(d.subtotal), 0)
                          FROM detalle_compra d
                         WHERE d.id_compra = %(id_compra)s)
         WHERE id_compra = %(id_compra)s
        RETURNING total
        """,
        {"id_compra": id_compra},
        operacion="R3 · UPDATE compra.total = Σ subtotales",
    )
    return fila["total"]


# =====================================================================
# READ
# =====================================================================
def buscar_compra_por_uuid(uuid_recepcion: str) -> dict | None:
    return pg.consultar_uno(
        """
        SELECT id_compra, fecha, total, estado
          FROM compra
         WHERE uuid_recepcion = %(uuid)s
        """,
        {"uuid": uuid_recepcion},
        operacion="READ compra por uuid_recepcion",
    )


def listar_compras(limite: int = 200) -> list[dict]:
    return pg.consultar(
        """
        SELECT c.id_compra, c.fecha, c.total, c.estado, c.uuid_recepcion,
               p.nombre AS proveedor,
               COALESCE(SUM(pa.monto), 0)           AS pagado,
               c.total - COALESCE(SUM(pa.monto), 0) AS saldo
          FROM compra c
          JOIN proveedor p ON p.id_proveedor = c.id_proveedor
          LEFT JOIN pago pa ON pa.id_compra = c.id_compra
         GROUP BY c.id_compra, p.nombre
         ORDER BY c.fecha DESC, c.id_compra DESC
         LIMIT %(limite)s
        """,
        {"limite": limite},
        operacion="READ compra + pagos",
    )


def obtener_compra(id_compra: int) -> dict | None:
    return pg.consultar_uno(
        """
        SELECT c.id_compra, c.fecha, c.total, c.estado, c.uuid_recepcion,
               c.id_proveedor, p.nombre AS proveedor, u.nombre AS usuario,
               COALESCE((SELECT SUM(pa.monto) FROM pago pa
                          WHERE pa.id_compra = c.id_compra), 0) AS pagado,
               EXISTS (SELECT 1 FROM cierre_diario cd
                        WHERE cd.fecha = c.fecha)              AS dia_cerrado
          FROM compra c
          JOIN proveedor p ON p.id_proveedor = c.id_proveedor
          JOIN usuario   u ON u.id_usuario   = c.id_usuario
         WHERE c.id_compra = %(id_compra)s
        """,
        {"id_compra": id_compra},
        operacion="READ compra (una)",
    )


def detalle_de_compra(id_compra: int) -> list[dict]:
    return pg.consultar(
        """
        SELECT d.id_det_compra, d.id_producto, e.nombre_comun AS especie,
               pr.presentacion, d.peso_kg, d.precio_kg, d.subtotal
          FROM detalle_compra d
          JOIN producto pr ON pr.id_producto = d.id_producto
          JOIN especie  e  ON e.id_especie   = pr.id_especie
         WHERE d.id_compra = %(id_compra)s
         ORDER BY d.id_det_compra
        """,
        {"id_compra": id_compra},
        operacion="READ detalle_compra",
    )


def pagos_de_compra(id_compra: int) -> list[dict]:
    return pg.consultar(
        """
        SELECT id_pago, fecha, monto, metodo
          FROM pago
         WHERE id_compra = %(id_compra)s
         ORDER BY fecha, id_pago
        """,
        {"id_compra": id_compra},
        operacion="READ pago",
    )


# =====================================================================
# CREATE · Pago a proveedor (transacción). El trigger trg_pago_saldo
# rechaza un pago mayor que el saldo; al completarse, estado = pagada.
# =====================================================================
def registrar_pago(id_compra: int, fecha: date, monto: Decimal, metodo: str) -> dict:
    with pg.transaccion("Registrar pago a proveedor"):
        pago = pg.consultar_uno(
            """
            INSERT INTO pago (id_compra, fecha, monto, metodo)
            VALUES (%(id_compra)s, %(fecha)s, %(monto)s, %(metodo)s)
            RETURNING id_pago
            """,
            {"id_compra": id_compra, "fecha": fecha, "monto": monto, "metodo": metodo},
            operacion="CREATE pago",
        )
        estado = pg.consultar_uno(
            """
            UPDATE compra
               SET estado = 'pagada'
             WHERE id_compra = %(id_compra)s
               AND estado = 'pendiente_pago'
               AND total <= (SELECT COALESCE(SUM(p.monto), 0)
                               FROM pago p
                              WHERE p.id_compra = %(id_compra)s)
            RETURNING estado
            """,
            {"id_compra": id_compra},
            operacion="UPDATE compra.estado si quedó pagada",
        )
    return {"id_pago": pago["id_pago"], "pagada": estado is not None}

"""
Repositorio PostgreSQL · Ventas y cobros (R4).

Una venta se registra en UNA transacción: cabecera, detalles, total
calculado por el motor como Σ subtotales y, si se indica, un cobro
inicial parcial. El trigger trg_cobro_saldo rechaza cobros mayores que
el saldo y trg_venta_dia_cerrado rechaza ventas en días cerrados.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from core.bd import pg


# =====================================================================
# CREATE · R4 · Registrar venta (todo o nada)
#   lineas: [{"id_producto": int, "peso_kg": Decimal, "precio_kg": Decimal}]
#   cobro_inicial: Decimal | None (permite cobro parcial)
# =====================================================================
def registrar_venta(
    id_cliente: int,
    id_usuario: int,
    fecha: date,
    lineas: list[dict],
    cobro_inicial: Decimal | None = None,
    metodo_cobro: str = "efectivo",
    *,
    nombre_transaccion: str = "R4 · Registrar venta",
) -> dict:
    with pg.transaccion(nombre_transaccion):
        venta = pg.consultar_uno(
            """
            INSERT INTO venta (id_cliente, id_usuario, fecha, total, estado)
            VALUES (%(id_cliente)s, %(id_usuario)s, %(fecha)s, 0, 'pendiente_cobro')
            RETURNING id_venta
            """,
            {"id_cliente": id_cliente, "id_usuario": id_usuario, "fecha": fecha},
            operacion="R4 · INSERT venta",
        )
        id_venta = venta["id_venta"]

        for linea in lineas:
            pg.consultar_uno(
                """
                INSERT INTO detalle_venta (id_venta, id_producto, peso_kg, precio_kg, subtotal)
                VALUES (%(id_venta)s, %(id_producto)s, %(peso_kg)s, %(precio_kg)s,
                        ROUND(%(peso_kg)s::numeric * %(precio_kg)s::numeric, 2))
                RETURNING id_det_venta, subtotal
                """,
                {
                    "id_venta": id_venta,
                    "id_producto": linea["id_producto"],
                    "peso_kg": linea["peso_kg"],
                    "precio_kg": linea["precio_kg"],
                },
                operacion="R4 · INSERT detalle_venta",
            )

        total = pg.consultar_uno(
            """
            UPDATE venta
               SET total = (SELECT COALESCE(SUM(d.subtotal), 0)
                              FROM detalle_venta d
                             WHERE d.id_venta = %(id_venta)s)
             WHERE id_venta = %(id_venta)s
            RETURNING total
            """,
            {"id_venta": id_venta},
            operacion="R4 · UPDATE venta.total = Σ subtotales",
        )["total"]

        estado = "pendiente_cobro"
        if cobro_inicial and cobro_inicial > 0:
            _insertar_cobro(id_venta, fecha, cobro_inicial, metodo_cobro)
            if _actualizar_estado_venta(id_venta):
                estado = "cobrada"

    return {"id_venta": id_venta, "total": total, "estado": estado}


# =====================================================================
# CREATE · R4 · Cobro posterior (transacción)
# =====================================================================
def registrar_cobro(id_venta: int, fecha: date, monto: Decimal, metodo: str) -> dict:
    with pg.transaccion("R4 · Registrar cobro"):
        id_cobro = _insertar_cobro(id_venta, fecha, monto, metodo)
        cobrada = _actualizar_estado_venta(id_venta)
    return {"id_cobro": id_cobro, "cobrada": cobrada}


def _insertar_cobro(id_venta: int, fecha: date, monto: Decimal, metodo: str) -> int:
    fila = pg.consultar_uno(
        """
        INSERT INTO cobro (id_venta, fecha, monto, metodo)
        VALUES (%(id_venta)s, %(fecha)s, %(monto)s, %(metodo)s)
        RETURNING id_cobro
        """,
        {"id_venta": id_venta, "fecha": fecha, "monto": monto, "metodo": metodo},
        operacion="CREATE cobro",
    )
    return fila["id_cobro"]


def _actualizar_estado_venta(id_venta: int) -> bool:
    """Cuando los cobros alcanzan el total: estado = cobrada."""
    fila = pg.consultar_uno(
        """
        UPDATE venta
           SET estado = 'cobrada'
         WHERE id_venta = %(id_venta)s
           AND estado = 'pendiente_cobro'
           AND total <= (SELECT COALESCE(SUM(c.monto), 0)
                           FROM cobro c
                          WHERE c.id_venta = %(id_venta)s)
        RETURNING estado
        """,
        {"id_venta": id_venta},
        operacion="UPDATE venta.estado si quedó cobrada",
    )
    return fila is not None


# =====================================================================
# READ
# =====================================================================
def listar_ventas(limite: int = 200) -> list[dict]:
    return pg.consultar(
        """
        SELECT v.id_venta, v.fecha, v.total, v.estado,
               cl.nombre AS cliente,
               COALESCE(SUM(c.monto), 0)           AS cobrado,
               v.total - COALESCE(SUM(c.monto), 0) AS saldo
          FROM venta v
          JOIN cliente cl ON cl.id_cliente = v.id_cliente
          LEFT JOIN cobro c ON c.id_venta = v.id_venta
         GROUP BY v.id_venta, cl.nombre
         ORDER BY v.fecha DESC, v.id_venta DESC
         LIMIT %(limite)s
        """,
        {"limite": limite},
        operacion="READ venta + cobros",
    )


def obtener_venta(id_venta: int) -> dict | None:
    return pg.consultar_uno(
        """
        SELECT v.id_venta, v.fecha, v.total, v.estado, v.id_cliente,
               cl.nombre AS cliente, u.nombre AS usuario,
               COALESCE((SELECT SUM(c.monto) FROM cobro c
                          WHERE c.id_venta = v.id_venta), 0) AS cobrado
          FROM venta v
          JOIN cliente cl ON cl.id_cliente = v.id_cliente
          JOIN usuario u  ON u.id_usuario  = v.id_usuario
         WHERE v.id_venta = %(id_venta)s
        """,
        {"id_venta": id_venta},
        operacion="READ venta (una)",
    )


def detalle_de_venta(id_venta: int) -> list[dict]:
    return pg.consultar(
        """
        SELECT d.id_det_venta, d.id_producto, e.nombre_comun AS especie,
               pr.presentacion, d.peso_kg, d.precio_kg, d.subtotal
          FROM detalle_venta d
          JOIN producto pr ON pr.id_producto = d.id_producto
          JOIN especie  e  ON e.id_especie   = pr.id_especie
         WHERE d.id_venta = %(id_venta)s
         ORDER BY d.id_det_venta
        """,
        {"id_venta": id_venta},
        operacion="READ detalle_venta",
    )


def cobros_de_venta(id_venta: int) -> list[dict]:
    return pg.consultar(
        """
        SELECT id_cobro, fecha, monto, metodo
          FROM cobro
         WHERE id_venta = %(id_venta)s
         ORDER BY fecha, id_cobro
        """,
        {"id_venta": id_venta},
        operacion="READ cobro",
    )


# READ · R4 · El total cuadra con el detalle
def cuadre_venta(id_venta: int) -> dict:
    return pg.consultar_uno(
        """
        SELECT v.total,
               COALESCE(SUM(d.subtotal), 0)             AS suma_detalle,
               v.total = COALESCE(SUM(d.subtotal), 0)   AS cuadra
          FROM venta v
          LEFT JOIN detalle_venta d ON d.id_venta = v.id_venta
         WHERE v.id_venta = %(id_venta)s
         GROUP BY v.id_venta
        """,
        {"id_venta": id_venta},
        operacion="READ cuadre total vs Σ detalle",
    )


# =====================================================================
# READ · R5 · Saldos con el valor oficial del momento (vistas)
# =====================================================================
def saldos_clientes() -> list[dict]:
    return pg.consultar(
        """
        SELECT id_cliente, nombre, identificacion, tipo,
               total_vendido, total_cobrado, saldo_pendiente
          FROM v_saldo_cliente
         ORDER BY saldo_pendiente DESC, nombre
        """,
        operacion="R5 · READ v_saldo_cliente",
    )


def saldo_cliente(id_cliente: int) -> dict | None:
    return pg.consultar_uno(
        """
        SELECT id_cliente, nombre, identificacion, tipo,
               total_vendido, total_cobrado, saldo_pendiente
          FROM v_saldo_cliente
         WHERE id_cliente = %(id_cliente)s
        """,
        {"id_cliente": id_cliente},
        operacion="R5 · READ v_saldo_cliente (uno)",
    )


def ventas_de_cliente(id_cliente: int) -> list[dict]:
    return pg.consultar(
        """
        SELECT v.id_venta, v.fecha, v.total, v.estado,
               COALESCE(SUM(c.monto), 0)           AS cobrado,
               v.total - COALESCE(SUM(c.monto), 0) AS saldo
          FROM venta v
          LEFT JOIN cobro c ON c.id_venta = v.id_venta
         WHERE v.id_cliente = %(id_cliente)s
         GROUP BY v.id_venta
         ORDER BY v.fecha DESC, v.id_venta DESC
        """,
        {"id_cliente": id_cliente},
        operacion="R5 · READ ventas del cliente",
    )


def saldos_proveedores() -> list[dict]:
    return pg.consultar(
        """
        SELECT id_proveedor, nombre, identificacion,
               total_comprado, total_pagado, saldo_pendiente
          FROM v_saldo_proveedor
         ORDER BY saldo_pendiente DESC, nombre
        """,
        operacion="R5 · READ v_saldo_proveedor",
    )


def saldo_proveedor(id_proveedor: int) -> dict | None:
    return pg.consultar_uno(
        """
        SELECT id_proveedor, nombre, identificacion,
               total_comprado, total_pagado, saldo_pendiente
          FROM v_saldo_proveedor
         WHERE id_proveedor = %(id_proveedor)s
        """,
        {"id_proveedor": id_proveedor},
        operacion="R5 · READ v_saldo_proveedor (uno)",
    )


def compras_de_proveedor(id_proveedor: int) -> list[dict]:
    return pg.consultar(
        """
        SELECT c.id_compra, c.fecha, c.total, c.estado, c.uuid_recepcion,
               COALESCE(SUM(p.monto), 0)           AS pagado,
               c.total - COALESCE(SUM(p.monto), 0) AS saldo
          FROM compra c
          LEFT JOIN pago p ON p.id_compra = c.id_compra
         WHERE c.id_proveedor = %(id_proveedor)s
         GROUP BY c.id_compra
         ORDER BY c.fecha DESC, c.id_compra DESC
        """,
        {"id_proveedor": id_proveedor},
        operacion="R5 · READ compras del proveedor",
    )

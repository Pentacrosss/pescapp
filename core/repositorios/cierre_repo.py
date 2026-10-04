"""
Repositorio PostgreSQL · Cierre diario (R6).

El cierre lo calcula y lo inserta la función emitir_cierre() del motor.
Un segundo cierre de la misma fecha falla por cierre_diario.fecha UNIQUE
y el trigger fn_bloquear_dia_cerrado impide modificar lo cerrado.
"""
from __future__ import annotations

from datetime import date

from core.bd import pg


# =====================================================================
# CREATE · R6 · Emitir cierre (función del motor)
# =====================================================================
def emitir_cierre(fecha: date, id_usuario: int) -> dict:
    return pg.consultar_uno(
        """
        SELECT * FROM emitir_cierre(%(fecha)s, %(id_usuario)s)
        """,
        {"fecha": fecha, "id_usuario": id_usuario},
        operacion="R6 · SELECT emitir_cierre()",
    )


# =====================================================================
# READ
# =====================================================================
def listar_cierres() -> list[dict]:
    return pg.consultar(
        """
        SELECT cd.id_cierre, cd.fecha, cd.total_compras, cd.total_ventas,
               cd.diferencia, u.nombre AS usuario
          FROM cierre_diario cd
          JOIN usuario u ON u.id_usuario = cd.id_usuario
         ORDER BY cd.fecha DESC
        """,
        operacion="READ cierre_diario",
    )


def movimientos_por_fecha() -> list[dict]:
    """Fechas con compras o ventas y si ya tienen cierre (vista previa)."""
    return pg.consultar(
        """
        SELECT t.fecha, t.total_compras, t.total_ventas,
               t.total_ventas - t.total_compras AS diferencia,
               EXISTS (SELECT 1 FROM cierre_diario cd
                        WHERE cd.fecha = t.fecha) AS cerrado
          FROM (SELECT f.fecha,
                       (SELECT COALESCE(SUM(c.total), 0) FROM compra c
                         WHERE c.fecha = f.fecha AND c.estado <> 'anulada') AS total_compras,
                       (SELECT COALESCE(SUM(v.total), 0) FROM venta v
                         WHERE v.fecha = f.fecha AND v.estado <> 'anulada')  AS total_ventas
                  FROM (SELECT fecha FROM compra
                        UNION
                        SELECT fecha FROM venta) f) t
         ORDER BY t.fecha DESC
        """,
        operacion="READ movimientos por fecha",
    )


def fecha_sugerida() -> date | None:
    """Primera fecha con movimientos que aún no tiene cierre."""
    fila = pg.consultar_uno(
        """
        SELECT MIN(f.fecha) AS fecha
          FROM (SELECT fecha FROM compra
                UNION
                SELECT fecha FROM venta) f
         WHERE NOT EXISTS (SELECT 1 FROM cierre_diario cd WHERE cd.fecha = f.fecha)
        """,
        operacion="READ primera fecha sin cierre",
    )
    return fila["fecha"] if fila else None


def ultima_fecha_cerrada() -> date | None:
    fila = pg.consultar_uno(
        """
        SELECT MAX(fecha) AS fecha FROM cierre_diario
        """,
        operacion="READ última fecha cerrada",
    )
    return fila["fecha"] if fila else None

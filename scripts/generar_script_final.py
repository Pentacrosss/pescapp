#!/usr/bin/env python
"""
Genera db/postgres/script_final_postgres.sql (anexo técnico del examen)
uniendo 01_schema.sql, 02_triggers.sql y 03_funciones_vistas.sql, más un
apéndice comentado con las sentencias de las operaciones clave tal como
las ejecuta la aplicación.

Uso:  python scripts/generar_script_final.py
"""
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CARPETA = RAIZ / "db" / "postgres"
PARTES = ["01_schema.sql", "02_triggers.sql", "03_funciones_vistas.sql"]

ENCABEZADO = """\
-- #####################################################################
-- pescAPP · Script final PostgreSQL 16 (anexo técnico · Momento 2)
-- Tópicos Avanzados de Bases de Datos
--
-- Contenido:
--   Parte 1 · 01_schema.sql           12 tablas + índices
--   Parte 2 · 02_triggers.sql         fn_bloquear_dia_cerrado (R6) y
--                                     validación de saldo de cobros/pagos
--   Parte 3 · 03_funciones_vistas.sql emitir_cierre() (R6),
--                                     v_saldo_proveedor y v_saldo_cliente (R5)
--   Apéndice · sentencias de las operaciones clave (comentadas)
--
-- Ejecución:  psql -U pescapp -d pescapp -f script_final_postgres.sql
-- Archivo GENERADO por scripts/generar_script_final.py: edite las partes.
-- #####################################################################

"""

APENDICE = """\

-- #####################################################################
-- Apéndice · Operaciones clave tal como las ejecuta la aplicación
-- (los valores entre %(...)s son parámetros enlazados por psycopg 3)
-- #####################################################################

-- R3 · Validación transaccional: una recepción de MongoDB -> compra oficial
-- BEGIN;
--   INSERT INTO compra (id_proveedor, id_usuario, uuid_recepcion, fecha, total, estado)
--   VALUES (%(id_proveedor)s, %(id_usuario)s, %(uuid_recepcion)s, %(fecha)s, 0, 'pendiente_pago')
--   RETURNING id_compra;
--   INSERT INTO detalle_compra (id_compra, id_producto, peso_kg, precio_kg, subtotal)
--   VALUES (%(id_compra)s, %(id_producto)s, %(peso_kg)s, %(precio_kg)s,
--           ROUND(%(peso_kg)s::numeric * %(precio_kg)s::numeric, 2))
--   RETURNING id_det_compra, subtotal;            -- una por línea
--   UPDATE compra
--      SET total = (SELECT COALESCE(SUM(d.subtotal), 0)
--                     FROM detalle_compra d WHERE d.id_compra = %(id_compra)s)
--    WHERE id_compra = %(id_compra)s
--   RETURNING total;
-- COMMIT;
-- Reintentar con el mismo uuid_recepcion ->
--   ERROR 23505: duplicate key value violates unique constraint "compra_uuid_recepcion_key"

-- R4 · Venta con cobro inicial parcial (una transacción)
-- BEGIN;
--   INSERT INTO venta (id_cliente, id_usuario, fecha, total, estado)
--   VALUES (%(id_cliente)s, %(id_usuario)s, %(fecha)s, 0, 'pendiente_cobro') RETURNING id_venta;
--   INSERT INTO detalle_venta (...) VALUES (..., ROUND(peso * precio, 2));   -- por línea
--   UPDATE venta SET total = (SELECT SUM(subtotal) FROM detalle_venta WHERE id_venta = ...)
--    WHERE id_venta = ... RETURNING total;
--   INSERT INTO cobro (id_venta, fecha, monto, metodo) VALUES (...) RETURNING id_cobro;
--   UPDATE venta SET estado = 'cobrada'
--    WHERE id_venta = ... AND estado = 'pendiente_cobro'
--      AND total <= (SELECT COALESCE(SUM(monto), 0) FROM cobro WHERE id_venta = ...);
-- COMMIT;

-- R4 · El total cuadra con el detalle
-- SELECT v.total, SUM(d.subtotal) AS suma_detalle, v.total = SUM(d.subtotal) AS cuadra
--   FROM venta v JOIN detalle_venta d USING (id_venta)
--  WHERE v.id_venta = 1 GROUP BY v.id_venta;

-- R5 · Saldo pendiente con el valor oficial del momento
-- SELECT * FROM v_saldo_cliente   WHERE id_cliente   = 2;
-- SELECT * FROM v_saldo_proveedor WHERE id_proveedor = 2;

-- R6 · Emitir el cierre del día y comprobar el bloqueo
-- SELECT * FROM emitir_cierre(CURRENT_DATE - 1, 1);
-- SELECT * FROM emitir_cierre(CURRENT_DATE - 1, 1);   -- ERROR 23505 (fecha UNIQUE)
-- INSERT INTO venta (id_cliente, id_usuario, fecha, total, estado)
-- VALUES (1, 1, CURRENT_DATE - 1, 0, 'pendiente_cobro');
--   -> ERROR P0001: Día cerrado: el dd/mm/aaaa ya tiene cierre emitido (cierre #n).
--      No se puede insertar en la tabla venta.
"""


def main() -> None:
    partes = []
    for i, nombre in enumerate(PARTES, start=1):
        texto = (CARPETA / nombre).read_text(encoding="utf-8").rstrip() + "\n"
        partes.append(f"\n-- =====================================================================\n"
                      f"-- Parte {i} · {nombre}\n"
                      f"-- =====================================================================\n\n{texto}")
    destino = CARPETA / "script_final_postgres.sql"
    destino.write_text(ENCABEZADO + "".join(partes) + APENDICE, encoding="utf-8", newline="\n")
    print(f"Generado {destino.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()

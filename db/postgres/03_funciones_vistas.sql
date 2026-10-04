-- =====================================================================
-- pescAPP · PostgreSQL 16 · 03_funciones_vistas.sql
--   R6 · emitir_cierre(p_fecha, p_id_usuario)
--   R5 · v_saldo_proveedor y v_saldo_cliente (valor oficial del momento)
-- =====================================================================

-- ---------------------------------------------------------------------
-- R6 · Emitir el cierre del día
-- Suma compras y ventas no anuladas de la fecha, inserta el cierre con
-- diferencia = total_ventas - total_compras y devuelve la fila.
-- Un segundo cierre de la misma fecha falla por cierre_diario.fecha UNIQUE.
-- ---------------------------------------------------------------------
DROP FUNCTION IF EXISTS emitir_cierre(DATE, INT);

CREATE FUNCTION emitir_cierre(p_fecha DATE, p_id_usuario INT)
RETURNS cierre_diario
LANGUAGE plpgsql AS $$
DECLARE
    v_total_compras  NUMERIC(12,2);
    v_total_ventas   NUMERIC(12,2);
    v_cierre         cierre_diario;
BEGIN
    SELECT COALESCE(SUM(c.total), 0) INTO v_total_compras
      FROM compra c
     WHERE c.fecha = p_fecha AND c.estado <> 'anulada';

    SELECT COALESCE(SUM(v.total), 0) INTO v_total_ventas
      FROM venta v
     WHERE v.fecha = p_fecha AND v.estado <> 'anulada';

    INSERT INTO cierre_diario (id_usuario, fecha, total_compras, total_ventas, diferencia)
    VALUES (p_id_usuario, p_fecha, v_total_compras, v_total_ventas,
            v_total_ventas - v_total_compras)
    RETURNING * INTO v_cierre;

    RETURN v_cierre;
END;
$$;

-- ---------------------------------------------------------------------
-- R5 · Saldo pendiente por proveedor
-- total comprado (no anulado) - pagos realizados sobre esas compras
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW v_saldo_proveedor AS
SELECT p.id_proveedor,
       p.nombre,
       p.identificacion,
       COALESCE(c.total_comprado, 0)                              AS total_comprado,
       COALESCE(pg.total_pagado, 0)                               AS total_pagado,
       COALESCE(c.total_comprado, 0) - COALESCE(pg.total_pagado, 0) AS saldo_pendiente
  FROM proveedor p
  LEFT JOIN (SELECT co.id_proveedor, SUM(co.total) AS total_comprado
               FROM compra co
              WHERE co.estado <> 'anulada'
              GROUP BY co.id_proveedor) c  ON c.id_proveedor = p.id_proveedor
  LEFT JOIN (SELECT co.id_proveedor, SUM(pa.monto) AS total_pagado
               FROM pago pa
               JOIN compra co ON co.id_compra = pa.id_compra
              WHERE co.estado <> 'anulada'
              GROUP BY co.id_proveedor) pg ON pg.id_proveedor = p.id_proveedor;

-- ---------------------------------------------------------------------
-- R5 · Saldo pendiente por cliente
-- total vendido (no anulado) - cobros recibidos sobre esas ventas
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW v_saldo_cliente AS
SELECT cl.id_cliente,
       cl.nombre,
       cl.identificacion,
       cl.tipo,
       COALESCE(v.total_vendido, 0)                               AS total_vendido,
       COALESCE(cb.total_cobrado, 0)                              AS total_cobrado,
       COALESCE(v.total_vendido, 0) - COALESCE(cb.total_cobrado, 0) AS saldo_pendiente
  FROM cliente cl
  LEFT JOIN (SELECT ve.id_cliente, SUM(ve.total) AS total_vendido
               FROM venta ve
              WHERE ve.estado <> 'anulada'
              GROUP BY ve.id_cliente) v  ON v.id_cliente = cl.id_cliente
  LEFT JOIN (SELECT ve.id_cliente, SUM(co.monto) AS total_cobrado
               FROM cobro co
               JOIN venta ve ON ve.id_venta = co.id_venta
              WHERE ve.estado <> 'anulada'
              GROUP BY ve.id_cliente) cb ON cb.id_cliente = cl.id_cliente;

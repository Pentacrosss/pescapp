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


-- =====================================================================
-- Parte 1 · 01_schema.sql
-- =====================================================================

-- =====================================================================
-- pescAPP · PostgreSQL 16 · 01_schema.sql
-- Núcleo oficial: 12 tablas de negocio + índices.
-- El script es re-ejecutable: primero elimina los objetos si existen.
-- =====================================================================

SET client_min_messages = warning;

DROP VIEW  IF EXISTS v_saldo_cliente   CASCADE;
DROP VIEW  IF EXISTS v_saldo_proveedor CASCADE;
DROP TABLE IF EXISTS cierre_diario   CASCADE;
DROP TABLE IF EXISTS cobro           CASCADE;
DROP TABLE IF EXISTS pago            CASCADE;
DROP TABLE IF EXISTS detalle_venta   CASCADE;
DROP TABLE IF EXISTS venta           CASCADE;
DROP TABLE IF EXISTS detalle_compra  CASCADE;
DROP TABLE IF EXISTS compra          CASCADE;
DROP TABLE IF EXISTS producto        CASCADE;
DROP TABLE IF EXISTS especie         CASCADE;
DROP TABLE IF EXISTS cliente         CASCADE;
DROP TABLE IF EXISTS proveedor       CASCADE;
DROP TABLE IF EXISTS usuario         CASCADE;

-- ---------------------------------------------------------------------
-- Catálogos
-- ---------------------------------------------------------------------
CREATE TABLE usuario (
    id_usuario SERIAL PRIMARY KEY, nombre VARCHAR(120) NOT NULL,
    rol VARCHAR(20) NOT NULL,      -- administrador | vendedor | auxiliar
    estado VARCHAR(15) NOT NULL);

CREATE TABLE proveedor (
    id_proveedor SERIAL PRIMARY KEY, nombre VARCHAR(140) NOT NULL,
    identificacion VARCHAR(13) NOT NULL UNIQUE, telefono VARCHAR(20));

CREATE TABLE cliente (
    id_cliente SERIAL PRIMARY KEY, nombre VARCHAR(140) NOT NULL,
    identificacion VARCHAR(13) NOT NULL UNIQUE,
    tipo VARCHAR(15) NOT NULL);    -- minorista | mayorista

CREATE TABLE especie (
    id_especie SERIAL PRIMARY KEY, nombre_comun VARCHAR(80) NOT NULL UNIQUE,
    categoria VARCHAR(30) NOT NULL);  -- pescado | crustáceo | molusco

CREATE TABLE producto (
    id_producto SERIAL PRIMARY KEY,
    id_especie INTEGER NOT NULL REFERENCES especie (id_especie),
    presentacion VARCHAR(40) NOT NULL, unidad VARCHAR(10) NOT NULL DEFAULT 'kg',
    UNIQUE (id_especie, presentacion));

-- ---------------------------------------------------------------------
-- Compras (nacen de una recepción validada en MongoDB)
-- uuid_recepcion UNIQUE: una recepción no se contabiliza dos veces (R3)
-- ---------------------------------------------------------------------
CREATE TABLE compra (
    id_compra SERIAL PRIMARY KEY,
    id_proveedor INTEGER NOT NULL REFERENCES proveedor (id_proveedor),
    id_usuario INTEGER NOT NULL REFERENCES usuario (id_usuario),
    uuid_recepcion UUID NOT NULL UNIQUE,
    fecha DATE NOT NULL, total NUMERIC(12,2) NOT NULL CHECK (total >= 0),
    estado VARCHAR(15) NOT NULL);  -- pendiente_pago | pagada | anulada

CREATE TABLE detalle_compra (
    id_det_compra SERIAL PRIMARY KEY,
    id_compra INTEGER NOT NULL REFERENCES compra (id_compra),
    id_producto INTEGER NOT NULL REFERENCES producto (id_producto),
    peso_kg NUMERIC(10,2) NOT NULL CHECK (peso_kg > 0),
    precio_kg NUMERIC(10,2) NOT NULL CHECK (precio_kg > 0),
    subtotal NUMERIC(12,2) NOT NULL);

-- ---------------------------------------------------------------------
-- Ventas (R4)
-- ---------------------------------------------------------------------
CREATE TABLE venta (
    id_venta SERIAL PRIMARY KEY,
    id_cliente INTEGER NOT NULL REFERENCES cliente (id_cliente),
    id_usuario INTEGER NOT NULL REFERENCES usuario (id_usuario),
    fecha DATE NOT NULL, total NUMERIC(12,2) NOT NULL CHECK (total >= 0),
    estado VARCHAR(15) NOT NULL);  -- pendiente_cobro | cobrada | anulada

CREATE TABLE detalle_venta (
    id_det_venta SERIAL PRIMARY KEY,
    id_venta INTEGER NOT NULL REFERENCES venta (id_venta),
    id_producto INTEGER NOT NULL REFERENCES producto (id_producto),
    peso_kg NUMERIC(10,2) NOT NULL CHECK (peso_kg > 0),
    precio_kg NUMERIC(10,2) NOT NULL CHECK (precio_kg > 0),
    subtotal NUMERIC(12,2) NOT NULL);

-- ---------------------------------------------------------------------
-- Pagos a proveedores y cobros a clientes (R4, R5)
-- ---------------------------------------------------------------------
CREATE TABLE pago (
    id_pago SERIAL PRIMARY KEY,
    id_compra INTEGER NOT NULL REFERENCES compra (id_compra),
    fecha DATE NOT NULL, monto NUMERIC(12,2) NOT NULL CHECK (monto > 0),
    metodo VARCHAR(20) NOT NULL);  -- efectivo | transferencia

CREATE TABLE cobro (
    id_cobro SERIAL PRIMARY KEY,
    id_venta INTEGER NOT NULL REFERENCES venta (id_venta),
    fecha DATE NOT NULL, monto NUMERIC(12,2) NOT NULL CHECK (monto > 0),
    metodo VARCHAR(20) NOT NULL);

-- ---------------------------------------------------------------------
-- Cierre diario (R6): fecha UNIQUE, un solo cierre por día
-- ---------------------------------------------------------------------
CREATE TABLE cierre_diario (
    id_cierre SERIAL PRIMARY KEY,
    id_usuario INTEGER NOT NULL REFERENCES usuario (id_usuario),
    fecha DATE NOT NULL UNIQUE,
    total_compras NUMERIC(12,2) NOT NULL, total_ventas NUMERIC(12,2) NOT NULL,
    diferencia NUMERIC(12,2) NOT NULL);

-- ---------------------------------------------------------------------
-- Índices de consulta frecuente (saldos por persona y fecha)
-- ---------------------------------------------------------------------
CREATE INDEX idx_compra_proveedor ON compra (id_proveedor, fecha);
CREATE INDEX idx_venta_cliente    ON venta (id_cliente, fecha);
CREATE INDEX idx_pago_compra      ON pago (id_compra);
CREATE INDEX idx_cobro_venta      ON cobro (id_venta);

-- =====================================================================
-- Parte 2 · 02_triggers.sql
-- =====================================================================

-- =====================================================================
-- pescAPP · PostgreSQL 16 · 02_triggers.sql
-- Reglas que protege la base de datos (no la aplicación):
--   R6 · fn_bloquear_dia_cerrado: lo cerrado no puede modificarse.
--   R4 · fn_validar_saldo_cobro / fn_validar_saldo_pago: no se cobra ni
--        se paga más que el saldo pendiente.
-- =====================================================================

-- ---------------------------------------------------------------------
-- R6 · Trigger fn_bloquear_dia_cerrado
-- BEFORE INSERT/UPDATE/DELETE en compra, venta, pago, cobro y en los
-- detalles (estos verifican la fecha de su cabecera).
-- Si existe cierre_diario para la fecha afectada, RAISE EXCEPTION.
--
-- Única excepción controlada: marcar como 'pagada' o 'cobrada' una
-- compra/venta de un día cerrado cuando NINGUNA otra columna cambia.
-- Liquidar una deuda vieja hoy no altera los totales de aquel cierre;
-- el pago o cobro se registra con su propia fecha (abierta).
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_bloquear_dia_cerrado() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_fechas  DATE[] := ARRAY[]::DATE[];
    v_fecha   DATE;
    v_cierre  INTEGER;
    v_accion  TEXT;
BEGIN
    -- Excepción controlada: solo cambia el estado a pagada/cobrada.
    -- (IF anidado + to_jsonb: los detalles, pagos y cobros no tienen
    --  columna estado y PL/pgSQL no admite NEW.estado en esas tablas.)
    IF TG_OP = 'UPDATE' AND TG_TABLE_NAME IN ('compra', 'venta') THEN
        IF (to_jsonb(NEW) - 'estado') = (to_jsonb(OLD) - 'estado')
           AND to_jsonb(NEW) ->> 'estado' IN ('pagada', 'cobrada') THEN
            RETURN NEW;
        END IF;
    END IF;

    -- Fechas afectadas por la operación
    IF TG_TABLE_NAME IN ('compra', 'venta', 'pago', 'cobro') THEN
        IF TG_OP IN ('UPDATE', 'DELETE') THEN v_fechas := v_fechas || OLD.fecha; END IF;
        IF TG_OP IN ('INSERT', 'UPDATE') THEN v_fechas := v_fechas || NEW.fecha; END IF;
    ELSIF TG_TABLE_NAME = 'detalle_compra' THEN
        IF TG_OP IN ('UPDATE', 'DELETE') THEN
            v_fechas := v_fechas || (SELECT c.fecha FROM compra c WHERE c.id_compra = OLD.id_compra);
        END IF;
        IF TG_OP IN ('INSERT', 'UPDATE') THEN
            v_fechas := v_fechas || (SELECT c.fecha FROM compra c WHERE c.id_compra = NEW.id_compra);
        END IF;
    ELSIF TG_TABLE_NAME = 'detalle_venta' THEN
        IF TG_OP IN ('UPDATE', 'DELETE') THEN
            v_fechas := v_fechas || (SELECT v.fecha FROM venta v WHERE v.id_venta = OLD.id_venta);
        END IF;
        IF TG_OP IN ('INSERT', 'UPDATE') THEN
            v_fechas := v_fechas || (SELECT v.fecha FROM venta v WHERE v.id_venta = NEW.id_venta);
        END IF;
    END IF;

    v_accion := CASE TG_OP WHEN 'INSERT' THEN 'insertar en'
                           WHEN 'UPDATE' THEN 'modificar'
                           ELSE 'eliminar de' END;

    FOREACH v_fecha IN ARRAY v_fechas LOOP
        SELECT cd.id_cierre INTO v_cierre FROM cierre_diario cd WHERE cd.fecha = v_fecha;
        IF FOUND THEN
            RAISE EXCEPTION 'Día cerrado: el % ya tiene cierre emitido (cierre #%). No se puede % la tabla %.',
                to_char(v_fecha, 'DD/MM/YYYY'), v_cierre, v_accion, TG_TABLE_NAME
                USING ERRCODE = 'P0001',
                      HINT = 'R6: lo cerrado no puede modificarse. Registre el movimiento en una fecha abierta.';
        END IF;
    END LOOP;

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_compra_dia_cerrado
    BEFORE INSERT OR UPDATE OR DELETE ON compra
    FOR EACH ROW EXECUTE FUNCTION fn_bloquear_dia_cerrado();

CREATE TRIGGER trg_venta_dia_cerrado
    BEFORE INSERT OR UPDATE OR DELETE ON venta
    FOR EACH ROW EXECUTE FUNCTION fn_bloquear_dia_cerrado();

CREATE TRIGGER trg_pago_dia_cerrado
    BEFORE INSERT OR UPDATE OR DELETE ON pago
    FOR EACH ROW EXECUTE FUNCTION fn_bloquear_dia_cerrado();

CREATE TRIGGER trg_cobro_dia_cerrado
    BEFORE INSERT OR UPDATE OR DELETE ON cobro
    FOR EACH ROW EXECUTE FUNCTION fn_bloquear_dia_cerrado();

CREATE TRIGGER trg_detalle_compra_dia_cerrado
    BEFORE INSERT OR UPDATE OR DELETE ON detalle_compra
    FOR EACH ROW EXECUTE FUNCTION fn_bloquear_dia_cerrado();

CREATE TRIGGER trg_detalle_venta_dia_cerrado
    BEFORE INSERT OR UPDATE OR DELETE ON detalle_venta
    FOR EACH ROW EXECUTE FUNCTION fn_bloquear_dia_cerrado();

-- ---------------------------------------------------------------------
-- R4 · Un cobro no puede superar el saldo pendiente de la venta.
-- Bloquea la fila de la venta (FOR UPDATE) para que dos cobros
-- simultáneos no pasen ambos la verificación.
-- (Se ejecuta después de trg_cobro_dia_cerrado: orden alfabético.)
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_validar_saldo_cobro() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_total    NUMERIC(12,2);
    v_estado   VARCHAR(15);
    v_cobrado  NUMERIC(12,2);
BEGIN
    SELECT v.total, v.estado INTO v_total, v_estado
      FROM venta v WHERE v.id_venta = NEW.id_venta FOR UPDATE;
    IF NOT FOUND THEN
        RETURN NEW;  -- la clave foránea reportará el error
    END IF;
    IF v_estado = 'anulada' THEN
        RAISE EXCEPTION 'Cobro rechazado: la venta % está anulada.', NEW.id_venta;
    END IF;

    SELECT COALESCE(SUM(c.monto), 0) INTO v_cobrado
      FROM cobro c
     WHERE c.id_venta = NEW.id_venta
       AND (TG_OP = 'INSERT' OR c.id_cobro <> NEW.id_cobro);

    IF NEW.monto > v_total - v_cobrado THEN
        RAISE EXCEPTION 'Cobro rechazado: el monto % supera el saldo pendiente % de la venta #%.',
            NEW.monto, v_total - v_cobrado, NEW.id_venta
            USING ERRCODE = 'P0001';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_cobro_saldo
    BEFORE INSERT OR UPDATE OF monto, id_venta ON cobro
    FOR EACH ROW EXECUTE FUNCTION fn_validar_saldo_cobro();

-- ---------------------------------------------------------------------
-- R5 · Un pago no puede superar el saldo pendiente de la compra.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_validar_saldo_pago() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_total   NUMERIC(12,2);
    v_estado  VARCHAR(15);
    v_pagado  NUMERIC(12,2);
BEGIN
    SELECT c.total, c.estado INTO v_total, v_estado
      FROM compra c WHERE c.id_compra = NEW.id_compra FOR UPDATE;
    IF NOT FOUND THEN
        RETURN NEW;  -- la clave foránea reportará el error
    END IF;
    IF v_estado = 'anulada' THEN
        RAISE EXCEPTION 'Pago rechazado: la compra % está anulada.', NEW.id_compra;
    END IF;

    SELECT COALESCE(SUM(p.monto), 0) INTO v_pagado
      FROM pago p
     WHERE p.id_compra = NEW.id_compra
       AND (TG_OP = 'INSERT' OR p.id_pago <> NEW.id_pago);

    IF NEW.monto > v_total - v_pagado THEN
        RAISE EXCEPTION 'Pago rechazado: el monto % supera el saldo pendiente % de la compra #%.',
            NEW.monto, v_total - v_pagado, NEW.id_compra
            USING ERRCODE = 'P0001';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_pago_saldo
    BEFORE INSERT OR UPDATE OF monto, id_compra ON pago
    FOR EACH ROW EXECUTE FUNCTION fn_validar_saldo_pago();

-- =====================================================================
-- Parte 3 · 03_funciones_vistas.sql
-- =====================================================================

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

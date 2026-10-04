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

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

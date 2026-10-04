# Mapa CRUD · pescAPP

Cada fila dice **dónde se ve** la operación (pantalla), **dónde está** (archivo y función) y **qué se envía al motor**.
En la aplicación, el panel **«Consulta ejecutada»** muestra la misma sentencia con sus parámetros, tiempo y resultado o error.

- Las sentencias SQL viven en `core/repositorios/*_repo.py` y se ejecutan con `core/bd/pg.py` (`consultar`, `consultar_uno`, `ejecutar`, `transaccion`).
- Los comandos MongoDB viven en `core/repositorios/recepciones_repo.py` y se ejecutan con `core/bd/mongo.py` (`update_one`, `find`, `delete_one`, `explain_find`...).
- Búsqueda rápida: cada operación tiene un encabezado `# CREATE`, `# READ`, `# UPDATE`, `# DELETE`, `# R3 · ...` en el código.

## A · Muelle · MongoDB · CRUD de recepciones

| Operación | Motor | Pantalla | Archivo y función | Consulta | Req. |
|---|---|---|---|---|---|
| **CREATE** · capturar recepción (UUID en el navegador) | MongoDB | Muelle → Captura en muelle | `core/static/core/captura.js` → `construirDocumento()` (`crypto.randomUUID()`), `enviar()` | `POST /muelle/api/sincronizar/` | R1, R2 |
| **CREATE** · upsert idempotente por `_id` (paso 1) | MongoDB | Captura → Guardar / Sincronizar | [`recepciones_repo.py`](../core/repositorios/recepciones_repo.py) → `sincronizar_recepcion()` · vista [`muelle.py`](../core/views/muelle.py) → `api_sincronizar()` | `db.recepciones_muelle.updateOne({_id}, {$setOnInsert: {...}}, {upsert: true})` | R1 |
| **UPDATE** · reenvío del mismo UUID (paso 2) | MongoDB | Captura → Reenviar | `recepciones_repo.py` → `sincronizar_recepcion()` | `updateOne({_id, estado: "pendiente"}, {$set: {lineas, sincronizado_en...}, $inc: {reenvios: 1}})` + `countDocuments({})` antes/después | R1 |
| Cola sin señal | navegador | Captura → «Simular sin señal», «Sincronizar» | `captura.js` → `localStorage["pescapp_cola_sin_senal"]`, `sincronizar()` | — | R1 |
| **READ** · lista con filtros | MongoDB | Muelle → Recepciones | `recepciones_repo.py` → `construir_filtro()`, `listar()` · vista `muelle.lista()` | `find({estado?, capturado_en: {$gte, $lt}?, id_proveedor?, "lineas.especie"?}).sort({capturado_en: -1}).limit(200)` | R1 |
| **READ** · pendientes del día | MongoDB | Muelle → Pendientes del día | `recepciones_repo.py` → `filtro_pendientes_del_dia()`, `pendientes_del_dia()` · vista `muelle.pendientes()` | `find({estado: "pendiente", capturado_en: {$gte: hoy00:00, $lt: mañana00:00}}).sort({capturado_en: 1})` | R1 |
| **READ** · plan de consulta | MongoDB | Recepciones / Pendientes → «Ver plan de consulta» | `recepciones_repo.py` → `explicar()` · `mongo.py` → `explain_find()`, `resumir_plan()` | `db.runCommand({explain: {find, filter, sort}, verbosity: "executionStats"})` → `FETCH → IXSCAN (estado_1_capturado_en_1)` | R1 |
| **READ** · detalle (atributos por línea) | MongoDB | Recepción → Detalle | `recepciones_repo.py` → `obtener()` · vista `muelle.detalle()` | `findOne({_id})` | R2 |
| **READ** · conteo por estado | MongoDB | Inicio | `recepciones_repo.py` → `conteo_por_estado()` | `aggregate([{$group: {_id: "$estado", total: {$sum: 1}}}])` | — |
| **UPDATE** · corregir peso/precio | MongoDB | Detalle → «Corregir peso o precio» | `recepciones_repo.py` → `corregir_linea()` · vista `muelle.corregir_linea()` | `updateOne({_id, estado: "pendiente"}, {$set: {"lineas.N.peso_kg": x, "lineas.N.precio_kg": y}})` | R2 |
| **UPDATE** · agregar atributo nuevo | MongoDB | Detalle → «Agregar atributo nuevo» | `recepciones_repo.py` → `agregar_atributo()` · vista `muelle.agregar_atributo()` | `updateOne({_id, estado: "pendiente"}, {$set: {"lineas.N.atributos.lote": "L-0457"}})` | R2 |
| **UPDATE** · rechazar | MongoDB | Detalle → «Rechazar» | `recepciones_repo.py` → `rechazar()` · vista `muelle.rechazar()` | `updateOne({_id, estado: "pendiente"}, {$set: {estado: "rechazada", motivo_rechazo}})` (PostgreSQL no se toca) | R3 |
| **DELETE** · eliminar captura errónea | MongoDB | Detalle → «Eliminar» | `recepciones_repo.py` → `eliminar()` · vista `muelle.eliminar()` | `deleteOne({_id, estado: {$in: ["pendiente", "rechazada"]}})` → validada: `deleted_count = 0` | R1 |
| Validador `$jsonSchema` e índices | MongoDB | Muelle → Validador e índices | [`esquema.py`](../core/servicios/esquema.py) → `VALIDADOR_RECEPCIONES`, `INDICES_RECEPCIONES`, `crear_coleccion_mongo()`, `info_coleccion()` · [`script_final_mongo.js`](../db/mongo/script_final_mongo.js) | `createCollection(..., {validator})`, `createIndex(...)`, `getCollectionInfos()`, `getIndexes()` | R1, R2 |
| Prueba del validador | MongoDB | Validador e índices → «Insertar documento inválido» | `recepciones_repo.py` → `insertar_invalido_demo()` | `insertOne({estado: "aprobada", lineas: [{peso_kg: -5...}]})` → `Document failed validation` | R2 |

## B · Validación · Integración MongoDB → PostgreSQL

| Operación | Motor | Pantalla | Archivo y función | Consulta | Req. |
|---|---|---|---|---|---|
| Leer la recepción | MongoDB | Validación → «Validar» | [`servicios/validacion.py`](../core/servicios/validacion.py) → `validar_recepcion()` | `findOne({_id})` | R3 |
| **CREATE** · compra en una transacción | PostgreSQL | Validación → «Validar» / Detalle → «Validar y crear compra» | `validacion.py` → `_crear_compra()` · [`compras_repo.py`](../core/repositorios/compras_repo.py) → `insertar_compra()`, `insertar_detalle_compra()`, `recalcular_total_compra()` · [`pg.py`](../core/bd/pg.py) → `transaccion()` | `BEGIN; INSERT INTO compra (..., uuid_recepcion, fecha, total, estado) VALUES (..., 0, 'pendiente_pago') RETURNING id_compra; INSERT INTO detalle_compra (..., subtotal) VALUES (..., ROUND(peso::numeric * precio::numeric, 2)); UPDATE compra SET total = (SELECT SUM(subtotal) ...) RETURNING total; COMMIT;` | R3 |
| **UPDATE** · marcar validada | MongoDB | (después del COMMIT) | `recepciones_repo.py` → `marcar_validada()` | `updateOne({_id, estado: "pendiente"}, {$set: {estado: "validada", id_compra, validado_en}})` | R3 |
| Forzar revalidación (demo) | PostgreSQL | Validación → «Forzar revalidación (demo)» | `validacion.py` → `forzar_revalidacion()`, `_contabilizar()` | mismo `INSERT INTO compra` → `ERROR 23505 duplicate key value violates unique constraint "compra_uuid_recepcion_key"` + `ROLLBACK` | R3 |
| Reconciliar MongoDB desfasado | MongoDB | Validación → «Simular desfase» y luego «Validar» | `recepciones_repo.py` → `desfasar_demo()`, `reconciliar_validada()` · `compras_repo.buscar_compra_por_uuid()` | `SELECT id_compra FROM compra WHERE uuid_recepcion = %(uuid)s` + `updateOne({_id, estado: {$ne: "validada"}}, {$set: {estado: "validada", id_compra}})` | R3 |
| Validar en día cerrado | PostgreSQL | Validación (tras cerrar la fecha) | trigger `fn_bloquear_dia_cerrado` | `ERROR P0001: Día cerrado: ... No se puede insertar en la tabla compra.` + `ROLLBACK` | R3, R6 |

## C · Catálogo · PostgreSQL · CRUD de productos

| Operación | Motor | Pantalla | Archivo y función | Consulta | Req. |
|---|---|---|---|---|---|
| **CREATE** · producto | PostgreSQL | Catálogo → Productos → «Crear producto» | [`catalogo_repo.py`](../core/repositorios/catalogo_repo.py) → `crear_producto()` · vista [`catalogo.py`](../core/views/catalogo.py) → `productos()` | `INSERT INTO producto (id_especie, presentacion, unidad) VALUES (...) RETURNING id_producto, ...` → duplicado: `ERROR 23505 ... "producto_id_especie_presentacion_key"` | — |
| **READ** · productos | PostgreSQL | Catálogo → Productos | `catalogo_repo.py` → `listar_productos()` | `SELECT p.*, e.nombre_comun, (SELECT COUNT(*) FROM detalle_compra ...), (SELECT COUNT(*) FROM detalle_venta ...) FROM producto p JOIN especie e ...` | — |
| **UPDATE** · producto | PostgreSQL | Productos → «Editar» | `catalogo_repo.py` → `actualizar_producto()` · vista `catalogo.producto_editar()` | `UPDATE producto SET presentacion = ..., unidad = ... WHERE id_producto = ... RETURNING ...` | — |
| **DELETE** · producto | PostgreSQL | Productos → «Eliminar» | `catalogo_repo.py` → `eliminar_producto()` · vista `catalogo.producto_eliminar()` | `DELETE FROM producto WHERE id_producto = ...` → con movimientos: `ERROR 23503 ... violates foreign key constraint` | — |
| Proveedores: listar / crear | PostgreSQL | Catálogo → Proveedores | `catalogo_repo.py` → `listar_proveedores()`, `crear_proveedor()` | `SELECT ... FROM proveedor` · `INSERT INTO proveedor ... RETURNING` | — |
| Clientes: listar / crear | PostgreSQL | Catálogo → Clientes | `catalogo_repo.py` → `listar_clientes()`, `crear_cliente()` | `SELECT ... FROM cliente` · `INSERT INTO cliente ... RETURNING` | — |

## D · Ventas, cobros, pagos y saldos · PostgreSQL

| Operación | Motor | Pantalla | Archivo y función | Consulta | Req. |
|---|---|---|---|---|---|
| **CREATE** · venta + cobro inicial | PostgreSQL | Ventas y saldos → Registrar venta | [`ventas_repo.py`](../core/repositorios/ventas_repo.py) → `registrar_venta()` · vista [`ventas.py`](../core/views/ventas.py) → `nueva()` | `BEGIN; INSERT INTO venta ... RETURNING id_venta; INSERT INTO detalle_venta ... ROUND(peso*precio,2); UPDATE venta SET total = Σ subtotal RETURNING total; INSERT INTO cobro ...; UPDATE venta SET estado='cobrada' WHERE total <= Σ cobros; COMMIT;` | R4 |
| **READ** · cuadre total vs detalle | PostgreSQL | Venta → Detalle | `ventas_repo.py` → `cuadre_venta()` | `SELECT v.total, SUM(d.subtotal), v.total = SUM(d.subtotal) AS cuadra FROM venta v LEFT JOIN detalle_venta d ...` | R4 |
| **CREATE** · cobro posterior | PostgreSQL | Venta → «Registrar cobro» | `ventas_repo.py` → `registrar_cobro()` · vista `ventas.cobro()` | `INSERT INTO cobro ...` (+ trigger `trg_cobro_saldo`: `Cobro rechazado: el monto ... supera el saldo pendiente ...`) + `UPDATE venta SET estado = 'cobrada' ...` | R4 |
| **CREATE** · pago a proveedor | PostgreSQL | Compras y pagos → Detalle → «Registrar pago» | `compras_repo.py` → `registrar_pago()` · vista `ventas.pago()` | `INSERT INTO pago ...` (+ trigger `trg_pago_saldo`) + `UPDATE compra SET estado = 'pagada' WHERE total <= Σ pagos` | R5 |
| **READ** · saldos de clientes | PostgreSQL | Ventas y saldos → Saldos de clientes | `ventas_repo.py` → `saldos_clientes()`, `saldo_cliente()`, `ventas_de_cliente()` | `SELECT ... FROM v_saldo_cliente [WHERE id_cliente = ...]` | R5 |
| **READ** · saldos de proveedores | PostgreSQL | Ventas y saldos → Saldos de proveedores | `ventas_repo.py` → `saldos_proveedores()`, `saldo_proveedor()`, `compras_de_proveedor()` | `SELECT ... FROM v_saldo_proveedor [WHERE id_proveedor = ...]` | R5 |
| **READ** · ventas / compras | PostgreSQL | Ventas y cobros · Compras y pagos | `ventas_repo.listar_ventas()`, `compras_repo.listar_compras()` | `SELECT ... LEFT JOIN cobro/pago ... GROUP BY ...` | R4, R5 |

## E · Cierre diario · PostgreSQL

| Operación | Motor | Pantalla | Archivo y función | Consulta | Req. |
|---|---|---|---|---|---|
| **CREATE** · emitir cierre | PostgreSQL | Cierre diario → «Emitir cierre» | [`cierre_repo.py`](../core/repositorios/cierre_repo.py) → `emitir_cierre()` · vista [`cierre.py`](../core/views/cierre.py) → `emitir()` | `SELECT * FROM emitir_cierre(%(fecha)s, %(id_usuario)s)` → repetido: `ERROR 23505 ... "cierre_diario_fecha_key"` | R6 |
| **READ** · cierres y movimientos | PostgreSQL | Cierre diario | `cierre_repo.py` → `listar_cierres()`, `movimientos_por_fecha()` | `SELECT ... FROM cierre_diario JOIN usuario ...` | R6 |
| Venta en día cerrado (demo) | PostgreSQL | Cierre diario → «Intentar venta con esa fecha» | vista `cierre.demo_venta_dia_cerrado()` → `ventas_repo.registrar_venta()` | `INSERT INTO venta ... fecha cerrada` → `ERROR P0001: Día cerrado: el dd/mm/aaaa ya tiene cierre emitido (cierre #n). No se puede insertar en la tabla venta.` | R6 |

## Objetos de base de datos

| Objeto | Archivo | Qué hace | Req. |
|---|---|---|---|
| 12 tablas + 4 índices | [`db/postgres/01_schema.sql`](../db/postgres/01_schema.sql) | `compra.uuid_recepcion UNIQUE`, `cierre_diario.fecha UNIQUE`, CHECK de montos y pesos | R3–R6 |
| `fn_bloquear_dia_cerrado()` + 6 triggers | [`db/postgres/02_triggers.sql`](../db/postgres/02_triggers.sql) | Bloquea INSERT/UPDATE/DELETE en compra, venta, pago, cobro y detalles (por la fecha de la cabecera) si hay cierre | R6 |
| `fn_validar_saldo_cobro()` / `fn_validar_saldo_pago()` | `02_triggers.sql` | Rechazan cobros/pagos mayores que el saldo pendiente | R4, R5 |
| `emitir_cierre(p_fecha, p_id_usuario)` | [`db/postgres/03_funciones_vistas.sql`](../db/postgres/03_funciones_vistas.sql) | Suma compras y ventas no anuladas, inserta y devuelve el cierre | R6 |
| `v_saldo_proveedor`, `v_saldo_cliente` | `03_funciones_vistas.sql` | Saldo = total no anulado − pagos/cobros | R5 |
| Validador `$jsonSchema` + 2 índices | [`db/mongo/script_final_mongo.js`](../db/mongo/script_final_mongo.js) · `core/servicios/esquema.py` | `_id` UUID, tipos, `estado` enum, `lineas` ≥ 1, `atributos` sin esquema fijo | R1, R2 |

## Infraestructura del panel «Consulta ejecutada»

| Pieza | Archivo | Función |
|---|---|---|
| Registro por petición (`contextvars`) y Bitácora (50 últimas) | [`core/consultas.py`](../core/consultas.py) | `iniciar()`, `registrar()`, `guardar_accion()`, `bitacora()` |
| Middleware (POST → redirección → panel en la página siguiente) | [`core/middleware.py`](../core/middleware.py) | `ConsultasMiddleware` |
| Ejecución registrada de SQL (sentencia, parámetros, `mogrify`, tiempo, error del motor) | [`core/bd/pg.py`](../core/bd/pg.py) | `_ejecutar()`, `describir_error()`, `transaccion()` |
| Ejecución registrada de MongoDB (comando mongosh, resultado del motor) | [`core/bd/mongo.py`](../core/bd/mongo.py) | `_ejecutar()`, `describir_error()` |
| Plantilla del panel | `core/templates/core/_panel.html` · `core/static/core/panel.js` | — |

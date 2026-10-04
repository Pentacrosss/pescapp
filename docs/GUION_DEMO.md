# Guion del video · pescAPP · Momento 2 (8–10 minutos)

**Idea central que debe quedar clara:** *capturar en el muelle un registro variable y sin conexión garantizada (MongoDB, provisional) y convertirlo después en un dato contable oficial (PostgreSQL), sin pérdidas ni duplicados.*

En cada paso, **señalar el recuadro «Consulta ejecutada»**: muestra el motor, la sentencia SQL con sus parámetros o el comando MongoDB, el tiempo y el resultado o el error real del motor.

---

## Antes de grabar (2 minutos, sin cámara)

1. `docker compose up --build` y abrir <http://localhost:8000>.
2. En **Inicio**, pulsar **«Reiniciar datos de demo»**: deja 30 recepciones (8 pendientes hoy, 1 rechazada), los días −5 a −2 cerrados y el día −1 abierto. También vacía la cola local del navegador.
3. Zoom del navegador al 90 % y ventana a pantalla completa (1440 px o más).
4. **Usuario actual** (barra superior): *Administrador*.
5. Tener a mano `db/postgres/01_schema.sql` en el editor (bloque de Yandry).

Las fechas son relativas a hoy: «día −1» es ayer.

---

## Bloque 1 · Yandry Urdánigo · Núcleo PostgreSQL (0:00 – 3:00)

| Tiempo | Clic / acción | Qué decir | Qué debe verse |
|---|---|---|---|
| 0:00 | **Inicio** | «pescAPP separa dos responsabilidades: MongoDB guarda la recepción provisional del muelle y PostgreSQL es la fuente oficial. La validación las une.» | Diagrama *Muelle → Validación → Núcleo*; conteos de las 12 tablas y de `recepciones_muelle`. |
| 0:30 | Editor: `db/postgres/01_schema.sql` (tabla `compra` y `cierre_diario`) | «Las 12 tablas las crean scripts SQL, no el ORM. Tres restricciones sostienen la contabilidad: `uuid_recepcion UNIQUE`, `cierre_diario.fecha UNIQUE` y los `CHECK` de montos y pesos.» | `uuid_recepcion UUID NOT NULL UNIQUE`, `fecha DATE NOT NULL UNIQUE`. |
| 1:00 | **Catálogo → Productos** · crear *Atún / en rodajas / kg* | «CREATE con `INSERT ... RETURNING`; el panel muestra la sentencia con sus parámetros.» | Alerta verde y panel con `INSERT INTO producto ... RETURNING id_producto`. |
| 1:15 | Crear otra vez *Dorado / entero* | «Si repito especie y presentación, no lo impide Python: lo rechaza el `UNIQUE` del motor.» | Alerta roja con `duplicate key value violates unique constraint "producto_id_especie_presentacion_key"`. |
| 1:30 | **Editar** el producto nuevo → *rodajas finas* | «UPDATE de presentación y unidad.» | `UPDATE producto SET ... RETURNING`. |
| 1:40 | **Eliminar** el producto nuevo y luego **Eliminar** *Dorado entero* | «El nuevo se borra. *Dorado entero* tiene compras: la clave foránea lo impide.» | 1 fila afectada; luego «No se puede eliminar: el producto tiene compras o ventas asociadas» + `violates foreign key constraint`. |
| 2:00 | **Ventas y saldos → Registrar venta**: cliente *Restaurante La Red Dorada*, fecha hoy; líneas *Dorado · filete* 25 kg × 6.20 y *Camarón · sin cabeza* 10 kg × 9.50; cobro inicial **100.00** | «La venta, su detalle, el total y el cobro inicial van en UNA transacción. El total lo calcula PostgreSQL como Σ subtotales.» | Panel: `BEGIN` → `INSERT venta` → 2 × `INSERT detalle_venta` → `UPDATE venta.total` (**250.00**) → `INSERT cobro` → `COMMIT`. Estado `pendiente_cobro`. |
| 2:25 | En el detalle de la venta: recuadro **Cuadre** | «El total cuadra con el detalle (R4).» | «venta.total = $250.00 · Σ detalle = $250.00 → cuadra». |
| 2:35 | **Registrar cobro** de **200.00** | «Intento cobrar más que el saldo: lo rechaza un trigger y la base no cambia.» | `Cobro rechazado: el monto 200.00 supera el saldo pendiente 150.00 ...` + `ROLLBACK`. |
| 2:45 | Clic en el cliente → **saldo** (o **Saldos de clientes**) | «El saldo sale de la vista `v_saldo_cliente`: el valor oficial del momento (R5).» | Saldo pendiente incluye los **$150.00** de esta venta; panel con `SELECT ... FROM v_saldo_cliente`. |

---

## Bloque 2 · Regynald Zambrano · MongoDB (3:00 – 6:30)

| Tiempo | Clic / acción | Qué decir | Qué debe verse |
|---|---|---|---|
| 3:00 | **Muelle → Captura en muelle** | «Esta pantalla simula el teléfono del auxiliar. El UUID se genera en el dispositivo con `crypto.randomUUID()`.» | Formulario con proveedor, usuario *Auxiliar de muelle* y una línea. |
| 3:10 | Línea 1: *Dorado · entero* 142.5 kg × 3.10 → talla *grande*, calidad *A*, temperatura 2.1. **+ Agregar línea**: *Camarón · con cabeza* 60 kg × 5.40 → calibre *31-40*. **+ Agregar atributo libre** `lote` = `L-0457`. **Guardar recepción** | «Cada especie trae atributos distintos y puedo agregar uno libre sin tocar el esquema (R2).» | Respuesta: `insertada`, paso 1 con `upserted_id` = UUID, total **30 → 31**. Panel: `updateOne({_id}, {$setOnInsert: ...}, {upsert: true})`. |
| 3:45 | Activar **«Simular sin señal»** · capturar *Atún · entero* 210 kg × 3.25 (peso por pieza 32.5, grado 1) · **Guardar** | «Sin señal la recepción no se pierde: queda en la cola del dispositivo (localStorage) con su UUID ya asignado.» | Etiqueta roja «Sin señal»; la recepción aparece en **Cola sin conexión**; el servidor no recibió nada. |
| 4:05 | Desactivar «Simular sin señal» · **Sincronizar** | «Vuelve la señal y se sincroniza la cola.» | `insertada`, total **31 → 32**; la cola queda vacía. |
| 4:20 | En **Enviadas desde este dispositivo**, **Reenviar** la primera recepción | «Si el teléfono reenvía la misma recepción, el upsert por `_id` no la duplica: solo cuenta el reenvío (R1).» | `actualizada`; paso 1 `matched 1 / modified 0 / upserted null`, paso 2 `matched 1 / modified 1`; total **32 → 32 «no aumentó»**; `reenvios: 1`. |
| 4:45 | **Muelle → Pendientes del día** → **Ver plan de consulta** | «La consulta de pendientes del día filtra por `estado` y un rango de `capturado_en`; usa el índice compuesto.» | `FETCH → IXSCAN (estado_1_capturado_en_1)`; claves examinadas = documentos devueltos. |
| 5:05 | **Muelle → Recepciones**: filtrar especie *Camarón* → **Ver plan de consulta** | «Por especie no hay índice: el plan lo dice. Los índices responden a las consultas que hacemos.» | `SORT → COLLSCAN` (insignia roja). |
| 5:15 | Abrir el detalle de la recepción *Dorado + Camarón* | «Read: cada línea con sus propios atributos. Abajo, el documento tal como está en MongoDB.» | Badges `talla`, `calidad`, `temperatura_c` vs `calibre`, `lote`. |
| 5:30 | **Corregir peso**: línea 1 → 150.5 · **Agregar atributo** línea 2 → `zona_pesca` = `Manta` | «Update con `$set`, solo mientras la recepción está pendiente.» | `updateOne({_id, estado: "pendiente"}, {$set: {"lineas.0.peso_kg": 150.5}})` con `modified_count: 1`. |
| 5:45 | Abrir la recepción *Atún* (en **Recepciones**) → **Rechazar** con motivo *Temperatura fuera de rango* → **Eliminar** | «Rechazar cambia el estado solo en MongoDB: la contabilidad no se toca. Una captura errónea pendiente o rechazada se puede borrar.» | `estado: "rechazada"`; luego `deleteOne(...)` con `deleted_count: 1`. |
| 6:00 | **Recepciones** filtro *validada* → abrir una → **Eliminar** | «Una validada ya tiene compra oficial: el filtro del `deleteOne` no la encuentra.» | «No se puede eliminar: ... compra oficial #n ...» y `deleted_count: 0`. |
| 6:10 | **Muelle → Validador e índices** → **Insertar documento inválido** | «El validador `$jsonSchema` exige UUID, tipos, estado válido y peso > 0, pero deja `atributos` libre.» | `Document failed validation · estado: enum; lineas.peso_kg: minimum` y el `errInfo` completo en el panel. |

---

## Bloque 3 · Christian Vera · Integración y cierre (6:30 – 9:30)

| Tiempo | Clic / acción | Qué decir | Qué debe verse |
|---|---|---|---|
| 6:30 | **Validación** → **Validar** la recepción *Dorado + Camarón* de Regynald | «Validar lee el documento en MongoDB y crea la compra oficial en una sola transacción: todo o nada (R3).» | Panel: `findOne` → `BEGIN` → `INSERT compra` (`uuid_recepcion` = UUID) → 2 × `INSERT detalle_compra` con `ROUND(peso × precio, 2)` → `UPDATE compra.total` → `COMMIT` → `updateOne(... estado: "validada", id_compra ...)`. |
| 7:00 | Clic en la compra (**Compras y pagos** → detalle) | «La compra guarda el UUID del dispositivo; el enlace vuelve al documento de MongoDB.» | Detalle de compra con total = Σ subtotales y `uuid_recepcion`. |
| 7:15 | **Validación** → en «Validadas recientemente», **Forzar revalidación (demo)** sobre esa misma | «Ahora me salto la verificación de MongoDB e intento contabilizarla otra vez. ¿Quién lo impide? PostgreSQL.» | «Rechazado por PostgreSQL: esta recepción ya fue contabilizada (uuid_recepcion único)»; panel con `ERROR 23505 duplicate key ... compra_uuid_recepcion_key` y `ROLLBACK`. |
| 7:45 | (Opcional) **Simular desfase** → **Validar** de nuevo | «Si MongoDB no alcanzó a marcarla, el UNIQUE la detecta y la aplicación reconcilia el estado.» | «MongoDB estaba desfasado y se reconcilió a 'validada'». |
| 8:00 | **Cierre diario** · revisar «Movimientos por fecha» · **Emitir cierre** con la fecha sugerida (día −1) | «El cierre lo calcula la función `emitir_cierre()` del motor: compras y ventas no anuladas y su diferencia (R6).» | `SELECT * FROM emitir_cierre(...)` devuelve la fila; aparece en «Cierres emitidos». |
| 8:25 | **Emitir cierre** otra vez con la misma fecha | «Un segundo cierre del mismo día lo impide el `UNIQUE`.» | `duplicate key value violates unique constraint "cierre_diario_fecha_key"`. |
| 8:40 | **Probar venta en día cerrado (demo)** con la fecha del día −1 | «Lo cerrado no puede modificarse: el trigger `fn_bloquear_dia_cerrado` rechaza la venta y la transacción se revierte.» | `Día cerrado: el dd/mm/aaaa ya tiene cierre emitido (cierre #5). No se puede insertar en la tabla venta.` + `ROLLBACK`. |
| 9:05 | **Bitácora** | «Todas las operaciones de ambos motores quedan registradas: es el mapa para la defensa.» | Últimas 50 operaciones con insignias PostgreSQL y MongoDB. |
| 9:20 | Cierre | «Resultado: MongoDB absorbe la variabilidad y la falta de señal; PostgreSQL garantiza que cada recepción se contabiliza una sola vez y que lo cerrado no cambia.» | — |

---

## Respaldo para preguntas

- **Mapa de cada consulta:** `docs/MAPA_CRUD.md`.
- **Anexos técnicos:** `db/postgres/script_final_postgres.sql` y `db/mongo/script_final_mongo.js`.
- **Prueba automática:** `docker compose exec web python scripts/verificar_demo.py` → todas las verificaciones en `PASS` (reinicia los datos antes y después).
- **¿Por qué el pago de una deuda vieja no choca con el cierre?** El pago lleva su propia fecha (abierta). El trigger solo permite que la cabecera cerrada pase a `pagada`/`cobrada` cuando ninguna otra columna cambia: los totales del cierre no se alteran.
- **¿Qué pasa si se cae MongoDB después del COMMIT?** La compra ya existe; al reintentar, el `UNIQUE` lo detecta y se reconcilia el documento a `validada`.

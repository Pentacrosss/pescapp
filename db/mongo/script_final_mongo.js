// #####################################################################
// pescAPP · Script final MongoDB 7 (anexo técnico · Momento 2)
// Tópicos Avanzados de Bases de Datos
//
// Colección recepciones_muelle: registro PROVISIONAL del muelle.
//   - _id = UUID generado en el dispositivo -> reenviar no duplica (R1)
//   - lineas[].atributos sin esquema fijo  -> cada especie trae sus
//     propios atributos sin cambiar el esquema (R2)
//   - MongoDB NO guarda saldos ni cierres (eso es PostgreSQL)
//
// Ejecución (seguro: si la colección existe solo actualiza el validador
// con collMod y crea los índices que falten; no borra datos):
//   mongosh pescapp script_final_mongo.js
//   docker compose exec mongo mongosh pescapp /mongo/script_final_mongo.js
// #####################################################################

db = db.getSiblingDB("pescapp");

// ---------------------------------------------------------------------
// 1. Validador $jsonSchema
// ---------------------------------------------------------------------
const numeroPositivo = { bsonType: "number", minimum: 0, exclusiveMinimum: true };
const entero = { bsonType: ["int", "long"] };

const validador = {
  $jsonSchema: {
    bsonType: "object",
    title: "Recepción en muelle (registro provisional)",
    required: ["_id", "id_usuario", "id_proveedor", "capturado_en", "estado", "lineas"],
    properties: {
      _id: {
        bsonType: "string",
        pattern: "^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$",
        description: "UUID generado en el dispositivo",
      },
      id_usuario: entero,
      id_proveedor: entero,
      capturado_en: { bsonType: "date" },
      sincronizado_en: { bsonType: "date" },
      estado: { enum: ["pendiente", "validada", "rechazada"] },
      lineas: {
        bsonType: "array",
        minItems: 1,
        items: {
          bsonType: "object",
          required: ["id_producto", "especie", "peso_kg", "precio_kg", "atributos"],
          properties: {
            id_producto: entero,
            especie: { bsonType: "string", minLength: 1 },
            peso_kg: numeroPositivo,
            precio_kg: numeroPositivo,
            // Sin "properties": aquí está la flexibilidad (R2)
            atributos: { bsonType: "object", description: "Atributos propios de cada especie, sin esquema fijo" },
          },
        },
      },
      observaciones: { bsonType: ["string", "null"] },
      reenvios: { bsonType: ["int", "long"], minimum: 0 },
      // Campos opcionales que agrega la aplicación
      validado_en: { bsonType: "date" },
      id_compra: entero,
      motivo_rechazo: { bsonType: "string" },
    },
  },
};

// ---------------------------------------------------------------------
// 2. Colección (crear o actualizar el validador)
// ---------------------------------------------------------------------
if (db.getCollectionNames().includes("recepciones_muelle")) {
  db.runCommand({
    collMod: "recepciones_muelle",
    validator: validador,
    validationLevel: "strict",
    validationAction: "error",
  });
  print("recepciones_muelle ya existía: validador actualizado con collMod.");
} else {
  db.createCollection("recepciones_muelle", {
    validator: validador,
    validationLevel: "strict",
    validationAction: "error",
  });
  print("recepciones_muelle creada con su validador $jsonSchema.");
}

// ---------------------------------------------------------------------
// 3. Índices
// ---------------------------------------------------------------------
// Pendientes del día: igualdad en estado + rango en capturado_en
db.recepciones_muelle.createIndex({ estado: 1, capturado_en: 1 }, { name: "estado_1_capturado_en_1" });
// Historial por proveedor, lo más reciente primero
db.recepciones_muelle.createIndex({ id_proveedor: 1, capturado_en: -1 }, { name: "id_proveedor_1_capturado_en_-1" });
printjson(db.recepciones_muelle.getIndexes().map(i => ({ nombre: i.name, claves: i.key })));

// #####################################################################
// 4. Ejemplos comentados de cada operación CRUD (como los ejecuta la app)
// #####################################################################

// ---------------------------------------------------------------------
// CREATE · R1 · Upsert idempotente por _id (core/repositorios/recepciones_repo.py)
// Paso 1: si no existe la inserta; si existe no cambia nada.
// ---------------------------------------------------------------------
// db.recepciones_muelle.updateOne(
//   { _id: "3f2b9c1e-7a41-4c2e-9d0b-5b8f2a6c1e90" },
//   { $setOnInsert: {
//       id_usuario: 3, id_proveedor: 2,
//       capturado_en: ISODate("2026-10-03T13:15:00Z"),
//       sincronizado_en: ISODate("2026-10-03T13:40:00Z"),
//       estado: "pendiente", reenvios: 0,
//       observaciones: "Dos gavetas con hielo insuficiente",
//       lineas: [
//         { id_producto: 1, especie: "Dorado", peso_kg: 142.5, precio_kg: 3.10,
//           atributos: { talla: "grande", calidad: "A", temperatura_c: 2.1 } },
//         { id_producto: 3, especie: "Camarón", peso_kg: 60, precio_kg: 5.40,
//           atributos: { calibre: "31-40", calidad: "B" } }
//       ] } },
//   { upsert: true }
// )
// -> primera vez: { matchedCount: 0, modifiedCount: 0, upsertedId: "3f2b9c1e-..." }
// -> reenvío:     { matchedCount: 1, modifiedCount: 0, upsertedId: null }
//
// Paso 2 (solo si ya existía): actualizar únicamente si sigue pendiente
// db.recepciones_muelle.updateOne(
//   { _id: "3f2b9c1e-7a41-4c2e-9d0b-5b8f2a6c1e90", estado: "pendiente" },
//   { $set: { lineas: [ ... ], sincronizado_en: new Date() }, $inc: { reenvios: 1 } }
// )
// -> pendiente: { matchedCount: 1, modifiedCount: 1 } ; validada/rechazada: { matchedCount: 0 }
// db.recepciones_muelle.countDocuments({})   // el total no aumenta al reenviar

// ---------------------------------------------------------------------
// READ · Pendientes del día (usa estado_1_capturado_en_1)
// ---------------------------------------------------------------------
// db.recepciones_muelle.find({
//   estado: "pendiente",
//   capturado_en: { $gte: ISODate("2026-10-03T05:00:00Z"), $lt: ISODate("2026-10-04T05:00:00Z") }
// }).sort({ capturado_en: 1 })
//
// Plan de consulta: FETCH -> IXSCAN (estado_1_capturado_en_1)
// db.recepciones_muelle.find({ estado: "pendiente",
//   capturado_en: { $gte: ISODate("2026-10-03T05:00:00Z"), $lt: ISODate("2026-10-04T05:00:00Z") }
// }).sort({ capturado_en: 1 }).explain("executionStats")
//
// Otros filtros de la lista: por proveedor (índice id_proveedor_1_capturado_en_-1) y por especie
// db.recepciones_muelle.find({ id_proveedor: 2 }).sort({ capturado_en: -1 })
// db.recepciones_muelle.find({ "lineas.especie": "Camarón" }).sort({ capturado_en: -1 })
// db.recepciones_muelle.findOne({ _id: "3f2b9c1e-7a41-4c2e-9d0b-5b8f2a6c1e90" })

// ---------------------------------------------------------------------
// UPDATE · solo pendientes ($set)
// ---------------------------------------------------------------------
// Corregir peso o precio de la primera línea
// db.recepciones_muelle.updateOne(
//   { _id: "3f2b9c1e-7a41-4c2e-9d0b-5b8f2a6c1e90", estado: "pendiente" },
//   { $set: { "lineas.0.peso_kg": 150.5, "lineas.0.precio_kg": 3.20 } }
// )
// R2 · Agregar un atributo nuevo sin cambiar el esquema
// db.recepciones_muelle.updateOne(
//   { _id: "3f2b9c1e-7a41-4c2e-9d0b-5b8f2a6c1e90", estado: "pendiente" },
//   { $set: { "lineas.1.atributos.lote": "L-0457" } }
// )
// Rechazar (PostgreSQL no se toca)
// db.recepciones_muelle.updateOne(
//   { _id: "3f2b9c1e-7a41-4c2e-9d0b-5b8f2a6c1e90", estado: "pendiente" },
//   { $set: { estado: "rechazada", motivo_rechazo: "Fuera de la cadena de frío" } }
// )
// R3 · Tras el COMMIT de la compra en PostgreSQL
// db.recepciones_muelle.updateOne(
//   { _id: "3f2b9c1e-7a41-4c2e-9d0b-5b8f2a6c1e90", estado: "pendiente" },
//   { $set: { estado: "validada", id_compra: 22, validado_en: new Date() } }
// )

// ---------------------------------------------------------------------
// DELETE · solo pendiente o rechazada (una validada ya tiene compra oficial)
// ---------------------------------------------------------------------
// db.recepciones_muelle.deleteOne({
//   _id: "3f2b9c1e-7a41-4c2e-9d0b-5b8f2a6c1e90",
//   estado: { $in: ["pendiente", "rechazada"] }
// })
// -> validada: { deletedCount: 0 }

// ---------------------------------------------------------------------
// Prueba del validador: este documento se rechaza (estado fuera del enum, peso negativo)
// ---------------------------------------------------------------------
// db.recepciones_muelle.insertOne({
//   _id: "11111111-2222-4333-8444-555555555555", id_usuario: 3, id_proveedor: 1,
//   capturado_en: new Date(), estado: "aprobada",
//   lineas: [{ id_producto: 1, especie: "Dorado", peso_kg: -5, precio_kg: 3.1, atributos: {} }]
// })
// -> MongoServerError: Document failed validation

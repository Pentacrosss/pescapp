"""
Datos semilla reproducibles (semilla aleatoria fija) y reinicio de la demo.

Recrea ambos esquemas y carga los datos usando LAS MISMAS funciones que
usa la aplicación (upsert de recepciones, validación transaccional,
ventas, cobros, pagos y emitir_cierre), de modo que la semilla también
pasa por las reglas del motor.

Distribución (relativa a la fecha de hoy en America/Guayaquil):
  - Días −5 a −2: recepciones validadas con su compra, pagos, ventas con
    cobros y cierre emitido.
  - Día −1: recepciones validadas y ventas, SIN cierre.
  - Hoy: 8 recepciones pendientes y 1 rechazada.
Total: 30 recepciones.
"""
from __future__ import annotations

import random
import uuid as uuid_lib
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from core import consultas
from core.bd import pg
from core.repositorios import (
    cierre_repo,
    compras_repo,
    recepciones_repo,
    ventas_repo,
)
from core.servicios import esquema, validacion
from core.utilidades import a_decimal, hoy

SEMILLA = 2026

USUARIOS = [
    ("Administrador", "administrador"),
    ("Vendedor", "vendedor"),
    ("Auxiliar de muelle", "auxiliar"),
]
ID_ADMIN, ID_VENDEDOR, ID_AUXILIAR = 1, 2, 3

ESPECIES = [("Dorado", "pescado"), ("Camarón", "crustáceo"), ("Atún", "pescado")]

PRODUCTOS = [
    ("Dorado", "entero"),
    ("Dorado", "filete"),
    ("Camarón", "con cabeza"),
    ("Camarón", "sin cabeza"),
    ("Atún", "entero"),
    ("Atún", "lomo"),
]

PROVEEDORES = [
    ("Cooperativa Pesquera San Mateo", "1391700001001", "0991000001"),
    ("Asociación de Pescadores Playa Norte", "1391700002001", "0991000002"),
    ("Armadores del Pacífico Sur", "1391700003001", "0991000003"),
    ("Luis Alberto Mero Delgado", "1300000004", "0991000004"),
    ("Rosa Elena Pinargote Cedeño", "1300000005", "0991000005"),
]

CLIENTES = [
    ("Distribuidora Mariscos del Litoral", "0991800001001", "mayorista"),
    ("Restaurante La Red Dorada", "1391800002001", "minorista"),
    ("Comercial Frío Costa", "0991800003001", "mayorista"),
    ("Hotel Brisas del Puerto", "1391800004001", "mayorista"),
    ("Marisquería El Ancla", "1391800005001", "minorista"),
]

# Rango de precio de compra (USD/kg) y de peso por línea (kg) por especie
PRECIO_COMPRA = {"Dorado": (3.0, 4.5), "Camarón": (4.5, 7.0), "Atún": (2.5, 4.0)}
PESO_COMPRA = {"Dorado": (40, 180), "Camarón": (20, 120), "Atún": (80, 320)}

OBSERVACIONES = [
    None,
    None,
    "Dos gavetas con hielo insuficiente",
    "Descarga en muelle 2",
    "Producto recibido con buena cadena de frío",
    "Se pesó en báscula auxiliar",
]
EMBARCACIONES = ["Fibra San Pedro", "Bote Estrella del Mar", "Lancha Don Lucho", "Fibra La Gaviota"]
ZONAS = ["Manta", "Jaramijó", "San Mateo", "Puerto López"]


# =====================================================================
# Punto de entrada
# =====================================================================
def reiniciar_demo() -> dict:
    """Restaura ambas bases al estado inicial (comando reset_demo y botón).

    La parte PostgreSQL (DDL + semilla) va en una sola transacción: si algo
    falla no queda un esquema a medias y el próximo arranque lo reintenta.
    """
    with consultas.silenciado(), transaction.atomic():
        esquema.aplicar_esquema_postgres()
        esquema.crear_coleccion_mongo()
        resumen = _sembrar(random.Random(SEMILLA))
    return resumen


# =====================================================================
# Catálogos (SQL explícito)
# =====================================================================
def _sembrar_catalogos() -> dict[str, list[tuple[int, str]]]:
    for nombre, rol in USUARIOS:
        pg.ejecutar(
            "INSERT INTO usuario (nombre, rol, estado) VALUES (%s, %s, 'activo')",
            [nombre, rol],
        )
    for nombre, categoria in ESPECIES:
        pg.ejecutar(
            "INSERT INTO especie (nombre_comun, categoria) VALUES (%s, %s)",
            [nombre, categoria],
        )
    for especie, presentacion in PRODUCTOS:
        pg.ejecutar(
            """
            INSERT INTO producto (id_especie, presentacion, unidad)
            SELECT id_especie, %s, 'kg' FROM especie WHERE nombre_comun = %s
            """,
            [presentacion, especie],
        )
    for nombre, identificacion, telefono in PROVEEDORES:
        pg.ejecutar(
            "INSERT INTO proveedor (nombre, identificacion, telefono) VALUES (%s, %s, %s)",
            [nombre, identificacion, telefono],
        )
    for nombre, identificacion, tipo in CLIENTES:
        pg.ejecutar(
            "INSERT INTO cliente (nombre, identificacion, tipo) VALUES (%s, %s, %s)",
            [nombre, identificacion, tipo],
        )
    filas = pg.consultar(
        """
        SELECT p.id_producto, e.nombre_comun AS especie
          FROM producto p JOIN especie e ON e.id_especie = p.id_especie
         ORDER BY p.id_producto
        """
    )
    productos: dict[str, list[tuple[int, str]]] = {}
    for fila in filas:
        productos.setdefault(fila["especie"], []).append((fila["id_producto"], fila["especie"]))
    return productos


# =====================================================================
# Recepciones (documentos MongoDB)
# =====================================================================
def _atributos(rng: random.Random, especie: str) -> dict:
    if especie == "Dorado":
        atributos = {
            "talla": rng.choice(["pequeño", "mediano", "grande"]),
            "calidad": rng.choice(["A", "A", "B", "C"]),
            "temperatura_c": round(rng.uniform(0.5, 4.0), 1),
        }
    elif especie == "Camarón":
        atributos = {
            "calibre": rng.choice(["21-25", "26-30", "31-40", "41-50"]),
            "calidad": rng.choice(["A", "B", "B", "C"]),
        }
    else:  # Atún
        atributos = {
            "peso_pieza_kg": round(rng.uniform(8, 45), 1),
            "grado": rng.choice(["1", "2", "2", "3"]),
            "temperatura_c": round(rng.uniform(-1.0, 3.0), 1),
        }
    # Atributos libres ocasionales: el esquema no cambia (R2)
    sorteo = rng.random()
    if sorteo < 0.15:
        atributos["lote"] = f"L-{rng.randint(1, 999):04d}"
    elif sorteo < 0.25:
        atributos["embarcacion"] = rng.choice(EMBARCACIONES)
    elif sorteo < 0.32:
        atributos["zona_pesca"] = rng.choice(ZONAS)
    return atributos


def _recepcion(rng: random.Random, productos: dict, capturado: datetime) -> dict:
    especies = rng.sample(list(productos.keys()), k=rng.choice([1, 1, 2, 2, 3]))
    lineas = []
    for especie in especies:
        id_producto, _ = rng.choice(productos[especie])
        bajo, alto = PRECIO_COMPRA[especie]
        peso_min, peso_max = PESO_COMPRA[especie]
        lineas.append(
            {
                "id_producto": id_producto,
                "especie": especie,
                "peso_kg": round(rng.uniform(peso_min, peso_max), 1),
                "precio_kg": round(rng.uniform(bajo, alto), 2),
                "atributos": _atributos(rng, especie),
            }
        )
    return {
        "_id": str(uuid_lib.UUID(int=rng.getrandbits(128), version=4)),
        "id_usuario": ID_AUXILIAR,
        "id_proveedor": rng.randint(1, len(PROVEEDORES)),
        "capturado_en": capturado,
        "lineas": lineas,
        "observaciones": rng.choice(OBSERVACIONES),
    }


def _momento_local(fecha, hora: float) -> datetime:
    zona = timezone.get_current_timezone()
    base = datetime.combine(fecha, time.min, tzinfo=zona)
    return base + timedelta(hours=hora)


# =====================================================================
# Carga completa
# =====================================================================
def _sembrar(rng: random.Random) -> dict:
    productos = _sembrar_catalogos()
    fecha_hoy = hoy()
    ahora = timezone.now()
    compras: list[dict] = []
    ventas: list[dict] = []

    # --- Días −5 a −1: recepciones validadas -> compras ----------------
    for desplazamiento, cantidad in [(-5, 4), (-4, 5), (-3, 4), (-2, 5), (-1, 3)]:
        fecha = fecha_hoy + timedelta(days=desplazamiento)
        horas = sorted(rng.uniform(5.0, 13.0) for _ in range(cantidad))
        for hora in horas:
            capturado = _momento_local(fecha, hora)
            doc = _recepcion(rng, productos, capturado)
            sincronizado = capturado + timedelta(minutes=rng.randint(2, 150))
            recepciones_repo.sincronizar_recepcion(doc, momento=sincronizado)
            if rng.random() < 0.2:  # el teléfono reenvió la misma recepción
                recepciones_repo.sincronizar_recepcion(doc, momento=sincronizado + timedelta(minutes=5))
            resultado = validacion.validar_recepcion(
                doc["_id"], ID_ADMIN, validado_en=capturado + timedelta(hours=rng.uniform(2, 5))
            )
            if not resultado.ok:
                raise RuntimeError(f"Semilla: no se pudo validar {doc['_id']}: {resultado.mensaje}")
            compras.append({"id_compra": resultado.id_compra, "total": resultado.total, "fecha": fecha})

    # --- Ventas con cobros (cobro inicial completo, parcial o ninguno) --
    for desplazamiento in range(-5, 0):
        fecha = fecha_hoy + timedelta(days=desplazamiento)
        for _ in range(rng.randint(3, 4)):
            especies = rng.sample(list(productos.keys()), k=rng.choice([1, 2]))
            lineas = []
            for especie in especies:
                id_producto, _ = rng.choice(productos[especie])
                bajo, alto = PRECIO_COMPRA[especie]
                lineas.append(
                    {
                        "id_producto": id_producto,
                        "peso_kg": a_decimal(round(rng.uniform(40, 160), 1)),
                        "precio_kg": a_decimal(round(rng.uniform(bajo, alto) * rng.uniform(1.25, 1.5), 2)),
                    }
                )
            # mismo redondeo que el motor: Σ ROUND(peso × precio, 2)
            estimado = sum(a_decimal(l["peso_kg"] * l["precio_kg"]) for l in lineas)
            sorteo = rng.random()
            if sorteo < 0.4:
                cobro = a_decimal(estimado)  # cobro completo
            elif sorteo < 0.8:
                cobro = a_decimal(estimado * Decimal(str(round(rng.uniform(0.3, 0.7), 2))))
            else:
                cobro = None
            venta = ventas_repo.registrar_venta(
                rng.randint(1, len(CLIENTES)),
                ID_VENDEDOR,
                fecha,
                lineas,
                cobro_inicial=cobro,
                metodo_cobro=rng.choice(["efectivo", "transferencia"]),
            )
            venta["fecha"] = fecha
            venta["cobro"] = cobro or Decimal("0")
            ventas.append(venta)

    # --- Pagos a proveedores ------------------------------------------
    for compra in compras:
        sorteo = rng.random()
        if sorteo < 0.45:
            monto = compra["total"]
        elif sorteo < 0.7:
            monto = a_decimal(compra["total"] * Decimal(str(round(rng.uniform(0.4, 0.6), 2))))
        else:
            continue
        compras_repo.registrar_pago(
            compra["id_compra"], compra["fecha"], monto, rng.choice(["efectivo", "transferencia"])
        )
        compra["pagado"] = monto

    # --- Cierres emitidos para los días −5 a −2 ------------------------
    for desplazamiento in range(-5, -1):
        cierre_repo.emitir_cierre(fecha_hoy + timedelta(days=desplazamiento), ID_ADMIN)

    # --- Día −1: se liquidan deudas de días ya cerrados ----------------
    # (el pago/cobro lleva su propia fecha abierta; el trigger permite
    #  que la cabecera cerrada pase a pagada/cobrada sin otros cambios)
    ayer = fecha_hoy - timedelta(days=1)
    antigua_venta = next(
        (v for v in ventas if v["fecha"] < ayer and Decimal("0") < v["cobro"] < v["total"]), None
    )
    if antigua_venta:
        ventas_repo.registrar_cobro(
            antigua_venta["id_venta"], ayer, antigua_venta["total"] - antigua_venta["cobro"], "transferencia"
        )
    antigua_compra = next(
        (c for c in compras if c["fecha"] < ayer and Decimal("0") < c.get("pagado", 0) < c["total"]), None
    )
    if antigua_compra:
        compras_repo.registrar_pago(
            antigua_compra["id_compra"], ayer, antigua_compra["total"] - antigua_compra["pagado"], "transferencia"
        )

    # --- Hoy: 8 pendientes y 1 rechazada -------------------------------
    inicio_hoy = _momento_local(fecha_hoy, 0)
    ventana_inicio = inicio_hoy + timedelta(hours=5) if ahora > inicio_hoy + timedelta(hours=6) else inicio_hoy
    ventana_fin = max(ahora - timedelta(minutes=1), ventana_inicio + timedelta(seconds=30))
    segundos = (ventana_fin - ventana_inicio).total_seconds()
    momentos = sorted(ventana_inicio + timedelta(seconds=rng.uniform(0, segundos)) for _ in range(9))
    uuids_hoy = []
    for i, capturado in enumerate(momentos):
        doc = _recepcion(rng, productos, capturado)
        sincronizado = min(capturado + timedelta(minutes=rng.randint(1, 90)), ahora)
        recepciones_repo.sincronizar_recepcion(doc, momento=sincronizado)
        if i == 2:  # una recepción reenviada dos veces desde el teléfono
            recepciones_repo.sincronizar_recepcion(doc, momento=sincronizado)
            recepciones_repo.sincronizar_recepcion(doc, momento=sincronizado)
        uuids_hoy.append(doc["_id"])
    recepciones_repo.rechazar(uuids_hoy[4], "Temperatura de 9 °C: fuera de la cadena de frío")

    return {
        "compras": len(compras),
        "ventas": len(ventas),
        "recepciones": 30,
        "cierres": 4,
    }

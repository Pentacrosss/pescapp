# pescAPP · Prototipo Momento 2

Prototipo web de **pescAPP** (Tópicos Avanzados de Bases de Datos · examen final, Momento 2).

Una comercializadora pesquera compra en el muelle, donde la señal es intermitente, y luego vende. El problema de datos es **capturar en el muelle un registro variable y sin conexión garantizada, y convertirlo después en un dato contable oficial, sin pérdidas ni duplicados.**

```
Muelle (MongoDB, provisional)  ──►  Validación  ──►  Núcleo (PostgreSQL, oficial)
recepciones_muelle                  1 transacción     12 tablas · triggers · vistas
_id = UUID del dispositivo          uuid_recepcion    ventas, cobros, saldos, cierre
```

| Req. | Qué demuestra | Motor |
|---|---|---|
| R1 | Recepción sin señal; reenviarla no la duplica (upsert por `_id`) | MongoDB |
| R2 | Atributos propios de cada especie sin cambiar el esquema | MongoDB |
| R3 | Recepción validada → compra oficial, todo o nada, sin contabilizar dos veces | PostgreSQL |
| R4 | Ventas y cobros; el total cuadra con el detalle | PostgreSQL |
| R5 | Saldo pendiente de proveedor o cliente con el valor oficial del momento | PostgreSQL |
| R6 | Cierre del día; lo cerrado no puede modificarse | PostgreSQL |

**Stack:** Python 3.12 · Django 5 (plantillas + Bootstrap 5 por CDN + JavaScript simple) · PostgreSQL 16 con SQL explícito (psycopg 3, sin ORM para las tablas de negocio) · MongoDB 7 con pymongo · Docker Compose.

---

## 1. Requisitos

- **Con Docker (recomendado):** Docker Desktop con WSL 2 (Windows) o Docker Engine + Compose v2.
- **Sin Docker:** Python 3.12, PostgreSQL 16 y MongoDB 7 instalados localmente.

## 2. Levantar con Docker

```bash
docker compose up --build
```

Abrir <http://localhost:8000>. El primer arranque crea el esquema PostgreSQL (scripts de `db/postgres`), la colección MongoDB con su validador e índices y carga los datos semilla; no hay pasos manuales. Los arranques siguientes conservan los datos.

| Servicio | Dentro de Docker | Desde el equipo |
|---|---|---|
| web (Django + gunicorn) | `web:8000` | <http://localhost:8000> |
| PostgreSQL 16 | `postgres:5432` | `127.0.0.1:5433` (usuario/clave/base: `pescapp`) |
| MongoDB 7 | `mongo:27017` | `mongodb://127.0.0.1:27018/pescapp` |

Los puertos publicados se cambian en `.env` (`WEB_PUERTO`, `PG_PUERTO_HOST`, `MONGO_PUERTO_HOST`); ver `.env.example`.

Otros comandos útiles:

```bash
docker compose exec web python scripts/verificar_demo.py
```

```bash
docker compose exec web python manage.py reset_demo
```

```bash
docker compose down -v
```

`verificar_demo.py` recorre el CRUD de cada motor y las cinco operaciones clave e imprime `PASS`/`FAIL` (reinicia los datos antes y después; `--sin-reinicio` para no hacerlo). `down -v` borra los volúmenes; el siguiente `up` vuelve a sembrar.

## 3. Levantar sin Docker

1. Crear la base y el usuario en PostgreSQL 16:

   ```sql
   CREATE USER pescapp WITH PASSWORD 'pescapp';
   CREATE DATABASE pescapp OWNER pescapp;
   ```

2. Tener MongoDB 7 escuchando (por defecto `mongodb://localhost:27017`).
3. Entorno de Python e instalación:

   ```bash
   python -m venv .venv
   ```

   ```bash
   .venv\Scripts\activate
   ```

   (en Linux/macOS: `source .venv/bin/activate`)

   ```bash
   pip install -r requirements.txt
   ```

4. Copiar `.env.example` como `.env` y ajustar los hosts:

   ```ini
   POSTGRES_HOST=localhost
   POSTGRES_PORT=5432
   MONGO_URI=mongodb://localhost:27017
   ```

5. Crear esquema + semilla y arrancar:

   ```bash
   python manage.py init_demo
   ```

   ```bash
   python manage.py runserver
   ```

   Abrir <http://localhost:8000>.

> Variante mixta: usar solo las bases de Docker (`docker compose up -d postgres mongo`) con `POSTGRES_HOST=localhost`, `POSTGRES_PORT=5433` y `MONGO_URI=mongodb://localhost:27018` en `.env`.

## 4. Reiniciar la demo (para grabar el video)

- Botón **«Reiniciar datos de demo»** en Inicio, o
- `python manage.py reset_demo` (con Docker: `docker compose exec web python manage.py reset_demo`).

Ambos recrean el esquema PostgreSQL y la colección MongoDB y cargan la semilla (semilla aleatoria fija, fechas relativas a hoy en `America/Guayaquil`):

| Días | Contenido |
|---|---|
| −5 a −2 | Recepciones validadas con su compra, pagos, ventas con cobros y **cierre emitido** |
| −1 | Recepciones validadas y ventas, **sin cierre** (para demostrar el cierre) |
| Hoy | **8 pendientes** y **1 rechazada** |

Total: 30 recepciones, 3 usuarios (Administrador, Vendedor, Auxiliar de muelle), 3 especies, 6 productos, 5 proveedores y 5 clientes ficticios.

## 5. Pantallas (URLs)

| Sección | URL | Motor |
|---|---|---|
| Inicio | `/` | ambos |
| Captura en muelle (Create, cola sin señal, reenvío) | `/muelle/captura/` | MongoDB |
| Recepciones (Read con filtros, plan de consulta) | `/muelle/` | MongoDB |
| Pendientes del día | `/muelle/pendientes/` | MongoDB |
| Detalle (Update, Rechazar, Delete) | `/muelle/<uuid>/` | MongoDB |
| Validador e índices | `/muelle/esquema/` | MongoDB |
| Validación (R3) | `/validacion/` | MongoDB → PostgreSQL |
| Productos (CRUD) | `/catalogo/productos/` | PostgreSQL |
| Proveedores · Clientes | `/catalogo/proveedores/` · `/catalogo/clientes/` | PostgreSQL |
| Registrar venta · Ventas | `/ventas/nueva/` · `/ventas/` | PostgreSQL |
| Compras y pagos | `/compras/` | PostgreSQL |
| Saldos | `/saldos/clientes/` · `/saldos/proveedores/` | PostgreSQL |
| Cierre diario | `/cierre/` | PostgreSQL |
| Bitácora (últimas 50 operaciones) | `/bitacora/` | ambos |

Cada acción muestra el recuadro **«Consulta ejecutada»** con el motor, la sentencia SQL y sus parámetros (o el comando MongoDB en JSON), el tiempo y el resultado o el error real del motor.

## 6. Anexos técnicos

- `db/postgres/script_final_postgres.sql`: esquema, triggers, función y vistas en un solo archivo (generado desde `01_schema.sql`, `02_triggers.sql` y `03_funciones_vistas.sql` con `python scripts/generar_script_final.py`).

  ```bash
  docker compose exec postgres psql -U pescapp -d pescapp -f /sql/script_final_postgres.sql
  ```

  (Recrea el esquema vacío: después ejecute `reset_demo` para volver a cargar la semilla.)

- `db/mongo/script_final_mongo.js`: colección, validador `$jsonSchema`, índices y ejemplos comentados de cada operación CRUD. Es seguro de ejecutar con datos: si la colección existe solo actualiza el validador (`collMod`).

  ```bash
  docker compose exec mongo mongosh pescapp /mongo/script_final_mongo.js
  ```

- `docs/MAPA_CRUD.md`: cada operación con su motor, pantalla, archivo, función y consulta.
- `docs/GUION_DEMO.md`: guion del video (8–10 minutos, tres integrantes).

## 7. Estructura

```
pescapp/
├─ docker-compose.yml · Dockerfile · requirements.txt · .env.example
├─ manage.py · pescapp/ (settings, urls, wsgi)
├─ core/
│  ├─ consultas.py          registro por petición (contextvars) y Bitácora
│  ├─ middleware.py         panel tras POST→redirección · usuario actual (cookie)
│  ├─ bd/pg.py              SQL con parámetros, transacciones, errores del motor
│  ├─ bd/mongo.py           comandos pymongo registrados, explain resumido
│  ├─ repositorios/         SQL y comandos de cada operación (CREATE/READ/UPDATE/DELETE)
│  ├─ servicios/            validacion.py (R3) · esquema.py · semilla.py
│  ├─ views/ templates/ static/
│  └─ management/commands/  init_demo · reset_demo
├─ db/postgres/             01_schema · 02_triggers · 03_funciones_vistas · script_final_postgres
├─ db/mongo/                script_final_mongo.js
├─ docs/                    MAPA_CRUD.md · GUION_DEMO.md
└─ scripts/                 verificar_demo.py · generar_script_final.py
```

## 8. Decisiones de diseño

- **Sin ORM para el negocio.** Django no instala apps que creen tablas (sin `auth`, `admin`, `sessions`, `contenttypes`); los mensajes usan `CookieStorage`. Las 12 tablas las crean los scripts SQL y se consultan con SQL explícito en `core/repositorios`.
- **Upsert idempotente en dos pasos.** Paso 1: `updateOne({_id}, {$setOnInsert}, {upsert: true})` inserta solo si no existe. Paso 2, si ya existía: `updateOne({_id, estado: "pendiente"}, {$set, $inc: {reenvios: 1}})`. Una recepción validada o rechazada no se toca.
- **Las reglas las protege el motor.** `uuid_recepcion UNIQUE` (doble contabilización), `cierre_diario.fecha UNIQUE`, trigger `fn_bloquear_dia_cerrado` (días cerrados) y los triggers `trg_cobro_saldo` / `trg_pago_saldo` (cobros y pagos mayores al saldo). La aplicación muestra el mensaje real de PostgreSQL o MongoDB.
- **Pagos de deudas viejas.** El pago o cobro lleva su propia fecha. El trigger permite que una compra/venta de un día cerrado pase a `pagada`/`cobrada` solo si ninguna otra columna cambia, así los totales del cierre no se alteran.
- **Bitácora en memoria.** Las últimas 50 operaciones viven en el proceso web; por eso gunicorn corre con 1 proceso y 4 hilos.

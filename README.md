# Control de Inventario y Activo Fijo Web

Sistema web para control interno, sin contabilidad. Incluye:

- Usuario y contraseña.
- Roles y permisos.
- Inventario Kardex para productos que no son activo fijo.
- Activo fijo con reglas de depreciación.
- Control de quién anuló movimientos y motivo.
- Bitácora.
- Respaldo automático diario y respaldo manual.
- SQLite local y PostgreSQL para producción mediante DATABASE_URL.
- Logo del Consorcio BAV Torogoz en `assets/logo.jpeg`.

## Usuario inicial

Usuario: `admin`
Contraseña: `admin123`

El sistema pedirá cambiar la contraseña al primer ingreso.

## Ejecutar localmente

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

O doble clic en `INICIAR_SISTEMA.bat`.

## Producción con PostgreSQL

Define `DATABASE_URL`:

```text
postgresql+psycopg2://usuario:password@host:5432/base
```

## Render/Railway

Start command:

```bash
streamlit run app.py --server.port $PORT --server.address 0.0.0.0
```

## Corrección incluida

Esta versión corrige el error `DetachedInstanceError` al iniciar sesión.


## Corrección FIX2

Esta versión corrige:

- Error `InvalidRequestError: Can't determine which FROM clause to join from` en Movimientos Kardex.
- Pantalla de Depreciación vacía cuando no hay activos o reglas activas.
- Warnings principales de Streamlit por `use_container_width`.
- Warnings principales de SQLAlchemy por `Query.get`.


## Corrección FIX3 - Reversas de Kardex

Esta versión corrige la lógica de anulación de movimientos:

- Una reversa ya no afecta el saldo de inventario; queda solo como trazabilidad.
- El saldo se calcula únicamente con movimientos `Registrado` y sin `reversal_of`.
- Si una versión anterior dejó reversas como `Registrado`, el sistema las cambia automáticamente a `Reversa` al iniciar.
- No se permite editar/anular registros de reversa para evitar cadenas de reversas.
- Para anular una entrada, se valida que la existencia disponible sea suficiente.


## FIX4 - Bloques, filtros y adjuntos

Cambios incluidos:

- Catálogo de bloques cargado desde `Bloques master.xlsx`. El archivo contiene 79 bloques.
- Al registrar movimientos de Kardex se debe seleccionar bloque.
- Al registrar activos fijos se debe seleccionar bloque.
- Las existencias ahora se agrupan por producto, bodega y bloque.
- La pantalla de Existencias usa tabla con filtros por encabezado mediante `streamlit-aggrid`.
- Si `streamlit-aggrid` no está disponible, muestra una tabla normal como respaldo.
- Al registrar una entrada o movimiento se puede adjuntar PDF de factura/soporte.
- Al registrar un activo fijo también se puede adjuntar PDF de factura/soporte.
- Los adjuntos se guardan en la base de datos, compatible con PostgreSQL para producción.
- El respaldo incluye bloques, adjuntos y metadata de adjuntos.

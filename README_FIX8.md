# BAV TOROGOZ — FIX8: Requisiciones, traslados y comprobantes PDF

**Versión piloto para instalación y pruebas antes de actualizar producción.** Se conserva el sistema existente: activo fijo, depreciación, Kardex, bloques, clasificación de consumos, usuarios/roles y adjuntos.

## Funcionalidades

**Kardex:** se genera un PDF de Entrada, Salida, Devolución entrada o Devolución salida sin llenar un segundo formulario. Quedan nombre de quien entrega, recibe y registra, con líneas para firmar en papel. Se puede reimprimir desde **Movimientos Kardex > Comprobantes PDF**. Los anulados aparecen identificados.

**Traslados entre bodegas (FIX6 integrada):** un traslado descuenta una bodega y acredita la otra, en una sola operación SQL, por producto, bodega y bloque. Permite anular el traslado completo con validación de existencias y generar un PDF con entrega y recepción.

**Requisiciones de campo (FIX8):**
1. El usuario con rol **Campo** entra a **Requisiciones de campo > Nueva requisición**, elige productos y cantidades, bodega, bloque, cuadrilla y clasificación de consumo. Guarda `RQ-000001`. La solicitud no descuenta stock.
2. **Bodega** entra a **Preparar salida**, revisa existencias y define las cantidades a entregar (incluida entrega parcial). La preparación no modifica saldos.
3. **Bodega** entra a **Emitir salida e imprimir**, confirma la entrega. El sistema revalida existencias, descuenta el Kardex, vincula cada artículo a la requisición y emite `SR-000001`.
4. Descarga el **PDF de salida**, que muestra cantidades solicitadas y entregadas y tiene firmas para **entrega**, **recepción** y **registro**. Se imprime y firma físicamente.
5. Opcionalmente, bodega escanea el comprobante firmado y lo adjunta en **Documentos firmados**.
6. Una misma requisición puede completarse en varias salidas. Al cancelar una salida, se anulan todos sus movimientos asociados; el estado y las cantidades pendientes de la requisición se actualizan sin duplicar movimientos.

### Roles de requisición

| Rol | Acceso |
|---|---|
| Campo | Crear requisición y ver/imprimir las propias |
| Bodega | Consultar, preparar, emitir salida y anexar comprobantes firmados |
| Supervisor | Operaciones completas, incluidas anulaciones |
| Administrador | Operaciones completas, incluidas anulaciones |

## Requisitos y primer inicio

- Python y las dependencias en `requirements.txt`, incluyendo `reportlab`.
- Base PostgreSQL local o externa para varios usuarios. SQLite solo para desarrollo o pruebas de un usuario.
- En Windows: `python -m pip install -r requirements.txt` y `python -m streamlit run app.py`.
- **Realiza un respaldo verificable antes de la primera ejecución de esta versión**. Al iniciar, SQLAlchemy crea *cuatro tablas nuevas*, sin eliminar tablas de movimientos existentes. La actualización añade columnas opcionales para nombres de entrega/recepción cuando es necesario.
- No subas SQLite, `.env`, archivos `backups/` ni documentos internos a GitHub.

## Actualizar el repositorio conectado a Streamlit

La rama `main` del repositorio de origen contenía FIX5 cuando se preparó esta actualización; este paquete incluye FIX6 y FIX8 acumulativas. **Compara el `app.py` remoto actual** antes de reemplazarlo si modificaste el repositorio desde entonces.

Copia los archivos del ZIP de actualización, preservando las carpetas. Desde un clon Git legítimo, después de pruebas y respaldo:

```powershell
python -m py_compile app.py traslados.py consumos.py requisiciones.py comprobantes.py comprobantes_requisicion.py
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
# Para los tests de traslados con pytest:
python -m pytest -q tests/test_traslados.py

git status
git add app.py requirements.txt traslados.py requisiciones.py comprobantes.py comprobantes_requisicion.py assets/logo_comprobante.png tests/test_traslados.py tests/test_requisiciones.py README_FIX8.md
git diff --cached --check
git commit -m "FIX8: requisiciones, traslados y comprobantes de salida PDF"
git push origin main
```

La base de datos **no** debe incluirse en ese commit. Streamlit Cloud volverá a desplegar al actualizar `main` si está enlazado.

## Consideraciones de control interno antes de operación plena

- La **firma es física**; generar el PDF no equivale a tener un comprobante firmado.
- En **Preparación** no se descuentan existencias. En **Emisión** sí, antes de imprimir para firmas.
- En una instalación concurrente, **PostgreSQL** es la base recomendada. El módulo de requisiciones bloquea registros del producto al emitir; las operaciones manuales heredadas de Kardex deben revisarse para aplicar la misma disciplina en todos los casos de uso simultáneos.
- La restricción **por bodega asignada a cada usuario** y el acceso remoto mediante VPN siguen siendo fases separadas, no instaladas por este ZIP.
- Los respaldos automáticos actuales se guardan localmente; define almacenamiento externo y una tarea programada verificable para producción multi-sede.
- La firma y el archivo escaneado pueden conservarse en la BD mediante el módulo de adjuntos; se recomienda revisar espacio y políticas de conservación.

## Pruebas realizadas

- Pruebas de clasificación de consumos, traslados y requisiciones con bases SQLite temporales.
- Casos de preparación sin consumo, parcial, completa, insuficiencia de inventario, rechazo de duplicación, anulación integral y folios PDF.
- Prueba de inicialización y permisos con interfaz simulada sin conexión a producción.
- Renderizado y revisión visual de un PDF de salida con tres materiales y firmas (una página carta).

No se ha realizado una prueba end-to-end con la interfaz Streamlit real ni una prueba de carga concurrente con tres usuarios o PostgreSQL remoto en este entorno; debe completarse antes de liberar la versión productiva.

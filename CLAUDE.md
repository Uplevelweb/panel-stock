# Panel Oportunidades — Comercial Emergenza

App Streamlit para vender por Convenio Marco: muestra **qué compran las instituciones del
Estado**, lo cruza con lo que Emergenza vende y arma la cotización y el correo.
**Antes de editar, lee `BITACORA.md`** (decisiones tomadas, con fecha y motivo).

Publicada en https://panel-stock-uplevel.streamlit.app — **acceso restringido** a
`serlingvera@gmail.com` y `svera@emergenza.cl` (Manage app ▸ Settings ▸ Sharing).
Repositorio: `uplevelweb/panel-stock` (público, rama `main`).

## Quién la usa

Serling Vera, KAM Gobierno de Comercial Emergenza. **No es desarrolladora**: hay que
entregarle instrucciones numeradas, en español, con el nombre exacto del botón que debe
tocar. El código va siempre en `.txt` cuando tiene que copiarlo a otra parte (un `.html`
o `.gs` se le abre renderizado). No agregar funciones que no pidió: si conviene algo, se
propone aparte.

## Qué hace la app

**Pestaña «Mercado Público»**: elegir institución → ver qué compró, a qué precio y a
quién → marcar productos → PDF de cotización y correo.

**Pestaña «Módulo Cotizador»** (22-08): subir el requerimiento que mandó la institución
(`.xlsx`/`.csv`) → buscar cada producto en el catálogo → **cotizar solo lo publicado en esa
región**. Vive en `seccion_cotizacion_regional`.

**Se cruza por NOMBRE, no por ID**: la planilla de la institución trae su código interno
(`0130012`) y un nombre genérico (`MAICENA`), no ID de Convenio Marco. El diccionario
`SINONIMOS_PRODUCTO` traduce lo que ellos escriben a como se llama en el catálogo («maicena» →
«ALMIDÓN DE MAÍZ»); **hay que engordarlo cada vez que aparezca un producto que existe con otro
nombre**. El buscador propone y ella elige en una tabla con casillas, marcado el que mejor
calza y, entre iguales, el más barato. Las `sugerencia` nunca vienen marcadas.

El PDF muestra el **ID de Convenio Marco y la descripción del catálogo** (es con ese ID que el
comprador genera la compra); lo sin equivalencia va abajo como N/D. En pantalla se elige qué
muestra: precio (ninguno / oferta de la semana / mi precio publicado) y cantidad+total sí o no.

El catálogo trae la columna «REGIÓN» en sus cuatro pestañas. **«IP» y «JF» son Isla de Pascua
y Juan Fernández**: se tratan como zona propia, no como Valparaíso. **No trae columna de
precio**, así que el modo «mi precio publicado» avisa en vez de cotizar hasta que se le agregue
una columna «MI PUBLICADO».

La pestaña **«Análisis de compras»** (la hoja de Google que ella armaba a mano) se **deshabilitó
el 18-08**: el módulo nuevo la reemplaza. El código sigue ahí (`seccion_analisis_compras`,
`render_informe`) por si hay que volver a mostrarla; para eso basta reponer el `st.tabs` en
`main()`.

**La cotización sale separada por rubro**: si se marcan productos de Alimentos y de Aseo se
generan dos PDF y dos correos, porque cada convenio se compra aparte. Lo hace `propuesta()`, que
`cotizacion_y_correo()` llama una vez por rubro.

**El período manda**: la tabla muestra solo lo comprado dentro de las fechas pedidas, aunque el
barrido arrastre compras anteriores. Se elige con **atajos (7, 15, 30, 90 días, 1 año) o libre**;
los atajos terminan en el último día de la bodega, para que la consulta salga al instante.

**El convenio se elige ANTES de consultar**, en una lista que sale de la bodega (los convenios por
los que esa institución compró en ese período). Solo se puede cuando la respuesta viene de la
bodega: en vivo el convenio no existe y ahí reaparece abajo el filtro por rubro del catálogo.

**Lo que ve el comprador**: el PDF dice **INSTITUCIÓN**, no «cliente» —todavía no le compra— y el
asunto es «ID disponibles en Convenio Marco | Comercial Emergenza **2208-0306**», terminando en el
número de cotización. Con dos rubros, el documento lleva sufijo (`-ALI`, `-ASE`) pero el asunto
no.

## Archivos

| Archivo | Para qué |
|---|---|
| `app.py` | Toda la app |
| `bodeguero.py` | Baja Mercado Público cada madrugada y llena `bodega/` |
| `.github/workflows/bodega.yml` | La tarea nocturna que ejecuta el bodeguero (02:00 de Chile) |
| `bodega/` | Lo descargado: `mapa/AAAA-MM.parquet`, `detalle/AAAA-MM.parquet`, `unidades.parquet`, `estado.json` |
| `catalogo_unidades.csv` | Unidades compradoras (respaldo: la bodega lo amplía) |
| `requirements.txt` | streamlit, pandas, openpyxl, fpdf2, gspread, google-auth, **pyarrow** (la bodega es parquet) |
| `LogoVec.png` | Logo horizontal: cabecera y firma del correo |
| `icono.png` | El mismo logo en cuadrado: favicon y acceso directo del celular |
| `.streamlit/config.toml` | Tema oscuro + `baseFontSize = 13` |
| `enviador-para-copiar.txt` | Apps Script que envía los correos (uno por cuenta) |
| `licitador.py` | Hermano del bodeguero: baja las LICITACIONES a `bodega/licitaciones` |
| `alertador.py` | El correo diario de oportunidades (ver más abajo) |
| `modulo_alertas.py` | Pestaña «Alertas»: configurar el correo y ver antes qué llegaría |
| `modulo_oportunidades.py` | Pestaña «Oportunidades»: el mapa comercial por RUT |
| `modulo_mercado.py` | Los cuatro gráficos de barras del mercado, dentro de esa misma pestaña. Miran las **seis vías**, no solo Convenio Marco |
| `modulo_visitas.py` | El IPT: el itinerario de visitas y **la línea donde se deja de visitar y se empieza a llamar** |
| `modulo_cuentas.py` | Cuentas, roles y territorios (pestaña «Mi equipo»). Quién entró y qué le toca ver |
| `supabase-cuentas-para-copiar.txt` | El SQL de las tablas `cuentas` y `usuarios`. **Hay que pegarlo una vez** para que los roles empiecen a mandar |
| `supabase-soporte-para-copiar.txt` | El SQL del rol `superadmin` y la `bitacora_soporte`. Se pega **después** del anterior |
| `modulo_seguimiento.py` | El embudo: en qué quedó cada oportunidad que avisó el correo (pestaña «Seguimiento») |
| `supabase-seguimiento-para-copiar.txt` | El SQL de la tabla `seguimiento`, las `visitas` y la foto que `envios` guarda de cada oportunidad |
| `inspector_apis.py` | Mira qué traen de verdad las dos APIs. No envía ni escribe nada |
| `alertas-workflow-para-copiar.txt` | El workflow de las 08:00 |
| `bienvenida-workflow-para-copiar.txt` | El SQL de la columna + el workflow del primer correo |
| `disparador-instantaneo-para-copiar.txt` | El trigger que avisa a GitHub en el momento del alta |
| `modulo_planes.py` | **Qué abre cada plan.** Una sola fuente de verdad; no hacer otra lista |
| `alta-automatica-para-copiar.txt` | El SQL que crea la cuenta y el usuario al inscribirse |
| `supabase-alertas-para-copiar.txt` | El SQL de las columnas nuevas |
| `alertas_config.json` | Configuración de prueba local. **NUNCA subirlo: el repo es público** |
| `bienvenidas_enviadas.json` | A quién ya se le mandó el primer correo, en pruebas locales. **NUNCA subirlo: lleva correos de clientes** |
| `auth0-para-copiar.txt` | Los 9 pasos para encender el login propio. **NUNCA subirlo: lleva la clave de la sesión** |
| `Mis-instituciones.xlsx` | Punto de partida de la hoja «Mis instituciones». Todavía no se usa: pendiente de la bitácora |

## Cómo se actualiza

**Desde el 27-08-2026 se sube con `gh`, no a mano.** GitHub CLI quedó instalado y
autenticado como `Uplevelweb` (scopes `repo` y `workflow`), así que los commits los
puede hacer Claude directamente. `gh` **no está en el PATH**: hay que llamarlo por su
ruta o agregarla primero.

```bash
export PATH="$PATH:/c/Program Files/GitHub CLI"
```

El repositorio pesa 121 MB por la bodega, así que **no se clona entero**:

```bash
git clone --depth 1 --filter=blob:none --sparse https://github.com/uplevelweb/panel-stock.git
git sparse-checkout set --no-cone '/*' '!/bodega/'
```

Streamlit redesplega solo en 1-2 minutos.

**El camino manual sigue sirviendo** si `gh` no está disponible: **Add file ▸ Upload
files**, arrastrar el archivo con el mismo nombre, **Commit changes**. Para archivos
dentro de carpetas (`.streamlit/`, `.github/`) es más simple **Create new file** y escribir
la ruta completa en el nombre, que subir la carpeta.

⚠️ **Los secretos no los pone Claude, nunca.** `SUPABASE_URL` sí (es una dirección
pública), pero `RESEND_API_KEY` y `SUPABASE_SECRET_KEY` los carga ella: son claves.

Verificar después de subir, porque `raw.githubusercontent.com` sirve una copia en caché
por unos minutos y engaña:

```powershell
$b = Invoke-RestMethod "https://api.github.com/repos/uplevelweb/panel-stock/contents/app.py" -Headers @{"User-Agent"="c"}
[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($b.content)).Length
```

## Las tres fuentes de Drive (no confundirlas)

La app lee la carpeta compartida de Drive sin credenciales, con
`drive.google.com/embeddedfolderview?id=CARPETA#list` (devuelve HTML plano con los IDs de
archivo) y baja cada uno con `uc?export=download&id=`. Requiere que la carpeta esté compartida
por enlace. Si Drive devuelve HTML en vez de `.xlsx` es una hoja de Google: se baja por
`/export?format=xlsx`.

| Archivo | Qué trae | Para qué |
|---|---|---|
| `CATÁLOGO CONVENIO MARCO.xlsx` | **22.626 productos que ella vende**, sin precio, una pestaña por rubro (Alimentos, Aseo, Emergencia y Prevención, Escritorio) | decide **CON STOCK / NO LO TENGO** |
| `OFERTAS ... .xlsx` | ~840 productos **rebajados esa semana**, con precio | llena la columna **MI OFERTA** |
| La hoja de compras (Google Sheet) | El análisis que ella arma por institución | alimenta la pestaña «Análisis de compras» |

**El estado se decide contra el CATÁLOGO, nunca contra las ofertas.** Si el ID está en el
catálogo va CON STOCK aunque no tenga oferta, y MI OFERTA queda en blanco (un guión en el PDF).
Decidirlo por las ofertas dejaba fuera el 96% de lo que puede vender: en la Escuela Naval eran
7 productos en vez de 18, y entre los perdidos había ventas de $6 millones. **SIN STOCK no
existe** en el módulo de Mercado Público: el catálogo no dice si hay existencias.

**El ID no se llama "ID"** en esos archivos, sino "ID REGIÓN CM" o "ID CONVENIO REGIÓN".
`mapear_columnas` acepta cualquier encabezado que empiece con ID. Los encabezados tampoco están
en la primera fila: `detectar_fila_encabezado` los busca.

## La bodega (datos abiertos de ChileCompra)

`bodeguero.py` corre en GitHub Actions a las 02:00 y deja los datos en `bodega/detalle`. La app
los lee al instante y **sin gastar el ticket**.

**Desde el 21-08-2026 la fuente son los datos abiertos, no la API**:
`https://transparenciachc.blob.core.windows.net/oc-da/AAAA-M.zip` — un archivo por mes con
**todas** las órdenes de compra de Chile (~100 MB), actualizado a diario con un día de desfase,
disponible desde 2007. Bajar 2025-2026 entero pasó de **51 días a 54 minutos**, y además trae el
**convenio marco de cada orden**, que la API no entrega.

Estado actual: **1,29 millones de líneas de Convenio Marco, 20 meses, 35,4 MB en parquet.**

**Dos trampas del archivo, ambas costaron tiempo:**

- **`AAAA-1.zip` es ENERO, no el semestre 1.** Leyéndolo como semestral los números no cuadran.
- **`CodigoUnidadCompra` NO es el prefijo del código de la orden**: son dos identificadores
  distintos que **solo coinciden en el 37%**. Usando la columna del archivo, el cruce con el
  catálogo da **cero filas**. La unidad se saca del código (`2950-485-CM26` → `2950`).

**El bodeguero baja solo los dos últimos meses** en cada corrida (~5 minutos); los meses viejos
ya no cambian. Con `--completo` **vacía la bodega y rehace toda la historia** (~1 hora): sin
vaciarla, las líneas se suman a las que ya estaban y los montos salen inflados. Al terminar borra
los ZIP, que pesan 100 MB cada uno.

**`bodega/estado.json` es lo que mira la app para decidir si responde con lo guardado o va en
vivo.** Lo escribe `anotar_cobertura()` al final de cada corrida, con todos los días desde el
primer mes descargado hasta el último con compras. Si ese archivo no se actualiza, la app cree
que la bodega está casi vacía y consulta la API aunque el parquet esté ahí; su campo
`actualizado` es además el sello que suelta la caché. **No confundirlo con
`bodega/detalle/estado.json`**, que es la nota del bodeguero sobre qué meses procesó y la app no
lee.

**El convenio marco**: la columna `Codigo_ConvenioMarco` trae el código (`2239-9-LR24`) y el
nombre se pide una vez a `licitaciones.json` (~28 consultas), quedando en `bodega/convenios.json`.
Es el único uso que le queda al ticket. Si la consulta es en vivo el convenio no existe, y el
filtro cae al rubro del catálogo de ella.

- **La app funciona con y sin bodega.** Si el período pedido está completo, lee de la bodega; si
  le falta un día, consulta en vivo por la API y lo dice en pantalla.
- **`compras_desde_bodega` filtra por `dia`**, que en la bodega nueva es la **fecha de creación**
  de la orden. Así el período que ella pide es el período que ve.
- **El catálogo de unidades combina el CSV con la bodega**: el CSV tenía 2.103 unidades de 8
  días; con los datos abiertos son **4.211**.

`bodeguero_api_viejo.py.txt` guarda el bodeguero que consultaba la API, por referencia.

## API de Mercado Público (lo comprobado con el ticket real)

Base: `https://api.mercadopublico.cl/servicios/v1/publico/`

| Consulta | URL | Notas |
|---|---|---|
| OC de un día | `ordenesdecompra.json?fecha=DDMMAAAA` | ~16.000 órdenes de todo Chile, **2 MB**. Solo trae `Codigo`, `Nombre`, `CodigoEstado`. |
| **OC de un día en un organismo** | `ordenesdecompra.json?fecha=DDMMAAAA&CodigoOrganismo=NNNN` | Lo mismo filtrado: decenas de órdenes y **10 KB**, 200 veces menos. **Es lo que se usa.** |
| Detalle de una OC | `ordenesdecompra.json?codigo=XXXX` | Comprador (organismo, unidad, nombre del contacto), proveedor con RUT, items con producto, cantidad y precio, y totales. |
| Licitaciones | `licitaciones.json?fecha=DDMMAAAA` / `?codigo=...` | El detalle trae `Comprador.CodigoOrganismo`. |

`OrdenCompra.json` (el nombre que aparece en la documentación oficial) **da 404**: el detalle
se pide al mismo `ordenesdecompra.json` con `codigo`. `CodigoUnidad` **no existe** como
parámetro: responde 400. **No hay endpoint de convenios marco**: `conveniomarco.json`,
`convenios.json`, `catalogo.json`, `productos.json` y `conveniosmarco.json` dan 404.

**`fecha=` NO es la fecha de creación de la orden**: es el día en que la orden tuvo
**movimiento**. Un barrido de 6 días de cuatro unidades de la Armada devolvió 43 órdenes de
las cuales solo 6 estaban creadas en esos días; había 15 de septiembre y octubre de 2025. La
fecha de verdad está en el detalle (`Fechas.FechaCreacion`). Corolario: barrer los últimos N
días no garantiza traer todo lo creado en esos días (si el movimiento cae mañana, aparece
mañana).

**Filtrar por `CodigoOrganismo` es casi idéntico a filtrar el día completo, pero no del todo.**
Comparando 36 pares (organismo × día) con 6.199 órdenes, la consulta filtrada **perdió 5**
(0,08%): existen en el día completo, pertenecen a ese organismo —verificado en el detalle— y aun
así no vienen. Se sigue usando porque la alternativa cuesta 200 veces más datos, pero **no es
exhaustiva**: sirve para encontrar oportunidades, no para cuadrar cifras al peso.

**El código de la orden lo dice todo** y por eso no hace falta pedir detalles para filtrar:
en `1002772-4755-CM26`, `1002772` es la **unidad compradora** (= `Comprador.CodigoUnidad`) y
`CM26` el mecanismo y el **año del convenio** (no el de la compra: en agosto de 2026 aparecen
órdenes CM25 y CM24 vigentes). Mecanismos vistos en un día: SE 7.005, AG 6.322, **CM 2.070**,
TD 1.057, CC 121, CT 1.

**El ID de Convenio Marco viene entre paréntesis** al principio de
`Items.EspecificacionComprador` (`(4427537) GOMA DE BORRAR RHEIN...`) y es **el mismo número
de la columna ID de sus archivos**: es el puente entre las dos mitades de la app.

**Lo que la API NO da:** `Comprador.MailContacto` llegó vacío en las 55 órdenes revisadas
(`NombreContacto` sí viene siempre); `Items.Categoria` y `CodigoProducto` vienen siempre vacíos;
y el rubro del convenio aparece en el `Nombre` de la orden en solo 6 de 2.009 casos, porque lo
escribe el comprador a mano.

**CUIDADO CON LA CUOTA AGOTADA:** cuando se acaban las consultas del día, la API responde
**HTTP 203 (un código de ÉXITO)** con `{"Codigo":203,"Mensaje":"Ticket superó la cuota diaria
asignada."}`. Si no se detecta, pasa por respuesta buena y la app dice «no se encontraron
órdenes», que es mentira. Regla: **cualquier respuesta sin `Listado` pero con `Mensaje` es un
fallo**, no un resultado vacío.

**Límites:** 10.000 consultas diarias por ticket, y **una sola consulta a la vez**: dos
procesos con el mismo ticket se estorban y devuelven 429. El 429 y los 500/502/503 son
pasajeros y se resuelven reintentando con espera creciente. Agotado el cupo diario, la API
responde **500** sin decir por qué. ChileCompra pide hacer las descargas grandes entre 22:00 y
07:00. La API responde al menos hasta enero de 2023.

**Para comercializarlo, cada cliente necesita su propio ticket**: por los términos (es personal
y se monitorea por IP) y por lo técnico (una consulta a la vez). Riesgo asumido: el bodeguero
consulta desde servidores de GitHub, no desde su IP.

## El correo diario de oportunidades (`alertador.py`)

Sale a las 08:00 de Chile, de lunes a viernes, desde GitHub Actions. **No escribe
nada en el repositorio**: los suscriptores viven en Supabase, y el repo es público.

Se prueba entero **sin gastar el ticket**, tratando las licitaciones más nuevas
de la bodega como si fueran de hoy:

```powershell
python alertador.py --prueba --guardar correo.html
```

**La identidad es el correo, no el RUT.** `suscriptores.email` es único y es el
respaldo del consentimiento. El RUT es un atributo del filtro y puede ir vacío.
`filtros.correos_envio` agrega destinatarios al **mismo mensaje**: tres personas
de una empresa gastan un envío de los 100 diarios, no tres.

**Las tres maneras de filtrar terminan en una sola bolsa de palabras:** el RUT
la rellena solo (de los productos que ese RUT ya vendió en Convenio Marco), los
rubros y las palabras clave la rellenan a mano. Se combinan.

### Lo comprobado contra las APIs reales (26-08-2026)

- **El listado de activas trae CUATRO campos**: `CodigoExterno`, `Nombre`,
  `CodigoEstado`, `FechaCierre`. Ni descripción, ni región, ni comprador. Por eso
  el alertador filtra primero por el nombre y solo a las que sobreviven les pide
  el detalle (de 4.580 quedaron 240), con los 2 segundos de espera obligatorios.
  El detalle sí trae `Comprador.CodigoUnidad`, `RegionUnidad` y `ComunaUnidad`.
- **La API de compras ágiles entierra las filas en `payload.items`**, no en la
  raíz: la respuesta es `{success, trace, payload, errors}`. Buscar la lista solo
  en el primer nivel devuelve vacío sin error.
- **`tamano_pagina` debe estar entre 10 y 50.** Con 5 responde 400.
- **Hay ~8.900 compras ágiles publicadas** en cualquier momento (890 páginas de
  10). No se piden todas: el correo diario usa `publicado_desde`.
- **Esa API se cae sola con `504 Endpoint request timed out`** (pasó en la página
  6). Sin reintentar, el correo sale con la mitad y no hay error que lo delate.
- **`institucion.region` es un número** (13); el nombre está en `nombre_region`.
- **En la bodega de licitaciones, `codigo_onu` es el número del rubro**
  (`80141607`); el nombre legible está en `rubro1`.

### Las dos trampas del filtrado, ambas encontradas probando

- **El umbral de coincidencias NO puede ser fijo**, y costó dos días de correos
  vacíos descubrirlo. Con el RUT salen ~87 términos automáticos y llenos de
  relleno: ahí exigir 3 filtra bien (con 1 entraban «plantas de pera» y «CCTV del
  Metro»). Pero dos suscriptoras reales con 5 y 6 palabras **escritas a mano** se
  quedaron en 3 y 5 términos, y el mismo 3 exigía que casi todas aparecieran en
  la misma licitación: **cero correos, sin ningún error visible**. Ahora
  `minimo_coincidencias()` escala —hasta 10 términos basta 1, hasta 30 son 2, más
  arriba 3— y con 15 o menos no se quita ninguna palabra por «común». Una palabra
  que alguien se tomó el trabajo de escribir vale más que una sacada de un
  catálogo. Probado: con «alimentos, aseo, papelería, abarrotes, limpieza» pasa
  de 0 a 15 aciertos, todos reales.
- **Las palabras de la bolsa del RUT** tienen que aparecer en al menos 3 productos
  distintos del proveedor: una palabra que sale en un solo producto describe ese
  producto, no el negocio.
- **Ordenar por la PRIORIDAD pone arriba lo que no tiene nada que ver.** La
  PRIORIDAD mide al **comprador** (cuánto gasta, qué tan repartido está), no si
  la oportunidad le sirve al proveedor. Un comprador que no aparece en la bodega
  saca nota baja aunque la licitación le calce perfecto: así «ALIMENTOS Y BEBIDAS
  ANIVERSARIO PATRIO» quedaba última con nota 1 y arriba iba un servicio de
  teleasistencia. **Ordena el encaje; la nota solo desempata.**

### El correo va agrupado por tipo

Compras ágiles primero —cierran en 24-72 horas— y licitaciones después, cada
grupo con su título y su cuenta. No mezclados: son dos cosas distintas y se
actúa distinto.

### La cabecera del correo va BLANCA

El logo de Uplevel tiene fondo blanco. Sobre el azul marino deja un recuadro y
se ve pegoteado. La cabecera es blanca con el nombre en marino, y el color de
marca lo pone una franja naranja de 3px debajo.

### La memoria de lo avisado

Una licitación abierta sigue abierta una o dos semanas. Sin anotar lo enviado, el
correo repite lo mismo cada mañana. Se registra en `envios` (o en
`envios_enviados.json` en pruebas locales) **después** de que el envío salió: si
falla, esas oportunidades tienen que poder salir mañana.

### ⚠️ Manejar el navegador de Serling: qué sí y qué no

Comprobado el 28-08-2026 sobre tres paneles distintos (GitHub, Supabase, Auth0):

- **SÍ funciona:** apretar botones, marcar casillas, elegir de listas desplegables.
  El formulario del token de GitHub se llenó entero así.
- **NO funciona: escribir en campos de texto.** Ni tecleando por coordenada ni
  fijando el valor por elemento (`form_input` devuelve `Set text value to ""`).
  Falló en el nombre del token de GitHub, en el editor SQL de Supabase y en los
  campos de Tenant Settings de Auth0.
- **Los clics por coordenada se desvían** en Supabase y Auth0: el marco de la
  captura no calza con el de la página y terminan en el botón de al lado. En
  Supabase abrieron dos veces el panel «Connect» sin querer. Ahí conviene parar:
  es una base de producción.
- **Moraleja operativa:** cualquier cosa que se escriba —SQL, claves, nombres—
  la pega ella. Lo que se aprieta se puede automatizar. Y para diagnosticar
  GitHub sirve más `gh` desde el computador que el navegador.


### ⚠️ El reloj NO es el de GitHub

**`schedule:` en GitHub Actions es «cuando se pueda», no «a esta hora».** Medido el
28-08-2026 sobre las tres primeras corridas reales: el turno de las 08:00 corrió a
las 17:45, el de las 13:00 a las 21:13, el de las 18:00 a la 01:53 del día
siguiente. Entre 7 y 10 horas de atraso, consistente. En repositorios públicos la
cola tiene la prioridad más baja y GitHub lo documenta: no hay nada que configurar.

Eso mataba el argumento central del producto —«las ágiles cierran en 24 a 72 horas:
si no te enteras el mismo día, se pasó»—, así que **el reloj se mudó a Supabase**
(`pg_cron` + `pg_net`), que sí es puntual. El SQL está en
`reloj-supabase-para-copiar.txt`.

- Supabase solo **da la orden de partida**; GitHub sigue haciendo el trabajo pesado.
- **Los workflows disparados por el reloj no llevan `schedule:` propio.** Si lo
  llevan, se disparan dos veces: una puntual y otra horas tarde.
- La llave de GitHub vive en el baúl de Supabase (`vault`), nunca en el SQL ni en
  el repositorio.
- Para ver si el reloj corrió: `select * from cron.job_run_details order by
  start_time desc limit 10;`. Para ver qué contestó GitHub: `select status_code from
  net._http_response order by created desc limit 3;` — **204 es el «recibido»**.


### El primer correo, al inscribirse

`alertador.py --bienvenidas` manda el correo a **quien nunca ha recibido nada**.
Lo dispara `.github/workflows/bienvenida.yml` cada 15 minutos, y el instructivo
está en `bienvenida-workflow-para-copiar.txt`.

- Es **el mismo camino** que el correo diario, no una copia: mismas tarjetas,
  mismo `anotar_avisado`. Solo cambian el bloque de arriba («Tu cuenta quedó
  lista» en vez de «Oportunidades de hoy»), el asunto, y que mira **una semana**
  de compras ágiles en vez de un día, para que no llegue casi vacío.
- **Un primer correo vacío mata la impresión.** Si nada alcanza el mínimo de
  coincidencias, se baja el listón a 1 una sola vez y van las mejores cinco.
  Esa relajación **solo ocurre en la bienvenida**, nunca en el diario.
- La marca vive en `suscriptores.bienvenida_enviada` y se escribe **después** de
  enviar, igual que lo avisado. Si el envío falla, esa persona sigue en la cola.
- El workflow son **dos trabajos**: uno pregunta con un `curl` de dos segundos y
  el otro —el que baja los 121 MB del repositorio— solo despierta si hay alguien.
  Sin eso serían 96 descargas diarias para descubrir que no hay nadie.
- ⚠️ **Al crear la columna hay que marcar a los suscriptores que ya existen**
  (`update suscriptores set bienvenida_enviada = now() where ... is null`). Sin
  eso, la primera corrida les manda a todos una bienvenida que no esperaban.


- **Dos caminos disparan la bienvenida, a proposito.** El trigger
  `al_inscribirse` avisa en el instante del alta (`after insert`, nunca puede
  tumbar la inscripcion: si falla, avisa y deja pasar). El reloj de cada 5
  minutos queda como red de seguridad. **No sacar el reloj**: sin el, un aviso
  perdido deja a esa persona sin su primer correo para siempre.
- **El trigger es `after insert`, asi que no ve las re-inscripciones.** Quien se
  inscribe con un correo que ya existe actualiza su fila y no dispara nada —
  correcto, ya recibio su bienvenida—. Confundio a Serling el 29-08-2026.
- ⚠️ **`bienvenida.yml` lleva `concurrency` y no se le puede sacar.** El reloj
  dispara cada 5 minutos y el trabajo demora ~15: sin eso se apilan corridas y
  **cada una manda su propio correo a la misma persona**. Pasó el 29-08-2026:
  hubo tres en vuelo a la vez y se cancelaron dos a mano. Con `cancel-in-progress:
  false` la nueva espera, y al arrancar su `mirar` vuelve a preguntar — si la
  primera ya marcó `bienvenida_enviada`, termina en segundos sin bajar nada.
- **Cuánto demora, medido el 29-08-2026:** 14 min 32 s de punta a punta. La
  landing promete «en unos minutos»; está estirado pero es defendible. Si hay que
  acortarlo, la palanca es `dias_agiles` (hoy 7 para la bienvenida, 1 para el
  diario): menos días, menos peticiones a la API, menos material.

### ⚠️ El límite que decide a quién se le puede vender

**La bodega guarda SOLO órdenes de Convenio Marco** (`bodeguero.py` descarta todo
código que no termine en `CM`). Consecuencia directa, comprobada en la primera
corrida real del 27-08-2026:

| Cliente | Encuentra oportunidades | Dice cuánto gasta el comprador |
|---|---|---|
| Proveedor de Convenio Marco (Emergenza) | ✅ | ✅ el diferenciador completo |
| Proveedor fuera de CM (software, obras) | ✅ | ❌ sin historial: sale «PRIORIDAD D · 0» |

Con palabras clave de software, las cuatro oportunidades salieron en D con gasto
cero. **No es un fallo del cálculo**: es que esas licitaciones no son Convenio
Marco y la bodega no tiene con qué cruzarlas. Para venderle a proveedores fuera
de CM hay que ampliar la bodega a **todas** las órdenes de compra.

### Resend

Plan gratis: **3.000 al mes con tope de 100 al día**. El tope diario es el que
traba. `TOPE_DIARIO` lo respeta desde el código en vez de descubrirlo a mitad de
la tanda. Plan Pro: USD 20/mes por 50.000.

## Secretos y acceso

En **Streamlit ▸ Manage app ▸ Settings ▸ Secrets** (nunca en GitHub):

```toml
[correo]
clave_envio = "..."                  # la misma que está dentro de los dos Apps Script

[correo.scripts]
"svera@emergenza.cl" = "https://script.google.com/macros/s/.../exec"
"serlingvera@gmail.com" = "https://script.google.com/macros/s/.../exec"

[mercadopublico]
ticket = "..."

# Para que la pestaña «Alertas» pueda guardar la configuración.
[supabase]
url = "https://nvjmgpmvhrodirykoirq.supabase.co"
secret_key = "sb_secret_..."
```

La clave secreta de Supabase en los secretos de Streamlit **no contradice** la
regla de «solo en GitHub Actions»: los secretos de Streamlit son del servidor,
no llegan al navegador, y la app tiene acceso restringido. Lo que nunca puede
pasar es que esa clave llegue a una página web o al repositorio.

Mientras se desarrolla, el ticket está en `C:\Users\serli\ticket-mp.txt`, **fuera del proyecto a
propósito** para que no pueda subirse por error.

### El seguimiento: en qué quedó cada oportunidad (27-08-2026)

Hasta ahora el correo mandaba y se olvidaba. `envios` guardaba que algo salió,
no qué pasó después, y por eso **no se podía decir «esto te consiguió $X»** —
que es la frase de la que depende que alguien renueve.

Seis etapas: *por revisar · siguiendo · ofertando · ganada · perdida ·
descartada*. **«Por revisar» no se guarda en ninguna parte**: es no tener fila
en `seguimiento`. Así el embudo funciona desde el primer día, incluso con lo
que se envió antes de que la tabla existiera, y no se escribe una fila por cada
correo que sale.

**La llave es el RUT, no el usuario**, porque el seguimiento es de la empresa:
si el comercial del norte marca una como «ofertando», su jefa lo ve sin
preguntar. Igual se guarda `quien` la movió.

`alertador.py` guarda ahora la **foto** de cada oportunidad al enviarla
(nombre, comprador, monto, cierre, y las palabras exactas por las que calzó).
Sin eso, dibujar esta pantalla obligaría a volver a preguntarle a la API:
ticket gastado por datos que en ese momento ya estaban en la mano.

La urgencia **se calcula y depende del tipo**: una compra ágil que cierra en 20
horas es normal —se contesta con un precio—, una licitación que cierra en 20
horas ya no se alcanza a preparar. Avisar «cierra pronto» sin distinguirlas es
mandar a alguien a perder la tarde.

### Quién entra y qué ve (27-08-2026)

Son **dos cosas distintas y conviene no confundirlas**:

- **Quién puede ABRIR el panel** lo decide `modulo_cuentas.puerta()` **si existe el
  bloque `[auth]` en los secretos**; si no existe, sigue decidiéndolo la lista de
  Streamlit (*Manage app ▸ Settings ▸ Sharing*) y nada de lo de abajo se nota. Los
  pasos para encenderlo están en `auth0-para-copiar.txt` (**local, nunca al repo:
  lleva la clave de la sesión**). Si el login se rompe, el arreglo son 30 segundos:
  **borrar el bloque `[auth]` de los secretos** y todo vuelve a la lista de antes.
  - `st.user.is_logged_in` **revienta con AttributeError** si la identificación no
    quedó bien configurada, en vez de devolver `False`. Por eso se pregunta por
    `_entro()` y nunca directo: una coma mal puesta en los secretos tumbaría el
    panel entero.
  - **`st.user` ya no trae el correo de la cuenta de Community Cloud** (cambió en
    Streamlit 1.42). Sin `[auth]` no hay identidad, y por eso hoy el panel se ve
    entero y la pestaña Soporte no aparece nunca.
  - **`st.login()` necesita DOS librerías que no vienen con Streamlit**, las dos en
    `requirements.txt`: `Authlib` y `httpx`. Sin la primera, apretar el botón tumba
    el panel con `StreamlitMissingAuthlibError`; sin la segunda —que Authlib declara
    como opcional y no instala sola— sale `Internal server error.` en pantalla y
    `ModuleNotFoundError: No module named 'httpx'` en el registro. Las dos revientan
    **al apretar entrar**, no al volver de Auth0: si el error aparece ahí, no es la
    configuración del proveedor. Ojo: tocar `requirements.txt` hace que Streamlit
    rearme el ambiente entero — 3 a 5 minutos, no los segundos de un cambio de código.
- **Qué MÓDULOS ve** lo decide `modulo_planes.py` con `cuentas.plan`. Cuatro reglas
  que conviene no romper:
  - **Falla abierto.** Plan vacío, desconocido o consulta caída ⇒ `soporte`, ve todo.
    Dejar a un cliente que paga sin su pestaña es mucho peor que mostrar de más.
  - **La pestaña cerrada NO se esconde:** dice qué es y en qué plan viene. Es la
    única publicidad que se lee, porque la mira alguien que ya está adentro.
  - **Mercado Público y Cotizador son la excepción y sí se esconden.** Leen el Drive
    de Emergenza, no le sirven a otro cliente y no están a la venta. Se dan por
    cuenta con `modulos_extra`, nunca por plan.
  - **El IPT vive dentro de Mercado, que vive dentro de Oportunidades.** Su candado
    está en `modulo_mercado.py` y lee a quien entró de `st.session_state["yo"]`,
    que lo deja `app.main()`. Arrastrarlo por tres firmas era peor.
- ⚠️ **La cuenta de Uplevel necesita `plan = 'soporte'`** o pierde Mercado Público y
  el Cotizador. `es_soporte()` mira el ROL y no salva eso: son cosas distintas.
- **El muro del fin de prueba** vive en `modulo_planes.muro_de_prueba()` y se dibuja
  ANTES de las pestañas, en `app.main()`. Dos extensiones de 10 días, y **cada una se
  paga con un dato**: el teléfono la primera, el motivo la segunda. Diseño de Serling:
  un vencimiento normal solo pierde clientes; este los convierte en una conversación.
- **El aviso de que se acaba viaja también en el correo diario**, a falta de 3 días
  o menos (`alertador.dias_de_prueba` + el bloque naranjo de `armar_correo`). La
  franja del panel solo la ve quien entra, y el que hay que recuperar es justo el
  que no entra. **Falla abierto:** si la consulta se cae o la columna `hasta` no
  existe todavía, el correo sale igual, sin la franja.
- **La identidad tolera que las columnas nuevas no existan.** `_buscar_usuario` pide
  primero `hasta,extensiones,modulos_extra` y, si PostgREST responde error porque
  todavía no están, vuelve a preguntar por lo mínimo. Así no importa el orden entre
  pegar el SQL y subir el código: sin las columnas el panel funciona igual, solo que
  sin muro ni módulos extra.
- **Qué ve cada uno adentro** lo decide `modulo_cuentas.py` contra las tablas
  `cuentas` y `usuarios` de Supabase. Tres roles: el `superadmin` es Uplevel y
  ve todas las cuentas; el `admin` ve toda su empresa; el `comercial` solo su
  territorio (regiones, o comunas si hay que partir la Metropolitana entre dos
  personas).

**Nadie tiene contraseña**, y eso cambia qué significa «desbloquear». Se entra
por correo, así que «se me olvidó la clave» no existe. Los bloqueos reales son
otros: una empresa que desactivó a su único `admin` y desde adentro no tiene
salida, o un correo mal escrito que deja a alguien afuera sin ningún mensaje
que lo explique. Eso lo arregla la pestaña **🛟 Soporte**, que solo le aparece
al `superadmin` y deja huella en `bitacora_soporte` — el soporte puede entrar a
los datos de cualquier cliente y ese poder sin registro no se le puede explicar
a nadie. La regla `dejaria_sin_admin()` impide que la herramienta que existe
para sacar de un bloqueo pueda meter en uno.

Mientras la puerta sea la lista de Streamlit, **agregar un comercial son dos
pasos**: en la pestaña «Mi equipo» y en esa lista. Para vender el plan Empresa
de verdad hay que cambiar la puerta por un login propio —Streamlit 1.61 ya trae
`st.login()` / `st.user`, que es de donde el módulo saca el correo—; el módulo
no cambia, solo se agrega el bloque `[auth]` a los secretos.

**La regla, partida en dos.** *Qué ve* cada uno falla **abierto**: si las tablas no
existen, si faltan credenciales o si la consulta falla, se ve todo — un sistema de
permisos que se cae cerrado convierte cualquier problema chico en «hoy no puedo
trabajar». Pero *quién entra* falla **cerrado**, y es lo único del panel que lo
hace: cuando la puerta es la app, dejar pasar a un desconocido es dejarlo entrar a
la cartera de clientes. La salida a ese candado es `[acceso] siempre` en los
secretos: los correos de Uplevel entran aunque Supabase esté caído.

## Lo que no es evidente y cuesta caro olvidar

- **El tema (colores y tamaño de letra) solo se puede definir en `.streamlit/config.toml`**,
  no desde el código. Si ese archivo no está en GitHub, la app se ve en claro y descuadrada.
- **No usar selectores CSS amplios** como `[class*="st-"]` con `font-family`: los iconos de
  Streamlit son ligaduras de Material Symbols y se ven como texto (`keyboard_double_arrow_left`)
  encima de la pantalla. Hay una regla de seguridad que les devuelve su fuente.
- **El orden de las reglas CSS importa**: `@media` con la misma especificidad tiene que ir
  **al final**, o la regla general lo pisa (pasó con el tamaño del título en el celular).
- **Las columnas numéricas van como números** (`Int64`), no como texto con `$`: si van como
  texto, la tabla ordena "11" entre "1" y "2". El formato con separador de miles lo pone
  `column_config` con `format="localized"`, que respeta el idioma del navegador.
- **La selección de filas se limpia antes de usarla** (`filas_seleccionadas`): si se marcan
  filas y luego se cambia el filtro o se reordena, las posiciones guardadas ya no existen y
  `iloc` reventaba con TypeError. Lo mismo con los `multiselect` cuyas opciones cambian: hay
  que sanear `session_state` **antes** de dibujarlos.
- **`@st.cache_data` sin `ttl` también guarda los fracasos, y para siempre.** Pasó al publicar:
  la app arrancó antes de que `catalogo_unidades.csv` estuviera subido, guardó "no existe" y
  siguió diciendo que faltaba aunque ya estaba. Se arregló dejando la comprobación de existencia
  **afuera** de la caché y usando la fecha del archivo como llave.
- **Un argumento que empieza con guion bajo queda FUERA de la llave de la caché** en Streamlit.
  Si la llave es la fecha del archivo, llamarla `_fecha` anula todo el mecanismo sin avisar.
- **El ticket viaja pegado en la URL de cada consulta**, así que ningún mensaje de error puede
  mostrar la URL. Por eso `consultar_mp` atrapa todo y vuelve a levantar el error con un texto
  propio (`from None`).
- **Google recorta los nombres de pestaña a 31 caracteres** al exportar el libro, así que
  "Escuela Naval Ultimo Semestre 2025" llega sin el año. `sugerir_pestana` lo resuelve
  buscando palabras de período.
- **El buscador de unidades busca palabras sueltas y también en el organismo.** Las dos cosas
  son necesarias: buscando la frase pegada, «servicio oceano» no encontraba «SERVICIO
  HIDROGRÁFICO Y OCEANOGRÁFICO»; y buscando solo en el nombre de la unidad, «municipalidad
  valparaíso» no encontraba nada, porque **16 de las 21 unidades de municipios** se llaman
  «Dirección de Salud» o «EDUCACION».
- **El envío de correo NO usa SMTP.** Se descartaron las contraseñas de aplicación porque el
  administrador de emergenza.cl puede bloquearlas. Se hace POST a un Apps Script instalado
  en cada cuenta, implementado como aplicación web con acceso "Cualquier persona" (por eso
  la clave viaja en el cuerpo). Verificar un enviador sin mandar nada: abrir su `/exec` en el
  navegador, responde `{"ok":true,"cuenta":...}`.
- **`st.set_page_config(page_icon=...)` solo cambia el favicon.** Para que el acceso directo del
  celular muestre el logo hace falta `apple-touch-icon`, que se inyecta con `st.markdown`.
- **El servidor de Streamlit corre en UTC, no en hora de Chile.** Después de las 20:00 de acá,
  `date.today()` ya devuelve el día siguiente. Proponía consultar hasta una fecha que en Chile
  todavía no existía.
- **La bodega SIEMPRE va un día atrás**: los datos abiertos se publican con un día de desfase, así
  que «hoy» nunca está guardado. Y como la regla es **todo o nada** (si falta un día del rango, se
  consulta en vivo el rango entero), ese único día mandaba 234 días a la API: minutos de espera y
  234 consultas del ticket teniendo el dato en disco. Por eso el período se propone **hasta donde
  la bodega llega**, no hasta hoy.
- **Un atajo de período solo debe aplicarse cuando ella lo cambia.** Aplicándolo en cada dibujado,
  mover una fecha a mano la devolvía sola a su lugar.
- **El valor inicial de un widget va en `session_state` o en `value=`, nunca en los dos.** Si algo
  más escribe esa llave (los atajos escriben `mp_periodo`), Streamlit reclama en el registro.
- **La app publicada se duerme** por inactividad: al abrirla aparece "Zzzz" y hay que
  despertarla. Es el plan gratuito.
- **⚠️ El techo de memoria de Streamlit son ~1.000 MB, y pasarse NO deja traceback.** El proceso
  muere, el registro se queda en «Updated app!» y la pantalla dice «Oh no. Error running app»:
  exactamente lo que se ve cuando hay un error de código, pero sin ninguna pista. **Si el
  registro no tiene traza, es memoria.** Pasó el 27-08-2026 al ampliar la bodega a las seis
  vías (de 1,2 a 8,3 millones de líneas).
- **La bodega se lee en UN solo lugar: `alertador.resumen_de_ordenes`**, y una sola
  `@st.cache_data` la guarda (`modulo_oportunidades.cargar_compras`). **No hacer otra caché de
  la bodega.** `st.tabs` dibuja TODAS las pestañas en cada corrida, así que dos cachés se
  llenan siempre aunque nadie abra esa pestaña, y `@st.cache_data` además **devuelve una copia
  en cada llamada**. Esa función no devuelve líneas sueltas: viene **resumida** —una fila por
  comprador-vía-convenio-proveedor, con `total` y `lineas`—, que es el 22% de las filas con la
  misma plata. Quien necesite contar órdenes usa `lineas`, no `len()`.
- **Después de un cierre por memoria hay que REINICIAR la app**, no basta con subir el arreglo:
  Streamlit sigue mostrando «Oh no» aunque despliegue el código nuevo. *Manage app ▸ ⋮ ▸ Reboot
  app* (o el mismo menú en share.streamlit.io).
- **`convenio_marco = "NA"` no es un convenio**: es lo que traen las órdenes que no son de
  Convenio Marco. Si entra en una lista de convenios, `isin` se lleva todas las compras de las
  otras cinco vías. Se filtra con `modulo_oportunidades.convenios_de()`.

## Verificación antes de entregar

Las pruebas viven en el scratchpad de la sesión, no en el repo. Cinco suites: funciones del
módulo de Mercado Público, tabla agrupada por producto, caché del catálogo, lectura de la
bodega e interfaz completa. Cubren además lo del panel de siempre: filtros y columnas,
comentarios de oportunidad, números en formato chileno, PDF (con y sin precios, texto largo),
correo (saludo por género, asunto, firma según la cuenta) y enviador contra un servidor de
mentira.

**Los números de las pruebas no deben ser fijos si dependen de la bodega**, que crece cada
noche: se comprueba la propiedad («la primera es la que más compra»), no el valor.

Para el PDF hay que mirarlo, no solo generarlo: `pypdfium2` lo convierte a PNG y así se
detectan los defectos visuales (el logo montado sobre el texto, la tabla pintada de azul, el
título cortado en dos líneas: los tres aparecieron así).

El navegador de estas sesiones **no dibuja la tabla de Streamlit** (es un canvas y el panel no
compone imagen), así que la selección de filas y los colores de la tabla los tiene que
confirmar ella. Por lo mismo **tampoco se pueden elegir opciones en los desplegables**: la
lista es virtualizada y sin compositor llega vacía. Sí sirve `javascript_tool` para medir el
CSS aplicado (ancho, centrado, tamaño de letra, desborde en celular).

Para probar la interfaz de verdad (elegir unidades, apretar el botón, leer lo que quedó en
pantalla) se usa **`streamlit.testing.v1.AppTest`**, que corre la app entera sin navegador:

```python
from streamlit.testing.v1 import AppTest
app = AppTest.from_file("app.py", default_timeout=180).run()
app.selectbox(key="mp_region").set_value("Región de Valparaíso").run()
app.multiselect(key="mp_unidades").set_value(["2950"]).run()
app.button(key="mp_consultar").click().run()
```

Las tablas se buscan **por sus columnas, no por su posición** (`app.dataframe[-1]` se rompió al
cambiar el orden de las pestañas).

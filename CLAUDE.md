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

**La tabla de abajo, «Quién compra qué, y en qué meses»** (03-09-2026,
`seccion_quien_compra_que`): una fila por producto **de su catálogo** y una columna por unidad
compradora. Se dibuja sola al final del módulo con lo que quedó de la consulta —no tiene
filtros propios, hereda los de arriba— porque así lo pidió Serling: «que se genere
automáticamente al extraer la data».

- **En la celda van los MESES, no la cantidad de veces**: `FEB · MAR×2 · JUL`. Idea de ella, y
  es mejor que el número: saber que compra en marzo dice **cuándo llamar**; saber que compró
  tres veces, no. Se cuenta por mes del **calendario** —dos marzos de años distintos suman
  ×2—, porque lo que busca es la estacionalidad. Y se cuentan **órdenes distintas**, no líneas.
- **El encabezado lleva la suma de OC** de esa unidad (`ESCUELA NAVAL (387 OC)`): en una
  pasada se ve quién compra más (encabezado) y cuándo compra (celda).
- **Máximo 20 columnas de unidad** (`TOPE_COLUMNAS_UNIDAD`), las que más órdenes tienen. ⚠️ Las
  demás **no se pierden**: van juntas en «otras (n)» y **sus compras siguen sumadas** en MONTO,
  OC y P. PROM. Esto se le explicó y lo confirmó; no cambiarlo por un recorte de verdad.
- **PRODUCTO va fijo** (`pinned`, con guarda `ACEPTA_FIJAR`): con 20 columnas la tabla se va de
  lado y sin eso no se sabe de qué fila son los meses. Es lo que la hace usable en el celular,
  que ella pidió expresamente («aunque sea ajustada, y si desea más que amplíe la vista» — para
  ampliar está el ⛶ nativo de la tabla).
- **MI PRECIO sale de `cargar_catalogo_regional`**, el mismo lector del Módulo Cotizador, que ya
  está cacheado: no cuesta una lectura más de Drive. **Falla abierto**: si no se puede leer, la
  tabla sale igual sin esa columna.

**La cotización sale separada por rubro**: si se marcan productos de Alimentos y de Aseo se
generan dos PDF y dos correos, porque cada convenio se compra aparte. Lo hace `propuesta()`, que
`cotizacion_y_correo()` llama una vez por rubro.

**El período manda**: la tabla muestra solo lo comprado dentro de las fechas pedidas, aunque el
barrido arrastre compras anteriores. Se elige con **atajos (7, 15, 30, 90 días, 1 año) o libre**;
los atajos terminan en el último día de la bodega, para que la consulta salga al instante.

**El convenio es el PRIMER filtro de la pantalla, arriba de Región** (03-09-2026, pedido de
Serling): se parte de «quiero ver Alimentos» y recién después se elige dónde mirar. Antes
estaba al final, debajo de las fechas.

**Siempre se nombra por su NOMBRE, nunca por el código** (`2239-9-LR24`): el número no le dice
nada a nadie. Los nombres viven en `bodega/convenios.json`, que el bodeguero llena
preguntándole una vez a la API por cada código que ve — **28 códigos y 26 nombres al
03-09-2026, ninguno vacío**. La lista del selector se arma solo con los nombres: un código sin
nombre no aparecería ahí (sí en la tabla y en el aviso de «compró por», que muestran el código
crudo). Si algún día pasa, el arreglo es agregarlo al archivo: el bodeguero **fusiona y no
pisa**, así que escribirlo a mano es permanente.

⚠️ **`bodega/convenios.json` es de los archivos que se desactualizan en la copia local.** El
03-09-2026 la copia de trabajo tenía 24 códigos y el repositorio 28: se dio por «faltan dos
nombres», se gastaron dos consultas del ticket pidiéndolos y el commit **habría borrado dos
nombres buenos**. Lo atajó mirar el `git diff` antes de empujar. Es la misma regla de los
workflows: **preguntarle al repositorio, no a esta carpeta.**

```bash
gh api repos/uplevelweb/panel-stock/contents/bodega/convenios.json --jq '.content' | base64 -d
```

Como el selector va arriba, su lista es la de **todos los convenios conocidos**, no la de los
que compró esa institución —a esa altura todavía no hay institución elegida—. Eso permite
pedir un convenio que esa unidad nunca compró, y por eso más abajo, ya con las unidades y el
período, **se avisa antes de consultar** («no compró nada por X · compró por: Y, Z») en vez de
devolver una tabla vacía que parece una consulta fallida. Si el período se va en vivo, el aviso
dice que el filtro no se aplicará: la API no entrega el convenio y ahí manda el rubro del
catálogo.

⚠️ **CADA OPCIÓN LLEVA EL AÑO DEL CONVENIO, y no es decorativo.** Un mismo rubro tiene varios
convenios con nombres parecidos y de años distintos: «Convenio Marco de Alimentos» es el de
**2017** y «Convenio Marco para la adquisición de Alimentos» el de **2024**. Sin el año se leen
igual, y elegir el viejo devuelve una tabla vacía sin que se entienda por qué — le pasó a
Serling el 03-09-2026 consultando la Armada, y fue ella la que pidió el año. Pasa lo mismo con
gas licuado, mobiliario, vehículos y ofimática.

El año sale del código (`-LR24` → 2024) con `anios_de_convenios()`, y lo pinta `con_anio()` en
los tres lugares donde aparece un convenio: la lista, el aviso de «sí compró por» y el
encabezado del resultado. **Lo que se guarda y con lo que se filtra sigue siendo el nombre
pelado** (es lo que trae la columna `CONVENIO`); el año es solo lo que se ve, con `format_func`.
Un nombre con dos años («Escritorio y Papelería · 2023, 2024») los muestra los dos y filtra los
dos, que es lo correcto.

⚠️ **El «NA» no es un convenio y no puede aparecer en ninguna lista.** Es lo que traen las
órdenes que no son de Convenio Marco. Se coló en el aviso de «compró por» hasta el 03-09-2026.
`convenios_del_periodo` lo saca ahora, con la misma regla que `alertador.convenios_de`.

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
| `mis_productos.py` | El catálogo del cliente. **Se lee solo del Drive**, del archivo «CATALOGO CONVENIO MARCO». Un ID de Convenio Marco tiene **exactamente 7 dígitos** (`LARGO_ID`) |
| `cartera.py` | Las unidades que se decidió trabajar. El puente entre el panel y el envío del catálogo: se elige acá y lo lee el otro lado |
| `vistas.py` | El filtro guardado de cada vendedor. Es de la PERSONA, no de la cuenta. La marcada «de entrada» se aplica sola al abrir. **Sirve a DOS ámbitos** (03-09-2026): `oportunidades` y `mercado` —la cartera del comercial—, con `leer/guardar/aplicar/barra_de_vistas(usuario, ambito)`. Los campos de Mercado van en **una sola columna `jsonb`**, no una por filtro |
| `modulo_envios.py` | Pestaña «Envíos de Ofertas, Catálogo y Mailing»: la puerta única a los dos paneles de Apps Script. No manda correo, los abre |
| `exportar.py` | El mismo botón de bajar a Excel en todos los módulos. Baja lo que está **filtrado en pantalla**, no la tabla entera |
| `cartera-para-copiar.txt` | El SQL de la tabla `cartera` |
| `vistas-para-copiar.txt` | El SQL de la tabla `vistas` |
| `mis-productos-para-copiar.txt` | El SQL de `cuentas.ids_publicados` |
| `alertas-filtro-fino-para-copiar.txt` | El SQL de `filtros.instituciones` y `filtros.unidades` |
| `supabase-cuentas-para-copiar.txt` | El SQL de las tablas `cuentas` y `usuarios`. **Hay que pegarlo una vez** para que los roles empiecen a mandar |
| ⚠️ *Los cuatro `-para-copiar.txt` del 02-09-2026* | *Sin correr al cierre de esa sesión. Nada se rompe: cada pantalla avisa «para esta sesión» y sigue andando* |
| `supabase-soporte-para-copiar.txt` | El SQL del rol `superadmin` y la `bitacora_soporte`. Se pega **después** del anterior |
| `modulo_seguimiento.py` | El embudo: en qué quedó cada oportunidad que avisó el correo (pestaña «Seguimiento») |
| `supabase-seguimiento-para-copiar.txt` | El SQL de la tabla `seguimiento`, las `visitas` y la foto que `envios` guarda de cada oportunidad |
| `inspector_apis.py` | Mira qué traen de verdad las dos APIs. No envía ni escribe nada |
| `alertas-workflow-para-copiar.txt` | El workflow de las 08:00 |
| `bienvenida-workflow-para-copiar.txt` | El SQL de la columna + el workflow del primer correo |
| `disparador-instantaneo-para-copiar.txt` | El trigger que avisa a GitHub en el momento del alta |
| `modulo_metas.py` | Las tres puertas del mes: NUEVO, RECOMPRA y CRECER, y qué tan ganable es cada una |
| `modulo_planes.py` | **Qué abre cada plan.** Una sola fuente de verdad; no hacer otra lista |
| `alta-automatica-para-copiar.txt` | El SQL que crea la cuenta y el usuario al inscribirse |
| `supabase-alertas-para-copiar.txt` | El SQL de las columnas nuevas |
| `supabase-fichas-para-copiar.txt` | El SQL de `fichas_licitacion`: las fichas guardadas de un día para otro |
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
MSYS_NO_PATHCONV=1 git sparse-checkout set --no-cone '/*' '!/bodega/'
```

⚠️ **`MSYS_NO_PATHCONV=1` no es opcional en Git Bash.** Sin él, Git Bash convierte el
`!/bodega/` en `!C:/Program Files/Git/bodega/`, la exclusión no calza con nada y **se baja la
bodega entera**: 490 MB y varios minutos colgado. Pasó el 03-09-2026 al intentar
`sparse-checkout add`. Para comprobar que quedó bien: `git sparse-checkout list` tiene que
mostrar `!/bodega/`, no una ruta de Windows.

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

Estado actual (medido 30-08-2026): **8,26 millones de líneas resumidas en 869.131
filas, las seis vías de compra, 121 MB en parquet.** Los meses de producción pesan
~21 MB cada uno; si en un clon local pesan ~2 MB, esa copia es anterior al
27-08-2026 y solo tiene Convenio Marco.

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

### Las fichas de licitación se guardan de un día para otro

El 96% del tiempo del correo se va pidiendo detalles de a uno con 2 segundos
obligatorios entre cada uno. Pero una licitación sigue abierta una o dos semanas
y su ficha —comprador, región, descripción, visita a terreno— no cambia. Se
guarda en `fichas_licitacion` (SQL en `supabase-fichas-para-copiar.txt`) y se
reusa 30 días.

- **Lo que cambia día a día NO sale de la ficha**: que siga abierta y su fecha de
  cierre salen del listado de activas, que se sigue pidiendo entero cada mañana.
  Por eso una ficha guardada no puede envejecer mal sin que nadie lo note.
- **Falla abierto**: sin tabla o sin Supabase, se piden todas como antes.
- **El techo de 400 cuenta solo las que hay que pedir.** Una ficha guardada no
  gasta ticket ni espera, así que no tiene por qué ocupar cupo: con la caché
  llena, el correo alcanza a mirar más licitaciones que antes, no menos.

### El bloque «Tus 3 del mes» en el correo

Una puerta de cada tipo —la mejor CRECER, la mejor RECOMPRA, la mejor NUEVO—
con su dirección, cuántos proveedores se la reparten y cuánta plata es peleable
**por servicio**. Sin nada que llenar: el mes siguiente la bodega dice sola si
esa unidad compró.

⚠️ **El correo usa lo que YA VENDIÓ, no el catálogo del Drive**, y es a
propósito: `alertas.yml` instala solo `pandas` y `pyarrow`, sin `openpyxl` ni
`streamlit`, así que ahí no se puede leer el Drive. Y está bien: el correo manda
a golpear **puertas**, y una puerta no se echa a perder porque un producto se
haya deshabilitado. **La oferta producto a producto —que sí depende del catálogo
vigente— vive en el panel.** Si algún día el correo tiene que leer el catálogo,
hay que agregar `openpyxl` al workflow y sacar el lector de `app.py`, que
arrastra streamlit.

- **Falla abierto en todo.** Sin RUT, sin bodega o si algo revienta, el correo
  sale igual sin ese bloque.
- ⚠️ **Se lee la bodega DOS VECES POR SUSCRIPTOR** (una para sus IDs, otra para
  el mercado). Con dos suscriptores está bien; **pasando de diez clientes hay
  que juntarlo en una sola pasada para todos**. La corrida imprime
  `[tiempo] puertas del mes` para poder verlo venir.
- Las direcciones salen de `fichas_licitacion`, que se llena sola desde el
  detalle que este mismo correo ya pide cada mañana.

### La memoria de lo avisado

Una licitación abierta sigue abierta una o dos semanas. Sin anotar lo enviado, el
correo repite lo mismo cada mañana. Se registra en `envios` (o en
`envios_enviados.json` en pruebas locales) **después** de que el envío salió: si
falla, esas oportunidades tienen que poder salir mañana.

### ⚠️ Manejar el navegador de Serling: qué sí y qué no

Comprobado el 28-08-2026 sobre tres paneles distintos (GitHub, Supabase, Auth0):

- **SÍ funciona:** apretar botones, marcar casillas, elegir de listas desplegables
  **en GitHub y en Supabase**. El formulario del token de GitHub se llenó entero así.
- **SÍ funciona el panel entero, incluido escribir** (03-09-2026), entrando a la URL de
  adentro del iframe (`/~/+/`, ver «Verificación antes de entregar»). Se consultó el Senado
  de punta a punta —buscar la institución, marcar las seis unidades, apretar Consultar y leer
  la tabla— sin que ella tocara nada. También el menú de Streamlit Cloud: *Manage app ▸ ⋮ ▸
  Reboot app* se apretó así. ⚠️ **Ahí conviene apretar por referencia y no por coordenada**:
  «Delete app» queda 41 píxeles debajo de «Reboot app».
- ⚠️ **EN AUTH0 NO FUNCIONA NADA, ni siquiera los clics** (comprobado el 31-08-2026
  en Email Provider): el interruptor «Use my own email provider» y el radio de
  Resend no se marcan ni con `.click()`, ni con `MouseEvent` sintético, ni sobre
  su `<label>`. El texto tampoco: en Email Templates el asunto queda escrito en
  pantalla pero **el botón Save no se habilita**, o sea que React nunca se entera.
  **La única excepción es el editor del cuerpo del correo**, que es CodeMirror y
  expone `nodo.CodeMirror.setValue()` — por ahí sí se pudo cargar la plantilla.
  **Regla: en Auth0, todo lo hace ella.**
- **NO funciona: escribir en campos de texto.** Ni tecleando por coordenada ni
  fijando el valor por elemento (`form_input` devuelve `Set text value to ""`).
  Falló en el nombre del token de GitHub y en los campos de Tenant Settings de
  Auth0.
- **SÍ funciona el editor SQL de Supabase, por JavaScript** (comprobado el
  30-08-2026: se crearon `fichas_licitacion` y la función del alta sin que
  Serling tocara nada). El truco es no escribir: se le habla al editor por su
  propia API.
  - `window.monaco` queda expuesto una vez que carga el editor (esperar: al
    entrar todavía no está).
  - Hay **dos** modelos y los dos son `pgsql`. El del editor principal es el que
    tiene URI `file:///...`; el `inmemory://` es el panel del asistente. Elegir
    por la URI, no por el tamaño: `getDomNode()` devuelve 5×5 en los dos y
    filtrar por rectángulo no encuentra ninguno.
  - `modelo.setValue(SQL)` escribe y React lo toma (aparece «Unsaved edits»).
  - El botón **Run** se aprieta por JavaScript buscándolo por su texto, **no por
    coordenada** —las coordenadas se desvían en Supabase—. Hay dos botones «Run»:
    el de la barra principal es el de menor `left`.
  - **El SQL viaja en base64** y se decodifica con `atob` + `TextDecoder`. Un
    literal de JavaScript se rompe con los backticks que llevan los comentarios
    del propio SQL, y además así llega byte a byte idéntico al archivo.
  - **Comprobar el largo contra el archivo antes de apretar Run**, y después
    comprobar el resultado **con un `select` contra la base**, no mirando la
    pantalla.
  - ⚠️ **Ninguna consulta puede llevar la palabra DROP, ni en un comentario.**
    El editor abre un diálogo de confirmación a mano y el SQL queda colgado sin
    ningún error visible: parece que corrió y no corrió. Se usa `create or
    replace trigger` en vez de borrar y volver a crear. Pasó el 30-08-2026.
  - **La grilla de resultados no aparece en `innerText`.** Se lee del contenedor
    (`[role="grid"]`), o con una captura de pantalla.
  - **Probar contra producción sin ensuciarla:** `begin; ... rollback;` en la
    misma consulta. Deja ver el resultado y no guarda nada.
- **Los clics por coordenada se desvían** en Supabase y Auth0: el marco de la
  captura no calza con el de la página y terminan en el botón de al lado. En
  Supabase abrieron dos veces el panel «Connect» sin querer. Ahí conviene parar:
  es una base de producción.
- **Moraleja operativa, corregida el 30-08-2026:** lo que se aprieta se
  automatiza, y **lo que se escribe también, si el campo tiene una API detrás**
  (el editor de Supabase la tiene). Lo que sigue pegando ella son **las claves**,
  por regla, no por limitación. Y para diagnosticar
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

### A quién se le puede vender (medido el 30-08-2026)

**Esto decía que la bodega guardaba solo Convenio Marco. Ya no es cierto** y la
nota vieja costó un diagnóstico equivocado: `bodeguero.py` no filtra por
mecanismo desde el 27-08-2026. Medido sobre tres meses de la bodega **de
producción** (1.215.678 líneas):

| Vía | Monto 3 meses | Proveedores |
|---|---|---|
| SE (licitación) | $1.417.516 MM | 15.399 |
| TD (trato directo) | $496.193 MM | 9.412 |
| AG (compra ágil) | $209.164 MM | 21.947 |
| **CM (convenio marco)** | **$168.031 MM** | **861** |
| CC / CT | $7.827 MM | 286 |

**Convenio Marco es el 7% de la plata y el 2,4% de los proveedores.** Hay 36.623
proveedores vendiéndole al Estado y el panel nació mirando 861.

⚠️ **Lo que sigue SIN comprobar** es si el encaje y la nota de prioridad
funcionan bien fuera de Convenio Marco. La única prueba que hay —cuatro
oportunidades de software en «PRIORIDAD D · 0»— es del 27-08, el mismo día de la
ampliación, y casi seguro corrió contra la bodega vieja. **Repetirla antes de
prometerle nada a un proveedor de servicios.**

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

### Las tres metas del mes (`modulo_metas.py`, 30-08-2026)

**NUEVO** nunca te ha comprado · **RECOMPRA** te compró y se enfrió · **CRECER**
te compra hoy pero no todo. Diseño de Serling: la meta son **tres clientes al
mes, uno de cada tipo**, porque juegan en tiempos distintos —CRECER paga este
mes y se acaba en 71 puertas, NUEVO paga el año que viene.

**No es un CRM y no se va a convertir en uno.** El resultado se mide solo: si
visitaste una unidad en septiembre, la bodega dice en octubre si te compró. Un
embudo de seis etapas es el vendedor contando cómo cree que le va, y además es
lo que nadie llena.

⚠️ **LA REGLA DE EXACTITUD.** Los números con ID de producto y los sin ID **no
se suman jamás**. Medido sobre 24 meses: Convenio Marco trae el ID en el 100% de
sus líneas; licitación 0%, trato directo 0%, compra ágil 1%. Convenio Marco es
el **5% de la plata** del mercado público y el **100% de su precisión**. De ahí
las dos miradas, en columnas distintas:

- **A qué puerta golpear** → las seis vías (`alertador.resumen_de_ordenes`).
- **Qué ofrecerle** → solo Convenio Marco, producto a producto (`modulo_metas`).

**El catálogo manda, no lo vendido.** Se baja del Drive con
`app.cargar_catalogo_propio`, así que un producto deshabilitado desaparece solo.
De los 22.628 productos del catálogo de Emergenza solo se han vendido 2.067:
calcular con lo vendido dejaba fuera el 91% de lo que puede ofrecer. Pero el
catálogo dice lo que PUEDE vender y no lo que SABE vender —salieron «viviendas
de emergencia con instalación» por $1.790 MM—, por eso cada línea de la oferta
lleva `probado`.

⚠️ **La relación se mide con TODAS sus ventas; lo que hay por ganar, solo con el
catálogo.** Si le vendió algo que después se deshabilitó, esa unidad ya lo
conoce y **no es NUEVO**. Sin esa distinción salían diez unidades mal
clasificadas; hay 59 con ventas fuera del catálogo vigente. Por eso
`mercado_de()` recibe `rut_propio` y marca cada fila con `en_catalogo`.

**Ordena lo GANABLE, no la plata.** Idea de Serling: contra la marca en su
propio producto no se gana por precio, se gana por servicio. `que_tan_ganable()`
mira cuánto domina el líder y en cuántas unidades del país vende ese mismo
producto —vender lo mismo en 800 unidades es la marca; en tres, un distribuidor
al que sí se le pelea—. De $99.784 MM en juego, **$33.357 MM están en
«SERVICIO»**: unidades donde ya vende y nadie lo tiene cerrado.

Dato que destapó ese cálculo: **Macro Food se queda con el 36% de su propia
marca** en el mercado público; el otro 64% lo mueven noventa distribuidores.
Colun captura el 39% de Colun. **La pelea casi nunca es contra la marca.**

**El enfoque es un dato, no un supuesto.** `mercado_de()` recibe un conjunto de
IDs y no pregunta de dónde salen: para un proveedor son los de su catálogo, para
una marca serían los productos de esa marca. La cuenta es la misma. Se decidió
así el 30-08 para no tener que rehacerlo si algún día se vende la mirada de
marca, que es otro producto y no está construido.

### El plan de visitas: el paso 1 del IPT operativo (30-08-2026)

Dos tablas nuevas, `plan_visitas` y `movimientos_plan`, con el SQL en
`supabase-plan-visitas-para-copiar.txt`. **Ya están creadas y probadas en
producción.** Dos decisiones que después no se cambian sin migrar:

- **La llave es el RUT de la empresa y el vendedor es una columna.** Cada
  vendedor arma y mueve su propio plan con sus instituciones, pero el plan es de
  la gestión de la empresa: la jefa lo ve entero. Mismo patrón que el embudo.
- **Nunca se pisa, siempre se agrega una línea.** Lo escribe un DISPARADOR
  (`al_mover_el_plan`), no la aplicación, para que ningún camino pueda cambiar el
  plan sin dejar rastro. Probado: un alta más cuatro cambios dejan cinco líneas.

**Por qué hizo falta:** `seguimiento` tiene `unique (rut, codigo)` y `visitas`
tiene `primary key (rut, email)`. **Las dos guardan solo el presente**: cuando
algo cambia, lo anterior desaparece. Por eso hoy no se puede comparar cómo venía
el trabajo hace tres meses — la historia nunca se guardó. Y `visitas` además no
es por institución, así que para el IPT no sirve.

**Excluir no es borrar.** `incluida` es una casilla que se prende y se apaga; la
institución se puede devolver al plan y el movimiento queda anotado.

⚠️ **`current_date` de la base NO es hoy en Chile.** Medido el 30-08-2026 a las
21:00 de Chile: la base decía 2026-08-31. Para agendar visitas hay que sacar la
fecha de la hora de Chile, no de la base. Es la misma trampa del servidor de
Streamlit en UTC, en otro lugar.

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
- **El muro del fin de prueba** (14 días, ver `alta-automatica-para-copiar.txt`)
  vive en `modulo_planes.muro_de_prueba()` y se dibuja
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
- **⚠️ La plata va SIN DECIMALES, a peso entero.** El peso chileno no tiene centavos y los
  decimales solo ensuciaban la tabla (`53.073.864,5`). Se redondea **en el dato**, no en el
  formato: `promedio`, `oferta` y `MI PRECIO` salen ya redondeados, y así `_numeros_de_columna`
  los deja en `Int64`. Si se redondeara solo al mostrar, la columna seguiría siendo `Float64`
  y Streamlit escribiría «1.234,0». Pedido de Serling el 03-09-2026.
- **⚠️ P. PROM es el promedio SIMPLE y así se queda.** Es la suma de los precios de cada línea
  dividida por cuántos precios se sumaron — criterio de Serling, confirmado el 03-09-2026
  cuando dudó del número y se le mostraron los dos. **No es el precio medio realmente pagado
  por unidad**: en productos comprados en cantidades muy distintas se desvía —el pepino sale
  1.382 y pagaron 1.622, un 14,8%— y ella lo sabe. La razón de fondo es que así P.MIN, P. PROM
  y P.MAX se leen en la misma escala. **No cambiarlo sin preguntarle.**
- **Hay productos cuyo «precio unitario» es un contrato entero** y no hay cómo arreglarlo:
  «ALIMENTACIÓN -» son órdenes de cantidad 1 por $44 y $61 millones. El dato viene así.
- **Las columnas numéricas van como números** (`Int64`), no como texto con `$`: si van como
  texto, la tabla ordena "11" entre "1" y "2". El formato con separador de miles lo pone
  `column_config` con `format="localized"`, que respeta el idioma del navegador.
- **⚠️ Una celda numérica vacía NO sale en blanco: Streamlit le escribe «None».** Medido el
  03-09-2026 sobre ocho variantes: pasa con Styler y sin Styler, con `column_config` y sin
  él, con `Int64`, con `Float64` y con `float64`+NaN, en Streamlit 1.61.1 y 1.63.0 (la
  última) y con pandas 2.3.3 y 3.0.5. **El Arrow que sale de Python lleva nulos correctos**:
  lo dibuja así el navegador. `.format(na_rep="")` del Styler no lo arregla y además **le
  come el signo** a los negativos. Lo único que sale en blanco es una columna de **texto**,
  pero eso rompe el orden. **La salida es esconder la columna cuando está vacía entera**, que
  es lo que hace `sin_ofertas` con MI OFERTA y DIF%. Si un día hay que mostrar un hueco en
  medio de números, no hay forma: se ve «None».
- **Lo que ella busca en MI OFERTA y DIF% se encuentra ORDENANDO, no mirando.** La tabla llega
  ordenada por MONTO y los productos con oferta suelen ser montos chicos, así que quedan
  invisibles al fondo. Un clic en el encabezado DIF% los sube todos. Medido en el Senado el
  03-09-2026: quince o más productos con oferta, **todos con su precio bajo lo que la
  institución pagó** (de -7% a -21%). Por eso esas dos columnas tienen que seguir siendo
  numéricas: es su única forma de ordenarse.
- **⚠️ Un toque en el ⊗ del multiselect NO puede borrar veinte unidades marcadas.**
  Marcar las unidades de la Armada son veinte toques y el botón de limpiar las borra con uno,
  al lado de la flecha de abrir. Streamlit **no deja poner un «¿estás segura?» encima de su
  propio botón**, pero el `on_change` corre ANTES de redibujar el widget: ahí se repone lo
  borrado y se deja un aviso (`cuidar_unidades_marcadas`). **El segundo toque sí borra**, para
  que el resguardo no se vuelva una traba, y con una sola unidad marcada no pregunta. Cambiar
  Región u Organismo es la otra forma de perder la selección sin tocarla: las que ya no calzan
  se sueltan igual —no hay alternativa, Streamlit reclama si el valor no está en las opciones—
  pero ahora se dice cuáles y cómo recuperarlas.
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
- **⚠️ Filtrar AL LEER, nunca después.** `leer_bodega` (`app.py`) cargaba todas las columnas de
  todos los meses del período y recién ahí el que llamaba se quedaba con sus unidades. Medido
  con los meses de producción y las 5 unidades del Senado: **3 meses → 1.240.871 filas → +555
  MB**; filtrando al leer, **467 filas** y memoria plana —mismas filas, mismas columnas, mismo
  total $622.413.127. Un período de un año son doce meses: más de 2 GB contra un techo de
  1.000 MB. Por eso Módulo Mercado Público moría siempre en el mismo paso (02-09-2026, commit
  `a080b77`). Los tres que la llaman pasan `codigos`: `convenios_del_periodo`,
  `compras_desde_bodega` y la lectura cruda. **Toda caché de datos lleva `max_entries`**: sin
  él, `st.cache_data` guarda una copia entera por cada juego de argumentos distinto.
- **⚠️ La bodega local NO sirve para medir memoria.** El clon de trabajo tiene ~38.000 líneas
  por mes; producción tiene **393.919 y pesa 421 MB** (eran 121 MB). Medir contra la copia local
  da quince veces menos y lleva a diagnosticar mal: el 02-09-2026 se erró el diagnóstico tres
  veces por eso, y se desarmó el panel dos veces sin necesidad. Antes de decir «no es
  memoria», **bajar los meses de producción de verdad y medir con ellos.**
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

**Esto decía que la tabla y los desplegables no se podían manejar desde el navegador. Ya no
es cierto** (corregido el 03-09-2026), y esa nota costaba pedirle a ella comprobaciones que
se pueden hacer solas. Lo que fallaba era el panel embebido, no el navegador: **la app corre
dentro de un iframe** y hay que entrar a la URL de adentro,
`https://panel-stock-uplevel.streamlit.app/~/+/`. Desde ahí, en el Chrome de ella:

- **La tabla se dibuja entera** y se lee con una captura o con `zoom` sobre la región.
- **Los desplegables se abren y se eligen opciones** (incluido «Select all» del multiselect).
- **Se escribe en los campos de texto** normalmente.
- Sobre la URL de afuera no funciona nada de eso: `read_page` devuelve contenedores vacíos y
  `document.querySelectorAll('input')` no encuentra ni un campo, porque todo vive en el iframe.
- ⚠️ **La captura se cae con «renderer may be frozen» mientras la app calcula.** No es que el
  navegador esté colgado: es que Streamlit está trabajando. Se espera y se vuelve a capturar.

Sí sirve `javascript_tool` para medir el CSS aplicado (ancho, centrado, tamaño de letra,
desborde en celular).

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

## Los cuatro trabajos automáticos

| Archivo | Cuándo | Qué hace |
|---|---|---|
| `bodega.yml` | 02:00 Chile | llena la bodega de Mercado Público |
| `licitaciones.yml` | 07:00 Chile | llena la bodega de licitaciones |
| `alertas.yml` | 8, 13 y 18 Chile | el correo diario, disparado por el reloj de Supabase |
| `bienvenida.yml` | cada 5 min + al inscribirse | el **primer** correo |

⚠️ **ESTA CARPETA SE DESACTUALIZA Y ENGAÑA.** El 31-08-2026 la copia local
tenía solo `bodega.yml` y `licitaciones.yml`, así que un diagnóstico concluyó
que «ningún trabajo automático manda correos» —falso: `alertas.yml` y
`bienvenida.yml` llevaban semanas en el repositorio— y se subieron dos
workflows duplicados que habrían mandado cada correo dos veces. Se borraron
antes de que corrieran, pero por poco.

**Regla: antes de afirmar que algo no existe, preguntarle al repositorio.**

```bash
gh api repos/uplevelweb/panel-stock/contents/.github/workflows --jq '.[].name'
```

### Cuánto demora la bienvenida, y por qué importa el timeout

El 31-08-2026 la ventana de compras ágiles pasó de **3 días corridos a 7
HÁBILES** (pedido de Serling: hay ágiles con más vigencia y con 3 se perdían) y
el techo de páginas de 40 a 120. Eso es mucho más que pedirle a la API, así que
el `timeout-minutes` del trabajo de envío subió de **30 a 60**. Con 30 el
trabajo moría a medias y la persona se quedaba sin su primer correo.

**Si hay que acortarlo, la palanca es `techo_paginas`, no la ventana.**

### Ahora se descartan las oportunidades ya cerradas

`compras_agiles_abiertas` tira las que tienen `fecha_cierre` anterior a hoy.
Antes no había filtro y la única protección era `estado=publicada` de la API
—por eso el 29-08-2026 la ventana se había achicado a 3 días—. Con el filtro,
la ventana puede ser ancha sin riesgo de mostrar algo cerrado. Las que vienen
**sin** fecha de cierre no se descartan: ante la duda, se muestran.

### La promesa de la página

`inteligencia.uplevelweb.art` dice **«tu primera alerta sale en unos minutos»**.
El reloj de Supabase estuvo mudo entre el 29-08 03:15 y el 31-08 21:18 —dos
días y medio— y en ese hueco nadie recibió su bienvenida. Lo despertó el
disparador del alta de una inscripción nueva. **Vale la pena una alarma que
avise cuando el reloj lleva más de una hora sin latir**; hoy no existe y el
silencio no se nota hasta que alguien reclama.

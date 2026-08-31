## 30-08-2026 · El SQL ya no lo pega ella

Los dos bloques de hoy —la tabla `fichas_licitacion` y la función del alta con
los 14 días— se ejecutaron en Supabase **sin que Serling tocara nada**.

La bitácora decía desde el 28-08 que escribir en campos de texto no funcionaba,
y era cierto **tecleando**. El editor SQL de Supabase es Monaco y expone
`window.monaco`: no hay que escribir, hay que hablarle a su API. `setValue()` y
listo, React lo toma.

Tres detalles que costaron un intento cada uno:

- **Filtrar los editores por su rectángulo no sirve**: `getDomNode()` devuelve
  5×5 para los dos. Se eligen por la URI del modelo: el principal es `file:///`,
  el del asistente es `inmemory://`.
- **El SQL va en base64.** Los comentarios del propio SQL llevan backticks
  (`` `admin` ``) y rompen un literal de JavaScript. Codificado, además, llega
  byte a byte igual al archivo — se comprobó el largo (2.811) antes de ejecutar.
- **Hay dos botones «Run»** y se elige por posición, apretándolo por JavaScript.
  Por coordenada no: en Supabase se desvían.

Y la regla que queda: **comprobar contra la base, no contra la pantalla.** El
`select` final confirmó las 11 columnas, los 14 días, el RUT por dígitos y que
el disparador sigue apuntando a la función.

Lo que sigue pegando ella son **las claves**. Eso es por regla, no porque no se
pueda.

---

## 30-08-2026 · Las fichas de licitación se guardan, y la prueba baja a 14 días

**Convenio Marco resultó ser el 7% del mercado.** Medido sobre tres meses de la
bodega de producción: $2,3 billones en total, de los cuales Convenio Marco son
$168 mil millones. Y de los 36.623 proveedores que le venden al Estado, solo 861
están en Convenio Marco. El panel nació mirando el 2,4% del mercado porque ese es
el mundo de Emergenza.

El `CLAUDE.md` decía que la bodega guardaba solo Convenio Marco. **Era falso desde
el 27-08** y esa nota vieja me hizo dar un diagnóstico equivocado el 30-08: dije
que había que ampliar la bodega cuando ya estaba ampliada. Se corrigió, junto con
el tamaño (decía 1,29 millones de líneas; son 8,26 millones). **Moraleja: un dato
en la documentación que nadie vuelve a medir se convierte en mentira sola.**

**Las fichas de licitación ahora se guardan 30 días** (`fichas_licitacion`). El
96% del tiempo del correo se iba pidiendo detalles de a uno con los 2 segundos
obligatorios de espera, y una licitación sigue abierta una o dos semanas: se
estaba pagando el mismo peaje cada mañana por el mismo dato.

- Lo que cambia día a día —que siga abierta y su fecha de cierre— **no sale de la
  ficha**: sale del listado de activas, que se sigue pidiendo entero. Por eso una
  ficha guardada no envejece mal.
- **El techo de 400 ahora cuenta solo las que hay que pedir.** Una ficha guardada
  no gasta ticket ni espera; con la caché llena el correo mira más licitaciones
  que antes, no menos.
- Falla abierto: sin tabla, se piden todas como siempre.
- 15 comprobaciones en `probar_fichas.py`, incluida la que importa: que una fecha
  de cierre vieja guardada en la ficha **no pise** la del listado de hoy.

**La prueba pasa de 20 a 14 días**, manteniendo las dos extensiones. 40 días de
prueba le dicen al cliente que el producto no es urgente, y la urgencia es el
argumento central del producto. Las extensiones se mantienen: hoy no hay ni un
dato de por qué alguien no paga, y ese mecanismo es el único instrumento para
averiguarlo. No es un descuento, es una entrevista.

**El archivo del alta tenía todavía el bug del RUT.** El arreglo del 29-08 se
pegó directo en Supabase y `alta-automatica-para-copiar.txt` se quedó comparando
el RUT como texto. Quien lo hubiera vuelto a pegar reintroducía la duplicación de
cuentas. Corregido: el archivo en disco ahora dice lo mismo que la base.

**De lo que sugirió una IA externa revisando el sistema, dos de sus tres cambios
ya estaban construidos:** quitar el filtro de Convenio Marco (hecho el 27-08) y
cachear los detalles entre clientes (existe desde siempre — `main()` arma la
unión de las bolsas de todos los suscriptores y pide los detalles una sola vez).
Lo que sí faltaba era la caché **entre días**, que es lo que se hizo hoy.

---

# Bitácora — Panel Oportunidades

Decisiones tomadas, con fecha y motivo. Lo que **no** está aquí es historia del código: eso
lo cuenta el propio `app.py`. Aquí está el **por qué**, que es lo que no se puede reconstruir.

---

## 12-08-2026 · Nace como panel de stock

Encargo original: leer un Google Sheet, filtrar por la columna "MI ESTADO" (CON STOCK / SIN
STOCK) y mostrar **solo 7 columnas** (ID, PRODUCTO, P.MIN, P. PROM, P.MAX, MI PUBLICADO, OC),
descartando el resto. Dos informes: año en curso y período anterior.

- **Sin entorno virtual, a propósito.** La carpeta está en OneDrive y un `venv` (miles de
  archivos) rompe la sincronización. Las dependencias se instalaron con `pip install --user`
  sobre el Python 3.14 del sistema.
- Publicada el 16-08 en Streamlit Community Cloud desde GitHub, porque necesitaba usarla
  **desde el celular** sin tener el computador encendido.

## 16-08-2026 · Se convierte en Panel Oportunidades

Al ver los datos reales quedó claro que el panel no debía mostrar stock, sino **oportunidades
de venta**. Hallazgos sobre la hoja de la Escuela Naval que cambiaron el diseño:

- **La columna OC no es un número de orden: es cuántas órdenes de compra hubo en el período.**
  Es un medidor de frecuencia.
- **Proveedores es cuántos competidores** tiene ese producto.
- Los IDs que se repiten entre las dos pestañas son compra recurrente: 95 de 200.
- **65 productos recurrentes están en estado "No lo tengo"**: $569 millones que la institución
  compra y Emergenza no ofrece. Ese número fue el que justificó todo lo demás.

Decisiones:

- Cuatro estados en el filtro (CON / SIN / NO LO TENGO / TODOS), porque los 129 "No lo tengo"
  eran justamente el negocio y antes no aparecían en ninguna vista.
- Columna MONTO y columna COMENTARIO con las señales de negocio.
- **El estilo se copia del Panel Armada** (`emergenza-mailer`): mismo azul pizarra, mismo
  rojo, misma tipografía. Los dos paneles tienen que verse como un mismo sistema.
- **Se elimina el Informe 2.** El selector de pestaña ya permite abrir el período anterior;
  dos solapas era una pieza de más.

## 16-08-2026 · Cotización en PDF y correo

- El PDF copia el **formato de cotización que ella ya usa** (franja azul, logo, bloque
  ENVIAR A, franja DESPACHO INCLUIDO), pero **sin cantidades, sin precio total y sin
  totalizar**: es un listado de ID disponibles, no una cotización cerrada. Lo pidió explícito.
- El precio sale del **catálogo de ofertas semanales**, que la app busca sola en la carpeta de
  Drive (el archivo con "OFERTAS" en el nombre y la fecha más nueva). Los productos sin oferta
  salen con un guión.
- Dato de expectativa: de los 61 productos CON STOCK, **solo 11 tienen precio** en el catálogo
  de la semana. En NO LO TENGO, ninguno. Es esperable —si no lo vende, no está en su catálogo—
  pero hay que saberlo antes de mandar una cotización.

### El correo: se descartó SMTP

Primero se construyó con SMTP y contraseñas de aplicación de Google. **Se descartó** porque el
administrador de emergenza.cl puede tenerlas bloqueadas y ella necesitaba certeza de poder
enviar desde sus dos cuentas. Se reemplazó por un **Apps Script enviador en cada cuenta**, la
misma tecnología que ya opera en el Panel Armada: sin contraseñas, y el correo sale con firma
HTML y logo incrustado.

- Proyectos **independientes** del Panel Armada, para no arriesgar sus 224 contactos.
- Las dos cuentas quedaron instaladas y verificadas el 16-08. El riesgo de que la empresa
  bloqueara el acceso "Cualquier persona" **no se materializó**.
- El envío pide una clave porque la app es pública: sin ella, cualquiera con el enlace
  mandaría correos a su nombre.

### El saludo del correo

"Estimado/a Yanitza" le pareció frío y poco profesional. Ahora el saludo **define el género**:
manda un tratamiento explícito (Sra., Don, Directora), después el **primer** nombre (para que
"María José" sea mujer y "José María" hombre), después una lista de nombres chilenos que la
regla de la última letra no acierta, y al final la terminación en A o en O. Si no se puede
determinar —o el contacto es un área y no una persona— usa **"Estimados,"**.

Los grados militares y navales importan: sin ellos, "Guardiamarina Diego" saludaba en femenino
(termina en A) y "Subteniente Camila" caía en "Estimados". Están todos en `PALABRAS_NEUTRAS`.

## 17-08-2026 · Frecuencia de compra y destacado

- **Compra recurrente se mide contra los meses transcurridos**, no con un número fijo: es
  recurrente cuando hay al menos una OC cada dos meses (la mitad de los meses corridos). En
  agosto, 4 OC o más. El divisor se ajusta según la pestaña (semestre = 6, año cerrado = 12).
- **Solo se pinta de amarillo la compra recurrente.** Se probó incluir "sin competencia" y
  "bajo el promedio", pero quedaban 42 de 61 filas amarillas: "sin competencia" la tiene el
  72% del catálogo y "bajo el promedio" la mitad de lo que ella vende. Destacar casi todo no
  destaca nada.

## 17-08-2026 · Mercado Público: por qué NO hay base de datos

> **SUPERADA el mismo día** (ver «Se da vuelta la arquitectura: nace la bodega»).
> El argumento se cayó al usarla: consultar el histórico tomaba 7,3 minutos.

Se pidió el ticket de la API (llegó a `webuplevel@gmail.com`; es personal, uno por RUT).

Se evaluó guardar las órdenes de compra en una base de datos con una ingesta diaria
automática. **Se descartó**, y la razón es de ella: si la herramienta consulta en vivo con
filtros, no hace falta nada corriendo de fondo. La base de datos solo aporta para acumular
histórico de meses o años sin que nadie esté presente, y hoy eso no se necesita: **el Excel
que descarga es el registro**, igual que antes.

Arquitectura elegida, sin base de datos:

1. `catalogo_unidades.csv` — tabla de nombres (código, unidad, organismo, región) que casi no
   cambia. **No es una base de datos**, viaja con el código. Da los filtros por región,
   organismo y unidad.
2. Consulta en vivo del período elegido: una consulta por día, filtrando por el prefijo del
   código (la unidad) y por `-CM` (Convenio Marco).
3. Detalle solo de las órdenes que calzan, que son decenas y no 16.500.
4. Interpretación con las mismas señales del panel (recurrencia, quién ganó, precio pagado
   contra el publicado, IDs que no tiene).

Límite conocido y aceptado: 15 días son 15 consultas (segundos); seis meses serían ~120
consultas y cientos de megas cada vez. **Ese es el punto donde una base de datos empezaría a
tener sentido**, no antes.

Alcance acordado: **empezar por Convenio Marco** (2.070 de 16.500 órdenes diarias) y ampliar
después si funciona.

### Dónde manipula ella la información (17-08-2026)

Todo el trabajo ocurre **dentro de la misma app**, en una sección nueva: elige región →
organismo → unidad → período, consulta, marca filas y descarga. No hay otra herramienta.

Lo que la app **no** puede hacer sin dónde escribir es **recordar**: Streamlit olvida entre
sesiones. Se ofrecieron tres niveles y **eligió el intermedio (B)**: una hoja de Google suya,
**"Mis instituciones"**, con las unidades que sigue, que la app lee al abrir igual que lee la
hoja de compras y la carpeta de ofertas. Así no tiene que buscarlas cada vez.

Queda descartada por ahora (opción C) la hoja de **seguimiento** que la app escribiría sola
—con el mismo Apps Script del enviador— porque suma una pieza más y exige disciplina de uso.
Se agrega cuando el módulo ya le esté sirviendo.

## 17-08-2026 · El módulo de Mercado Público, construido

Quedó como pestaña nueva (**Análisis de compras** / **Mercado Público**), no como una app
aparte: es el mismo trabajo y la bitácora ya decía que todo ocurre dentro de la misma app.

### `fecha=` NO es la fecha de la compra

Es lo que más cambió el diseño y no es lo que uno supone. `ordenesdecompra.json?fecha=` lista
las órdenes que tuvieron **movimiento** ese día, no las creadas ese día. Barriendo 6 días de
cuatro unidades de la Armada salieron **43 órdenes, de las cuales solo 6 estaban creadas en
esos días**: había 15 de septiembre y octubre de 2025.

Consecuencias, las dos asumidas:

- La tabla trae la **fecha real de creación** de cada orden y una casilla para dejar solo las
  del período. Por defecto se muestran todas: esas compras antiguas son reales y son historia
  gratis, así que se avisa en pantalla en vez de esconderlas.
- El barrido **no garantiza** traer todo lo creado ayer: si el movimiento de una orden cae
  mañana, aparece mañana. Para lo que ella hace —ver qué compra una institución— no estorba.

### Se consulta siempre por organismo

El listado de un día completo son ~16.000 órdenes y **2 MB**; filtrado por `CodigoOrganismo`
son decenas y **10 KB**, 200 veces menos. Se comprobó en 30 comparaciones (6 organismos × 5
días) que devuelve **exactamente** las mismas órdenes de la unidad que filtrar el día entero.
`CodigoUnidad` no existe como parámetro: la API responde 400.

Costo real medido: la Escuela Naval, 15 días, **32 consultas** (15 del barrido + 17 detalles),
segundos. El ticket permite 10.000 al día.

### Otras decisiones

- **176 unidades vienen sin región** (8%), casi todas hospitales y servicios de salud, y son
  el **11% de las órdenes de Convenio Marco**. Se les puso la etiqueta «(sin región informada)»
  en vez de esconderlas detrás del filtro. **No se les adivina la región** por otra unidad del
  mismo organismo: un organismo puede tener unidades en varias regiones.
- **Una fila por producto**, no por orden: lo que ella analiza son productos.
- El **ID de Convenio Marco viene entre paréntesis** dentro de la especificación
  (`(4427537) GOMA DE BORRAR...`) y es **el mismo número de la columna ID de su hoja**. Por eso
  la tabla lo trae en columna propia: es el puente para cruzar después lo que compró la
  institución con lo que ella tiene publicado.
- La columna se llama **ORDEN y no OC** a propósito: en el panel de arriba «OC» es cuántas
  órdenes hubo (un contador), y usar el mismo nombre para dos cosas distintas se paga caro.

### Al publicarlo: la caché guardó un fracaso

El primer intento mostró «Falta el archivo catalogo_unidades.csv» con el archivo ya subido a
GitHub. No era GitHub ni Streamlit: la app arrancó en el minuto en que el CSV todavía no
estaba, `@st.cache_data` **sin vencimiento** guardó ese "no existe" y lo siguió repitiendo.
Se corrigió dejando la comprobación afuera de la caché y usando la fecha del archivo como
llave, que además hace que reemplazar el CSV alcance para que lea el nuevo.

## 17-08-2026 · La tabla del panel, alimentada por la API

Pedido de ella: dejar de armar la hoja a mano y que la tabla salga sola al elegir el
organismo. Se alineó columna por columna antes de tocar código, porque **no todas se pueden**.

Lo que la API **sí** da: ID, PRODUCTO, MONTO, OC (órdenes distintas del ID), PROVEEDORES
(cuántos le vendieron ese ID) y los precios. Lo que **no** da, porque no es información del
comprador sino de ella: MI ESTADO y MI PUBLICADO.

Decisiones que tomó ella, con los datos a la vista:

- **P.MIN / P. PROM / P.MAX son lo que pagó esa institución** en el rango consultado, no
  precios de mercado. Traer precios de mercado obligaría a bajar el día completo de todo Chile
  (16.000 órdenes, 2 MB) y pedir el detalle de ~2.000 órdenes por día: no se puede en vivo.
- ~~**MI ESTADO se decide contra el catálogo de ofertas**~~ **(corregido el 18-08: se decide
  contra el CATÁLOGO completo, ver esa entrada).** Se midió y se le
  advirtió: de los 54 ID que compró la Escuela Naval en 15 días, **solo 7 están en el
  catálogo**; los otros 47 salen «NO LO TENGO», y ahí hay cosas que no vende (un notebook,
  pasajes aéreos) pero también tomate, manzana y ajo, que son de su rubro y solo faltaban en la
  oferta de esa semana. **Aceptó igual**: aquí «NO LO TENGO» significa «no está en el catálogo
  de esta semana».
- **Si el ID está en el catálogo se marca CON STOCK**, porque se entiende que lo comercializa.
  **SIN STOCK no existe en este módulo**: el catálogo no lo puede saber.
- **La columna se llama MI OFERTA y queda en blanco si no hay oferta.** Nunca se rellena con un
  precio normal: un precio sin descuento no es atractivo en el PDF que se envía.
- **El filtro arranca en TODOS**, al revés que el panel de arriba. Empezando en CON STOCK se
  veían 7 filas de 54 y parecía que la consulta había fallado.

**El hallazgo que justifica el módulo**: al cruzar lo pagado con su catálogo, en **4 de esos 7
productos su oferta está bajo lo que la institución ya pagó** (mayonesa −25%, galleta −27%,
mostaza −21%, postre −19%). Eso es un argumento de venta con ID y monto, y sale gratis del
mismo barrido. Por eso el amarillo aquí destaca también el precio, no solo la recurrencia.

El bloque de cotización y correo **no se duplicó**: se extrajo de `render_informe` a
`cotizacion_y_correo` y lo usan los dos lados. El nombre del contacto lo propone la API (el que
más se repite); el correo no, porque llega siempre vacío.

## 17-08-2026 · Período libre y el buscador que escondía instituciones

- **El período se elige con calendario**, sin los atajos de 7/15/30 días: pidió poder llegar al
  histórico. Se comprobó que la API responde **al menos hasta enero de 2023** (salió
  «2950-28-CM23»). El largo del rango **es** el costo: un año son ~365 consultas de barrido por
  organismo más una por orden, así que sobre 120 consultas la app avisa que va a demorar.
- **El buscador tenía un defecto que escondía instituciones enteras.** Buscó «SERVICIO OCEANO»
  y no salió nada, aunque el SHOA está en el catálogo (unidad 3073). Dos causas:
  1. Buscaba la **frase pegada**, así que «servicio oceano» no calzaba con «SERVICIO
     HIDROGRÁFICO Y OCEANOGRÁFICO». Ahora busca las palabras por separado.
  2. Buscaba **solo en el nombre de la unidad**, y **16 de las 21 unidades de municipios** se
     llaman «Dirección de Salud» o «EDUCACION»: «municipalidad valparaíso» no aparecía nunca.
     Ahora busca también en el organismo, y la etiqueta lo muestra cuando el nombre de la
     unidad no lo dice.

### El tipo de Convenio Marco no está en la API

Se buscó de tres formas y no existe:

- `conveniomarco.json`, `convenios.json`, `catalogo.json`, `productos.json` y
  `conveniosmarco.json` **dan 404**.
- El rubro aparece a veces al final del **nombre** de la orden (`(CM,TRANSVERSAL,...)`), pero
  el nombre lo escribe el comprador a mano: solo **6 de 2.009** órdenes de un día lo traen.
- En el detalle, `Items.Categoria` y `CodigoCategoria` vienen **siempre vacíos**.

Lo que sí se puede: el **rubro de su propio catálogo**, porque el archivo de ofertas tiene una
pestaña por rubro (**ALIMENTOS, ASEO, EMERGENCIAS**) y además una columna «TIPO DE PRODUCTO».
Eso solo alcanza a los ID que ella vende.

**Eligió filtrar por el año del convenio** (CM26, CM25, CM24): sale del último tramo del código
de cada orden, es exacto y cubre el 100%. El filtro aparece solo cuando el resultado trae más de
un convenio. Ojo: el número es el año **del convenio**, no el de la compra — en un barrido de
agosto de 2026 aparecen órdenes CM25 y CM24 todavía vigentes.

## 17-08-2026 · ¿Puede reemplazar la hoja? Se midió contra ella

Al consultar la Escuela Naval de enero a agosto de 2026 (el mismo período que la app supone
para la pestaña «Escuela Naval 2026») los números **no calzaron**: el plátano salió con 7 OC y
$32,8 millones, y la hoja dice 13 OC y $60,3 millones. En 145 IDs comunes la mediana del ratio
era **1.00** —o sea, en la mayoría coincidía exacto— pero los productos de compra frecuente
salían a la mitad.

**No era pérdida de datos: eran períodos distintos.** La pista fue que la frecuencia mensual
coincidía (0,93 órdenes de plátano por mes), y 13 órdenes a esa tasa son ~14 meses, no 8. Al
barrer junio-diciembre de 2025 aparecieron **8 órdenes más de plátano**: 7 de 2026 + 8 de 2025
= 15, contra las 13 de la hoja. Las órdenes «faltantes» existen y el módulo las encuentra
cuando el rango las incluye. **Queda por saber qué período cubre de verdad esa pestaña**, que la
armó ella con un reporte cuyo rango no está anotado en ninguna parte.

Dos correcciones que salieron de esta medición:

- **Los días del comentario son los que cubren las órdenes mostradas**, no los del rango pedido.
  Como el barrido trae órdenes anteriores, decir «3 OC en 15 días» cuando dos son de meses atrás
  exageraba la recurrencia.
- **La consulta filtrada por organismo no es exhaustiva**: perdió 5 de 6.199 órdenes (0,08%) que
  sí existen y sí son de ese organismo. Se documentó en `CLAUDE.md` y se mantiene la
  arquitectura, porque la alternativa cuesta 200 veces más datos.

### Lo que este módulo dejó pendiente

- ~~**La app es pública y ahora gasta su ticket personal.**~~ **Resuelto el 18-08**: la app
  quedó restringida a sus dos correos desde Streamlit ▸ Sharing.
- Falta el cruce con su catálogo (recurrencia, quién ganó, precio pagado contra el publicado,
  IDs que no tiene) y la hoja **«Mis instituciones»** (la opción B ya elegida).

### Para venderlo (pendiente, no resuelto)

- **Cada cliente necesita su propio ticket**, por los términos (es personal, se monitorea por
  IP) y porque la API atiende **una consulta a la vez**: dos usuarios con el mismo ticket se
  estorban.
- Falta revisar los términos de ChileCompra sobre uso comercial de los datos.
- Falta autenticación de verdad: hoy la app es pública y solo el envío de correo tiene clave.

## 17-08-2026 · Se da vuelta la arquitectura: nace la bodega

El 17-08 en la mañana se había descartado la base de datos con el argumento de ella: «si la
herramienta consulta en vivo con filtros, no hace falta nada corriendo de fondo». **Al usarla
se cayó ese argumento**: consultar el histórico de una institución tomaba 7,3 minutos, y eso
no es una herramienta de trabajo. Ella lo dijo claro: bajar todo una vez y después consultar
lo guardado, aunque los datos tengan 24 horas.

### Lo que se midió antes de construir (un día real, no estimaciones)

| | |
|---|---|
| Órdenes de Convenio Marco en un día de Chile | 2.009 de 15.976 |
| Productos comprados (líneas) | 10.724 |
| Consultas gastadas | 1.992 |
| Tiempo | 39 minutos |
| Peso guardado en parquet | 0,41 MB el día |

De ahí salió todo el diseño: un año son 151 MB, **más de los 100 MB que admite GitHub**, así
que la bodega va **partida por mes** (12 MB cada archivo). Y hubo una sorpresa: **958 reintentos
en 1.992 consultas**. La API rechaza casi la mitad de las peticiones aunque se vaya de a una,
así que el ritmo real es 1,16 s por orden y no 0,3.

### Las dos capas, que es lo que hace viable «todo Chile»

- **El mapa** (qué unidad compró, cuándo, qué convenio) cuesta **1 consulta por día**: los 594
  días de 2025-2026 se bajaron en **11 minutos**. Resultado: 453.248 órdenes y **4.293 unidades
  compradoras**, contra las 2.103 del catálogo armado con 8 días. Eso resuelve de raíz la
  molestia original: buscaba instituciones que no estaban.
- **El detalle** (productos, precios, proveedores) cuesta **1 consulta por orden**: 2.000 al día.
  Un año de todo Chile son 733.000 consultas ≈ 3 meses de noches. Por eso se llena de a poco,
  **empezando por lo más reciente**, que es lo que sirve para vender.

Se descartó priorizar por institución: las 300 unidades que más compran son solo el 62% de las
órdenes, así que filtrar ahorra 1,6 veces y no diez. No compensa la complejidad.

### Dónde vive y quién la llena

`bodeguero.py` corre en **GitHub Actions** a las 02:00 de Chile (dentro de la ventana 22:00-07:00
que pide ChileCompra) y guarda los parquet en el propio repositorio. Es **gratis**: los repos
públicos no pagan minutos de Actions. Se puede cortar y retomar: `estado.json` recuerda qué días
están listos.

Riesgo asumido y conversado: las consultas salen de servidores de GitHub, no de su IP, y el
ticket es personal y monitoreado por IP. **No se sabe cómo lo interpreta ChileCompra.**

### La app lee la bodega, pero sigue funcionando sin ella

Si el período pedido está completo en la bodega, se lee de ahí: **0,08 segundos y cero
consultas**. Si le falta aunque sea un día, se consulta en vivo como antes, y la pantalla dice
de dónde vienen los datos. Se comprobó que ambos caminos devuelven **las mismas órdenes y el
mismo monto** ($51.475.160 en la prueba).

El catálogo de unidades ahora **combina** el CSV con la bodega en vez de reemplazarlo: el
bodeguero va averiguando los nombres de a una consulta por unidad, y mientras no sepa uno manda
el CSV. La frecuencia de compra sí se recalcula con la bodega, y cambia mucho: Gendarmería RM
pasó de un estimado de 8 días a **9.899 órdenes** reales.

## 18-08-2026 · Acceso restringido y ajustes de pantalla

**La app dejó de ser pública.** Era el pendiente 1: cualquiera con el enlace podía quemar las
10.000 consultas diarias de su ticket personal. Se resolvió sin código, con **Streamlit ▸
Manage app ▸ Settings ▸ Sharing ▸ «Only specific people can view this app»** y sus dos correos.
Se descartó por ahora una portada propia con clave: la pantalla de acceso de Streamlit no se
puede personalizar, pero protege igual y no cuesta mantenimiento.

Ajustes de pantalla pedidos por ella:

- **Se eliminó la barra lateral** («Modo 2 · Conexión API»), que no hacía nada y se comía 300 px.
  Con eso y quitando el tope de ancho, el contenido pasó de ~980 a **1.270 px**.
- **Logo y título centrados**, y en celular en dos líneas (logo arriba, título más chico).
- **Favicon e icono del celular**: el logo original es horizontal (400x225) y salía aplastado,
  así que se genera `icono.png` cuadrado. Para que el acceso directo del celular muestre el logo
  y no una captura hace falta `apple-touch-icon`, que Streamlit no pone.
- **Mercado Público quedó como pestaña inicial.** `st.tabs` no permite elegir cuál abre, así que
  se invirtió el orden. Eso obligó a mover la carga del catálogo de ofertas a `main`, porque la
  pestaña de Mercado Público lo necesita y ahora se dibuja primero.
- **El correo se acortó** a «Le comparto adjunto nuestros ID disponibles en Convenio Marco según
  sus últimas compras»: nombrar la institución y contar los productos sonaba a circular.

## 18-08-2026 · El estado se decide contra el CATÁLOGO, no contra las ofertas

Corrige una decisión del 17-08 que estaba mal encaminada. Ese día se acordó que «MI ESTADO» se
decidiera contra el catálogo de ofertas, con la advertencia de que cubría poco. Al usarlo quedó
claro el costo: de 54 productos que compró la Escuela Naval, solo 7 salían CON STOCK.

**En la misma carpeta de Drive estaba `CATÁLOGO CONVENIO MARCO.xlsx`**, con **22.626 productos**
en cuatro pestañas (Alimentos, Aseo, Emergencia y Prevención, Escritorio). Nunca se había
mirado. Son dos archivos con papeles distintos:

| | Qué es | Cuántos | Para qué sirve |
|---|---|---|---|
| **CATÁLOGO** | todo lo que vende, sin precio | 22.626 | decide CON STOCK / NO LO TENGO |
| **OFERTAS** | lo rebajado de la semana | 843 | llena MI OFERTA |

Regla nueva, tal como la pidió: **primero se compara contra el catálogo**; si además está en
oferta lleva el precio, y si no, sale igual con un guión. Un producto que vende pero que esta
semana no está rebajado ya no desaparece.

El resultado en la Escuela Naval: **de 7 a 18 productos CON STOCK**. Los 11 que se recuperaron
incluyen Gatorade por $6,1 millones, Sprite por $2,4 millones y papel Tork. Decidir por las
ofertas dejaba fuera el 96% de lo que puede vender.

El comentario ahora distingue tres casos: «no está en tu catálogo», «lo vendes, sin oferta esta
semana» y la comparación de precio cuando sí hay oferta.

## 20-08-2026 · La cuota agotada mentía: decía que la institución no compraba nada

El defecto más grave encontrado hasta ahora, y estaba en silencio.

Cuando el ticket agota sus 10.000 consultas del día, la API **no devuelve un error**: responde
**HTTP 203 —que es un código de éxito— con `{"Codigo":203,"Mensaje":"Ticket superó la cuota
diaria asignada."}`**. El código lo tomaba por respuesta buena, no encontraba «Listado» dentro y
concluía que no había órdenes. En pantalla salía **«No se encontraron órdenes de Convenio Marco
de la Escuela Naval en el período consultado»**, que es falso y podía hacerle descartar una
cuenta que sí compra.

En el bodeguero era peor: habría marcado días como descargados con cero filas, dejando **huecos
permanentes** en la bodega. Se revisó y **no alcanzó a pasar** (8 días marcados, 9 con datos, 0
huecos), pero por suerte, no por diseño.

Ahora los dos detectan el 203: la app avisa que se acabó la cuota del día, y el bodeguero se
detiene guardando lo que alcanzó, sin marcar nada de más.

Se descubrió porque una consulta que el día anterior devolvía 390 órdenes devolvió 0.
**Cualquier respuesta sin `Listado` pero con `Mensaje` hay que tratarla como fallo.**

## 20-08-2026 · Simplificación de la pantalla

Todo salió de que ella miró la pantalla y encontró cosas que sobraban o se contradecían:

- **El período ahora manda**: la tabla muestra solo lo comprado dentro de las fechas pedidas.
  Se eliminó la casilla «ocultar compras anteriores», que era redundante: si se pide un período,
  se espera ese período. El costo asumido: en rangos cortos se ve bastante menos (39 → 3 en el
  Hospital de Quilpué), porque el barrido arrastra compras viejas que ahora se descartan.
- **Se quitó el filtro por año del convenio.** Confundía: el número es el año del convenio, no el
  de la compra, así que al filtrar 2026 aparecía CM24 y parecía un error.
- **Una propuesta por rubro.** Si se marcan productos de Alimentos y de Aseo salen dos PDF y dos
  correos: mezclar convenios en un mismo documento obliga al comprador a separarlo.
- **Columna DIF%**: la oferta comparada con el precio promedio que pagó esa institución.
  Negativo es a favor. Es el número que decide si hay argumento de venta.

### Por qué no se puede saber el convenio de un producto que ella no vende

Ella pidió asignar el convenio también a lo que está fuera de su catálogo. Se buscó por cuatro
vías y **ninguna sirve**:

1. **Ningún campo de la orden lo trae** (se volcaron todos los campos de 2.047 órdenes CM).
2. **`CodigoLicitacion` viene vacío** en todas.
3. **La categoría del producto** (UNSPSC) aparece en solo el **3%** de los items.
4. **Los rangos de ID se solapan** entre rubros: Alimentos (4.194.512-4.751.313) pisa a Aseo y a
   Escritorio, así que no se puede clasificar por número.

Lo que sí existe: `licitaciones.json?codigo=2239-9-LR24` devuelve **«Convenio Marco para la
adquisición de Alimentos», 2024**, con sus productos por categoría UNSPSC. Pero no hay forma de
conectar una orden de compra con ese código. **Queda pendiente una lista ID → convenio que cubra
todos los productos**; el catálogo de ella solo cubre los 22.626 que vende.

## 20-08-2026 · Cuánto falta para tener todo (medido, no estimado)

Ella pidió llenar la bodega 24/7 hasta terminar. **Correr 24/7 no sirve**: el límite no es el
tiempo sino **10.000 consultas por día** del ticket, que se gastan en 3,2 horas. Ya se usa el
máximo.

Tampoco se puede abaratar el costo por orden. Se probó pedir varias órdenes en una consulta
(coma, parámetro repetido, punto y coma) y traer el listado con los productos incluidos
(`detalle=1`, `incluirItems=true`, `ordenesdecompra/items.json`): **todas rechazadas**. Una
orden = una consulta, y no hay vuelta.

Quedan **453.248 órdenes** por bajar (2025 completo + 2026 hasta hoy):

| Tickets | Plazo |
|---|---|
| **1 (el actual)** | **51 días** — 2026 solo, 21 días |
| 2 | 26 días |
| 3 | 17 días |

Dos ajustes que sí sirvieron: subir el presupuesto de 9.000 a **9.800** por noche, y una
**pausa de 0,6 s** entre consultas que baja los rechazos de la API del 34% al 22% sin costar
tiempo (1,15 s por orden en ambos casos, porque cada rechazo obliga a reintentar). Si los
rechazos consumen cupo, eso adelanta la fecha final una semana.

**La única palanca real es un segundo ticket.** Es personal por RUT, así que habría que pedir
uno a nombre de Comercial Emergenza. El bodeguero puede alternarlos sin cambios grandes.

Va del día más reciente hacia atrás, así que no es esperar 51 días para tener algo: en una
semana están los últimos ~2 meses, que es donde está la venta.

## 21-08-2026 · Los datos abiertos de ChileCompra cambian todo

Ella preguntó si `datos-abiertos.chilecompra.cl` servía para el pendiente del convenio.
Servía para eso **y para el problema de fondo**.

### El archivo que reemplaza 51 días de descarga

`https://transparenciachc.blob.core.windows.net/oc-da/AAAA-M.zip` — **un archivo por mes con
todas las órdenes de compra de Chile**, ~100 MB, actualizado a diario con un día de desfase,
desde 2007. Una fila por producto comprado, con 78 columnas.

| | API (lo que había) | Datos abiertos |
|---|---|---|
| 2025-2026 completo | 51 días | **54 minutos** (y 6 min si los ZIP ya están) |
| Costo en el ticket | 9.800 consultas diarias | **cero** |
| Convenio de cada orden | imposible | **viene en el archivo** |

Resultado: **1.289.616 líneas de Convenio Marco, 310.985 órdenes, 20 meses, 35,4 MB en
parquet**. Cobertura del **93,3%** de lo que la API había mapeado en 51 días; el 6,7% que falta
son órdenes creadas antes de enero de 2025 (casi todas del convenio 2024), que están en los
archivos de 2024 y no se bajaron.

**Tres verificaciones contra datos ya conocidos, las tres cuadran**: la Escuela Naval del 3 al
17 de agosto da **11 órdenes** (lo mismo que la API), el plátano ID 4196839 da **15 órdenes**
(lo mismo que costó dos barridos largos) y la consulta de todo 2026 pasó de **7,3 minutos a 2
segundos**.

### Dos trampas del archivo

- **`AAAA-1.zip` es ENERO, no el semestre 1.** Al principio se leyó como semestral y los números
  no cuadraban: 14.538 órdenes de Convenio Marco donde debían ser cientos de miles.
- **`CodigoUnidadCompra` NO es el prefijo del código de la orden.** Son dos identificadores
  distintos y **solo coinciden en el 37%** de los casos. Usando la columna del archivo, el cruce
  con el catálogo daba **cero filas**. La unidad se saca del código de la orden, como en todo el
  resto del sistema.

### El filtro por convenio, resuelto

La columna `Codigo_ConvenioMarco` trae el código (`2239-9-LR24`) y el nombre se pide una sola
vez a `licitaciones.json` (~28 consultas): «Convenio Marco para la adquisición de Alimentos».
La Escuela Naval compra por **ocho convenios distintos**; filtrando Alimentos quedan 188 de 267
productos.

Cuando la consulta es en vivo (un día que la bodega aún no tiene) el convenio no existe, y ahí
el filtro cae al rubro del catálogo de ella, como antes.

### Lo que queda del bodeguero viejo

`bodeguero_api_viejo.py.txt` se guarda como referencia. El nuevo baja **solo los dos últimos
meses** en cada corrida (~5 minutos); con `--completo` rehace toda la historia. Bajar los 20
meses cada noche serían 50 minutos para nada, porque los meses viejos ya no cambian.

---

## 21-08-2026 · La bodega nueva no llegaba a la app (dos fallas encadenadas)

El cambio a datos abiertos estaba hecho y medido, pero **no había llegado a la app publicada**.
La corrida manual de la tarea nocturna (#6) falló a los 6 minutos y no guardó nada.

**Por qué se cayó.** En GitHub había quedado el `2026-08.parquet` del bodeguero de la API, que
**no tiene la columna `convenio_marco`**. Al mezclarlo con lo nuevo, esas 65.044 filas quedan con
el convenio vacío (NaN, que es un número), y la lista de convenios se ordena mezclando números
con textos: `TypeError: '<' not supported between instances of 'float' and 'str'`. Bajó los dos
meses —seis minutos— y murió justo al final.

De paso quedó a la vista el daño que se evitó: esas 65.044 filas viejas se sumaban a las 38.542
nuevas del mismo mes, así que de no haber reventado, los montos de agosto salían inflados.

**Tres correcciones:**

- `--completo` ahora **vacía la bodega antes de bajar**. Rehacer la historia encima de lo que ya
  estaba duplicaba líneas; es lo que «rehacer» tenía que significar desde el principio.
- Los convenios se ordenan **solo entre textos**, así ningún parquet incompleto vuelve a tirar
  abajo la tarea de la noche.
- Si en una corrida completa falla la descarga de un mes, **se detiene sin guardar**: media
  historia es peor que la de ayer completa (y como falla el paso, Actions no alcanza a subir
  nada).

**La segunda falla, silenciosa: la app no se enteraba de la bodega.** La app decide entre
consultar lo guardado o ir en vivo leyendo `bodega/estado.json` (la lista de días con detalle), y
el bodeguero nuevo **nunca escribía ese archivo**: dejaba otro, `bodega/detalle/estado.json`, con
los meses procesados. En GitHub el archivo que la app lee declaraba **9 días** (13 al 21 de
agosto), así que todo lo demás se consultaba en vivo por la API —lento y gastando ticket— aunque
el dato estuviera en disco. Y no era un problema de una vez: cada día nuevo tampoco quedaba
marcado.

Ahora lo escribe `anotar_cobertura()` al terminar. Cubre **desde el primer mes descargado hasta
el último día con compras**, sin huecos, porque los archivos de datos abiertos traen el mes
entero. Los meses anteriores a enero de 2025 que aparecen en la bodega **no se declaran**: solo
tienen las órdenes que se colaron por fecha de creación, no el mes completo, y darlos por
cubiertos sería mostrar datos a medias sin avisar. El mismo campo `actualizado` es el que suelta
la caché de la app, que también estaba congelada.

**Resultado (22-08, 01:48 UTC).** La corrida completa tardó **6 minutos**, no una hora: en el
servidor de GitHub el cuello de botella no es la descarga sino la lectura de los ZIP, y eso ya
estaba medido («6 min si los ZIP ya están»). Quedaron publicados los **25 parquet** y
`bodega/estado.json` declarando **598 días, del 01-01-2025 al 21-08-2026**. Comprobado contra la
copia local: mismas filas y mismo monto (enero 2025: 61.607 líneas / $49.293.197.698; agosto
2026: 38.542 / $30.533.944.097), **cero duplicados** y el convenio marco completo en todas. Los
archivos difieren byte a byte de los locales solo por la versión de pyarrow del servidor.

Medido con la app entera (`AppTest`) sobre esos mismos datos: Escuela Naval, **1 de enero al 21
de agosto de 2026 en 3,9 segundos y cero consultas al ticket** — 267 productos, $621.242.979. Por
la API ese mismo rango tardaba 7,3 minutos.

## 21-08-2026 · Un solo día que faltaba mandaba la consulta entera a la API

Con la bodega ya publicada, la primera consulta real siguió demorando minutos. El aviso lo decía:
«La bodega tiene **233 de estos 234 días**, así que el 1 que falta se consulta en vivo». Como la
regla es todo-o-nada, ese único día arrastraba a los otros 233 a la API: varios minutos de espera
y 234 consultas del ticket, teniendo el dato en disco.

**El día que faltaba era «hoy», y nunca iba a estar.** Dos motivos encadenados: los datos abiertos
se publican con **un día de desfase**, así que hoy jamás está en la bodega; y el servidor de
Streamlit corre en **UTC**, que después de las 20:00 de Chile ya va en el día siguiente, así que
`date.today()` proponía una fecha que en Chile todavía no existía. Pasaba con la consulta por
defecto, sin que ella tocara nada.

Ahora el período se propone **hasta donde la bodega llega**, y el día de hoy se calcula con la
hora de Chile. La consulta por defecto pasó de minutos a **1,3 segundos**. Se puede estirar el
rango hasta hoy igual que antes, y ahí la app avisa que irá en vivo.

**De paso volvió el filtro de convenio.** El nombre del convenio solo existe en los datos de la
bodega; al caer la consulta en vivo, el filtro se degradaba al rubro del catálogo de ella. Con la
consulta leyendo la bodega, la Escuela Naval muestra sus **ocho convenios con nombre**
(«Artículos de Aseo e Higiene», «Gas Licuado de Petróleo», «Artículos de Escritorio y
Papelería»...). No era un filtro que faltara: era el síntoma del mismo problema.

**Y un ajuste de pantalla que pidió ella:** la lista de unidades compradoras se despliega por
encima de lo que viene abajo y tapaba el botón «Consultar Mercado Público». Se le limitó el alto
a 190 px y se dejó un respiro de 90 px antes del botón, para que el botón siga a la vista con la
lista abierta.

## 21-08-2026 · Filtrar antes de consultar, y dos correcciones del envío

Con el módulo ya funcionando contra la bodega, ella usó el flujo completo (consulta, PDF y correo
a una institución real) y de ahí salieron tres cosas.

**El convenio se elige ANTES de consultar.** Estaba abajo, junto a la tabla: primero salían los
267 productos y después ella filtraba. Lo dijo claro: «necesito ser yo quien filtre la información
que quiera visualizar primero, no después». Ahora el selector aparece sobre el botón, con los
convenios por los que **esa institución** compró en **ese período** —salen de la bodega, no de una
lista fija— y todos vienen marcados, así que no filtrar sigue siendo lo por defecto. El selector
de abajo se eliminó: repetirlo obligaba a filtrar dos veces lo mismo; en su lugar queda una línea
que recuerda qué convenio está aplicado. En una consulta en vivo no se puede ofrecer (el convenio
no viene en la API), y ahí sigue apareciendo abajo el filtro por rubro del catálogo.

**El PDF dice INSTITUCIÓN, no CLIENTE.** El documento se manda a un comprador público que todavía
no le compra: tratarlo de cliente da por hecho algo que no está.

**El asunto del correo lleva el número de cotización, no el nombre de la institución.** Era «ID
disponibles en Convenio Marco - Centro de Salud Mental Comunitaria de San Felipe | Comercial
Emergenza»; quedó **«ID disponibles en Convenio Marco | Comercial Emergenza 2208-0235»**. Quien lo
recibe ya sabe dónde trabaja; el número, en cambio, es con lo que identifica el documento adjunto
cuando responde. De paso el número se resuelve una sola vez por propuesta: como el sugerido lleva
la hora, pedirlo dos veces podía dar un número en el asunto y otro en el documento.

## 21-08-2026 · Tres ajustes de uso, ya con envíos reales hechos

**El asunto termina en el número de cotización.** Salía «... Comercial Emergenza 2208-0306-ALI»:
cuando hay productos de dos rubros se generan dos propuestas y el número lleva un sufijo («-ALI»,
«-ASE») para distinguir los documentos. Ese sufijo identifica al **archivo**, no al correo, así
que se sacó del asunto. Los dos correos quedan con el mismo asunto y se distinguen por el adjunto.

**El convenio se elige de una lista, no marcando etiquetas.** El multiselect llegaba con los ocho
convenios marcados y había que ir sacándolos uno por uno; en el celular ocupaban media pantalla.
Ahora es una lista desplegable con **«Todos los convenios»** primero y uno por opción: un toque,
sin etiquetas.

**Vuelven los atajos de período: 7, 15, 30, 90 días, 1 año y «Libre».** Se habían quitado el 17-08
para dejar solo el calendario, y al usarlo pidió los dos. Conviven: el atajo mueve las fechas
—terminando siempre en el **último día que tiene la bodega**, para que la consulta sea inmediata—
y «Libre» deja el calendario a mano, que es como arranca. El atajo solo actúa cuando ella lo
cambia: si se aplicara en cada dibujado, no podría mover una fecha sin que se le volviera atrás.

De paso, el valor inicial de las fechas dejó de pasarse como `value=` y se deja en `session_state`:
darlo de las dos maneras a la vez —y el atajo escribe ahí— es lo que Streamlit reclamaba en el
registro.

### Alcance: solo Convenio Marco

Al ver que la bodega permitía análisis de mercado (quién compra, contra quién se compite, precio
nacional) se ofreció ampliarla a licitaciones y trato directo, que también vienen en el archivo
de datos abiertos. **Ella dijo que no**: por ahora solo Convenio Marco, ni licitaciones ni
grandes compras. Es donde vende, y mantenerlo acotado deja la bodega en 35 MB en vez de ~300 MB,
que es donde GitHub y el plan gratuito de Streamlit empiezan a apretar.

---

## Pendientes

1. **Bajar también 2024** si hace falta el 6,7% de órdenes anteriores a enero de 2025.
2. **Agente de IA** para preguntarle por ID, precios y acciones comerciales (punto 10 del
   18-08). Requiere clave de API de Anthropic y tiene costo por consulta. Ella dijo «ahora no».
3. **Hoja «Mis instituciones»**: que la app lea las unidades que sigue. El archivo de partida con
   40 unidades está en `Mis-instituciones.xlsx`; falta subirlo como hoja de Google y leerlo.
4. **Precio promedio de mercado** (todo Chile, no solo la institución consultada): se puede
   calcular cuando la bodega tenga suficiente historia. Sería el dato para fijar precio
   competitivo de verdad.
5. **Separador de miles**: la tabla usa el idioma del navegador y en su Chrome sale con coma
   (34,345,500) en vez de punto. Se arregla cambiando el idioma de Chrome a español de Chile.
6. **Correr las dos suites que consultan la API** (`test_mp.py` y `test_panel_mp.py`): el 20-08
   no se pudo porque la cuota estaba agotada. Todo lo verificable sin API pasó.

## 22-08-2026 · Pestaña «Cotización por región»

Encargo: tomar el requerimiento que manda una institución, cruzarlo contra el catálogo y
cotizar **solo lo que está publicado en la región de esa institución**. La región es el
filtro que manda: un ID de Valparaíso no se le puede ofrecer a Magallanes.

- **Vive dentro del panel, no en una herramienta aparte.** El catálogo, el formato del PDF y
  la firma ya estaban resueltos aquí; duplicarlos habría dejado dos documentos que se
  desalinean solos. Se agregó como segunda pestaña (`seccion_cotizacion_regional`).
- **El requerimiento entra como planilla** (`.xlsx` o `.csv`), con una columna de ID y otra de
  cantidad. Sin columna de cantidad se asume 1: el documento igual sirve como listado de
  disponibilidad. Un ID repetido suma cantidades, no genera dos líneas.
- **Lo que sale del documento se elige en pantalla**, porque no todas las ocasiones piden lo
  mismo: precio (ninguno / oferta de la semana / mi precio publicado) y cantidad+total sí o
  no. Con cantidades y precio el PDF se titula COTIZACIÓN; sin ellas, ID DISPONIBLE POR
  REGIÓN.
- **Lo no disponible no se borra: se muestra como N/D** en un bloque aparte, después de la
  tabla principal. Si desapareciera, el comprador creería que no se revisó su pedido.
- **El catálogo real trae la columna «REGIÓN» en las cuatro pestañas** (Alimentos, Aseo,
  Emergencia y Prevención, Escritorio): 22.626 ID, todos con producto.
- **«IP» y «JF» son Isla de Pascua y Juan Fernández**, no basura: 704 ID de la pestaña Aseo.
  Se leen como **zona propia y no como Valparaíso**, aunque administrativamente pertenezcan a
  esa región. Si se fusionaran, un ID que solo se despacha a la isla aparecería disponible en
  Valparaíso continental. Quedan como dos opciones más en el selector.
- **El catálogo no tiene columna de precio.** El modo «mi precio publicado» existe pero hoy
  saldría entero como «A solicitud»; la pantalla lo avisa en vez de entregar un PDF vacío de
  precios. Para usarlo hay que agregarle al archivo del catálogo una columna «MI PUBLICADO».
  El modo «precio de oferta» sí funciona: ese precio viene del archivo OFERTAS.
- Sin correo: el encargo pedía el PDF. El envío se puede enganchar después con `propuesta()`.

## 22-08-2026 (tarde) · El cruce es por NOMBRE, no por ID

Al probarla con un requerimiento real, los 105 productos salieron «No está en tu catálogo».
El motivo: **la planilla que manda la institución no trae ID de Convenio Marco**. Trae su
código interno (`0130012`) y un nombre genérico (`MARGARINA`, `MAICENA`, `TE EN HOJAS`). Ese
código no existe en el catálogo y nunca va a existir.

- **Se cruza por el nombre del producto.** La columna obligatoria de la planilla pasó a ser la
  descripción; el código de ellos se conserva solo para mostrarlo. Si ese código resultara ser
  un ID real de Convenio Marco, ese manda y no se adivina nada.
- **Hay un diccionario de equivalencias** (`SINONIMOS_PRODUCTO`): «maicena» → «ALMIDÓN DE
  MAÍZ», «aceite vegetal» → «ACEITE MARAVILLA», «papel confort» → «PAPEL HIGIÉNICO». Es la
  lista que hay que ir engordando cada vez que aparezca un producto que existe con otro nombre.
- **La primera palabra manda.** «ACEITE VEGETAL» tiene que traer aceites, no «ATÚN EN ACEITE»:
  si el tipo de producto no está, no es. Con el tipo calzando se mide cuánto del resto coincide.
- **Se exige la misma inicial para aceptar un parecido.** Sin esa regla «QUESILLO» calzaba con
  «HUESILLO» (jugo en polvo), que es otro producto.
- **Tres niveles de calce, visibles en pantalla**: `exacto` (el nombre coincide entero),
  `parecido` (coincide en parte) y `sugerencia` (es del mismo tipo de producto, segunda
  pasada). **La sugerencia nunca viene marcada**: marcarla sola terminaría cotizando un ID
  equivocado. Es la que rescata casos como «AJÍ SALSA» → «AJÍ EN CREMA».
- **Ella elige en pantalla, no el buscador.** Tabla editable con casillas: viene marcado el que
  mejor calza y, entre iguales, **el más barato**. Puede marcar varios ID del mismo pedido,
  cambiar la cantidad o desmarcar.
- **El PDF muestra el ID de Convenio Marco y la descripción del catálogo**, porque es con ese
  ID que el comprador genera la compra. Lo que no tuvo equivalencia va abajo como N/D, con el
  código de ellos y el nombre que pidieron.
- **El orden por precio solo alcanza a una parte.** Los precios vienen del archivo OFERTAS
  (843 productos): en la Región Metropolitana solo 352 de 2.396 ID publicados tienen precio.
  Los sin precio van después de los con precio. Para ordenar todo por precio habría que
  agregarle una columna de precio al archivo del catálogo.

Probado contra el catálogo real: 14 productos escritos como los escribe la institución, 14 con
equivalencia encontrada (antes: 0). 105 líneas se cruzan en menos de 1 segundo.

## 22-08-2026 (tarde 2) · Ajustes de Serling sobre el Módulo Cotizador

Se llama **Módulo Cotizador** (antes «Cotización por región»).

- **El documento y el asunto llevan empresa y organismo**: «Id Convenio Marco Comercial
  Emergenza, HOSPITAL DE TALCA, 2208-1629». El asunto llevaba solo el número desde el 18-08
  (el comprador ya sabe dónde trabaja); Serling pidió el nombre porque ella también busca el
  correo entre los enviados y ahí el número solo no distingue nada.
- **Los dos precios juntos**: el normal (MI PUBLICADO) y el de oferta, uno al lado del otro,
  para que el comprador vea el ahorro. El total usa el de oferta cuando existe y el normal
  cuando no. Con solo el normal la casilla de oferta va con una raya, no «A solicitud»: el
  producto se puede cotizar igual.
- **Los anchos de las columnas del PDF se calculan según el texto** (`anchos_automaticos`),
  con mínimo y máximo por columna y la descripción quedándose con lo que sobra. Antes eran
  fijos y la descripción salía apretada mientras «CANT.» sobraba.
- **Mercado Público: el ID salió de la descripción.** La API lo antepone («(4194137) PLATANO
  AMARILLO») y así ordenar por PRODUCTO ordenaba por número. El ID sigue en su columna.
  Se le agregó buscador a esa tabla, que con 465 productos era imposible de recorrer a ojo.
- **NaN no es un precio.** Una celda vacía de pandas es NaN y NaN es «verdadero» en Python:
  `if precio` daba por bueno un precio vacío y el total salía en blanco. De ahí
  `numero_o_nada`.

### Por qué faltaban productos, caso por caso

- **AZÚCAR CAMSA**: sí la encontraba, pero el corte era de 6 candidatos y hay 46 productos con
  azúcar en RM. El tope subió a 12 y, entre los que no tienen precio, ahora ordena por nombre
  (antes quedaba el orden del catálogo, o sea el azar). Además se agregó un **buscador libre**
  que permite agregar a mano cualquier ID de la región, la salida definitiva para cuando el
  buscador automático no propone lo que ella quiere.
- **FIDEOS GUISO ESPIRAL / QUIFARO**: falla real. El buscador exigía que la **primera** palabra
  del pedido existiera en el catálogo, y ahí la pasta se llama por su forma («ESPIRALES
  CAROZZI»): la palabra «fideos» no aparece nunca. Ahora también se llega por cualquier palabra
  distintiva del pedido **cuando el producto del catálogo empieza con una de las palabras
  pedidas**. «SOPA … CON FIDEOS» no entra, porque empieza con SOPA.
- **COMINO MOLIDO**: no era falla. El comino existe en el catálogo (1 ID) **solo en la Región
  Metropolitana**, y la consulta era de Valparaíso. El N/D estaba bien: es exactamente lo que
  el filtro regional tiene que hacer.
- **CUSCÚS**: no está en el catálogo, en ninguna región (0 de 22.626).
- **FIDEOS COLORES**: no hay pasta de colores publicada en Valparaíso.

## 22-08-2026 (noche) · Que las sugerencias tengan sentido

Probando con un requerimiento real de 105 líneas aparecieron sugerencias absurdas. Dos reglas
nuevas, las dos por la misma razón: la idea es vender como abasto («no tengo ese, tengo este
otro que cumple»), y una sugerencia que no cumple es peor que ninguna.

- **El gramaje manda.** Si el pedido dice el contenido («GALLETA CHOCOCHIP 125 GRS»), solo
  entran los productos cuyo contenido esté dentro de **±20%** (`VARIACION_MEDIDA`). Ofrecer 35 g
  contra un pedido de 125 g no es una alternativa, es otro producto. Se comparan gramos con
  gramos y mililitros con mililitros; si una de las dos partes no dice el contenido, no se
  exige nada. Lo lee `medida_del_texto`, que entiende K/KG/G/GR/L/LT/ML/CC y toma el contenido,
  no el envase («10 G CAJA 240 UNIDADES» son 10 g).
- **Empezar con el tipo genérico ya no basta.** «LECHE ASADA» es un postre, y traía leche
  líquida, cultivada, evaporada y en polvo: todas empiezan con LECHE. Ahora, cuando el producto
  del catálogo empieza con la **primera** palabra del pedido, se exige una segunda coincidencia.
  Si empieza con una palabra **posterior** del pedido («ESPIRALES...» para «fideos guiso
  espiral») basta con eso, porque ahí el catálogo está usando ese término como nombre del
  producto. Resultado: «LECHE ASADA» trae los tres postres de leche asada y nada más.
- **Las columnas de la tabla en pantalla también se ajustan al contenido** (`ancho_en_pantalla`,
  en píxeles). Por eso `requirements.txt` pasó a `streamlit>=1.60`: los anchos numéricos en
  `column_config` necesitan una versión reciente.
- Se sacó el corte por marca que se había probado antes: en el catálogo la segunda palabra no
  siempre es la marca («ACEITE MARAVILLA NATURA» → MARAVILLA para todos) y botaba productos
  buenos. El orden simple (calce, formato normal antes que sachet, precio, nombre) alcanza.

## 23-08-2026 · El documento, afinado

- **El nombre del archivo se descargaba como basura.** Chrome guardaba
  «42156ec716b91d3cc94e924faa173c13» sin extensión: las **comas** rompen la cabecera con la
  que el servidor manda el nombre. Ahora es «Id Convenio Marco Comercial Emergenza
  {organismo si se escribió} {número}.pdf», sin comas, sin tildes y sin signos raros.
- **ENVIAR A muestra uno solo**: el organismo si se escribió, y si no la región. Antes salían
  los dos y, sin organismo, el documento parecía dirigido a una región.
- **La columna ARTÍCULO pasó a llamarse PRODUCTO** y los títulos de las dos tablas del PDF van
  centrados (antes «ARTÍCULO» quedaba descolgado a la izquierda del resto).
- **Los precios vacíos escribían «None» en la tabla de la pantalla.** Con precios y `None`
  mezclados la columna queda de tipo «objeto» y Streamlit imprime el texto; se fuerza a número
  y la celda vacía queda vacía.

**«A solicitud»** en la columna de precio significa que ese ID no tiene precio cargado: no está
en las ofertas de la semana y el catálogo no trae columna de precio. Hoy solo 843 ID del
catálogo tienen precio (352 de los 2.396 publicados en RM), así que la mayoría sale así. Se
arregla agregándole al catálogo la columna «MI PUBLICADO».

## 23-08-2026 (tarde) · El tipo de producto manda

Tres reportes de Serling, una misma causa: la regla estricta que arregló «LECHE ASADA» dejaba
fuera pedidos legítimos cuando no había nada mejor.

- **Segunda pasada.** Si ningún candidato calza de verdad (nadie llega a 0,6), se suman los
  productos **que se llaman como lo pedido**, como sugerencia y sin marcar. «SAL DE MESA» no
  tenía nada —«MESA» no existe en el catálogo— y quedaba N/D; ahora propone la SAL FINA de
  kilo. Lo mismo con «QUEQUE INDIVIDUAL». Cuando sí hubo un calce firme, la reserva no se usa,
  así que «LECHE ASADA» sigue trayendo solo los tres postres.
- **El tipo de producto manda al ordenar y al filtrar.** Si existen productos cuyo nombre
  EMPIEZA con lo pedido, los demás se descartan: ante «QUEQUE CHOCOLATE» ya no aparece una
  barra de chocolate, y ante «AJI SALSA» aparece el ají y no la salsa de tomate. Solo cuando no
  existe ninguno se muestran los otros («LECHE ASADA» → los postres, que empiezan con POSTRE).
- **El prefijo ahora exige dos palabras largas.** Con solo mirar la primera, «SAL» calzaba con
  «SALSA» y la sal fina se colaba entre las salsas.
- **«A solicitud» pasó a ser un guión (-).** Pedía una acción; el guión solo informa que ese ID
  no tiene precio de oferta esa semana, que es lo que de verdad ocurre. La nota al pie del PDF
  lo explica.

## 23-08-2026 (noche) · MI PUBLICADO ya existe, y los anchos por fin se aplican

- **El catálogo de Drive ya trae la columna «MI PUBLICADO»** en sus cuatro pestañas, y con
  precio en los 22.626 ID (el archivo pasó a llamarse «CATÁLOGOS CONVENIO MARCO.xlsx»). O sea
  que el modo «precio normal» dejó de ser teórico. Se agregó la columna **MI PRECIO** a la
  tabla de selección y a la del buscador, al lado de **P. OFERTA**: así se elige cuál ofrecer
  según la ocasión.
- **Los anchos en píxeles no se estaban aplicando.** `column_config` acepta el ancho numérico
  desde Streamlit 1.48 y el centrado (`alignment`) desde la 1.55; en versiones anteriores el
  número **se ignora en silencio** —por eso las columnas seguían anchísimas en la app
  publicada— y `alignment` directamente revienta. Ahora se pregunta por la versión
  (`ANCHO_NUMERICO`, `ACEPTA_CENTRADO`) y, si es vieja, se cae a las tallas
  `small`/`medium`/`large` en vez de romperse. **Hay que subir `requirements.txt`**
  (`streamlit>=1.60`) para que la app publicada los respete.
- **Las celdas sin precio escribían «None».** `pd.to_numeric` no bastaba: hay que dejar la
  columna en `Float64` (con mayúscula), que es el tipo numérico que admite vacíos.
- Las columnas cortas (ID, CALCE, MI PRECIO, P. OFERTA, CANT.) van centradas; la descripción
  del producto sigue a la izquierda, que es como se lee un nombre largo.

## 23-08-2026 (noche 2) · El kilo escrito con letras y el «diet» del catálogo

- **«KILO» sin número no se leía.** El filtro de gramaje busca «1 K», «500 G»; ante «JALEA
  NARANJA KILO» no encontraba medida, no filtraba nada y proponía presentaciones de 22 g
  habiendo de un kilo. Ahora, si no hay número, se leen las palabras sueltas KILO/KILOS/LITRO
  como 1.000 g o 1.000 ml.
- **«DIET» y «LIGHT» son la misma cosa.** La institución pide «JUGO DIET PIÑA POLVO» y el
  catálogo lo escribe «JUGO EN POLVO **LIGHT** LIVEAN…» o «para **diabéticos**». Se agregó
  `GRUPOS_EQUIVALENTES`, una lista de palabras que valen lo mismo al comparar (diet = light =
  dietética = diabético; polvo = instantáneo). Es la otra lista que hay que ir engordando,
  junto con `SINONIMOS_PRODUCTO`.
- **Polvo no es líquido.** Aunque compartan el resto del nombre, un jugo líquido no resuelve un
  pedido de jugo en polvo. `CONTRARIOS` descarta esos pares de frente.

Resultado: «JALEA NARANJA KILO» propone las dos jaleas de 1 kilo y ninguna de 22 g; «JUGO DIET
PIÑA POLVO» propone los once jugos en polvo light y ningún líquido.

## 23-08-2026 (madrugada) · La tabla se montaba sobre el texto

Al abrir la lista de productos en pantalla completa, la tabla se pintaba encima del texto de
más abajo («83 ID marcados…», el buscador, el bloque N/D). La causa era el
`st.container(border=True)` que la envolvía: el recuadro crea su propio marco de apilado y la
vista ampliada quedaba atrapada dentro en vez de cubrir la página. La tabla de selección quedó
fuera del recuadro y sin alto fijo (Streamlit calcula el suyo y la tabla trae su propia barra
de desplazamiento). Comprobado: ampliada ocupa la ventana completa y no hay texto debajo.

## 24-08-2026 · Galleta de soda y bebida láctea

Dos equivalencias más, del mismo tipo que «diet = light»:

- **Agua = soda.** La galleta «de agua sin sal» es la que el catálogo llama «de soda». Antes
  «GALLETAS DE AGUA SIN SAL» proponía solo las dos de agua; ahora propone las siete (dos de
  agua y cinco de soda, incluida la 4204235 que faltaba).
- **«Yogu yogu» es una marca, no un producto.** En el catálogo eso se llama «LECHE SABORIZADA
  BEBIDA LACTEA», así que el sinónimo apunta al tipo y no a «yogurt». Con eso «YOGU YOGU MORA
  200ML» trae las cuatro bebidas lácteas (Colún frutilla, Colún vainilla, Shake a Shake manjar
  y la propia Yogu Yogu) y, más abajo, las leches saborizadas de 200 ml de otras marcas. El
  filtro de contenido deja fuera las de 1 litro.

Ojo con las equivalencias en cascada: «YOGU YOGU» → «LECHE SABORIZADA BEBIDA LACTEA» dispara la
regla de «BEBIDA LACTEA» si esa también está en la lista, y el texto queda duplicado. Cada
término se traduce a uno solo, y no a otro que también esté traducido.

## 27-08-2026 (noche) · La app se cayó por memoria, y la bodega ya no se lee entera

El panel publicado quedó en «Oh no. Error running app» desde las 21:33 UTC. **El registro de
Streamlit no tenía ni un traceback**: se leyó completo hasta el final y solo hay líneas de
despliegue. Eso ya es el diagnóstico — un error de Python deja traza; un cierre por falta de
memoria mata el proceso sin escribir nada.

**La cuenta que lo confirma**, medida sobre los parquet de verdad bajados del repositorio:

| | Antes | Ahora |
|---|---|---|
| Un mes de detalle en memoria | 47 MB | se suelta al terminar el mes |
| Los 20 meses juntos | ~800 MB en trozos + otro tanto al concatenar | 6,5 MB la tabla final |
| Peor momento de la carga | **~1.600 MB** | **62 MB** |
| Cachés que hacían eso | **dos** | una |

El techo de Streamlit son ~1.000 MB. Con la bodega de solo Convenio Marco (1,2 millones de
líneas) cabía; con las seis vías son 8,3 millones y dejó de caber. Y eran **dos** cachés
—`modulo_oportunidades.cargar_compras` y `modulo_alertas.cargar_ordenes`— leyendo las mismas
filas, porque `st.tabs` dibuja todas las pestañas en cada corrida aunque nadie las abra.

**La decisión: nadie necesitaba las líneas sueltas.** Todo lo que se le pedía a esa tabla era
sumar plata y contar proveedores por comprador, así que ahora se suma **al leer**, mes a mes:
415.864 líneas de un mes quedan en 93.621 filas —el 22%— y no se pierde un peso. La columna
`lineas` guarda cuántas órdenes había detrás de cada fila, que es lo único que se contaba.
Comprobado contra el cálculo crudo: mismo mercado, mismo vendido, mismas unidades, mismo
retrato del comprador, mismo nombre del proveedor.

Las tres funciones que leían el detalle **son una sola**: `alertador.resumen_de_ordenes`. La
usa el correo diario y la envuelve la única `@st.cache_data` del panel, en
`modulo_oportunidades.cargar_compras`; `modulo_alertas` le pide a esa misma. Además la pestaña
Alertas **ya no abre la bodega al dibujarse**: con el formulario en blanco —que es como llega
todo el que entra— no toca un solo parquet.

**Lo que había que reiniciar, no bastaba con subir el arreglo.** Después de un cierre por
memoria, Streamlit sigue mostrando «Oh no» aunque despliegue el código nuevo: *Manage app ▸ ⋮ ▸
Reboot app*. Recién ahí levantó.

### Un error que salió a la luz de paso: el convenio «NA»

Desde que la bodega guarda las seis vías, las órdenes que **no** son de Convenio Marco traen
`convenio_marco = "NA"`. La pantalla de Oportunidades arma «el mercado de sus rubros» con los
convenios por los que el RUT ya vendió, y ahí entraba «NA»: `isin` se llevaba entonces **todas**
las líneas que no son Convenio Marco de Chile entero, y el mercado del proveedor salía
multiplicado. `convenios_de()` lo saca a mano. Un valor de relleno que parece un dato es la
misma trampa del RUT `'UPLEVEL'` de la mañana.

### El correo de las 08:00 no habría salido, y la corrida habría dicho «success»

El cron **sí funciona**: el 27-08 disparó dos veces sola (turnos 13 y 18) y las dos se cortaron
en «Nadie pidió recibirlo a esta hora», porque los 3 suscriptores están en el turno de las 8.
Pero la rama que decide entre enviar y ensayar estaba escrita así:

```bash
if [ "${{ github.event.inputs.ensayo }}" = "false" ]; then   # enviar
```

**`github.event.inputs` no existe cuando dispara el horario**: llega vacío, la comparación da
falso y la corrida programada se iba siempre por el ensayo (`--guardar`). Habría salido
«success», el registro habría dicho que armó el correo, y a los suscriptores no les habría
llegado nada — el peor tipo de falla, la que no se ve. Ahora una corrida `schedule` fuerza
`ENSAYO=false`: **programada siempre envía**, y el ensayo queda para las corridas a mano, que
es donde se pidió que viniera marcado por defecto.

## 27-08-2026 (noche 2) · La puerta pasa a ser propia

Decidido con Serling: **Auth0**, **20 días de piloto**, y el registro pide correo, contraseña
y **RUT** — no teléfono. El plan completo está en `PLAN_PUERTA_Y_PLANES.md`.

**Por qué Auth0 y no un formulario propio.** No es preferencia: **Streamlit no recuerda una
sesión que no sea suya**. Un login escrito a mano dentro de la app se pierde en cada recarga
—el cliente aprieta F5 y vuelve al login—, y la única forma de que la sesión aguante es
`st.login()`, que exige un proveedor externo. Entre los proveedores, Auth0 es el único que
deja crear cuenta con contraseña (Google directo deja fuera a quien no tenga Gmail) y su plan
gratis incluye **un dominio propio para la pantalla de login**, así que esa pantalla puede
vivir en `uplevelweb.art` aunque el panel siga en `streamlit.app`.

**Por qué el teléfono no se pide ni se verifica.** Verificar por SMS cuesta USD 10/mes fijos
por el número chileno más ~USD 0,13 por registro (Twilio) — más que el VPS que se descartó. Y
sobre todo **verifica el canal equivocado**: el producto se entrega por correo, así que un
teléfono confirmado no sirve de nada si el correo está mal escrito. La verificación que sí
conviene es gratis y ya existe: **el primer correo de alerta es la prueba de que la dirección
funciona**; si rebota, Resend avisa. El teléfono se pide después, cuando hay algo que ofrecer
a cambio («¿te aviso por WhatsApp lo que cierra en 24 horas?»).

**Por qué el RUT sí es obligatorio.** Es la llave del producto —la bolsa de palabras sale de
ahí—, identifica a la empresa para `cuentas`, y filtra basura gratis: un RUT inventado no pasa
el dígito verificador, y esa función ya estaba escrita.

**Y una limitación que dejó de existir sin que nadie lo notara.** Estaba escrito que un RUT sin
Convenio Marco no podía armar su bolsa. **Ya no es cierto desde que la bodega guarda las seis
vías**: probados cinco proveedores que solo venden por licitación, trato directo y compra ágil,
sacaron 30, 52, 63, 67 y 111 términos. Cambia a quién se le puede vender esto. Ojo con la
calidad: en esos casos las palabras salen de textos de licitación y entra relleno («bases»,
«adjuntar», «2026»), que es justo lo que `quitar_palabras_de_todos` limpia al enviar.

### Cómo quedó armada la puerta

- **Mientras no exista `[auth]` en los secretos, no cambia nada.** `puerta()` devuelve lo
  mismo que `quien_soy()`. Por eso el código se pudo subir sin riesgo y sin coordinar nada.
- **Es lo único del panel que falla cerrado**, y la regla vieja se partió en dos: *quién entra*
  cerrado, *qué ve* abierto. Con `[acceso] siempre` en los secretos como llave de repuesto,
  para que «cerrado» no signifique «nadie puede entrar a arreglarlo».
- **`st.user.is_logged_in` revienta con AttributeError** si la identificación no quedó bien
  configurada, en vez de devolver `False`. Descubierto probando: sin `_entro()` de por medio,
  una coma mal puesta en los secretos tumbaba el panel entero.
- **El orden de encendido importa**: primero los secretos con la app todavía privada, se prueba
  en incógnito, y recién ahí se suelta la lista de Streamlit. Al revés, la app queda abierta un
  rato con la puerta a medio poner.

## 28-08-2026 · La puerta se abrió, y el silencio de 17 horas

Dos cosas en el mismo día: el login propio quedó funcionando, y se tapó el agujero
del embudo.

**El login.** `st.login()` con Auth0 arrancó al tercer intento, y los dos primeros
fallos no estaban en la configuración sino en librerías que Streamlit no trae:
`Authlib` primero, y `httpx` después —que Authlib declara como opcional y no
instala solo—. Las dos revientan **al apretar entrar**, no al volver del proveedor:
si el error aparece ahí, no hay que ir a mirar el callback. El tercer fallo sí fue
el callback, y la causa fue mía: puse el nombre del campo dentro del recuadro de
copiar y se pegó junto con la dirección.

- Auth0 quedó a nombre de `webuplevel@gmail.com`, no del correo personal. La cuenta
  que administra la puerta es un activo del negocio; la que **entra** al panel sigue
  saliendo de la tabla `usuarios`. Son cosas distintas y el instructivo las confundía.
- **En incógnito no se puede probar** mientras la app siga privada: Streamlit frena
  antes con su propia pantalla. Eso no es una falla del login.

**El correo de bienvenida.** Quien se inscribía a las 15:00 no recibía nada hasta
las 08:00 del día siguiente. Diecisiete horas de silencio justo en el momento de más
entusiasmo, y el producto sin mostrarse ni una vez.

- Se resolvió **dentro de `alertador.py`**, no como pieza aparte: `--bienvenidas`
  recorre el mismo camino del correo diario y solo cambia la presentación. La razón
  es que las oportunidades salen de la bodega con pandas, y eso no corre ni en
  Supabase ni en el navegador: el correo instantáneo de verdad no era posible, así
  que la pregunta real era cuánto se demora. Quince minutos.
- **La regla que obligó a cambiar la selección:** un primer correo vacío mata la
  impresión. Si nada alcanza el mínimo de coincidencias, se baja el listón a 1 una
  sola vez y van las mejores cinco. Para eso hubo que apartar la selección en una
  función pedible dos veces. Se comprobó contra el ensayo anterior: mismas 2
  oportunidades, misma nota 85 (A). El diario no cambió.
- El workflow son **dos trabajos**. El que baja los 121 MB del repositorio solo
  despierta si un `curl` de dos segundos dice que hay alguien esperando. Sin eso
  serían 96 descargas al día para descubrir que no hay nadie.
- **Se decidió no subirlo yo.** Es lo único de este cambio que manda correos solo,
  así que va en `bienvenida-workflow-para-copiar.txt` para que lo encienda ella.

**Posicionamiento, decidido de paso:** `inteligencia.uplevelweb.art` no será una app
con marca propia sino un **producto de Uplevel**. El activo son nueve años dentro de
Mercado Público, y eso no es transferible a una marca nueva. Una persona sola no
sostiene dos marcas.

## 28-08-2026 (tarde) · El correo de las 08:00 llegaba a las 18:00

Mirando la lista de corridas por otro motivo apareció algo que nadie había medido:
las tres únicas corridas automáticas del correo diario salieron con 9h45, 8h13 y
7h53 de atraso. No fallaban —la del turno de las 08:00 duró 17 minutos y mandó el
correo— pero llegaban ocho horas después de la hora prometida.

- **La causa no tiene arreglo por nuestro lado.** El `schedule:` de GitHub Actions
  es «cuando se pueda»; en repositorios públicos la cola es la de menor prioridad.
- **Por qué no se podía dejar así:** la página promete que las compras ágiles
  cierran en 24 a 72 horas y que por eso hay que enterarse el mismo día. Un correo
  que llega a las 18:00 pierde el día. Era el argumento central del producto.
- **Se descartó cambiar la promesa** («cada día» en vez de «cada mañana a las
  8:00»): más honesto, pero le quitaba al producto lo que lo hace valer.
- Se mudó el reloj a **Supabase con `pg_cron`**, que ya estaba contratado y es
  puntual. Llama a GitHub por `pg_net` a la hora exacta; GitHub sigue haciendo el
  trabajo. Se prefirió sobre un servicio de cron externo por no sumar una cuenta
  más ni dejar una llave de GitHub en un tercero.
- La bienvenida se colgó del mismo reloj, cada 5 minutos, **con la pregunta hecha
  en SQL**: si nadie se inscribió, ni siquiera llama a GitHub.
- **El horario de GitHub se quita solo después** de comprobar que el nuevo reloj
  funciona. Al revés quedaría un rato sin ningún correo.

Corrección de esa misma mañana: se le dijo a Serling que el correo de las 08:00 ya
había salido ese día. No era así; a las 15:50 todavía no había corrido.

## 28-08-2026 (noche) · La página puente deja de ser una bifurcación

`inteligencia.uplevelweb.art` preguntaba «¿te inscribes o entras al panel?» a
alguien que todavía no sabía qué era el producto. Un desvío antes de haber
explicado nada, y con la mitad del tráfico mandado a una pantalla de login que
no le sirve.

- **Pasa a ser UNA landing.** Explica, muestra el correo, y el formulario está
  abajo en la misma página. «Entrar al panel» queda como enlace chico arriba,
  que es lo que necesita el que ya es cliente.
- **El formulario se mudó de `/alertas/` a la portada, y hay UNA sola copia.**
  `/alertas/` ya circula en enlaces compartidos, así que no se borró: redirige
  al ancla. Dos copias del mismo formulario se desincronizan siempre.
- **Lo que le faltaba no eran animaciones: era mostrar el producto.** Antes
  describía el correo con palabras. Ahora hay una tarjeta igual a la que manda
  el sistema —comprador, cuánto gasta, quién se lo lleva, nota— marcada como
  ejemplo. Y las cifras propias, que no se estaban usando: 1,2 millones de
  órdenes cruzadas, 6 vías, +9 años.
- **El mensaje de éxito ya no dice «mañana».** Desde que existe el correo de
  bienvenida, la primera alerta sale en minutos, y el texto tenía que decirlo.
- La aparición al bajar lleva **red de seguridad**: a los 1,8 segundos se
  muestra todo igual, dispare o no el vigía. Una animación que no ocurre es un
  detalle; una página en blanco es una venta perdida.
- Comprobado antes de publicar: sin desborde horizontal ni a 370 px ni a
  1280 px, los cuatro bloques visibles, 9 campos en el formulario, sin errores
  de consola.
- **No se pudo publicar:** Hostinger devolvió `Failed to fetch upload
  credentials` en los cinco intentos. Es la trampa 10, ya conocida. Quedó un
  reintento programado.

**Pendiente de decir en voz alta:** la landing promete «Gratis 20 días», que es
lo que ya publica uplevelweb.art. Hoy **nada en el código corta a los 20 días**
—eso es el paso 3 del plan, `cuentas.hasta` respetado por el alertador—. Es una
promesa comercial que todavía se sostiene a mano.

### 28-08-2026 (noche) · El reloj quedo andando

Supabase dispara y GitHub responde. Se quito el `schedule` de `alertas.yml`:
pg_cron es ahora el unico reloj, y por eso ese workflow ya no lleva horario
propio —si se le repone, se dispara dos veces—.

**Lo que costo la hora:** el bloque de SQL se corrio sin reemplazar el marcador
`PEGAR_AQUI_LA_LLAVE`, asi que el baul guardo esas 19 letras como si fueran la
credencial y GitHub devolvio 401. Se encontro comparando el largo de lo
guardado (19) contra el de un token real (93). **Un 401 apunta a la
credencial; un 403 habria sido el permiso.** Esa distincion ahorro rehacer
todo el formulario del token, que estaba bien desde el principio.

**Lo que no funciono:** manejar el editor SQL de Supabase por el navegador. Los
clics caian en el boton equivocado —abrieron dos veces el panel «Connect»— y se
abandono a proposito antes que seguir tocando cosas al azar en produccion. El
formulario de GitHub si se pudo manejar. Para diagnosticar sirvio mas disparar
el workflow con `gh` desde el computador: probo que el problema no era el
workflow ni el nombre del archivo, sino lo que salia de Supabase.

### 29-08-2026 (madrugada) · El primer correo de bienvenida salio

Cadena completa, sola: pg_cron detecto al suscriptor pendiente, llamo a GitHub,
GitHub armo el correo y Resend lo entrego (`cc55a1a8-6448-40ae-a308-5db412b70244`).
Una oportunidad, nota 92 (A). **14 min 32 s** de punta a punta.

- **El fallo que aparecio mirando:** el reloj dispara cada 5 minutos y el trabajo
  demora 15. Se apilaron tres corridas y cada una habria mandado su propio correo.
  Se cancelaron dos a mano y se le puso `concurrency` al workflow. **Cualquier
  workflow disparado mas seguido de lo que demora necesita esto.**
- **El «no me llega el correo» no era del reloj:** Serling se inscribio con una
  direccion que ya estaba, asi que no se creo fila nueva —se actualizo la que
  habia, que ya tenia fecha en `bienvenida_enviada`— y quedo fuera de la cola. Se
  encontro contando las filas de `suscriptores`: seguian siendo cuatro. La
  leccion es mirar el dato antes de sospechar del mecanismo nuevo.
- Su suscripcion filtra por **11 palabras y no por RUT**: 14 terminos y una sola
  oportunidad. Con el RUT serian decenas. Vale la pena revisarlo con ella.

### 29-08-2026 · Los módulos por plan

Lo que Serling pidió al principio de todo. `modulo_planes.py` es la única lista de
qué abre cada plan; si aparece otra en algún archivo, está de más.

- **La estructura real no era la del borrador.** El plan escrito listaba «Mercado» e
  «IPT» como pestañas; en el código son secciones anidadas: el itinerario vive dentro
  de Mercado, que vive dentro de Oportunidades. Se construyó sobre lo que hay.
- **La pestaña cerrada se dibuja igual.** Esconderla dejaría al cliente sin saber que
  existe, y sin entender de qué le hablan cuando le llegue el correo de fin de prueba.
- **Los dos extras de Emergenza sí se esconden**, porque no están a la venta.
- **Falla abierto a propósito:** sin plan legible se ve todo. Un cliente que paga y no
  encuentra su pestaña se va; uno que ve de más por un rato, no.
- De paso, el catálogo de Drive **ya no se lee** si la cuenta no tiene ninguno de los
  dos módulos que lo usan. Para un cliente cualquiera eran segundos de espera en cada
  pantalla, para nada.
- Probado con 20 casos de la tabla de decisión antes de subir: los tres planes, el
  piloto, soporte, el plan desconocido y los extras por cuenta.

### 29-08-2026 · El muro del fin de prueba

Dos extensiones de 10 días y **cada una se paga con un dato**: el teléfono la primera,
el motivo la segunda. Es diseño de Serling y es mejor que las tres opciones que se le
ofrecieron: un vencimiento normal solo pierde clientes; este los convierte en una
conversación y en información de producto. Quien no contesta el teléfono igual deja
escrito qué le faltó para pagar.

- **El alta se hace dentro de Postgres**, colgada del trigger que ya existía, y no
  tocando el formulario de la landing ni `inscribir_alerta`. Menos piezas que coordinar.
- **Sin RUT no se crea cuenta.** El panel es de una empresa y la empresa se identifica
  por su RUT. Quien se inscribe solo con palabras recibe correos igual. Empuja en la
  dirección correcta: con el RUT las alertas son mucho mejores.
- **Nada de esto puede tumbar el alta.** Todo va dentro de un `exception when others`:
  si falla, la inscripción entra y queda una advertencia en el registro. Una persona
  que no puede inscribirse es peor que una cuenta que hay que crear a mano.
- **La identidad se hizo tolerante** a que las columnas nuevas no existan, para que no
  importe el orden entre pegar el SQL y subir el código.

### 29-08-2026 · La cifra del comprador salia al doble

Buscando por que la bienvenida demoraba 15 minutos aparecio un error viejo: la tarjeta
del correo dice **«en lo que tu vendes · ultimos 12 meses»** y `main()` cargaba la
bodega a **24**. La cifra que veia el cliente —el diferenciador del producto, lo que
ningun competidor pone— estaba al doble de lo que prometia su propia etiqueta.

- Se corrigio para los **dos** correos, no solo la bienvenida: el diario tenia el mismo
  problema desde siempre.
- **El panel sigue a 24 y esta bien**: alli la columna se llama «Gasto 24m» y dice lo
  que muestra. El error era la desalineacion, no el numero de meses.
- De paso acorta el trabajo a la mitad, que era lo que se estaba buscando.

Y las compras agiles de la bienvenida bajaron de 7 dias a 3. Tampoco es solo velocidad:
una compra agil cierra en 24 a 72 horas, asi que una de hace una semana ya esta cerrada.
Mostrarsela a alguien en su PRIMER correo es peor que no mostrarle nada.

**Leccion:** el error no aparecio revisando el codigo sino midiendo otra cosa. Las
etiquetas que describen datos hay que leerlas contra la consulta que los trae.

### 29-08-2026 · El fin de prueba se avisa por correo, no solo en pantalla

Faltaba la mitad del punto 4.4 del plan: la franja del panel estaba, la línea del
correo no.

- **La franja del panel solo la ve quien entra**, y el que hay que recuperar es
  precisamente el que no entra hace una semana. Ese se enteraba chocando con el muro.
  El correo diario sí lo abre.
- **Aparece a falta de 3 días, no antes.** Una cuenta atrás de tres semanas se
  vuelve ruido y se deja de leer justo cuando importa.
- **En la bienvenida no aparece nunca.** Tres centímetros más arriba ya dice «tienes
  20 días con todo abierto»; repetirlo el primer día suena a apuro por cobrar.
- **Siempre dice que el correo sigue llegando.** Es la promesa del plan: lo que se
  cierra es el panel, no las alertas.
- **Falla abierto**, como la identidad: una sola consulta para toda la tanda y, si se
  cae o la columna `hasta` todavía no existe, se envía igual sin la franja. El correo
  con las oportunidades del día vale mucho más que el recordatorio.
- Probado con los 9 casos: sin fecha, a 20, a 4, a 3, a 1, el último día, vencida, y
  las dos de bienvenida.

### 29-08-2026 · Dónde se van los 20 minutos de la bienvenida

Primera medición completa, corrida 33230120662 (todavía con 24 meses y 7 días):

| Tramo | Tiempo |
|---|---|
| Bodega | 5 s |
| Bolsas de términos | 14 s |
| **Consultas a Mercado Público** | **1.194 s** |
| Fichas y envío | 29 s |
| TOTAL | 1.242 s (20 m 42 s) |

**El 96% son las consultas a la API.** La bodega no tiene nada que ver, así que
los 24→12 meses no acortan casi nada: se hicieron por la etiqueta que mentía, y
eso sigue siendo motivo suficiente.

- **La marca estaba mal puesta:** una sola para las dos consultas. Decía «1.194 s»
  sin decir cuál de las dos, y son cosas distintas que se arreglan distinto. Las
  licitaciones pagan **2 segundos de espera obligatoria por cada detalle** (170
  candidatas de 4.717 ⇒ ~340 s solo en esperas); las compras ágiles pagan páginas.
  Ahora se miden por separado.
- **No se tocó nada más todavía.** Con el reparto medido se decide; sin él, acortar
  a ciegas es apostar.

### 29-08-2026 · El techo de páginas cortaba en silencio

`compras_agiles_abiertas` trajo **exactamente 2.000**: 40 páginas de 50, el techo
justo. Un número redondo en un dato de la calle es siempre sospechoso — había más
compras ágiles y no se pidieron.

- El techo de las licitaciones **sí avisa** («se piden solo las primeras 400»); el
  de las ágiles terminaba el `for` sin decir nada. Ahora avisa igual, con un
  `for ... else`.
- **No se subió el techo.** Puede que no importe —si la API devuelve lo más nuevo
  primero, lo que quedó fuera son ágiles ya cerradas— pero eso hay que comprobarlo,
  no suponerlo. Primero que se vea; después se decide.
- Es el mismo error que la cifra de los 12 meses, en otra parte: **un dato que sale
  mal sin que nada falle**. No hay excepción, no hay log rojo, el correo se ve
  perfecto.

### 29-08-2026 · La pantalla de entrada quedó con cara de Uplevel

Personalizada en dos lugares de Auth0, que es como Auth0 lo separa:

| Dónde | Qué |
|---|---|
| **Settings ▸ General** | Friendly Name `Uplevel`, Logo URL, Support Email, Support URL, idioma español |
| **Branding ▸ Universal Login** | Primary `#f18c3f`, Page Background `#0c2c57` |

Comprobado con **Getting Started ▸ Login Box ▸ Try It Out**, que abre la pantalla real
sin necesitar el panel: sale «Te damos la bienvenida», «Inicia sesión en **Uplevel**»,
botón naranjo y fondo marino.

- **El logo va DENTRO del recuadro blanco**, no sobre el fondo. Por eso su fondo blanco
  sólido no se nota y no hizo falta una versión transparente. Era la única duda que
  había quedado abierta al personalizarlo.
- **El Support URL apunta al WhatsApp** (`wa.me` con `?text=` ya escrito), para que el
  mensaje llegue diciendo de dónde viene. Ese número queda público: lo ve cualquiera
  que se tope con una pantalla de error de Auth0. Decisión tomada sabiéndolo.
- La aplicación ya se llamaba `Uplevel Inteligencia`, así que la frase «para continuar
  con…» sale bien sin tocar nada. La otra, `Default App`, la creó Auth0 y no se usa.

### 29-08-2026 · El botón de Google queda con llaves de prueba, a propósito

`google-oauth2` usa las **llaves de desarrollo de Auth0**: Client ID y Secret vacíos, y
Auth0 lo avisa en amarillo («not recommended for Production environments»).

**Decisión de Serling: dejarlo así por ahora** y salir a vender. Queda anotado qué
implica, para reconocerlo si aparece:

- Límites de uso de Auth0, la pantalla de permisos de Google no dice Uplevel, y Auth0
  no lo soporta para producción.
- **El riesgo que más va a doler no son las llaves**, es otro: el sistema encuentra al
  cliente porque el correo del panel es el MISMO con que se suscribió. Quien toca
  «Continuar con Google» suele elegir su Gmail personal y cae en «Tu cuenta todavía no
  está habilitada».
- **Síntoma a reconocer:** un cliente que dice que no puede entrar. La primera pregunta
  es si entró con el botón de Google.
- Se apaga en un clic cuando se quiera (Authentication ▸ Social), o se arregla bien con
  credenciales propias de Google Cloud (~30 min).

### 30-08-2026 · El panel quedó público, y la puerta aguanta

Se abrió `Manage app ▸ Settings ▸ Sharing` a acceso por enlace. Es el interruptor que
faltaba: hasta hoy ningún cliente llegaba al panel aunque se le creara la cuenta.

**No es irreversible**, al contrario de lo que decía el documento de planificación: en
Streamlit Community Cloud el acceso se cambia de público a privado y de vuelta cuando
se quiera. Se corrigió el dato antes de tocar nada, porque cambiaba la decisión.

**Comprobado desde un navegador sin sesión alguna:**

1. La URL pública muestra **solo la portada** y el botón. Ni un dato.
2. El botón lleva a Auth0 con la marca puesta: «Te damos la bienvenida», «Inicia
   sesión en **Uplevel** para continuar con **Uplevel Inteligencia**», en español,
   botón naranjo, fondo marino.

Sirve `puerta()`, que corre ANTES de leer el Drive y la bodega. Un desconocido no hace
trabajar al servidor.

**Falsa alarma que vale anotar:** la primera prueba en incógnito mostró el itinerario
completo con cifras. No era un agujero: era la sesión de `webuplevel@gmail.com`, que es
`superadmin` y ve todo. **Probar «como si fuera un desconocido» no vale si uno se
identifica en medio de la prueba.**

### 30-08-2026 · El RUT se compara por dígitos, no por texto

Al probar el alta automática se creó una cuenta duplicada de la propia Uplevel: el RUT
llegó como `777119591` y en `cuentas` estaba como `77.711.959-1`. Comparando texto
literal no son iguales, así que el disparador no encontró la cuenta y creó otra.

- **Lo que costaba en la calle:** dos comerciales de la misma empresa, uno escribe el
  RUT con puntos y el otro sin, y quedan en dos cuentas separadas con dos pruebas de 20
  días. No comparten nada y ninguno entiende por qué.
- El disparador ahora normaliza con `regexp_replace(rut, '[^0-9kK]', '', 'g')` en los
  dos lados de la comparación. Comprobado: preguntando por `770820510` devuelve
  «Comercial Emergenza», guardada como `77.082.051-0`.
- `alertador.solo_digitos_rut` ya hacía esto desde antes. **La regla existía y no se
  aplicó en el lugar nuevo** — es el modo típico en que estas cosas se escapan.

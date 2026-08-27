# CIERRE DE SESIÓN — 27 de agosto de 2026, tarde
## Uplevel Inteligencia · de panel a producto: mercado, territorio, cuentas y embudo

**Uso:** pegar esto en Claude Code al abrir la sesión siguiente. Continúa a
`CIERRE_27-08-2026.md` (el de la mañana); lo de allá sigue valiendo salvo en lo
que acá se corrija.

---

## 0. LO PRIMERO: LA APP ESTÁ CAÍDA

`panel-stock-uplevel.streamlit.app` responde **«Oh no. Error running app»**
desde las ~21:33 UTC del 27-08.

**Lo que se sabe:**

- El registro de Streamlit solo muestra despliegues (*Pulling code changes ·
  Processing dependencies · Updated app!*), **sin ningún traceback a la vista**.
  El panel del log estaba cortado a la derecha y sin bajar hasta el final.
- **En local la app SÍ levanta**, con sus seis pestañas, después del arreglo de
  la sección 4. O sea: no es un error de sintaxis ni de importación.
- Los parquet del repositorio **sí** tienen la columna `mecanismo` (comprobado
  en `2025-01`, `2025-06` y `2026-02`), así que el fallo de columnas que se
  arregló era de la bodega local vieja, **no** el de Streamlit.

**Lo primero que hay que hacer en la sesión siguiente:** conseguir el traceback
real. *Manage app* ▸ ensanchar el panel ▸ bajar hasta después del último
«Updated app!». Sin eso se está adivinando.

**Sospecha principal, sin confirmar: memoria.** El techo de Streamlit son
~1.000 MB. La bitácora de la mañana ya anotaba 217 MB con la bodega de solo
Convenio Marco; **hoy la bodega pasó a las seis vías y multiplicó las líneas por
seis**. Además hay dos cachés que cargan el detalle entero por separado
—`modulo_oportunidades.cargar_compras` y `modulo_alertas.cargar_ordenes`— y
`st.tabs` dibuja TODAS las pestañas en cada corrida, así que las dos se llenan
siempre, aunque nadie abra esa pestaña. Un cierre por falta de memoria no deja
traceback, que calza con lo que se ve.

Si se confirma, el arreglo natural es **una sola caché compartida** en vez de
dos, y/o leer el detalle por trozos.

---

## 1. LO QUE SE CONSTRUYÓ HOY EN LA TARDE

| Pieza | Estado | Dónde |
|---|---|---|
| Bodega de Licitaciones corriendo | ✅ 20 meses, 2,7 M líneas, en el repo | `licitaciones.yml` |
| Comunas que faltaban, rellenadas solas | ✅ 269 unidades | `licitador.completar_comunas()` |
| Los cuatro gráficos del mercado | ✅ probado en pantalla | `modulo_mercado.py` |
| El IPT — itinerario de visitas | ✅ probado con datos reales | `modulo_visitas.py` |
| Cuentas, roles y territorios | ✅ código listo, SQL corrido | `modulo_cuentas.py` |
| Soporte Uplevel (superadmin) | ✅ código listo, SQL corrido | `modulo_cuentas.seccion_soporte` |
| El embudo de seguimiento | ⚠️ código listo, **SQL sin confirmar** | `modulo_seguimiento.py` |

---

## 2. LOS TRES SQL DE SUPABASE

| Archivo | ¿Corrido? |
|---|---|
| `supabase-cuentas-para-copiar.txt` | ✅ confirmado: devolvió las 3 filas `admin` |
| `supabase-soporte-para-copiar.txt` | ✅ dijo «listo» |
| `supabase-seguimiento-para-copiar.txt` | ❓ **sin confirmar** — hay que verificarlo |

**Cómo verificar el tercero** (SQL Editor, pegar y Run):

```sql
select count(*) from information_schema.columns
where table_name = 'envios'
  and column_name in ('rut','nombre','comprador','region','monto',
                      'cierre','encaje','motivo','enlace');
```

Tiene que devolver **9**. Si devuelve menos, hay que correr
`supabase-seguimiento-para-copiar.txt` completo.

⚠️ **Esto tiene plazo.** `alertador.anotar_avisado` ahora guarda la foto de cada
oportunidad en esas columnas. Si no existen, la anotación falla en silencio —el
correo igual sale— pero como `ya_avisado` lee de `envios`, **al día siguiente se
reenviarían las mismas oportunidades**.

---

## 3. LO QUE SE ROBÓ DE PIAM, Y CÓMO SE MEJORÓ

PIAM (`piam.cl/panel`) es el competidor que ella tiene abierto. De su pantalla
«Mis oportunidades» se tomaron cuatro cosas, y ninguna tal cual:

**El embudo de seis etapas** — *por revisar · siguiendo · ofertando · ganada ·
perdida · descartada*. Tres diferencias deliberadas:

- **Es de la empresa, no de la persona.** La llave es el RUT. Si el comercial
  del norte marca una como «ofertando», su jefa lo ve sin preguntar.
- **Las tarjetas muestran plata, no cuenta.** «8 oportunidades» no le dice nada
  a nadie; «$14 M en juego» sí. Y cuando hay algo ganado sale **«$X adjudicados
  de oportunidades que salieron de este correo»**, que es la frase de la que
  depende una renovación.
- **«Por revisar» no se guarda en ninguna parte**: es no tener fila en
  `seguimiento`. Así el embudo funciona desde el primer día y no se escribe una
  fila por cada correo que sale.

**El «por qué te llegó»** — PIAM dice *«match perfecto»*, que no se puede
comprobar ni discutir. Acá van las palabras exactas: *«desarrollo, sitio, web,
corporativo»*. Quien lo lee sabe si el sistema entendió su negocio, y si no,
sabe qué palabra corregir.

**La urgencia depende del TIPO**, y es la mejor de las cuatro:

| | PIAM | Acá |
|---|---|---|
| Compra ágil, 20 h | ⚡ rojo | *cierra en 20 h* — normal, se contesta con un precio |
| Licitación, 20 h | ⚡ rojo | **⚠️ no alcanzas a preparar** |

**«Nuevas desde tu última visita»** — con un detalle: la visita se anota **al
final** de dibujar la pantalla. Anotándola al entrar, el aviso se borraba a sí
mismo antes de que alcanzaran a leerlo.

**Dónde está la diferencia de fondo con PIAM:** todo lo que ellos miden es el
embudo propio. No hay una sola cifra sobre el comprador —cuánto compra en tu
rubro, por cuál vía, quién se lo lleva—. PIAM contesta «¿a qué postulo?», que es
justo lo que Mikel dijo que ya no le importa. El mercado y el IPT son la cancha
propia; el embudo va, pero no de titular.

---

## 4. TRAMPAS ENCONTRADAS HOY (no repetirlas)

**El filtro del correo estaba inflado once veces.** `radiografia_de_unidades`
—la que calcula el «$187 M en tus rubros» de la tarjeta— exigía **una sola**
palabra coincidente. Con la bolsa de 100 términos del RUT de Emergenza, que
trae «agua», «blanca», «chile» y «barra», entraban factor antihemofílico, 90
camionetas y la normalización de un hospital. Medido sobre mayo-agosto 2026:
**$572.293 M con una palabra contra $51.081 M con tres**. Ahora usa
`minimo_coincidencias()`, el mismo umbral que ya se usaba para avisar.

**Pedir una columna que el parquet no tiene revienta la lectura entera.** Estaba
resuelto en `alertador.cargar_ordenes` pero **no** en sus dos copias:
`modulo_oportunidades.cargar_compras` y `modulo_alertas.cargar_ordenes`. Desde
una pestaña, eso tumba la app completa con «Error running app». Arregladas las
dos: ahora piden solo lo que el archivo tiene. **Hay tres funciones que hacen
casi lo mismo; deberían ser una.**

**`st.bar_chart` no sirve para un ranking.** Ordena las barras
**alfabéticamente** —«Compras ágiles» antes que «Convenio Marco», que es cinco
veces mayor— y corta los nombres a un puñado de letras. Se cambió a Altair con
`sort="-x"` y `labelLimit`. Altair no agrega dependencia: viene dentro de
Streamlit.

**Streamlit no recarga los módulos importados.** Al probar un cambio en un
`modulo_*.py` hay que **reiniciar el servidor**, no solo refrescar la página, o
se sigue viendo el código viejo. Media hora perdida creyendo que un arreglo no
funcionaba.

**Los heredocs siguen rompiendo archivos.** Un `cat >> archivo <<'FIN'` con
comillas y acentos se cortó a mitad de un texto y dejó `modulo_cuentas.py`
corrupto. **Usar siempre la herramienta de edición**, como ya decía la bitácora.

**Un archivo `.txt` de SQL tiene que ser SQL entero.** Los archivos «para
copiar» tenían el título y las explicaciones como texto suelto; al pegarlos
completos, Postgres se atraganta con la primera línea de `=====`. Ahora **todas**
las líneas son SQL o comentarios `--`, y la comprobación va al final como un
`select`, así se pega entero y se ve el resultado de una. **Los otros dos
archivos (`supabase-alertas-` y `supabase-formulario-`) siguen con la trampa
vieja**; ya se corrieron, pero si hay que repetirlos hay que arreglarlos igual.

**Marcar algo con un valor falso se rompe solo.** La cuenta de soporte se
distinguía por un RUT que decía `'UPLEVEL'`. En cuanto se puso el RUT real,
Uplevel habría aparecido en la lista de «empresas sin administrador». Ahora se
reconoce por `plan = 'soporte'`, que no depende de cómo esté escrito el RUT.

**Los archivos grandes no se suben con `-f content=`.** En base64 un archivo de
68 KB pasa los 90 KB y Windows corta la línea de comandos con «Argument list too
long», sin subir nada y sin error claro. Va por `--input` con un JSON. El script
está en el scratchpad como `subir.sh`.

---

## 5. DECISIONES QUE CONVIENE NO REDISCUTIR

**Nunca dejar a nadie afuera.** Si las tablas de Supabase no existen, si faltan
credenciales o si la consulta falla, el panel se comporta como antes de que
existiera `modulo_cuentas`: se ve todo. Un sistema de permisos que se cae
cerrado convierte cualquier problema chico en «hoy no puedo trabajar».

**Quién ENTRA y qué VE son dos cosas distintas.** Entrar lo decide la lista de
Streamlit (*Manage app ▸ Settings ▸ Sharing*). Qué ve cada uno lo decide
`modulo_cuentas`. Mientras la puerta sea esa lista, **agregar un comercial son
dos pasos**. Para vender el plan Empresa hay que cambiar la puerta por un login
propio: Streamlit 1.61 ya trae `st.login()` / `st.user`, y el módulo no cambia,
solo se agrega el bloque `[auth]` a los secretos.

**Nadie tiene contraseña.** Se entra por correo, así que «se me olvidó la clave»
no existe. Los bloqueos reales son otros: una empresa que desactivó a su único
`admin`, o un correo mal escrito. Eso lo arregla la pestaña 🛟 Soporte.

**El territorio se aplica ANTES de contar las horas del IPT.** Filtrando
después, el comercial de Antofagasta vería su primera visita en la semana 3
—porque delante quedaron las de Santiago, que no son suyas— y su agenda no
significaría nada.

**El IPT no es un calendario para verlos a todos.** Es la línea donde se deja de
visitar y se empieza a llamar. Con datos reales: 1 semana = 33 visitas y 17% de
la plata; 12 semanas = 55,9%.

---

## 6. ARCHIVOS NUEVOS O TOCADOS HOY

| Archivo | Qué pasó |
|---|---|
| `modulo_mercado.py` | **nuevo** — los cuatro gráficos, sobre las seis vías |
| `modulo_visitas.py` | **nuevo** — el IPT, visita por visita |
| `modulo_cuentas.py` | **nuevo** — cuentas, roles, territorios y soporte |
| `modulo_seguimiento.py` | **nuevo** — el embudo de seis etapas |
| `supabase-cuentas-para-copiar.txt` | **nuevo** — corrido ✅ |
| `supabase-soporte-para-copiar.txt` | **nuevo** — corrido ✅ |
| `supabase-seguimiento-para-copiar.txt` | **nuevo** — ❓ sin confirmar |
| `alertador.py` | umbral de coincidencias corregido; guarda la foto en `envios` |
| `licitador.py` | rellena comuna y región del catálogo cada mañana |
| `modulo_oportunidades.py` | lectura de parquet a prueba de columnas faltantes |
| `modulo_alertas.py` | lo mismo |
| `app.py` | pestañas 📌 Seguimiento, 👥 Mi equipo y 🛟 Soporte |
| `requirements.txt` | `altair>=5.0` |
| `CLAUDE.md` | secciones de seguimiento, roles y quién entra |

---

## 7. PENDIENTE

### Urgente — la app caída
Conseguir el traceback real de Streamlit y arreglarlo. Ver sección 0. **Nada
más importa hasta que el panel vuelva a levantar.**

### Con plazo — el correo de mañana
1. Confirmar que `supabase-seguimiento-para-copiar.txt` se corrió (sección 2).
2. **Revisar si el correo de las 08:00 sale solo.** Nunca ha disparado por
   horario; el 28-08 es su primer turno programado de verdad. Si no llega, el
   arreglo ya está decidido: que el workflow lo intente **cada dos horas** y que
   `alertador.py` decida —«¿ya pasó la hora de este suscriptor? ¿ya le mandé
   hoy?»—. La tabla `envios` ya guarda lo necesario.

### De Serling, y solo de ella
**Rotar la clave secreta de Supabase**, que salió en una captura de pantalla. Es
la que se salta RLS y puede leer los correos de todos los suscriptores. Se
genera en *Project Settings ▸ API Keys* y se reemplaza en dos lugares: secretos
de Streamlit y secretos de GitHub.

### Mediano
**Unificar las tres funciones que leen el detalle.**
`alertador.cargar_ordenes`, `modulo_oportunidades.cargar_compras` y
`modulo_alertas.cargar_ordenes` hacen casi lo mismo, con dos cachés separadas
que duplican la memoria. Si el «Oh no» resulta ser falta de memoria, esto pasa a
urgente.

**El filtro compara palabras exactas**: «colchón» no calza con «colchones». Es
así desde antes, pero afecta directamente la calidad del match y vale la pena
mirarlo.

**Hay unidades cuya región y comuna no calzan** —una «Dirección Regional del Bío
Bío» aparece en Santiago—. Es dato de ChileCompra, no del panel, pero desordena
rutas en el margen.

**El mapa con coordenadas.** Necesita las 346 comunas con latitud y longitud,
que no están en la bodega. La agenda en tabla contesta lo mismo por ahora.

### Grande
**Cambiar la puerta por un login propio** (`st.login()` + `[auth]` en los
secretos). Es lo que convierte «agregar un comercial son dos pasos» en uno solo,
y lo que permite vender el plan Empresa sin tocar la lista de Streamlit a mano.

---

## 8. CÓMO SE TRABAJA

**GitHub CLI** autenticado como `Uplevelweb`, no está en el PATH:

```bash
export PATH="$PATH:/c/Program Files/GitHub CLI"
```

El repo pesa ~400 MB, así que **no se clona**: para uno o dos archivos va la API
de contenidos, y el contenido por `--input` (ver sección 4).

⚠️ **Los secretos no los pone Claude, nunca.** `SUPABASE_URL` sí; `RESEND_API_KEY`
y `SUPABASE_SECRET_KEY` los carga Serling.

**La bodega local está vieja**: solo Convenio Marco, sin `mecanismo`. La de las
seis vías vive **solo en el repositorio**. Medir contra los parquet locales da
resultados equivocados. Para probar de verdad hay que bajarse un par de meses:

```bash
curl -sL -o 2026-07.parquet \
  https://raw.githubusercontent.com/uplevelweb/panel-stock/main/bodega/detalle/2026-07.parquet
```

**Probar el correo sin gastar ticket ni enviar nada:**

```bash
python alertador.py --prueba --guardar correo.html
```

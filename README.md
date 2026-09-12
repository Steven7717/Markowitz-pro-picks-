# Markowitz Pro Picks

Analiza empresas del S&P 500 con datos fundamentales sacados directamente de
sus informes a la SEC, propone un top 10-15 razonado, te deja aprobarlo o
corregirlo a mano, y con esa lista calcula cómo repartir el dinero entre ellas.

**Las decisiones las tomas tú.** El programa propone y deja constancia de lo
que apruebas; no compra ni vende nada, y el orden que produce es un criterio
de selección transparente, **no una previsión de rentabilidad** — no está
validado empíricamente y no debe leerse como una recomendación de inversión.

---

## Antes de empezar

No hace falta saber programar, ni instalar Python, ni escribir un solo comando.
Son tres clics y una espera. Lo que sí necesitas:

| | |
|---|---|
| **Un ordenador** | Windows o Mac |
| **Un correo electrónico** | El tuyo. **Es obligatorio**, incluso para la parte gratis: la SEC exige un contacto en cada petición que se le hace, y sin él no se descarga nada |
| **Unos minutos la primera vez** | Se bajan Python y las librerías, varios cientos de MB. Después arranca en segundos |
| **Espacio en disco** | Poco menos de 1 GB una vez instalado (medido: 843 MB, de los que 625 son el Python que se descarga) |

**Opcional:** una clave de [Anthropic](https://console.anthropic.com) si quieres
la mitad con IA. Cuesta dinero tuyo — alrededor de **1,25 $** por cada análisis
completo del S&P 500. Sin ella el programa funciona igual, sólo que sin las
fichas redactadas.

---

## Instalación en Windows

### 1. Descarga el programa

**[⬇ Descargar Markowitz Pro Picks](https://github.com/Steven7717/Markowitz-pro-picks-/archive/refs/heads/master.zip)**

Ese enlace baja un archivo comprimido de menos de 2 MB llamado
`Markowitz-pro-picks--master.zip`. Suele ir a tu carpeta **Descargas**.

<details>
<summary>Si el enlace no funciona</summary>

Entra en
[el repositorio](https://github.com/Steven7717/Markowitz-pro-picks-), pulsa el
botón verde que pone **Code**, y dentro elige **Download ZIP**.
</details>

### 2. Descomprímelo

**Esto no te lo puedes saltar.** Windows deja abrir un ZIP y ver lo que hay
dentro como si fuera una carpeta normal, pero el programa **no funciona desde
ahí**.

Haz **clic derecho** sobre el archivo descargado → **Extraer todo…** → **Extraer**.

Te queda una carpeta llamada `Markowitz-pro-picks--master`. Muévela donde te
apetezca — el Escritorio está bien, y también Documentos. Dentro hay otra
carpeta con el mismo nombre; entra hasta ver estos archivos:

```
Iniciar App.bat
Iniciar App.command
Iniciar App.vbs
programa
README.md
```

### 3. Doble clic en `Iniciar App.bat`

Y ya está. Lo demás lo hace el programa.

> **Si Windows muestra un aviso azul** que dice «Windows protegió su PC», es
> porque el archivo viene de internet y no está firmado por una empresa
> reconocida. Pulsa **Más información** y luego **Ejecutar de todas formas**.
> Sólo pasa la primera vez.

### 4. Qué va a pasar

Se abre una ventana negra con texto. **No la cierres**: ahí es donde corre el
programa.

1. Te preguntará si puede instalar **uv**, una herramienta que descarga Python
   por ti. Escribe `s` y pulsa Enter. *(No instala nada sin preguntarte.)*
2. Te ofrecerá crear un **acceso directo en el Escritorio**. Di que sí: a
   partir de entonces abres el programa desde ahí, sin ventana negra y sin
   venir a buscar esta carpeta.
3. Empieza la descarga. **Tarda varios minutos y parece que no hace nada.** Es
   normal. Son varios cientos de MB.
4. Cuando termine, **se abre solo en tu navegador**. Ya estás dentro.

Las siguientes veces arranca en segundos.

---

## Instalación en Mac

Los pasos 1 y 2 son iguales que en Windows: descargar y descomprimir. Luego hay
tres cosas propias de Mac, y **ninguna vuelve a hacer falta después**. Probado
en macOS 12.7.6 (Intel).

### 1. Saca la carpeta de Descargas

macOS protege Descargas, Escritorio y Documentos. Si el programa se queda ahí,
arranca, escribe dos líneas y se corta sin explicar por qué.

**Arrastra la carpeta a tu carpeta de usuario** — la del icono de la casita. Es
lo más cómodo y evita el problema entero.

<details>
<summary>Si prefieres dejarla donde está</summary>

Ve a **menú Apple → Ajustes del Sistema → Privacidad y seguridad → Archivos y
carpetas** —en macOS Monterey y anteriores se llama **Preferencias del Sistema →
Seguridad y privacidad → Privacidad**—, busca **Terminal** en la lista y marca la
casilla de la carpeta que corresponda. Después cierra Terminal del todo (**Cmd+Q**) antes de volver a
intentarlo.
</details>

### 2. Ábrelo con clic derecho, no con doble clic

La primera vez **haz clic derecho sobre `Iniciar App.command` → Abrir**, y
confirma **Abrir** en el diálogo que sale.

Con doble clic normal, macOS lo bloquea con un error de «desarrollador no
identificado», porque el archivo llegó de internet. Después de abrirlo una vez
con clic derecho, el doble clic ya funciona siempre.

### 3. Ten paciencia con el primer arranque

Se abre una ventana de Terminal y se queda un buen rato sin decir nada mientras
descarga. **No la cierres**: ahí es donde corre el programa. Cuando termine, se
abre solo en el navegador.

<details>
<summary>Si Finder da un error de permisos</summary>

Abre la app **Terminal**, escribe `chmod +x ` (con el espacio final), arrastra
`Iniciar App.command` dentro de la ventana para que escriba la ruta sola, y
pulsa Enter. Una vez y no más.
</details>

Mover o copiar la carpeta más adelante no rompe nada: el programa detecta el
cambio y se rehace solo en un par de segundos, sin volver a descargar.

---

## Lo primero que verás

El programa se abre en tu navegador. Antes de que pueda descargar nada, hay que
darle el correo:

**Barra lateral → Perfil y ajustes → Correo para EDGAR → Guardar credenciales**

Sin eso, la SEC rechaza las peticiones y no se genera nada. No es un registro,
no se envía a nadie más, y se guarda en tu carpeta personal —fuera de la carpeta
del programa— así que si algún día le pasas el programa a alguien, tus datos no
viajan dentro.

A partir de ahí, el recorrido es el que marca la pantalla de inicio: generar
candidatos, aprobarlos, y repartir el capital.

---

## Cómo se actualiza

El programa mejora cada pocas semanas. Hay dos formas de ponerlo al día, y
puedes elegir la que quieras.

### La forma sencilla: volver a descargarlo

Repites los pasos 1 y 2 y tienes la versión nueva. Pero **antes de borrar la
carpeta vieja, copia tus cosas a la nueva**, o las pierdes:

| Carpeta, dentro de `programa/` | Qué guarda |
|---|---|
| `libros/` | **Tus posiciones**: lo que compraste y a qué precio |
| `actas/` | Tus actas de aprobación |
| `portafolios/` | Los portafolios que guardaste |
| `salidas/` | Los rankings que generaste |

Cópialas de la carpeta vieja a la nueva, en el mismo sitio, y sustituye lo que
haya. **Tus credenciales no hace falta moverlas**: viven fuera, en tu carpeta
personal, y las encuentra solo.

### La forma automática: con git

Si instalas [git](https://git-scm.com/downloads) y descargas el programa con él
en vez de con el ZIP, **se actualiza solo cada vez que lo abres** y no tienes
que copiar nada nunca.

Requiere escribir un comando una sola vez, en la Terminal (Mac) o en el Símbolo
del sistema (Windows):

```
git clone https://github.com/Steven7717/Markowitz-pro-picks-.git
```

A partir de ahí, cada arranque comprueba si hay versión nueva y se la trae —
verás una línea de «Buscando actualizaciones…». **Una actualización que falla
nunca te impide usar el programa**: si no hay internet, te lo dice y abre la
versión que ya tienes.

> **¿Cuál elijo?** Si la palabra «Terminal» te pone nervioso, el ZIP. Funciona
> exactamente igual de bien; lo único que cambia es que las actualizaciones las
> haces tú.

---

## Cómo se cierra

Si abriste con **el acceso directo del Escritorio**, no hay ventana negra que
cerrar. Dos formas, las dos valen:

- El botón **«Salir del programa»**, abajo del todo en la barra lateral.
- Cerrar la pestaña del navegador y olvidarte. El programa mira cada pocos
  segundos si queda alguna pestaña abierta, y si lleva minuto y medio sin
  ninguna, se apaga solo.

Recargar la página no lo apaga, y volver a abrir el acceso directo mientras
sigue vivo no arranca un segundo programa: reutiliza el que ya está.

Si abriste con `Iniciar App.bat` o `Iniciar App.command`, además puedes cerrar
la ventana negra.

Lo que hayas guardado se queda donde está en cualquiera de los casos.

---

## Lo que cuesta dinero, y lo que no

El programa funciona en dos mitades:

- **Sin IA — gratis.** Descarga los datos de la SEC, calcula los indicadores y
  ordena las empresas. Es la mayor parte del programa.
- **Con IA — lo pagas tú.** Redacta una ficha por empresa con una tesis y hasta
  tres riesgos, **cada uno citando textualmente el informe original**. Cada cita
  se comprueba contra el documento: si no aparece, la ficha lo dice.

| Qué | Cuánto |
|---|---|
| Análisis completo del S&P 500 con fichas | ~**1,25 $** (estimado al alza a propósito) |
| Interpretar las noticias de tu cartera | ~**0,10 $** por pulsación |
| Comentar una propuesta de rebalanceo | menos de **0,01 $** |

Las pantallas que cuestan dinero **avisan antes de gastarlo y dicen lo que
costó después**. Nunca se llama a la IA sola: siempre hay que pulsar un botón.

### Las credenciales

Los dos datos se meten desde la propia app, en **Perfil y ajustes**, que está
al final de la barra lateral:

| Qué | De dónde sale | Hace falta para |
|---|---|---|
| Un correo electrónico | El tuyo. No es un registro y no se envía a nadie más | **Las dos mitades** — sin él no se genera nada |
| Clave de Anthropic | [console.anthropic.com](https://console.anthropic.com) — es tuya y tú pagas su uso | Sólo la mitad con IA |

Se guardan en tu carpeta personal (`~/.markowitz-pro-picks/credenciales.json`),
**no dentro de la carpeta del programa**. Si comprimes el programa y se lo pasas
a otra persona, tu clave no viaja dentro. Una vez guardada, se muestra siempre
enmascarada (`sk-ant-…4f2a`), nunca entera. Desde ese mismo sitio puedes
**Cambiar**la, **Cancelar** si te arrepentiste a mitad, o **Borrar**la del todo.

---

## Tus posiciones

Si usas el **Seguimiento** para anotar lo que compraste, eso se guarda en
`programa/libros/`, **dentro de la carpeta del programa**. Es la diferencia con
la clave: la clave vive fuera y no viaja nunca; tus posiciones sí están ahí.

Git las ignora, así que no acaban publicadas por accidente. Pero **eso protege
de git, no de un ZIP**: si comprimes esta carpeta y se la pasas a alguien, va
dentro cuánto dinero tienes y en qué. Bórrala antes, o mejor, **pásale el enlace
de descarga en vez de tu copia**.

Lo mismo vale para `programa/actas/` y `programa/portafolios/`, aunque esos
guardan decisiones y pesos, no importes.

---

## Si algo va mal

| Lo que ves | Qué pasa |
|---|---|
| La ventana negra se abre y se cierra de golpe | Falta la carpeta `programa`, o el ZIP se extrajo a medias. Vuelve a descomprimirlo entero |
| «Windows protegió su PC» | El archivo viene de internet. **Más información → Ejecutar de todas formas** |
| En Mac: «desarrollador no identificado» | Ábrelo con **clic derecho → Abrir** la primera vez |
| En Mac: arranca, escribe dos líneas y se corta | La carpeta está en Descargas, Escritorio o Documentos. Muévela a tu carpeta de usuario |
| Se queda minutos sin decir nada | Es la primera descarga. Es normal. No cierres la ventana |
| «No se pudo descargar» al generar candidatos | Falta el correo en **Perfil y ajustes** |

Si abriste con el acceso directo y quieres ver el error, abre el programa con
`Iniciar App.bat` en vez del icono: ese sí muestra la ventana con el detalle.

---

## Para desarrollar

Los comandos se ejecutan desde `programa/`, no desde la carpeta principal: ahí
es donde vive el proyecto de Python, con su `pyproject.toml` y su entorno.

```
cd programa
uv sync --all-groups     # entorno con dependencias de desarrollo
uv run pytest tests/ -q -m "not red"
```

`pandas` está topado por debajo de la versión 3 a propósito (ver
`programa/pyproject.toml`): la 3.0 cambia el comportamiento de `.stack()` y
rompe un test de la investigación. El código está validado contra pandas 2.x.

Los detalles de diseño están en `programa/CONTEXTO.md` y en
`programa/docs/superpowers/specs/`.

## Si vienes de una versión anterior

La estructura cambió: ahora el programa vive dentro de `programa/` y en la
carpeta principal sólo quedan los lanzadores y este archivo. Los lanzadores
entran solos donde toca, así que no tienes que hacer nada para usarlo.

Dos restos que puedes limpiar a mano:

- **Un `.venv` en la carpeta principal**, de unos 600 MB. Ya no se usa: el
  nuevo se crea dentro de `programa/`. Bórralo.
- **`salidas/` y `actas/`**, si habías generado rankings o aprobaciones antes
  del cambio. El programa ahora los busca en `programa/salidas` y
  `programa/actas`. Muévelos ahí y los vuelves a ver; no se han perdido, sólo
  están donde ya no se mira.

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
| **Espacio en disco** | Algo más de 1,5 GB (medido: 635 MB el entorno del programa, 134 MB el Python, y una copia de las librerías que la caché de uv conserva y que en Windows no se puede evitar) |

**Opcional:** una clave de [Anthropic](https://platform.claude.com) si quieres
la mitad con IA. Cuesta dinero tuyo — alrededor de **1,55 $** por cada análisis
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
apetezca — el Escritorio está bien, y también Documentos.

> **Si tu Escritorio o tus Documentos están dentro de OneDrive** —en muchos
> Windows 11 lo están—, elige mejor una carpeta que no lo esté, como
> `C:\Markowitz`. El programa ocupa más de medio giga y OneDrive intentaría
> subirlo entero a la nube.

Mover o copiar la carpeta más adelante no rompe nada: el programa detecta el
cambio y rehace su entorno solo, en un par de segundos y sin volver a
descargar nada. (La única excepción es una carpeta que ya hubieras movido
*antes* de actualizar a esta versión: esa vez verás un error en inglés que
menciona `Failed to spawn`, y basta con volver a abrir el programa.) Dentro hay otra
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

Sin eso, la SEC rechaza las peticiones y no se genera nada. No es un registro:
la SEC exige un contacto en la cabecera de cada petición y **sólo se envía ahí**,
a nadie más. Se guarda en tu carpeta personal —fuera de la carpeta del
programa— así que si algún día le pasas el programa a alguien, tus datos no
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

Si descargas el programa con **git** en vez de con el ZIP, **se actualiza solo
cada vez que lo abres** y no tienes que copiar nada nunca.

Hay que escribir dos comandos, **una sola vez en la vida**. No hace falta
entenderlos: se copian y se pegan.

#### 1. Abre una terminal

Es una ventana donde se escriben órdenes en vez de pulsar botones. Ya está
instalada, no hay que descargar nada.

- **Windows:** pulsa la tecla **Windows**, escribe `cmd` y pulsa **Enter**.
- **Mac:** pulsa **Cmd + Espacio**, escribe `Terminal` y pulsa **Enter**.

Se abre una ventana con texto y un cursor parpadeando. Ahí se escribe.

> Para **pegar** en la terminal de Windows se usa **clic derecho**, no Ctrl+V.
> En Mac, Cmd+V funciona con normalidad.

#### 2. Comprueba si ya tienes git

Escribe esto y pulsa Enter:

```
git --version
```

- **Si responde algo como `git version 2.43.0`**, ya lo tienes. Salta al paso 4.
- **Si dice que no se reconoce el comando** (Windows) o **abre una ventana
  ofreciéndote instalar las herramientas** (Mac), sigue en el paso 3.

#### 3. Instala git

**En Mac** ya lo tienes hecho: el propio `git --version` abre un cuadro de
diálogo que dice que hacen falta las «herramientas de desarrollo». Pulsa
**Instalar**, acepta, y espera unos minutos. No hay que descargar nada a mano.

**En Windows**, prueba primero con esto:

```
winget install --id Git.Git -e
```

Tarda un par de minutos y no pregunta nada. Si tu Windows no conoce `winget`,
descarga el instalador de [git-scm.com](https://git-scm.com/download/win) y
dale a **Siguiente** en todas las pantallas: las opciones por defecto son las
correctas y no hay que cambiar ninguna.

**Cuando termine, cierra la terminal y abre una nueva.** Es importante: la que
tenías abierta no se entera de lo que se acaba de instalar, y seguiría diciendo
que git no existe.

#### 4. Descarga el programa

Copia esta línea, pégala y pulsa Enter:

```
git clone https://github.com/Steven7717/Markowitz-pro-picks-.git
```

Tarda unos segundos. **La carpeta aparece en tu carpeta de usuario**, la del
icono de la casita: `Markowitz-pro-picks-`. No la muevas al Escritorio ni a
Documentos si estás en Mac — ahí es donde macOS bloquea al programa.

Ábrela y sigue como en la instalación normal: doble clic en `Iniciar App.bat`
(Windows) o clic derecho → **Abrir** en `Iniciar App.command` (Mac).

#### Y ya está, para siempre

Cada arranque comprueba si hay versión nueva y se la trae — verás una línea de
«Buscando actualizaciones…». **Una actualización que falla nunca te impide usar
el programa**: si no hay internet, o si tocaste algún archivo a mano, te lo dice
y abre la versión que ya tienes.

Tus cosas no se tocan nunca: posiciones, actas, portafolios y resultados no
forman parte de lo que se descarga, así que ninguna actualización los pisa.

> **¿Cuál elijo?** Si esto te ha parecido largo, quédate con el ZIP. Funciona
> exactamente igual de bien; lo único que cambia es que las actualizaciones las
> haces tú, y son los mismos tres clics de la instalación.

---

## Cómo se cierra

Si abriste con **el acceso directo del Escritorio**, no hay ventana negra que
cerrar. Dos formas, las dos valen:

- El botón **«Salir del programa»**, abajo del todo en la barra lateral.
- **En Windows**, cerrar la pestaña del navegador y olvidarte. El programa mira
  cada pocos segundos si queda alguna pestaña abierta, y si lleva minuto y medio
  sin ninguna, se apaga solo.
- **En Mac** el atajo abre una ventana de Terminal y ésa sí hay que cerrarla: el
  apagado automático no se activa por ese camino. Usa el botón «Salir del
  programa», o pulsa **Ctrl + C** en la ventana de Terminal.

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
| Análisis completo del S&P 500 con fichas | ~**1,55 $** (estimado al alza a propósito: es el peor caso, con un reintento en las quince fichas). El programa se planta solo en 2,50 $ |
| Interpretar las noticias de tu cartera | ~**0,10 $** por pulsación |
| Comentar una propuesta de rebalanceo | menos de **0,01 $** |

Las pantallas que cuestan dinero **avisan antes de gastarlo y dicen lo que
costó después**. Nunca se llama a la IA sola: siempre hay que pulsar un botón.

### Las credenciales

Los dos datos se meten desde la propia app, en **Perfil y ajustes**, que está
al final de la barra lateral:

| Qué | De dónde sale | Hace falta para |
|---|---|---|
| Un correo electrónico | El tuyo. No es un registro: viaja en la cabecera de cada petición a la SEC, que es quien lo exige, y a ningún otro sitio | **Las dos mitades** — sin él no se genera nada |
| Clave de Anthropic | [platform.claude.com](https://platform.claude.com) — es tuya y tú pagas su uso. **Hay que comprar saldo**, ver abajo | Sólo la mitad con IA |

### Cómo conseguir la clave de Anthropic, paso a paso

Sáltate esto si no quieres la mitad con IA: **el programa funciona sin clave**.

La clave es como una llave de tu cuenta: el programa la usa para pedirle cosas a
la IA, y **tú pagas lo que se gaste**. No es una suscripción — se paga por uso,
y aquí se gastan céntimos por pulsación.

#### 1. Crea una cuenta

Entra en **[platform.claude.com](https://platform.claude.com)** y regístrate con
tu correo. *(Si tienes una suscripción a Claude, **no sirve aquí**: la API se
paga aparte.)*

#### 2. Compra saldo — esto no te lo puedes saltar

**La clave no funciona con el saldo a cero.** Es lo que más despista: se crea la
clave, se prueba, y falla sin que se entienda por qué.

1. En la consola, arriba a la derecha, entra en **Settings** (Ajustes).
2. En el menú de la izquierda, **Billing** (Facturación).
3. Pulsa **Buy credits** (Comprar créditos).
4. Escribe la cantidad y confirma.

El saldo **está disponible al momento**. Con 5 $ tienes de sobra para probar:
el análisis completo cuesta alrededor de 1,55 $ y las pulsaciones de la parte de
seguimiento, céntimos.

> **Ojo a dos cosas:** los créditos **caducan al año** de comprarlos y **no se
> devuelven**. Compra poco y ve recargando.

#### 3. Ponte un límite de gasto

Opcional pero muy recomendable, sobre todo si te preocupa que se dispare. En la
misma página de **Billing**, busca **Spend limits** (Límites de gasto) y pulsa
**Set limit**. Pon la cifra que estés dispuesto a gastar al mes y no se pasará
de ahí.

#### 4. Crea la clave

1. Sigues en **Settings**. En el menú de la izquierda, **API Keys**.
   *(Atajo directo: [platform.claude.com/settings/keys](https://platform.claude.com/settings/keys))*
2. Pulsa **Create Key** (Crear clave).
3. Ponle un nombre para acordarte — por ejemplo `markowitz`.
4. **Cópiala en cuanto aparezca**, con el botón de copiar. Es un texto largo que
   empieza por `sk-ant-`.

Si la pierdes no pasa nada grave: vuelves aquí, borras esa y creas otra.

#### 5. Pégala en el programa

En el programa: **barra lateral → Perfil y ajustes → Clave de Anthropic →
Guardar credenciales**.

Pégala **de una sola vez y sin espacios**. El sitio más común de fallo es
copiarla desde un correo o un chat, que a veces mete un salto de línea en medio;
el programa lo detecta y te avisa.

#### ¿Cuánto voy a gastar de verdad?

Puedes verlo en cualquier momento en
**[platform.claude.com/usage](https://platform.claude.com/usage)**, con el
desglose por día. Y el programa te dice lo que costó cada pulsación justo
después de hacerla.

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

## Si algo va mal al instalar

| Lo que ves | Qué pasa |
|---|---|
| «No se encuentra la carpeta programa» | Estás ejecutándolo desde dentro del ZIP, o se extrajo a medias. **Descomprímelo primero**: clic derecho → Extraer todo |
| La ventana negra se abre y se cierra de golpe sin escribir nada | No es un fallo del programa: algo lo está cortando antes de empezar, casi siempre el antivirus. Mira el apartado del antivirus más abajo |
| «Windows protegió su PC» | El archivo viene de internet. **Más información → Ejecutar de todas formas** |
| En Mac: «desarrollador no identificado» | Ábrelo con **clic derecho → Abrir** la primera vez |
| En Mac: arranca, escribe dos líneas y se corta | La carpeta está en Descargas, Escritorio o Documentos. Muévela a tu carpeta de usuario |
| Se queda minutos sin decir nada | Es la primera descarga. Es normal. No cierres la ventana |
| «Falta EDGAR_IDENTITY en el entorno» al generar candidatos | Es tu correo, y falta. Ponlo en **Perfil y ajustes → Correo para EDGAR** |
| Texto rojo en inglés con `download`, `network` o `timeout` | Se ha cortado internet. Cierra la ventana, comprueba la conexión y vuelve a abrir el programa: lo ya descargado no se pierde, sigue por donde iba |

---

## Si la app se queda bloqueada

Lo de arriba es de la instalación. Esto es de después, cuando ya la usabas.

### No abre, o se queda cargando para siempre

**En Windows**, si abriste con el icono del Escritorio, el lanzador espera dos
minutos y, si el programa no responde, **te avisa y vuelve a abrirlo con la
ventana negra a la vista**. Ahí es donde está escrito el motivo. Léelo o
cópialo: esa ventana existe precisamente para eso.

**En Mac** la ventana está siempre a la vista, y si algo falla **se queda
abierta** con un «Pulsa una tecla para cerrar» en vez de desaparecer. El error
está en las líneas de arriba.

### «El puerto 8501 lo está usando otro programa»

Significa que quedó una copia anterior viva, o que otro programa cogió ese
número. Por orden:

1. **Espera diez segundos y vuelve a intentarlo.** Si acabas de cerrar el
   programa, puede que aún esté terminando.
2. **Cierra la copia anterior.** Si la ves en el navegador, usa el botón
   **«Salir del programa»** de la barra lateral.
3. **En Mac**, en la ventana de Terminal del programa pulsa **Ctrl + C**. Si no
   la tienes, cierra Terminal entera con **Cmd + Q**.
4. **Si sigue igual, reinicia el ordenador.** Resuelve este caso siempre, y es
   lo más seguro que puedes hacer.
5. **Sólo si tienes prisa y sabes lo que haces:** Ctrl+Shift+Esc abre el
   Administrador de tareas de Windows. Puede haber **varios** `python.exe` y
   sólo uno es el del programa; cerrar el que no es puede tirarte otra cosa que
   estuvieras usando. Reiniciar hace lo mismo sin ese riesgo.

### La página del navegador se queda en blanco o «cargando»

Recarga con **F5**. Recargar no apaga el programa ni pierde nada de lo que
tengas guardado.

Si sigue en blanco, cierra la pestaña, espera dos minutos —el programa se apaga
solo cuando lleva minuto y medio sin ninguna pestaña abierta— y vuelve a abrirlo.

### Windows pregunta si permitir el acceso a través del Firewall

Sale la primera vez. **Puedes decir que no sin miedo.** El programa sólo lo usas
desde este mismo ordenador, y eso funciona igual con el cortafuegos cerrado.
Decir que no es además la opción más discreta: impide que nadie más de tu red
pueda abrirlo.

### El antivirus borra o bloquea `Iniciar App.bat`

Algunos antivirus desconfían de cualquier archivo `.bat` descargado de internet.
No hay nada oculto dentro: es texto plano y puedes abrirlo con el Bloc de notas
para ver exactamente lo que hace. Si tu antivirus lo borra, tendrás que marcarlo
como excepción o volver a descargar el programa.

### Sigue sin funcionar

Abre el programa con `Iniciar App.bat` (Windows) o `Iniciar App.command` (Mac)
en vez de con el icono del Escritorio: así la ventana con el error se queda a la
vista. Copia las últimas líneas — ahí está escrito lo que pasó.

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

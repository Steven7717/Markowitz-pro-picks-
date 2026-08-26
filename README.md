# Markowitz Pro Picks

Analiza empresas del S&P 500 con datos fundamentales sacados directamente de
sus informes a la SEC, propone un top 10-15 razonado, te deja aprobarlo o
corregirlo a mano, y con esa lista calcula cómo repartir el dinero entre ellas.

**Las decisiones las tomas tú.** El programa propone y deja constancia de lo
que apruebas; no compra ni vende nada, y el orden que produce es un criterio
de selección transparente, **no una previsión de rentabilidad** — no está
validado empíricamente y no debe leerse como una recomendación de inversión.

## Cómo se descarga

Con `git clone`, no con el botón verde de descargar ZIP:

```
git clone https://github.com/Steven7717/Markowitz-pro-picks-.git
```

Esa es la diferencia entre una copia que se actualiza sola y una que no. Un ZIP
no guarda ningún vínculo con el repositorio: se queda para siempre en la versión
que bajaste, sin forma de avisarte de que hay una nueva.

Hace falta tener git. En Mac normalmente ya está, y si no, el propio comando
ofrece instalarlo con unos clics. En Windows se instala desde
[git-scm.com](https://git-scm.com/download/win), aceptando todas las opciones
por defecto.

Si no puedes instalar git, el ZIP también funciona y el programa arranca igual —
pero no se actualizará nunca. Para ponerlo al día tendrías que volver a bajarlo
entero, y antes copiar a otro sitio tu carpeta `actas/`, que es donde viven tus
registros de aprobación.

## Cómo se abre

**Windows:** doble clic en `Iniciar App.bat`

**Mac:** doble clic en `Iniciar App.command` — con un rodeo la primera vez,
explicado justo debajo.

No hace falta instalar Python. La primera vez el programa usa una herramienta
llamada [uv](https://astral.sh/uv) para descargar todo lo que necesita: te
preguntará antes de instalar nada. Esa primera vez tarda unos minutos y baja
varios cientos de MB. Las siguientes, arranca en segundos.

## Cómo se actualiza

Sola, si la descargaste con `git clone`. Cada vez que abres el programa comprueba
si hay versión nueva y se la trae antes de arrancar — verás una línea de
«Buscando actualizaciones...» al principio. No tienes que hacer nada ni saber
ningún comando.

Si no hay internet, o si tocaste a mano algún fichero del programa, te lo dice y
abre la versión que ya tienes. **Una actualización que falla nunca te impide usar
el programa.**

Tus cosas no se tocan: los resultados (`salidas/`), las actas de aprobación
(`actas/`) y tus credenciales —que viven en tu carpeta personal, fuera del
proyecto— no forman parte del repositorio, así que ninguna actualización los
pisa. Lo que sí verás al clonar es una lista de ejemplo en «Revisar candidatos»,
para que haya algo que mirar antes de generar la tuya; en cuanto generes la
primera, esa pasa a mandar.

## Mac: la primera vez

Probado en macOS 12.7.6 (Intel). Son cuatro cosas, y ninguna vuelve a hacer
falta después.

**1. Saca la carpeta de Descargas.** macOS protege Descargas, Escritorio y
Documentos: si Terminal no tiene permiso sobre la carpeta donde está el
programa, el lanzador arranca, imprime las primeras líneas y se corta. Lo más
cómodo es arrastrar la carpeta a tu carpeta de usuario (la de la casita).

Si prefieres dejarla donde está y el lanzador se queja, dale el permiso en
**menú Apple → Preferencias del Sistema → Seguridad y privacidad → Privacidad
→ Archivos y carpetas**, busca Terminal, marca la casilla de la carpeta que
toque, y cierra Terminal del todo (Cmd+Q) antes de reintentar.

**2. Ábrelo con clic derecho, no con doble clic.** Si el programa llegó como
ZIP, macOS lo marca como descargado de internet y el primer doble clic da un
error de desarrollador no identificado. Haz **clic derecho sobre `Iniciar
App.command` → Abrir**, y confirma **Abrir** en el diálogo. A partir de ahí el
doble clic normal ya funciona.

**3. Si Finder da un error de permisos**, abre la Terminal en esta misma
carpeta y ejecuta una vez:

```
chmod +x "Iniciar App.command"
```

**4. Ten paciencia con el primer arranque.** Se descargan Python y las
librerías, varios cientos de MB, y la ventana se queda un rato sin decir nada.
Cuando termine, la app se abre sola en el navegador. No cierres la ventana
negra mientras uses el programa: ahí es donde corre.

Mover o copiar la carpeta más adelante no rompe nada. El entorno de Python
lleva su propia ruta grabada dentro, así que al cambiarla de sitio deja de
servir; el lanzador lo detecta y lo rehace solo, en un par de segundos, sin
volver a descargar nada.

## Las credenciales

El programa funciona en dos mitades:

- **Sin IA — gratis.** Descarga los datos de la SEC, calcula los indicadores
  y ordena las empresas.
- **Con IA — cuesta alrededor de 1,25 $ por corrida** (estimado al alza a
  propósito: mejor que te sobre a que te falte). Además redacta una ficha
  por empresa, con una tesis y hasta tres riesgos, cada uno citando
  textualmente el informe original. Cada cita se comprueba contra el
  documento: si no aparece, la ficha lo dice.

Las dos mitades necesitan un correo electrónico: la SEC exige un contacto
identificándote en la cabecera de **cada** petición que le hagas, así que
hace falta también para la mitad gratis — sin él no se descarga nada y no
hay nada que ordenar. Lo único que separa a las dos mitades es la clave de
Anthropic, y es lo único que cuesta dinero. Los dos datos se meten desde la
propia app, en **Revisar candidatos → 🔑 Mis credenciales**:

| Qué | De dónde sale | Hace falta para |
|---|---|---|
| Un correo electrónico | El tuyo. No es un registro y no se envía a nadie más | Las dos mitades — sin él no se genera nada |
| Clave de Anthropic | [console.anthropic.com](https://console.anthropic.com) — es tuya y tú pagas su uso | Sólo la mitad con IA |

Se guardan en tu carpeta personal (`~/.markowitz-pro-picks/credenciales.json`),
**no dentro de esta carpeta**. Si comprimes el programa y se lo pasas a otra
persona, tu clave no viaja dentro. Una vez guardada, la clave se muestra
siempre enmascarada (por ejemplo `sk-ant-…4f2a`), nunca entera. Desde ese
mismo apartado puedes **Cambiar** la clave guardada, **Cancelar** si te
arrepentiste a mitad de editarla, o **Borrar** para quitarla del todo.

## Para desarrollar

```
uv sync --all-groups     # entorno con dependencias de desarrollo
uv run pytest tests/ -q -m "not red"
```

`pandas` está topado por debajo de la versión 3 a propósito (ver
`pyproject.toml`): la 3.0 cambia el comportamiento de `.stack()` y rompe un
test de la investigación. El código está validado contra pandas 2.x.

Los detalles de diseño están en `CONTEXTO.md` y en `docs/superpowers/specs/`.

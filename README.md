# Markowitz Pro Picks

Analiza empresas del S&P 500 con datos fundamentales sacados directamente de
sus informes a la SEC, propone un top 10-15 razonado, te deja aprobarlo o
corregirlo a mano, y con esa lista calcula cómo repartir el dinero entre ellas.

**Las decisiones las tomas tú.** El programa propone y deja constancia de lo
que apruebas; no compra ni vende nada, y el orden que produce es un criterio
de selección transparente, **no una previsión de rentabilidad** — no está
validado empíricamente y no debe leerse como una recomendación de inversión.

## Cómo se abre

**Windows:** doble clic en `Iniciar App.bat`

**Mac:** doble clic en `Iniciar App.command`. **Este lanzador no se ha
probado en un Mac real** — nadie en el equipo tiene uno. La sintaxis está
revisada, pero la primera vez que lo abras eres tú quien la comprueba. Si
Finder da un error de permisos (lo más probable la primera vez, sobre todo
si el programa llegó como ZIP y no como `git clone`), abre la Terminal en
esta misma carpeta y ejecuta una vez:

```
chmod +x "Iniciar App.command"
```

y vuelve a intentar el doble clic.

No hace falta instalar Python. La primera vez el programa usa una herramienta
llamada [uv](https://astral.sh/uv) para descargar todo lo que necesita: te
preguntará antes de instalar nada. Esa primera vez tarda unos minutos y baja
varios cientos de MB. Las siguientes, arranca en segundos.

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

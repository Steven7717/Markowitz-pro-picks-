# Rendimiento real en pesos — Fisher con datos de Banxico

**Fecha:** 2026-09-27
**Estado:** diseño aprobado, sin implementar

## Qué entrega

El panel de Seguimiento contesta hoy «¿cuánto rindió la cartera?» con la TWR y
la TIR, las dos **en dólares nominales**. Para quien invierte desde México esa
no es la pregunta completa. Falta saber cuánto ganó **en pesos**, y cuánto de
eso es poder de compra y no inflación.

Este sub-proyecto añade una fila nueva, «En pesos (MXN)», con cinco cifras:

| Cifra | Qué es |
|---|---|
| TWR MXN | La TWR de la serie convertida a pesos, anualizada |
| TIR MXN | La TIR de los flujos y del valor final convertidos a pesos |
| Inflación anual | El INPC del mismo periodo, anualizado |
| TWR real | Fisher sobre la TWR MXN |
| TIR real | Fisher sobre la TIR MXN |

Los datos (el tipo de cambio FIX y el INPC) vienen del SIE de Banxico.

## La decisión central: primero pesos, después Fisher

Los libros guardan `moneda = "USD"` (`seguimiento/libro.py:183`) porque los
activos cotizan en EE. UU. **Descontar el INPC de un rendimiento en dólares
mezcla dos monedas**: el resultado es un número plausible que no mide nada.
Por eso el orden es fijo:

1. Convertir a pesos el valor diario y cada flujo externo, con el FIX de su
   fecha.
2. Calcular la TWR y la TIR en pesos con las **mismas funciones** de
   `seguimiento/rendimiento.py`, sin tocarlas.
3. Aplicar Fisher con la inflación del mismo periodo.

**Por qué no el atajo `(1 + r_USD)(1 + Δtc) − 1`.** Da la TWR exacta, pero la
TIR sale mal en cuanto hay aportaciones, porque cada una entró a un tipo de
cambio distinto. Convertir flujo a flujo es lo único que respeta el calendario
del dinero en pesos.

**Fisher exacto, no aproximado.** Se usa `real = (1 + nominal) / (1 + π) − 1`,
no `nominal − π`. Con la inflación mexicana la aproximación se equivoca en
décimas, y esa diferencia sería invisible en pantalla.

**Sobre la TIR real.** Fisher aplicado a la TIR anual asume una inflación
constante en el periodo. La alternativa exacta es deflactar cada flujo y
resolver otra TIR, pero no es lo que se pidió y la diferencia es pequeña. Queda
fuera de alcance (ver al final).

## Componentes

### 1. `seguimiento/banxico.py` — los datos

Descarga dos series de la API REST del SIE
(`https://www.banxico.org.mx/SieAPIRest/service/v1/series/{id}/datos/{desde}/{hasta}`):

| Serie | Id | Frecuencia |
|---|---|---|
| Tipo de cambio FIX, pesos por dólar | `SF43718` | Diaria hábil |
| INPC general | `SP1` | Mensual |

Los ids se verifican contra una llamada real al implementar, y se guarda la
respuesta como fixture de test.

- **Transporte:** `urllib.request` de la librería estándar. El token va en la
  cabecera `Bmx-Token`, **nunca en la URL**. Así no acaba en ningún log ni en
  ningún historial. `httpx` y `requests` solo están como dependencias
  transitivas, y no se añaden dependencias nuevas.
- **Parseo:** Banxico devuelve las fechas como `dd/mm/aaaa` y los valores como
  texto con comas de miles. `"N/E"` significa sin dato y se descarta; no se
  convierte en cero. El resultado es una `pd.Series` indexada por fecha.
- **Caché en disco**, con el mismo patrón que `noticias/cache.py`, en `seguimiento/.cache/banxico/`
  (fuera de git, como `noticias/.cache/`; se añade a `.gitignore`):
  - FIX: validez de 1 día.
  - INPC: vale hasta el día 10 del mes siguiente al último dato, que es cuando
    suele salir el siguiente.
  - La hora de descarga se enseña siempre.
- **Fallos con nombre.** Devuelve `(datos | None, motivo)`, con motivo en
  `"ok"`, `"sin_token"`, `"token_invalido"` (401/403), `"sin_red"`,
  `"respuesta_rara"`. Si hay caché vieja y la red falla, se usa la caché y se
  marca como vieja.

### 2. Credenciales

`credenciales.py` gana un tercer campo, `banxico_token`. Se añade a
`_VARIABLES` como `("BANXICO_TOKEN", "banxico_token")` y a `limpia()`. Se
captura en la misma pantalla que la clave de Anthropic y la identidad de
EDGAR. El token se valida solo por su forma: 64 caracteres alfanuméricos, que
es lo que documenta Banxico.

**El token no se puede obtener por el usuario, ni sale del correo de EDGAR.**
Banxico no pide correo. La página
<https://www.banxico.org.mx/SieAPIRest/service/v1/token> solo pide resolver una
imagen de seguridad (un CAPTCHA) y pulsar «Generar token». El token se genera
una vez y se reutiliza. Automatizar ese paso sería saltarse el CAPTCHA, así que
la pantalla se limita a hacerlo corto: un enlace directo a esa página y la
instrucción «resuelve la imagen, pulsa Generar token y pega aquí el código de
64 caracteres».

**Límites de consulta.** Banxico inhabilita temporalmente el token que los
supera. Por eso la caché del punto 1 no es opcional: con cada clic, Streamlit
volvería a pedir las dos series.

### 3. `seguimiento/fisher.py` — las cuentas

Son funciones puras, sin red ni Streamlit, y todas se pueden probar con series
sintéticas.

- **`en_pesos(valor, flujos, fix) -> (valor_mxn, flujos_mxn)`.** Reindexa el
  FIX al calendario de la serie y arrastra el último publicado hacia delante
  (fines de semana, festivos mexicanos que en EE. UU. son hábiles). Si la serie
  empieza **antes** del primer FIX disponible, devuelve `None`: no se inventa
  el tipo de cambio hacia atrás.
- **`inflacion_periodo(inpc, desde, hasta) -> Inflacion`**, con los campos
  `acumulada`, `anual`, `oficial_hasta: date` y `estimada: bool`.
  - El INPC mensual se fecha a fin de mes. Dentro de un mes se interpola de
    forma geométrica por días.
  - Después del último INPC publicado se extiende la **última tasa mensual
    conocida**, y `estimada=True`.
  - `anual` usa `rendimiento.anualizar`, así que por debajo de 30 días es
    `None`, igual que la TWR.
- **`real(nominal, inflacion_anual) -> float | None`.** Es Fisher exacto.
  `None` en cualquiera de las dos entradas da `None`.

### 4. `seguimiento/panel.py` — `CabeceraPesos`

Es una dataclass **separada** de `Cabecera`. Lo que depende de Banxico puede
faltar sin que falte lo demás, y mezclarlas haría que un token caducado tocara
cifras que no dependen de él.

Campos:
- `twr_anual`, `tir`, `motivo_tir`
- `inflacion: Inflacion | None`
- `twr_real`, `tir_real`
- `fix_inicial`, `fix_final`, `movimiento_tc`
- `motivo: str`: `"ok"`, uno de los fallos de `banxico` o `"moneda_no_soportada"`

`cabecera_pesos(marcha, vivos, sin_valorar, moneda, fix, inpc)` sigue las
mismas reglas que `cabecera()`:
- Toma el mismo corte temporal desde `marcha.flujos`.
- Con `sin_valorar`, todo es `None`.
- La TIR sale de `rendimiento.tir_detallada` sobre los flujos ya convertidos,
  con su motivo.
- Si `moneda == "MXN"`, el FIX es 1 y no se convierte.
- Cualquier otra moneda que no sea `"USD"` o `"MXN"` da
  `motivo="moneda_no_soportada"`.

### 5. Pantalla — `vistas/seguimiento.py`

Una fila nueva, «En pesos (MXN)», debajo de TIR y Dividendos, con
`st.columns` de ancho suficiente. El panel de K ya midió que seis cifras en un
renglón se recortan, así que no se hace eso.

- Cada cifra usa `cartera.formato_porcentaje`: `None` se ve «—» y nunca 0,00.
- **Ayuda de TWR MXN y TIR MXN:** «FIX 17,05 → 18,40: el dólar subió 7,9% en
  el periodo», con el efecto del tipo de cambio desglosado.
- **Ayuda de Inflación:** «INPC oficial hasta ago-2026; del 1 al 26 de
  septiembre, estimado con la última tasa mensual (0,4%)». Solo si
  `estimada`.
- **Sin token:** la fila sale con «—» y una sola línea que dice cómo
  conseguirlo, sin lanzar un error.
- **Token inválido o sin red:** «—» y el motivo en palabras.
- Pie de fila: «Datos: Banxico SIE · descargado a las HH:MM».

La descarga va bajo `st.cache_data`, con la clave del rango de fechas, por
encima de la caché en disco. Streamlit vuelve a ejecutar el guion con cada
clic.

### 6. Exportación

El Excel de la pantalla (`vistas/seguimiento.py:811` y siguientes) gana las
columnas «TWR MXN», «TIR MXN», «Inflación anual (INPC)», «TWR real», «TIR real»
y «INPC estimado desde». Mismos valores y mismos `None` que la pantalla. Salen
de `CabeceraPesos` y no se recalculan.

## Tests

En `tests/test_seguimiento_fisher.py` y `tests/test_seguimiento_banxico.py`:

- **Fisher exacto:** nominal 10% con inflación 4% da 5,769…%, no 6%.
- **Con FIX constante, la TWR y la TIR en MXN son iguales a las de USD.** Esto
  prueba que la conversión no introduce nada.
- **Con el FIX subiendo un 10% y la cartera plana en dólares, la TWR MXN del
  periodo es 10%.**
- **Una aportación a un FIX distinto mueve la TIR MXN y no la TWR MXN.**
- **Con la inflación en cero, la cifra real es igual a la nominal.**
- **Interpolación:** a mitad de mes, el índice interpolado queda entre los dos
  meses, de forma geométrica.
- **Extensión:** con un periodo que pasa del último INPC, `estimada=True`,
  `oficial_hasta` es el último mes y la tasa usada es la última mensual.
- **Menos de 30 días:** inflación anual `None`, cifras reales `None`.
- **Serie que empieza antes del primer FIX:** da `None` y no se extrapola.
- **Parseo** del fixture real de Banxico: fechas `dd/mm/aaaa`, comas de miles y
  `"N/E"` descartado.
- **Red simulada:** 401 da `token_invalido`, un error de conexión con caché da
  la caché marcada vieja, y sin token da `sin_token` sin hacer ninguna llamada.
- **El token nunca aparece en la URL** pedida: se comprueba sobre la petición
  simulada.
- **`credenciales`:** `BANXICO_TOKEN` del entorno se lee y la forma se valida.
- **`cabecera_pesos` con `sin_valorar`:** todo `None`.

## Fuera de alcance

- El rendimiento real en dólares con el CPI de EE. UU.
- La gráfica del valor en pesos constantes.
- La TIR real deflactando cada flujo (en vez de Fisher sobre la TIR anual).
- Libros en monedas que no sean USD o MXN.

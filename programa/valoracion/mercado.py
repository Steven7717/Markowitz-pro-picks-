"""Lo único de `valoracion/` que toca la red, y lo que interpreta lo que trae.

Las funciones `*_desde_*` son puras: reciben lo que yfinance devolvió y deciden
qué significa. Las de red (más abajo) sólo descargan, guardan en caché y llaman
a las puras. Así los tests de lo que importa no necesitan red, y los `red`
comprueban que la fuente sigue teniendo la forma que las puras esperan.
"""

import math
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

from noticias import cache
from valoracion.criterio import BETA_SEMANAS, BETA_SEMANAS_MIN


@dataclass(frozen=True)
class Perfil:
    """Lo que se sabe de un ticker hoy. **No lleva beta, a propósito.**

    La beta de Yahoo no se lee: para WALMEX.MX dio 0,016, porque Yahoo la mide
    contra el S&P 500 con el precio en pesos. Para una empresa de EE. UU. sería
    razonable, pero dos caminos para el mismo dato se separan, y el que se queda
    atrás no da error: da un número plausible. Sin campo, no hay camino.
    """

    ticker: str
    precio: float
    capitalizacion: float
    moneda: str
    moneda_estados: str
    industria: "str | None"
    pais: "str | None"
    payout: "float | None"
    tipo: "str | None"
    hora: "str | None"


@dataclass(frozen=True)
class Beta:
    bruta: float
    r2: float
    semanas: int
    indice: str


def _num(valor: object) -> float:
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return math.nan
    return numero if math.isfinite(numero) else math.nan


def _opcional(valor: object) -> "float | None":
    numero = _num(valor)
    return None if math.isnan(numero) else numero


def _texto(valor: object) -> "str | None":
    return valor.strip() if isinstance(valor, str) and valor.strip() else None


def _hora(momento: object) -> "str | None":
    """La hora de la cotización en ISO y UTC. La hora es lo único prescindible
    del perfil: si Yahoo cambiase de unidad (milisegundos), `fromtimestamp`
    lanza, y por una marca de tiempo no se tira toda la valoración."""
    segundos = _opcional(momento)
    if segundos is None:
        return None
    try:
        return datetime.fromtimestamp(segundos, tz=timezone.utc).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def perfil_desde_info(ticker: str, info: dict) -> "Perfil | None":
    """El perfil desde `yf.Ticker(t).info`, o `None` si falta precio, capitalización o moneda."""
    # `_num` antes que `or`: un NaN es verdadero en Python, y `nan or 50.0` se
    # queda con el NaN en lugar de caer al precio de mercado.
    precio = _num(info.get("currentPrice"))
    if not precio > 0:
        precio = _num(info.get("regularMarketPrice"))
    capitalizacion = _num(info.get("marketCap"))
    moneda = _texto(info.get("currency"))
    if not (precio > 0 and capitalizacion > 0) or moneda is None:
        return None
    return Perfil(
        ticker=ticker,
        precio=precio,
        capitalizacion=capitalizacion,
        moneda=moneda,
        moneda_estados=_texto(info.get("financialCurrency")) or moneda,
        industria=_texto(info.get("industry")),
        pais=_texto(info.get("country")),
        payout=_opcional(info.get("payoutRatio")),
        # Sin tipo no se inventa uno: quien lo necesite decidirá qué hacer con
        # un `None`, y un "EQUITY" falso no se distinguiría de uno verdadero.
        tipo=_texto(info.get("quoteType")),
        hora=_hora(info.get("regularMarketTime")),
    )


def _semanal(cierres: pd.Series) -> pd.Series:
    """Sin zona horaria y al día: Yahoo fecha las velas del activo y del índice
    en zonas que no siempre coinciden, y sin esto el cruce sale vacío."""
    serie = pd.to_numeric(cierres, errors="coerce").dropna()
    indice = pd.DatetimeIndex(serie.index)
    if indice.tz is not None:
        indice = indice.tz_localize(None)
    serie.index = indice.normalize()
    # Ordenada antes de quitar repetidos y de todo lo posicional que viene
    # después (`pct_change`, `tail`); estable para que "la última" de una fecha
    # repetida sea la que llegó última.
    serie = serie.sort_index(kind="stable")
    return serie[~serie.index.duplicated(keep="last")]


def regresion_beta(
    activo: pd.Series, indice: pd.Series, nombre_indice: str
) -> "Beta | None":
    """La pendiente de los rendimientos semanales del activo contra los del índice.

    Las últimas `BETA_SEMANAS`; con menos de `BETA_SEMANAS_MIN`, `None`: un año
    de datos semanales ya da una beta ruidosa, y menos no da ninguna.
    """
    juntos = pd.concat([_semanal(activo), _semanal(indice)], axis=1, join="inner").dropna()
    precios = juntos.tail(BETA_SEMANAS + 1)
    # Un cierre a cero es un dato corrupto: da un -100 % seguido de un
    # rendimiento infinito. Quitar sólo el infinito dejaría el -100 %: una beta
    # finita, plausible y falsa. Con un cero en la ventana no hay beta.
    if (precios <= 0).any().any():
        return None
    rendimientos = precios.pct_change(fill_method=None).dropna()
    if len(rendimientos) < BETA_SEMANAS_MIN:
        return None
    y, x = rendimientos.iloc[:, 0], rendimientos.iloc[:, 1]
    if not (x.var() > 0 and y.var() > 0):
        return None
    bruta = float(y.cov(x) / x.var())
    r2 = float(y.corr(x) ** 2)
    # Última guarda: un NaN aquí envenenaría el coste del capital y la caché.
    if not (math.isfinite(bruta) and math.isfinite(r2)):
        return None
    return Beta(
        bruta=bruta,
        r2=r2,
        semanas=int(len(rendimientos)),
        indice=nombre_indice,
    )


def precio_convertido(precio: pd.Series, tipo: pd.Series) -> pd.Series:
    """El precio semanal por el tipo de cambio de esa misma semana.

    Para regresar contra un índice en otra moneda: AMX cotiza en dólares y su
    índice, el IPC, en pesos. Sólo quedan las semanas con los dos datos.
    """
    juntos = pd.concat([_semanal(precio), _semanal(tipo)], axis=1, join="inner").dropna()
    return juntos.iloc[:, 0] * juntos.iloc[:, 1]


def tasa_libre_desde_cierres(cierres: pd.Series) -> "float | None":
    """`^TNX` cotiza el rendimiento en puntos: 5,24 es un 5,24 %."""
    validos = pd.to_numeric(cierres, errors="coerce").dropna()
    if validos.empty:
        return None
    return float(validos.iloc[-1]) / 100


def tasa_efectiva_desde_estado(estado: "pd.DataFrame | None") -> "float | None":
    """La tasa efectiva más reciente con dato. yfinance ordena las columnas de
    la más reciente a la más antigua."""
    if estado is None or estado.empty or "Tax Rate For Calcs" not in estado.index:
        return None
    for valor in estado.loc["Tax Rate For Calcs"]:
        numero = _opcional(valor)
        if numero is not None:
            return numero
    return None


def consenso_desde_estimacion(
    estimacion: "pd.DataFrame | None", moneda_estados: str
) -> "float | None":
    """El crecimiento de ingresos que el consenso espera el próximo ejercicio.

    `+1y` y no `0y`, que suele estar ya medio publicado. Y sólo si viene en la
    moneda de los estados: en TSM, `revenue_estimate` viene en TWD y
    `earnings_estimate` en USD **en la misma consulta**, así que la moneda se
    comprueba fila a fila y no se supone.
    """
    if estimacion is None or estimacion.empty or "+1y" not in estimacion.index:
        return None
    fila = estimacion.loc["+1y"]
    if str(fila.get("currency", "")) != moneda_estados:
        return None
    return _opcional(fila.get("growth"))


def estado_a_plano(estado: "pd.DataFrame | None") -> dict:
    """Un estado de yfinance como `{fila: {fecha ISO: valor}}`, con NaN como None.

    Es esta función la que deja el estado en JSON estricto, no la caché:
    `cache.guardar` admite NaN y lo escribiría como el literal `NaN`, que un
    lector estricto rechaza. Lo que no es un número finito --texto, `inf`, una
    fecha-- también va a None.
    """
    if estado is None or estado.empty:
        return {}
    plano: dict = {}
    for fila, valores in estado.iterrows():
        plano[str(fila)] = {
            pd.Timestamp(columna).date().isoformat(): _opcional(valor)
            for columna, valor in valores.items()
        }
    return plano


def estado_de_plano(plano: object) -> pd.DataFrame:
    """La inversa de `estado_a_plano`, con la columna más reciente primero, como
    las entrega yfinance. Lanza `TypeError` si no tiene la forma de un estado."""
    if not isinstance(plano, dict):
        raise TypeError("estado guardado sin forma de diccionario")
    if not plano:
        return pd.DataFrame()
    try:
        columnas = {
            fila: {
                pd.Timestamp(fecha): (math.nan if valor is None else float(valor))
                for fecha, valor in valores.items()
            }
            for fila, valores in plano.items()
        }
        estado = pd.DataFrame(columnas).T
        return estado.reindex(columns=sorted(estado.columns, reverse=True)).astype("float64")
    except (AttributeError, ValueError) as error:
        # Una fila guardada como lista, una fecha «FY2025» o un valor «n/d».
        # `_traer` sólo reconoce `TypeError` y `KeyError` como «forma de una
        # versión anterior»; con otra excepción, la entrada lanzaría en cada
        # llamada en lugar de ir a la red.
        raise TypeError("estado guardado con una forma que no se lee") from error


# --- Red ------------------------------------------------------------------------
#
# Cada función devuelve el dato y un motivo con nombre, como
# `seguimiento/banxico.py`: `"ok"`, `"sin_red"`, o por qué el dato no existe.

RAIZ_CACHE = Path(__file__).resolve().parent / ".cache"
INDICE = "^GSPC"
BONO_10 = "^TNX"

# El precio cambia en minutos; la tasa libre, la beta de dos años, la tasa
# efectiva anual y el consenso, en días. Generar quince candidatos dos veces en
# una tarde no tiene por qué repetir sesenta descargas.
VALIDEZ = {
    "perfil": timedelta(minutes=15),
    "tasa_libre": timedelta(days=1),
    "beta": timedelta(days=1),
    "tasa_efectiva": timedelta(days=1),
    "consenso": timedelta(days=1),
    # La identidad viaja en la misma llamada que el precio: un ETF no tiene
    # perfil, y su precio sólo está aquí.
    "identidad": timedelta(minutes=15),
    # Los estados cambian una vez por trimestre, pero un día y no más: así el
    # trimestre nuevo se recoge el mismo día de resultados.
    "estados": timedelta(days=1),
    "tipo_de_cambio": timedelta(days=1),
}

# Hasta dónde sirve lo guardado cuando la red falla. Pasado esto, mejor decir
# que no hay dato que dar uno que ya no describe nada.
ANTIGUEDAD_MAXIMA = {
    # El precio lleva su propia hora (`Perfil.hora`), que es la que se enseña:
    # una semana vieja se ve como tal, pero no más allá.
    "perfil": timedelta(days=7),
    # La tasa libre se mueve cada día y entra directa en el coste del capital.
    "tasa_libre": timedelta(days=7),
    # Dos años de semanas: añadir un trimestre más cambia poco la pendiente.
    "beta": timedelta(days=90),
    # La tasa efectiva es anual y sólo cambia con cada cierre de ejercicio.
    "tasa_efectiva": timedelta(days=400),
    # El consenso se revisa con cada resultado trimestral.
    "consenso": timedelta(days=30),
    # Qué es un ticker no cambia de un día a otro; su precio sí, y lleva su hora.
    "identidad": timedelta(days=7),
    # Un trimestre nuevo llega cada noventa días.
    "estados": timedelta(days=30),
    # Una semana como mucho: el peso mexicano en tensión se mueve un 2-5 % en
    # una semana, y ese error pasa entero a la valoración convertida.
    "tipo_de_cambio": timedelta(days=7),
}


def _traer(fuente: str, clave: str, pedir, interpretar, leer) -> "tuple[object, str]":
    """Lo guardado si está vigente; si no, la red; si la red falla, lo guardado.

    - `pedir()` hace sólo las llamadas a yfinance, y es lo único dentro del
      `try`: devuelve lo que yfinance trajo, o `None` si no pudo saberlo.
    - `interpretar(crudo)` es nuestro y va fuera del `try`, para que un defecto
      propio salga con su excepción y no disfrazado de "sin_red". Devuelve un
      `dict` si sabe la respuesta --incluida "no hay"-- y entonces se guarda; o
      `None` si no pudo saberla, y entonces no se guarda nada ni se pisa lo
      bueno que hubiera.
    - `leer(dict)` saca el valor de lo guardado y lanza `TypeError` o
      `KeyError` si tiene la forma de una versión anterior; esa entrada ni se
      sirve ni sirve de respaldo.

    Lo guardado caducado se usa antes que nada, hasta `ANTIGUEDAD_MAXIMA`,
    porque estos datos envejecen despacio --una beta de dos años no cambia de un
    día a otro-- y el precio lleva su propia hora dentro (`Perfil.hora`).
    """
    guardado = cache.leer(RAIZ_CACHE, fuente, clave, VALIDEZ[fuente])
    previo, hay_previo = None, False
    if guardado is not None and isinstance(guardado.datos, dict):
        try:
            previo, hay_previo = leer(guardado.datos), True
        except (TypeError, KeyError):
            pass
    if hay_previo and guardado.vigente:
        return previo, "ok"
    try:
        crudo = pedir()
    except Exception:
        # yfinance lanza de todo según qué falle --HTTPError, KeyError,
        # JSONDecodeError, ValueError, TypeError en una respuesta a medias-- y
        # ninguna de esas clases distingue algo que aquí importe: o hay dato o no.
        crudo = None
    datos = None if crudo is None else interpretar(crudo)
    if datos is not None:
        try:
            cache.guardar(RAIZ_CACHE, fuente, clave, datos)
        except OSError:
            # Ya está descargado: perder la caché no es perder la respuesta.
            pass
        return leer(datos), "ok"
    if hay_previo:
        edad = datetime.now(timezone.utc) - guardado.cuando
        if edad <= ANTIGUEDAD_MAXIMA[fuente]:
            return previo, "ok"
    return None, "sin_red"


def _sin_cierres(cierres: pd.Series) -> bool:
    return pd.to_numeric(cierres, errors="coerce").dropna().empty


def _valor(datos: dict) -> "float | None":
    return datos["valor"]


def _instante(desde: object, nombre: str) -> "datetime | None":
    """La hora ISO con zona que `desde` guarda para `nombre`, o None si no se lee."""
    iso = desde.get(nombre) if isinstance(desde, dict) else None
    if not isinstance(iso, str):
        return None
    try:
        hora = datetime.fromisoformat(iso)
    except ValueError:
        return None
    return hora if hora.tzinfo is not None else None


def _conservables(fuente: str, clave: str, seccion: str, nombres, legible) -> dict:
    """Lo que `interpretar` puede rescatar de lo guardado cuando la descarga
    llega a medias: `{nombre: (valor, desde)}` de los valores llenos y
    `legible(valor)` de `datos[seccion]` que no pasan de `ANTIGUEDAD_MAXIMA`
    desde la última vez que llegaron llenos.

    El tope cuenta desde `datos["desde"][nombre]`, no desde la hora del
    fichero: lo conservado se reescribe con la hora nueva, y con ella volvería a
    estar dentro del tope en cada descarga y no caducaría nunca. Una entrada de
    antes de que hubiera `desde` cuenta desde su propia hora.
    """
    guardado = cache.leer(RAIZ_CACHE, fuente, clave, ANTIGUEDAD_MAXIMA[fuente])
    if guardado is None or not isinstance(guardado.datos, dict):
        return {}
    previos = guardado.datos.get(seccion)
    if not isinstance(previos, dict):
        return {}
    sin_desde = "desde" not in guardado.datos
    ahora = datetime.now(timezone.utc)
    conservables = {}
    for nombre in nombres:
        valor = previos.get(nombre)
        if not valor or not legible(valor):
            continue
        desde = guardado.cuando if sin_desde else _instante(guardado.datos["desde"], nombre)
        if desde is None or ahora - desde > ANTIGUEDAD_MAXIMA[fuente]:
            continue
        conservables[nombre] = (valor, desde.isoformat())
    return conservables


def _caducados(fuente: str, datos: dict, nombres) -> set:
    """Los `nombres` cuyo `datos["desde"]` pasa ya de `ANTIGUEDAD_MAXIMA[fuente]`.

    Lo usa `leer`. El respaldo de `_traer` mide la edad del fichero, que lo
    conservado rejuvenece: sin esto, con la red caída del todo, un valor
    conservado en la escritura del día 29 se serviría hasta el día 58. Una
    entrada sin `desde` vale como hasta ahora.
    """
    ahora = datetime.now(timezone.utc)
    caducados = set()
    for nombre in nombres:
        desde = _instante(datos.get("desde"), nombre)
        if desde is not None and ahora - desde > ANTIGUEDAD_MAXIMA[fuente]:
            caducados.add(nombre)
    return caducados


CLAVES_DE_IDENTIDAD = (
    "quoteType",
    "currency",
    "marketCap",
    "currentPrice",
    "regularMarketPrice",
)

# Lo que `identidad` guarda de `info`: qué es el ticker, dónde cotiza y en qué
# moneda, y su precio con la hora. Nada de beta: ver la docstring de `Perfil`.
CLAVES_IDENTIDAD_INFO = (
    "quoteType",
    "exchange",
    "currency",
    "financialCurrency",
    "sector",
    "industry",
    "country",
    "longName",
    "shortName",
    "currentPrice",
    "regularMarketPrice",
    "regularMarketTime",
)

ESTADOS = (
    "quarterly_income_stmt",
    "quarterly_balance_sheet",
    "quarterly_cashflow",
    "income_stmt",
    "balance_sheet",
    "cashflow",
)

# Lo que dice de qué es una empresa y sólo trae quoteSummary: si cae sólo esa
# petición, `info` llega con el tipo, la moneda y el precio, sin ninguna de éstas.
CLAVES_CLASIFICACION = ("sector", "industry", "country")

# Yahoo cotiza algunas bolsas en la subunidad de su moneda: Londres en peniques
# (GBp o GBX), Tel Aviv en agorot (ILA), Johannesburgo en céntimos (ZAc),
# Kuwait en fils (KWF, mil por dinar). yfinance pasa el símbolo a mayúsculas,
# así que `GBpUSD=X` es `GBPUSD=X`: el tipo de la libra, cien veces mayor, sin
# ningún error.
SUBUNIDADES = {
    "GBp": ("GBP", 100),
    "GBX": ("GBP", 100),
    "ILA": ("ILS", 100),
    "ZAc": ("ZAR", 100),
    "KWF": ("KWD", 1000),
}


def perfil(ticker: str) -> "tuple[Perfil | None, str]":
    def pedir():
        info = yf.Ticker(ticker).info
        return info if isinstance(info, dict) else None

    def interpretar(info):
        # Un 401, 404 o 5xx de quoteSummary no lanza: `info` queda en
        # {"trailingPegRatio": …}, igual que para un símbolo inexistente. Sin
        # ninguna clave de identidad no se sabe nada. Un símbolo que Yahoo
        # conoce pero sin precio conserva `quoteType` y `currency`, y ése sí se
        # guarda como "sin precio".
        if not any(clave in info for clave in CLAVES_DE_IDENTIDAD):
            return None
        encontrado = perfil_desde_info(ticker, info)
        return {"perfil": None if encontrado is None else asdict(encontrado)}

    def leer(datos):
        return None if datos["perfil"] is None else Perfil(**datos["perfil"])

    encontrado, motivo = _traer("perfil", ticker, pedir, interpretar, leer)
    if motivo != "ok":
        return None, motivo
    return (encontrado, "ok") if encontrado is not None else (None, "sin_precio")


def tasa_libre() -> "tuple[float | None, str]":
    def pedir():
        return yf.Ticker(BONO_10).history(period="5d")["Close"]

    def interpretar(cierres):
        # `history()` no lanza cuando falla la red: devuelve un marco vacío con
        # su columna `Close`. Sin cierres no se sabe nada; no se guarda.
        if _sin_cierres(cierres):
            return None
        return {"valor": tasa_libre_desde_cierres(cierres)}

    valor, motivo = _traer("tasa_libre", BONO_10, pedir, interpretar, _valor)
    if motivo != "ok" or valor is None:
        return None, "sin_tasa_libre"
    return float(valor), "ok"


def beta(
    ticker: str, indice: str = INDICE, par: "str | None" = None
) -> "tuple[Beta | None, str]":
    """La beta del ticker contra el índice. Con `par` (`USDMXN=X`), el precio se
    pasa a la moneda del índice semana a semana antes de regresar: un precio en
    dólares contra un índice en pesos mezclaría dos monedas."""

    def pedir():
        activo = yf.Ticker(ticker).history(period="2y", interval="1wk")["Close"]
        referencia = yf.Ticker(indice).history(period="2y", interval="1wk")["Close"]
        tipo = (
            None if par is None else yf.Ticker(par).history(period="2y", interval="1wk")["Close"]
        )
        return activo, referencia, tipo

    def interpretar(series):
        activo, referencia, tipo = series
        # `history()` no lanza cuando falla la red: devuelve un marco vacío. Eso
        # es "no lo sé"; un historial corto pero real (una salida a bolsa
        # reciente) es un hecho estable, y ése sí se guarda como "sin beta".
        if _sin_cierres(activo) or _sin_cierres(referencia):
            return None
        if tipo is not None:
            if _sin_cierres(tipo):
                return None
            activo = precio_convertido(activo, tipo)
        encontrada = regresion_beta(activo, referencia, indice)
        return {"beta": None if encontrada is None else asdict(encontrada)}

    def leer(datos):
        return None if datos["beta"] is None else Beta(**datos["beta"])

    clave = f"{ticker}|{indice}" if par is None else f"{ticker}|{indice}|{par}"
    encontrada, motivo = _traer("beta", clave, pedir, interpretar, leer)
    if motivo != "ok":
        return None, motivo
    # `regresion_beta` devuelve None por historial corto, pero también por un
    # precio no positivo en la ventana o una varianza nula: no siempre es la
    # historia lo que falta.
    return (encontrada, "ok") if encontrada is not None else (None, "sin_regresion")


def tasa_efectiva(ticker: str) -> "tuple[float | None, str]":
    def pedir():
        return yf.Ticker(ticker).income_stmt

    def interpretar(estado):
        # Igual que `history()`, `income_stmt` no lanza: si falla, devuelve vacío.
        if estado is None or estado.empty:
            return None
        return {"valor": tasa_efectiva_desde_estado(estado)}

    valor, motivo = _traer("tasa_efectiva", ticker, pedir, interpretar, _valor)
    if motivo != "ok":
        return None, motivo
    return (valor, "ok") if valor is not None else (None, "sin_tasa_efectiva")


def consenso(ticker: str, moneda_estados: str) -> "tuple[float | None, str]":
    def pedir():
        return yf.Ticker(ticker).revenue_estimate

    def interpretar(estimacion):
        # Igual que `history()`, `revenue_estimate` no lanza: si falla, devuelve
        # vacío. Con tabla pero sin `+1y`, o en otra moneda, sí se sabe --que no
        # hay consenso-- y eso se guarda.
        if estimacion is None or estimacion.empty:
            return None
        return {"valor": consenso_desde_estimacion(estimacion, moneda_estados)}

    valor, motivo = _traer(
        "consenso", f"{ticker}|{moneda_estados}", pedir, interpretar, _valor
    )
    if motivo != "ok":
        return None, motivo
    return (valor, "ok") if valor is not None else (None, "sin_consenso")


def identidad(ticker: str) -> "tuple[dict | None, str]":
    """Las claves de `info` que dicen qué es un ticker, aunque no tenga capitalización.

    Va aparte de `perfil` porque un ETF no tiene capitalización y `perfil` lo
    descarta con `sin_precio`; el Analizador necesita saber que es un ETF para
    enseñarlo sin valorarlo. Igual que en `perfil`, un `info` sin ninguna clave
    de identidad no dice nada --la red, un error de Yahoo o un símbolo que no
    conoce-- y no se guarda.
    """

    def pedir():
        info = yf.Ticker(ticker).info
        return info if isinstance(info, dict) else None

    def interpretar(info):
        if not any(clave in info for clave in CLAVES_DE_IDENTIDAD):
            return None
        nueva = {clave: info.get(clave) for clave in CLAVES_IDENTIDAD_INFO}
        ahora = datetime.now(timezone.utc).isoformat()
        desde = {clave: ahora for clave in CLAVES_CLASIFICACION if nueva.get(clave)}
        if not desde:
            # Si cae sólo quoteSummary, `info` pierde a la vez el sector, la
            # industria y el país, pero trae el precio nuevo. Eso es «no lo sé»
            # y no «ya no tiene sector»: vale lo nuevo, y esos tres se rellenan
            # con lo guardado hasta `ANTIGUEDAD_MAXIMA` desde que llegaron;
            # pasado el tope, la parcial se guarda tal cual. Un ETF no tiene
            # ninguno de los tres, ni nada que rellenar. `perfil` tiene la misma
            # exposición desde M y no se toca aquí.
            conservables = _conservables(
                "identidad", ticker, "identidad", CLAVES_CLASIFICACION,
                lambda valor: _texto(valor) is not None,
            )
            for clave, (valor, cuando) in conservables.items():
                nueva[clave] = valor
                desde[clave] = cuando
        return {"identidad": nueva, "desde": desde}

    def leer(datos):
        # `dict()` aceptaría una lista de pares, y con otra lista lanzaría
        # `ValueError`, que `_traer` no reconoce como forma antigua.
        if not isinstance(datos["identidad"], dict):
            raise TypeError("identidad guardada sin forma de diccionario")
        identidad = dict(datos["identidad"])
        for clave in _caducados("identidad", datos, CLAVES_CLASIFICACION):
            identidad[clave] = None
        return identidad

    return _traer("identidad", ticker, pedir, interpretar, leer)


def _plano_legible(plano: object) -> bool:
    """Un estado guardado roto no se conserva: lanzaría al leerlo, ya fuera de `_traer`."""
    try:
        estado_de_plano(plano)
    except TypeError:
        return False
    return True


def estados(ticker: str) -> "tuple[dict | None, str]":
    """Los seis estados de yfinance, trimestrales y anuales, como DataFrames."""

    def pedir():
        objeto = yf.Ticker(ticker)
        return {nombre: getattr(objeto, nombre) for nombre in ESTADOS}

    def interpretar(crudos):
        # Como `history()`, los estados no lanzan cuando falla la red: llegan
        # vacíos. Con los seis vacíos no se sabe nada, y guardarlo como «no hay
        # estados» es el defecto que la revisión de M encontró en el precio.
        planos = {nombre: estado_a_plano(crudos.get(nombre)) for nombre in ESTADOS}
        if not any(planos.values()):
            return None
        ahora = datetime.now(timezone.utc).isoformat()
        desde = {nombre: ahora for nombre in ESTADOS if planos[nombre]}
        # Pero cada estado es una petición aparte, y yfinance devuelve vacío el
        # que falla, también por un 429: tres llenos y tres vacíos pueden ser un
        # límite de peticiones en la cuarta. Exigir los seis llenos no sirve
        # --NESN.SW publica semestralmente y sus trimestrales de resultados y de
        # flujos llegan vacíos de verdad--, así que un estado que llega vacío no
        # pisa uno lleno guardado. Pero sólo hasta `ANTIGUEDAD_MAXIMA` desde que
        # llegó lleno por última vez (`desde`): un estado que ya no se publica,
        # o el de otra empresa con un ticker reasignado, no se arrastra. Queda
        # sin cubrir que la primera descarga ya sea parcial: eso se guarda y vale
        # hasta la siguiente, un día después (`VALIDEZ`).
        conservables = _conservables("estados", ticker, "estados", ESTADOS, _plano_legible)
        for nombre, (plano, cuando) in conservables.items():
            if not planos[nombre]:
                planos[nombre] = plano
                desde[nombre] = cuando
        return {"estados": planos, "desde": desde}

    def leer(datos):
        caducados = _caducados("estados", datos, ESTADOS)
        return {
            nombre: (
                pd.DataFrame() if nombre in caducados
                else estado_de_plano(datos["estados"][nombre])
            )
            for nombre in ESTADOS
        }

    return _traer("estados", ticker, pedir, interpretar, leer)


def tipo_de_cambio(origen: str, destino: str) -> "tuple[float | None, str]":
    """Cuántas unidades de `destino` vale una de `origen`, al último cierre.

    El par de Yahoo es `<ORIGEN><DESTINO>=X`: `TWDUSD=X` da dólares por cada
    dólar taiwanés. Una subunidad (`SUBUNIDADES`) se cambia como su moneda y se
    escala después. Una moneda consigo misma, o frente a su subunidad, no sale a
    la red. Un par que Yahoo no conoce, o sin ningún cierre válido, se ve igual
    que un fallo de red (`sin_red`): no hay otro motivo que `ok` o ése.
    """
    base_origen, escala_origen = SUBUNIDADES.get(origen, (origen, 1))
    base_destino, escala_destino = SUBUNIDADES.get(destino, (destino, 1))
    if base_origen == base_destino:
        return escala_destino / escala_origen, "ok"
    simbolo = f"{base_origen}{base_destino}=X"

    def pedir():
        return yf.Ticker(simbolo).history(period="5d")["Close"]

    def interpretar(cierres):
        # `history()` no lanza cuando falla la red: devuelve vacío. `inf > 0` es
        # verdadero y se guardaría como `Infinity`, y un último cierre a cero
        # taparía uno bueno anterior: sólo valen los finitos y positivos, y sin
        # ninguno no se sabe nada, igual que sin cierres.
        validos = [x for x in map(_opcional, cierres) if x is not None and x > 0]
        return {"valor": validos[-1]} if validos else None

    def leer(datos):
        # Una entrada con `valor: null`, de cuando un par sin cierres válidos se
        # guardaba, o con un valor que no es un tipo de cambio --texto, cero,
        # negativo, NaN-- lanza `TypeError` y no se sirve: `float()` lanzaría
        # `ValueError` en cada llamada, o daría por bueno un cero.
        valor = _opcional(datos["valor"])
        if valor is None or valor <= 0:
            raise TypeError("tipo de cambio guardado sin valor válido")
        return valor

    valor, motivo = _traer("tipo_de_cambio", simbolo, pedir, interpretar, leer)
    if motivo != "ok":
        return None, motivo
    return valor * escala_destino / escala_origen, "ok"

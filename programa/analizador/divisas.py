"""En qué moneda se valora un ticker, con qué tasa libre y contra qué índice.

| Estados | Se valora en | Tasa libre                    | Beta contra   |
|---------|--------------|-------------------------------|---------------|
| USD     | dólares      | `^TNX`                        | `^GSPC`       |
| MXN     | pesos        | Bono M a 10 años, de Banxico  | `^MXX` (IPC)  |
| otra    | dólares      | `^TNX`                        | `^GSPC`       |

En el tercer caso los estados se convierten a dólares al tipo del día, y se
dice (`Divisa.convertida`). Que la valoración lleve o no prima por riesgo país
no lo dice la moneda de los estados sino el país de la empresa: NPN.JO o
TEVA.TA presentan en dólares y se valoran sin ella, igual que TSM. El precio se
lleva a la moneda de la valoración para votar: un valor en dólares
frente a un precio en dólares canadienses no dice nada.

El Bono M se usa tal cual, sin restarle el diferencial soberano que Damodaran
propone quitarle antes de sumar una prima de riesgo país: con una beta cercana
a 1 la diferencia es de décimas, el supuesto se puede mover y la procedencia lo
dice.
"""

import math
from dataclasses import dataclass, fields, replace
from datetime import date

from seguimiento import banxico
from valoracion import mercado
from valoracion.fundamentos import Ejercicio, Fundamentos
from valoracion.mercado import Perfil

# «Valores Gubernamentales. Resultados de la subasta semanal. Tasa de
# rendimiento. Bono tasa fija 10 años», en porcentaje. Buscada en el catálogo
# del SIE el 2026-10-14; la fija un test `red` contra el título de sus
# metadatos (`tests/test_analizador_red.py`). Es de subasta, no de mercado
# secundario: el último dato puede tener semanas, y su fecha va en la
# procedencia.
SERIE_BONO_M_10 = "SF44071"
INDICE_MXN = "^MXX"
# Las monedas con tasa libre propia. Cualquier otra se valora en dólares.
MONEDAS_PROPIAS = ("USD", "MXN")
# Recuento de los estados entre el de la cotización. Fuera de este margen el
# recuento de los estados no es el de la cotización: una ADR con un ratio
# distinto de 1, o una clase de acción que no es la que cotiza.
ADR_TOLERANCIA = (0.8, 1.25)


@dataclass(frozen=True)
class Divisa:
    """Cómo se pasan los estados y el precio a la moneda de la valoración.

    Los tipos son unidades de `moneda_valoracion` por cada unidad de la otra
    moneda; 1 si coinciden.
    """

    moneda_estados: str
    moneda_precio: str
    moneda_valoracion: str
    tipo_estados: float
    tipo_precio: float
    indice_beta: str

    @property
    def convertida(self) -> bool:
        """Si los estados se pasaron a dólares. No dice nada de la prima por riesgo país."""
        return self.moneda_estados != self.moneda_valoracion

    def a_dict(self) -> dict:
        datos = {campo.name: getattr(self, campo.name) for campo in fields(self)}
        return {**datos, "estados_convertidos": self.convertida}


def moneda_de_valoracion(moneda_estados: str) -> str:
    return moneda_estados if moneda_estados in MONEDAS_PROPIAS else "USD"


def divisa(moneda_estados: str, moneda_precio: str) -> "tuple[Divisa | None, str]":
    """La moneda de la valoración y los dos tipos de cambio, o por qué no se pudo."""
    valoracion = moneda_de_valoracion(moneda_estados)
    tipo_estados, motivo = mercado.tipo_de_cambio(moneda_estados, valoracion)
    if tipo_estados is None:
        return None, motivo
    tipo_precio, motivo = mercado.tipo_de_cambio(moneda_precio, valoracion)
    if tipo_precio is None:
        return None, motivo
    indice = INDICE_MXN if valoracion == "MXN" else mercado.INDICE
    return (
        Divisa(moneda_estados, moneda_precio, valoracion, tipo_estados, tipo_precio, indice),
        "ok",
    )


_DINERO = tuple(campo.name for campo in fields(Ejercicio) if campo.name != "fin")


def convertir(fundamentos: Fundamentos, tipo: float, moneda: str) -> Fundamentos:
    """Los mismos fundamentos en otra moneda. NaN, «no declarado», se queda NaN."""
    if tipo == 1.0 and fundamentos.moneda == moneda:
        return fundamentos
    ejercicios = tuple(
        replace(e, **{nombre: getattr(e, nombre) * tipo for nombre in _DINERO})
        for e in fundamentos.ejercicios
    )
    return replace(
        fundamentos,
        moneda=moneda,
        ejercicios=ejercicios,
        deuda_total=fundamentos.deuda_total * tipo,
        efectivo=fundamentos.efectivo * tipo,
    )


def perfil_en(perfil: Perfil, tipo: float, moneda: str) -> Perfil:
    """El precio y la capitalización en la moneda de la valoración, para votar.

    `tipo` es el del precio. El recuento de acciones (capitalización ÷ precio)
    tiene que salir el de verdad: es lo que desactiva la trampa de la ADR,
    como en M. Por eso una cotización en subunidades se corrige: Yahoo da el
    precio de Londres en peniques y la capitalización en libras (SHEL.L:
    capitalización ÷ precio = acciones ÷ 100), así que la capitalización se
    convierte con el tipo de la moneda principal, que es el de la subunidad por
    su escala (`mercado.SUBUNIDADES`). Johannesburgo, Tel Aviv y Kuwait hacen
    lo mismo: precio en ZAc, ILA o KWF y capitalización en la moneda principal
    (comprobado el 2026-10-19 con NPN.JO, TEVA.TA y NBK.KW). Si Yahoo dejase de
    hacerlo, la única red sería `cociente_adr`, que daría ≈ 0,01 y avisaría.
    """
    _, escala = mercado.SUBUNIDADES.get(perfil.moneda, (perfil.moneda, 1))
    return replace(
        perfil,
        precio=perfil.precio * tipo,
        capitalizacion=perfil.capitalizacion * tipo * escala,
        moneda=moneda,
        moneda_estados=moneda,
    )


def cociente_adr(acciones_estados: "float | None", perfil: Perfil) -> "float | None":
    """El recuento de los estados entre el de la cotización (capitalización ÷ precio).

    Cerca de 1 es lo normal. TSM da 1 con yfinance, que ya trae su recuento en
    base ADR; con el XBRL del 20-F daría 5. El valor por acción se divide
    siempre por el de la cotización, así que esto no corrige nada: avisa.
    `perfil` es el ya convertido por `perfil_en`, que corrige la capitalización
    de las cotizaciones en subunidades; con el de Yahoo tal cual, una empresa de
    Londres saldría con un cociente de 100.
    """
    try:
        estados = float(acciones_estados)
    except (TypeError, ValueError):
        return None
    cotizacion = perfil.capitalizacion / perfil.precio
    if not (math.isfinite(estados) and estados > 0 and cotizacion > 0):
        return None
    return estados / cotizacion


def adr_dudosa(cociente: "float | None") -> bool:
    return cociente is not None and not ADR_TOLERANCIA[0] <= cociente <= ADR_TOLERANCIA[1]


def bono_m(
    clave: "str | None" = None, hoy: "date | None" = None, raiz=None
) -> "tuple[float | None, str, date | None]":
    """El rendimiento de la última subasta del Bono M a diez años, en tanto por uno.

    Con el transporte de `seguimiento/banxico.py`: el token en la cabecera y
    nunca en la URL, su caché y sus motivos (`sin_token`, `token_invalido`,
    `sin_red`, `respuesta_rara`). Sin subasta en la ventana, `sin_dato`.
    Devuelve también la fecha de la subasta, que va a la procedencia. `raiz`
    es la carpeta de la caché, para que los tests no escriban en la de verdad.
    """
    hoy = hoy or date.today()
    clave = banxico.token() if clave is None else clave
    otra_raiz = {} if raiz is None else {"raiz": raiz}
    # `traer` guarda en caché por serie y `desde`: con un `desde` que se mueve
    # cada día, el dato de ayer no serviría de respaldo si hoy Banxico no
    # responde. Anclado al 1 de enero del año anterior, la clave cambia una vez
    # al año y la ventana va de 12 a 24 meses, unas 20 subastas (la mayor
    # separación medida entre dos fue de 56 días).
    desde = date(hoy.year - 1, 1, 1)
    serie = banxico.traer(SERIE_BONO_M_10, desde, hoy, clave, **otra_raiz)
    if serie.motivo != "ok":
        return None, serie.motivo, None
    if serie.datos is None or serie.datos.empty:
        return None, "sin_dato", None
    return float(serie.datos.iloc[-1]) / 100, "ok", serie.datos.index[-1].date()

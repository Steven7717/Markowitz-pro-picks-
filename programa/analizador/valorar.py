"""La valoración de cualquier ticker: una sola vez a la red, y luego aritmética.

`entradas` trae de la red todo lo que la valoración necesita --perfil,
fundamentos, tasa libre, beta, tasa efectiva, consenso y tipos de cambio-- y lo
deja en la moneda de la valoración (ver `analizador.divisas`). `valorar` es
puro: con las mismas entradas y los mismos cambios da siempre lo mismo, y es lo
que llamarán los deslizadores de N2 sin volver a pedir nada.

Sin cambios, `valorar` da la valoración con los supuestos del programa: la que
va al acta. Con cambios, la de los deslizadores, que no se guarda en ningún
sitio.
"""

from dataclasses import dataclass

from analizador import divisas
from analizador.divisas import Divisa
from analizador.lineas_yf import fundamentos_anuales, lineas_de
from analizador.resolver import Resuelto
from valoracion import dcf, mercado, plano
from valoracion.criterio import INDUSTRIAS_FINANCIERAS
from valoracion.fundamentos import Fundamentos, desde_sec
from valoracion.mercado import Beta, Perfil
from valoracion.motor import calcular, datos_dcf, puente
from valoracion.supuestos import Supuestos, aplicar, deducir, exigir_costes_positivos

# Privada y aun así importada: es la misma validación que `aplicar` hace con
# cualquier supuesto movido, y la tasa que el usuario pone a mano lo es.
from valoracion.supuestos import _numero_finito


@dataclass(frozen=True)
class Entradas:
    """Todo lo que la valoración necesita, ya en la moneda de la valoración.

    `r_f` puede faltar: una emisora en pesos sin el Bono M de Banxico se queda
    sin tasa libre hasta que el usuario la ponga. `motivo_r_f` dice por qué
    falta: con el Bono M, los de Banxico (`sin_token`, `token_invalido`,
    `sin_red`, `respuesta_rara`) o `sin_dato`; con el Tesoro,
    `sin_tasa_libre`. `cociente_adr` es el de `divisas.cociente_adr`, o None.
    """

    ticker: str
    fundamentos: Fundamentos
    perfil: Perfil
    divisa: Divisa
    r_f: "float | None"
    procedencia_r_f: dict
    motivo_r_f: str
    beta: "Beta | None"
    tasa: "float | None"
    consenso: "float | None"
    motivos: dict
    cociente_adr: "float | None"


def _ultimo(serie) -> "float | None":
    validos = serie.dropna()
    return float(validos.iloc[-1]) if len(validos) else None


def entradas(resuelto: Resuelto, cache_dir=None) -> "tuple[Entradas | None, str]":
    """Todo lo que la valoración necesita, o el motivo por el que no se pudo traer.

    Primero el precio, porque sin él no hay acciones; después los estados,
    porque sin ellos no hay nada que proyectar; y después los tipos de cambio,
    porque sin ellos no se pueden pasar a la moneda de la valoración. La tasa
    libre no corta: `valoracion.motor.valorar` la exige antes que los estados,
    y aquí se trae pero no se exige, porque sin ella todavía se puede pintar
    todo lo demás y el deslizador la pide (ver `valorar`).
    """
    ticker = resuelto.ticker
    perfil, motivo = mercado.perfil(ticker)
    if perfil is None:
        return None, "sin_red" if motivo == "sin_red" else "sin_precio"
    acciones_estados = None
    if resuelto.clase == "sec":
        fundamentos, motivo = desde_sec(ticker, cache_dir=cache_dir)
    else:
        crudos, motivo = mercado.estados(ticker)
        if crudos is None:
            return None, motivo
        trimestrales, anuales = lineas_de(crudos)
        fundamentos = fundamentos_anuales(anuales, perfil.moneda_estados)
        motivo = "ok" if fundamentos is not None else "sin_historia"
        if not trimestrales.empty:
            acciones_estados = _ultimo(trimestrales["acciones_diluidas"])
    if fundamentos is None:
        return None, motivo
    divisa, motivo = divisas.divisa(fundamentos.moneda, perfil.moneda)
    if divisa is None:
        return None, motivo
    # El consenso es una tasa de crecimiento, y Yahoo lo da en la moneda de los
    # estados originales (en TSM, TWD): se compara antes de convertir.
    consenso, motivo_consenso = mercado.consenso(ticker, fundamentos.moneda)
    if divisa.moneda_valoracion == "MXN":
        r_f, motivo_r_f, fecha = divisas.bono_m()
        procedencia = {
            "fuente": "bono_m_10",
            "serie": divisas.SERIE_BONO_M_10,
            "fecha": None if fecha is None else fecha.isoformat(),
        }
    else:
        r_f, motivo_r_f = mercado.tasa_libre()
        procedencia = {"fuente": "tesoro_10", "serie": mercado.BONO_10}
    # La beta se regresa con el precio en la moneda de la valoración, que es la
    # del índice: AMX en dólares contra el IPC en pesos mezclaría dos monedas.
    base_precio, _ = mercado.SUBUNIDADES.get(perfil.moneda, (perfil.moneda, 1))
    par_beta = (
        None
        if base_precio == divisa.moneda_valoracion
        else f"{base_precio}{divisa.moneda_valoracion}=X"
    )
    beta, motivo_beta = mercado.beta(ticker, divisa.indice_beta, par_beta)
    tasa, motivo_tasa = mercado.tasa_efectiva(ticker)
    perfil_valoracion = divisas.perfil_en(perfil, divisa.tipo_precio, divisa.moneda_valoracion)
    return (
        Entradas(
            ticker=ticker,
            fundamentos=divisas.convertir(fundamentos, divisa.tipo_estados, divisa.moneda_valoracion),
            perfil=perfil_valoracion,
            divisa=divisa,
            r_f=r_f,
            procedencia_r_f=procedencia,
            motivo_r_f=motivo_r_f,
            beta=beta,
            tasa=tasa,
            consenso=consenso,
            motivos={"beta": motivo_beta, "tasa": motivo_tasa, "consenso": motivo_consenso},
            cociente_adr=divisas.cociente_adr(acciones_estados, perfil_valoracion),
        ),
        "ok",
    )


def supuestos_de(entradas: Entradas, cambios: "dict | None" = None) -> "Supuestos | None":
    """Los supuestos del programa con los cambios del usuario, o None sin tasa libre.

    Sin tasa libre (un Bono M sin token) sólo hay supuestos si el usuario la
    pone, y entra como `{"fuente": "usuario", "programa": None}`: el programa no
    tenía ninguna.
    """
    cambios = dict(cambios or {})
    r_f, procedencia = entradas.r_f, entradas.procedencia_r_f
    a_mano = r_f is None
    if a_mano:
        if "r_f" not in cambios:
            return None
        r_f = _numero_finito("r_f", cambios.pop("r_f"))
        procedencia = {"fuente": "usuario", "programa": None}
    supuestos = deducir(
        entradas.fundamentos,
        entradas.perfil,
        r_f,
        entradas.beta,
        entradas.tasa,
        entradas.consenso,
        entradas.motivos,
        procedencia_r_f=procedencia,
    )
    movidos = aplicar(supuestos, cambios)
    if a_mano:
        # La tasa puesta a mano entra por `deducir`, no por `aplicar`, y las
        # guardas de `aplicar` no la ven: con un −5 %, WALMEX salía con un coste
        # del capital propio negativo y un valor base. Se le exige lo mismo que
        # a una tasa movida, y sobre el resultado: con la beta movida a la vez,
        # el k_e intermedio, con la beta del programa, no es el que se usa.
        exigir_costes_positivos(movidos)
    return movidos


def _sin_prima_pais(entradas: Entradas) -> bool:
    """Si se valora en dólares una empresa de fuera de EE. UU.

    Con la tasa libre del Tesoro y la prima de un mercado maduro, a una empresa
    de Taiwán o de Israel le falta la prima por riesgo país. En pesos no: el
    Bono M ya lleva el riesgo soberano de México. Sin país conocido no se
    afirma nada.
    """
    pais = entradas.perfil.pais
    return (
        entradas.divisa.moneda_valoracion == "USD"
        and pais is not None
        and pais != "United States"
    )


def _sin_tasa(entradas: Entradas) -> str:
    return "sin_bono_m" if entradas.divisa.moneda_valoracion == "MXN" else "sin_tasa_libre"


def valorar(
    entradas: Entradas,
    pilar_valoracion: "float | None",
    cambios: "dict | None" = None,
    hoy=None,
) -> dict:
    """La valoración como diccionario, con la divisa y el cociente de la ADR al lado.

    JSON estricto, como `plano.a_dict`. Las dos claves de más (`divisa`,
    `cociente_adr`) las ignora quien no las conoce: `medidores_valoracion` y
    `aprobacion.carga.valoracion_de` sólo miran las suyas.
    """
    divisa = {**entradas.divisa.a_dict(), "sin_prima_pais": _sin_prima_pais(entradas)}
    extra = {"divisa": divisa, "cociente_adr": entradas.cociente_adr}
    supuestos = supuestos_de(entradas, cambios)
    if supuestos is None:
        return {**plano.fallida(_sin_tasa(entradas), hoy), **extra}
    v = calcular(entradas.fundamentos, entradas.perfil, supuestos, pilar_valoracion, hoy)
    return {**plano.a_dict(v), **extra}


def sensibilidad(entradas: Entradas, cambios: "dict | None" = None) -> "dcf.Sensibilidad | None":
    """La tabla de sensibilidad del DCF con los mismos datos con que se votó.

    None si no hay DCF que tabular: una financiera (se valora por beneficio
    residual), sin tasa libre, o sin datos para el DCF (sin historia, sin flujo
    libre, quema caja). Con el coste de capital sin holgura sobre el
    crecimiento perpetuo sí hay tabla: la casilla central sale vacía y las
    demás enseñan desde qué coste vuelve a haber valor.
    """
    if entradas.perfil.industria in INDUSTRIAS_FINANCIERAS:
        return None
    supuestos = supuestos_de(entradas, cambios)
    if supuestos is None:
        return None
    # El mismo puente que `calcular`: si la tabla tratara la deuda o las
    # acciones de otra forma, su casilla central no sería el valor base.
    deuda, efectivo, acciones = puente(entradas.fundamentos, entradas.perfil)
    datos, _ = datos_dcf(entradas.fundamentos, supuestos, deuda, efectivo, acciones)
    if datos is None:
        return None
    return dcf.sensibilidad(datos, supuestos.g_ref.valor)

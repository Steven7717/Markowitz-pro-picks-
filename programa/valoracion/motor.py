"""El motor: de fundamentos, perfil y supuestos al veredicto.

`calcular` es puro y es lo que prueban los tests. `valorar` sale a la red,
recoge lo que `calcular` necesita y devuelve ya el diccionario que se guarda.
"""

import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from valoracion import dcf, mercado, plano, residual
from valoracion.criterio import (
    DELTA_WACC_ESCENARIOS,
    INDUSTRIAS_FINANCIERAS,
    MARGEN_MINIMO,
    MARGEN_ROE_MINIMO,
    MIN_ANOS_HISTORIA,
)
from valoracion.dcf import Escenarios
from valoracion.epv import epv_por_accion, parte_crecimiento
from valoracion.fundamentos import Fundamentos, desde_sec
from valoracion.inverso import crecimiento_implicito
from valoracion.mercado import Perfil
from valoracion.supuestos import Supuestos, deducir
from valoracion.votos import (
    NO_APLICA,
    Voto,
    margen_voto,
    veredicto,
    voto_epv,
    voto_implicito,
    voto_pares,
)


@dataclass(frozen=True)
class Lectura:
    """Lo que el precio exige (crecimiento o ROE) frente a su referencia."""

    magnitud: str
    valor: "float | None"
    referencia: float
    margen: float
    fuera_de_limites: "str | None"


@dataclass(frozen=True)
class SinCrecimiento:
    """El valor sin crecimiento (EPV) por acción y qué parte del precio es apuesta.

    `parte_crecimiento` puede ser negativa: si el EPV supera al precio, la
    empresa cotiza por debajo de lo que ya gana sin crecer (VZ, −0,46). Es un
    resultado y no un fallo, y la pantalla sólo la pinta cuando es positiva:
    una «parte de crecimiento» negativa no es una apuesta, y mostrarla
    confundiría.
    """

    por_accion: float
    parte_crecimiento: "float | None"


@dataclass(frozen=True)
class Valoracion:
    fecha: date
    # El cierre del último ejercicio. Una valoración con estados de hace un año
    # no se puede leer como una de hoy, y en N cualquiera puede traer un ticker
    # cuyas cuentas se quedaron atrás. En candidatos no pasa: la guarda
    # `MAX_ANTIGUEDAD_TRIMESTRES` del ranking ya excluye a los rezagados.
    estados_hasta: date
    moneda: str
    precio: float
    precio_hora: "str | None"
    metodo: str
    valor: "Escenarios | None"
    margen_seguridad: "float | None"
    implicito: "Lectura | None"
    epv: "SinCrecimiento | None"
    votos: dict
    veredicto: str
    supuestos: Supuestos


def _o_cero(valor: float) -> float:
    """Deuda o efectivo sin declarar cuentan como cero; la procedencia del
    coste de capital ya dice si la deuda estaba declarada."""
    return valor if math.isfinite(valor) else 0.0


def _lectura_flujos(fundamentos, supuestos, deuda, efectivo, acciones, precio):
    g_ref = supuestos.g_ref.valor
    if g_ref is None or not fundamentos.ultimo.ingresos > 0:
        return Voto(NO_APLICA, "sin_historia"), None, None
    margen = dcf.margen_fcff(fundamentos, supuestos.t.valor)
    if margen is None:
        # Igual que `epv_por_accion` separa `sin_beneficio_operativo` de
        # `sin_historia`: lo que falta es el dato y no la historia. LLY, COST,
        # NEE, VZ o PEP tienen cinco años de ingresos y no declaran el capex
        # nunca; decir «sin historia» de ellas sería falso y despistaría.
        con_ingresos = sum(1 for e in fundamentos.ejercicios if e.ingresos > 0)
        motivo = "sin_flujo_libre" if con_ingresos >= MIN_ANOS_HISTORIA else "sin_historia"
        return Voto(NO_APLICA, motivo), None, None
    if margen <= 0:
        # Quema caja: valorarla exigiría inventar cuándo deja de hacerlo.
        return Voto(NO_APLICA, "quema_caja"), None, None
    datos = dcf.Datos(
        ingresos=fundamentos.ultimo.ingresos,
        margen=margen,
        wacc=supuestos.wacc.valor,
        g_perpetuo=supuestos.g_perpetuo.valor,
        deuda=deuda,
        efectivo=efectivo,
        acciones=acciones,
    )
    base = dcf.valor_por_accion(datos, g_ref)
    if base is None:
        return Voto(NO_APLICA, "wacc_bajo_crecimiento"), None, None
    holgura = margen_voto(g_ref, MARGEN_MINIMO)
    valor = Escenarios(
        pesimista=dcf.valor_por_accion(datos, g_ref - holgura, datos.wacc + DELTA_WACC_ESCENARIOS),
        base=base,
        optimista=dcf.valor_por_accion(datos, g_ref + holgura, datos.wacc - DELTA_WACC_ESCENARIOS),
    )
    implicito = crecimiento_implicito(datos, precio)
    lectura = Lectura("crecimiento", implicito.valor, g_ref, holgura, implicito.fuera_de_limites)
    return voto_implicito(implicito, g_ref, holgura), valor, lectura


def _lectura_residual(fundamentos, supuestos, acciones, precio):
    roe_ref = supuestos.roe_ref.valor
    if roe_ref is None:
        return Voto(NO_APLICA, "sin_historia"), None, None
    patrimonio = fundamentos.ultimo.patrimonio_neto
    # NaN es «no declarado», no negativo: decir `patrimonio_negativo` de un
    # banco que sólo omitió la línea afirmaría una cifra que nadie vio.
    if not math.isfinite(patrimonio):
        return Voto(NO_APLICA, "sin_historia"), None, None
    if patrimonio <= 0:
        return Voto(NO_APLICA, "patrimonio_negativo"), None, None
    datos = residual.DatosResidual(
        patrimonio=patrimonio,
        k_e=supuestos.k_e.valor,
        payout=supuestos.payout.valor,
        g_perpetuo=supuestos.g_perpetuo.valor,
        acciones=acciones,
    )
    base = residual.valor_por_accion(datos, roe_ref)
    if base is None:
        # El coste del capital no supera al crecimiento perpetuo en la
        # holgura: el valor terminal explotaría, igual que en el DCF.
        return Voto(NO_APLICA, "wacc_bajo_crecimiento"), None, None
    holgura = margen_voto(roe_ref, MARGEN_ROE_MINIMO)
    valor = Escenarios(
        pesimista=residual.valor_por_accion(datos, roe_ref - holgura, datos.k_e + DELTA_WACC_ESCENARIOS),
        base=base,
        optimista=residual.valor_por_accion(datos, roe_ref + holgura, datos.k_e - DELTA_WACC_ESCENARIOS),
    )
    implicito = residual.roe_implicito(datos, precio)
    lectura = Lectura("roe", implicito.valor, roe_ref, holgura, implicito.fuera_de_limites)
    return voto_implicito(implicito, roe_ref, holgura), valor, lectura


def _lectura_epv(fundamentos, supuestos, deuda, efectivo, acciones, precio):
    valor, motivo = epv_por_accion(
        fundamentos, supuestos.t.valor, supuestos.wacc.valor, deuda, efectivo, acciones
    )
    if valor is None:
        return Voto(NO_APLICA, motivo), None
    return voto_epv(valor, precio), SinCrecimiento(valor, parte_crecimiento(valor, precio))


def calcular(
    fundamentos: Fundamentos,
    perfil: Perfil,
    supuestos: Supuestos,
    pilar_valoracion: "float | None",
    hoy: "date | None" = None,
) -> Valoracion:
    """Las cuatro lecturas, los tres votos y el veredicto. Sin red.

    Las acciones son capitalización ÷ precio: el recuento en la base en la que
    está el precio. Es lo que desactiva la trampa de las ADR en N.
    """
    precio = perfil.precio
    acciones = perfil.capitalizacion / perfil.precio
    deuda, efectivo = _o_cero(fundamentos.deuda_total), _o_cero(fundamentos.efectivo)
    if perfil.industria in INDUSTRIAS_FINANCIERAS:
        metodo = "residual"
        flujos, valor, lectura = _lectura_residual(fundamentos, supuestos, acciones, precio)
        sin_crecimiento, epv = Voto(NO_APLICA, "financiera"), None
    else:
        metodo = "flujos"
        flujos, valor, lectura = _lectura_flujos(
            fundamentos, supuestos, deuda, efectivo, acciones, precio
        )
        sin_crecimiento, epv = _lectura_epv(
            fundamentos, supuestos, deuda, efectivo, acciones, precio
        )
    votos = {
        "flujos": flujos,
        "sin_crecimiento": sin_crecimiento,
        "pares": voto_pares(pilar_valoracion),
    }
    base = None if valor is None else valor.base
    return Valoracion(
        fecha=hoy or date.today(),
        estados_hasta=fundamentos.ultimo.fin,
        moneda=perfil.moneda,
        precio=precio,
        precio_hora=perfil.hora,
        metodo=metodo,
        valor=valor,
        margen_seguridad=None if base is None else (base - precio) / precio,
        implicito=lectura,
        epv=epv,
        votos=votos,
        veredicto=veredicto(votos.values()),
        supuestos=supuestos,
    )


def valorar(
    ticker: str,
    pilar_valoracion: "float | None",
    cache_dir: "Path | None" = None,
    hoy: "date | None" = None,
) -> dict:
    """La valoración de un ticker de la SEC, ya como diccionario para guardar.

    Lo que falta se dice con su motivo en vez de calcularse a medias: sin precio
    no hay acciones, sin tasa libre no hay coste de capital, y sin estados no
    hay nada que proyectar. `sin_red` y `sin_precio` se distinguen: con la red
    caída cada ticker tarda lo suyo en rendirse (21 s con una red que descarta
    paquetes), y quien recorre una lista tiene que poder parar en vez de
    intentar el resto; un ticker que Yahoo no conoce, en cambio, es sólo ése.

    Las excepciones se dejan propagar a propósito: un defecto propio o un fallo
    del entorno no es una propiedad de la empresa, y quien llama
    (`ranking/run.py`) las atrapa ficha a ficha para no confundirlas con una
    empresa sin datos.
    """
    perfil, motivo_perfil = mercado.perfil(ticker)
    if perfil is None:
        return plano.fallida("sin_red" if motivo_perfil == "sin_red" else "sin_precio", hoy)
    r_f, _ = mercado.tasa_libre()
    if r_f is None:
        return plano.fallida("sin_tasa_libre", hoy)
    fundamentos, motivo = desde_sec(ticker, cache_dir=cache_dir)
    if fundamentos is None:
        return plano.fallida(motivo, hoy)
    beta, _ = mercado.beta(ticker)
    tasa, _ = mercado.tasa_efectiva(ticker)
    consenso, _ = mercado.consenso(ticker, fundamentos.moneda)
    supuestos = deducir(fundamentos, perfil, r_f, beta, tasa, consenso)
    return plano.a_dict(calcular(fundamentos, perfil, supuestos, pilar_valoracion, hoy))

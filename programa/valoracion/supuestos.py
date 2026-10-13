"""Los supuestos de la valoración, cada uno con su procedencia.

La procedencia es **dato estructurado, no texto**
(`{"fuente": "regresion", "semanas": 104, ...}`), y la pantalla la traduce al
pintarla. Es la regla que dejó «La etiqueta de pantalla que se guardaba en
disco»: a un fichero de datos no se escribe nada cuyo valor sea una decisión de
redacción.

M no tiene forma de cambiar supuestos: en Revisar candidatos no hay
deslizadores. La función que aplica los cambios del usuario la añade N, que es
quien la usa.
"""

import math
from dataclasses import dataclass

import numpy as np

from valoracion.criterio import (
    BETA_SEMANAS_MIN,
    BLUME,
    COSTE_DEUDA_PRIMA_MAXIMA,
    CRECIMIENTO_PERPETUO,
    CRECIMIENTO_REF_ANOS,
    CRECIMIENTO_REF_TOPES,
    MIN_ANOS_HISTORIA,
    PAYOUT_SIN_DATO,
    PRIMA_RIESGO,
    PRIMA_RIESGO_FECHA,
    TASA_EFECTIVA_TOPES,
    TASA_LEGAL,
)
from valoracion.fundamentos import Fundamentos
from valoracion.mercado import Beta, Perfil

_PAISES = {"United States": "US", "Mexico": "MX"}


@dataclass(frozen=True)
class Supuesto:
    valor: "float | None"
    procedencia: dict


@dataclass(frozen=True)
class Supuestos:
    r_f: Supuesto
    beta: Supuesto
    prima: Supuesto
    k_e: Supuesto
    k_d: Supuesto
    t: Supuesto
    wacc: Supuesto
    g_ref: Supuesto
    g_perpetuo: Supuesto
    roe_ref: Supuesto
    payout: Supuesto


def _acotar(valor: float, limites: "tuple[float, float]") -> float:
    bajo, alto = limites
    return min(max(valor, bajo), alto)


def _redondeo(valor: "float | None") -> "float | None":
    return None if valor is None or not math.isfinite(valor) else round(float(valor), 4)


def beta_ajustada(beta: "Beta | None") -> Supuesto:
    """Blume sobre la regresión: la beta medida tiende a 1 con el tiempo."""
    if beta is None or beta.semanas < BETA_SEMANAS_MIN:
        return Supuesto(1.0, {"fuente": "por_defecto"})
    a, b = BLUME
    return Supuesto(
        a * beta.bruta + b,
        {
            "fuente": "regresion",
            "indice": beta.indice,
            "semanas": beta.semanas,
            "r2": _redondeo(beta.r2),
            "bruta": _redondeo(beta.bruta),
        },
    )


def tasa_impositiva(tasa: "float | None", pais: "str | None") -> Supuesto:
    if tasa is not None and math.isfinite(tasa):
        return Supuesto(
            _acotar(tasa, TASA_EFECTIVA_TOPES),
            {"fuente": "efectiva", "bruta": _redondeo(tasa)},
        )
    clave = _PAISES.get(pais or "", "otros")
    return Supuesto(TASA_LEGAL[clave], {"fuente": "legal", "pais": clave})


def coste_deuda(fundamentos: Fundamentos, r_f: float) -> Supuesto:
    """Gasto financiero entre deuda, sin bajar de la tasa libre ni subir como un bono basura."""
    deuda = fundamentos.deuda_total
    intereses = fundamentos.ultimo.gasto_financiero
    if not deuda > 0 or not math.isfinite(intereses):
        return Supuesto(r_f, {"fuente": "sin_dato"})
    bruto = abs(intereses) / deuda
    return Supuesto(
        _acotar(bruto, (r_f, r_f + COSTE_DEUDA_PRIMA_MAXIMA)),
        {"fuente": "gasto_entre_deuda", "bruto": _redondeo(bruto)},
    )


def coste_capital(
    k_e: float, k_d: float, t: float, capitalizacion: float, deuda: float
) -> Supuesto:
    """Capital a valor de mercado y deuda a valor contable.

    `capitalizacion` va en la moneda del precio y `deuda` en la de los estados.
    En M coinciden; N convierte antes de llamar.
    """
    declarada = math.isfinite(deuda)
    d = deuda if declarada and deuda > 0 else 0.0
    peso_deuda = d / (capitalizacion + d)
    return Supuesto(
        (1 - peso_deuda) * k_e + peso_deuda * k_d * (1 - t),
        {
            "fuente": "wacc",
            "peso_deuda": _redondeo(peso_deuda),
            "deuda_declarada": declarada,
        },
    )


def _cagr(fundamentos: Fundamentos) -> "float | None":
    anos = min(CRECIMIENTO_REF_ANOS, len(fundamentos.ejercicios) - 1)
    if anos < 1:
        return None
    final = fundamentos.ejercicios[0].ingresos
    inicial = fundamentos.ejercicios[anos].ingresos
    if not (final > 0 and inicial > 0):
        return None
    return (final / inicial) ** (1 / anos) - 1


def crecimiento_ref(fundamentos: Fundamentos, consenso: "float | None") -> Supuesto:
    historico = _cagr(fundamentos)
    partes = [v for v in (historico, consenso) if v is not None and math.isfinite(v)]
    if not partes:
        return Supuesto(None, {"fuente": "sin_dato"})
    bruto = sum(partes) / len(partes)
    return Supuesto(
        _acotar(bruto, CRECIMIENTO_REF_TOPES),
        {
            "fuente": "historia_y_consenso",
            "historico": _redondeo(historico),
            "consenso": _redondeo(consenso),
            "bruto": _redondeo(bruto),
        },
    )


def crecimiento_perpetuo(moneda: str, r_f: float) -> Supuesto:
    """Nunca por encima de la tasa libre: una empresa que crece para siempre más
    que la economía acaba siendo la economía."""
    base = CRECIMIENTO_PERPETUO[moneda]
    if base > r_f:
        return Supuesto(r_f, {"fuente": "recortado_a_r_f", "base": base})
    return Supuesto(base, {"fuente": "criterio", "moneda": moneda})


def roe_referencia(fundamentos: Fundamentos) -> Supuesto:
    """La mediana del ROE anual. No es el KPI `roe` del panel, que es trimestral."""
    roes = [
        e.beneficio_neto / e.patrimonio_neto
        for e in fundamentos.ejercicios
        if math.isfinite(e.beneficio_neto) and e.patrimonio_neto > 0
    ]
    if len(roes) < MIN_ANOS_HISTORIA:
        return Supuesto(None, {"fuente": "sin_dato"})
    return Supuesto(float(np.median(roes)), {"fuente": "mediana_historica", "anos": len(roes)})


def payout(valor: "float | None") -> Supuesto:
    if valor is not None and math.isfinite(valor):
        return Supuesto(_acotar(valor, (0.0, 1.0)), {"fuente": "yfinance"})
    return Supuesto(PAYOUT_SIN_DATO, {"fuente": "por_defecto"})


def deducir(
    fundamentos: Fundamentos,
    perfil: Perfil,
    r_f: float,
    beta: "Beta | None",
    tasa: "float | None",
    consenso: "float | None",
) -> Supuestos:
    """Los supuestos del programa. Siempre los mismos para los mismos datos."""
    b = beta_ajustada(beta)
    k_e = r_f + b.valor * PRIMA_RIESGO
    k_d = coste_deuda(fundamentos, r_f)
    t = tasa_impositiva(tasa, perfil.pais)
    return Supuestos(
        r_f=Supuesto(r_f, {"fuente": "tesoro_10", "serie": "^TNX"}),
        beta=b,
        prima=Supuesto(PRIMA_RIESGO, {"fuente": "damodaran", "fecha": PRIMA_RIESGO_FECHA}),
        k_e=Supuesto(k_e, {"fuente": "capm"}),
        k_d=k_d,
        t=t,
        wacc=coste_capital(
            k_e, k_d.valor, t.valor, perfil.capitalizacion, fundamentos.deuda_total
        ),
        g_ref=crecimiento_ref(fundamentos, consenso),
        g_perpetuo=crecimiento_perpetuo(fundamentos.moneda, r_f),
        roe_ref=roe_referencia(fundamentos),
        payout=payout(perfil.payout),
    )

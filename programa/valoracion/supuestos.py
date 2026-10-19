"""Los supuestos de la valoración, cada uno con su procedencia.

La procedencia es **dato estructurado, no texto**
(`{"fuente": "regresion", "semanas": 104, ...}`), y la pantalla la traduce al
pintarla. Es la regla que dejó «La etiqueta de pantalla que se guardaba en
disco»: a un fichero de datos no se escribe nada cuyo valor sea una decisión de
redacción.

M no tiene forma de cambiar supuestos: en Revisar candidatos no hay
deslizadores. `aplicar` es la de N: mueve lo que el usuario pide y recalcula lo
que depende de ello, sin volver a la red.
"""

import math
from dataclasses import dataclass, fields, replace

import numpy as np

from valoracion.criterio import (
    BETA_SEMANAS_MIN,
    BLUME,
    COSTE_DEUDA_PRIMA_MAXIMA,
    CRECIMIENTO_PERPETUO,
    CRECIMIENTO_REF_ANOS,
    CRECIMIENTO_REF_TOPES,
    INDUSTRIAS_FINANCIERAS,
    MIN_ANOS_HISTORIA,
    PAYOUT_SIN_DATO,
    PRIMA_RIESGO,
    PRIMA_RIESGO_FECHA,
    TASA_EFECTIVA_TOPES,
    TASA_LEGAL,
)
from valoracion.fundamentos import Fundamentos
from valoracion.mercado import BONO_10, Beta, Perfil

# Las claves son las cadenas exactas de `info["country"]` de Yahoo; cualquier otro
# país (o ninguno) cae en «otros» y usa la tasa legal por defecto.
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
    """Cuatro decimales para la procedencia, que sólo se pinta en pantalla; la
    precisión completa vive en `valor`, que es lo que entra en las cuentas."""
    return None if valor is None or not math.isfinite(valor) else round(float(valor), 4)


def _con_motivo(procedencia: dict, clave: str, motivo: "str | None") -> dict:
    """La procedencia con el motivo de mercado añadido, si lo hay y no es «ok».

    Sin él, un dato que no llegó por la red se guardaba igual que uno que no
    existe, y la pantalla daba una causa falsa: una beta sin red se leía como
    «historial corto». Es una clave, no texto: la frase la pone la pantalla.
    """
    if isinstance(motivo, str) and motivo != "ok":
        return {**procedencia, clave: motivo}
    return procedencia


def beta_ajustada(beta: "Beta | None", motivo: "str | None" = None) -> Supuesto:
    """Blume sobre la regresión: la beta medida tiende a 1 con el tiempo.

    `motivo` es el de `mercado.beta` cuando no trajo ninguna (`sin_red`,
    `sin_regresion`). Una regresión corta sí llegó y no lleva motivo de mercado:
    lo que le faltan son semanas.
    """
    if beta is None:
        return Supuesto(1.0, _con_motivo({"fuente": "por_defecto"}, "motivo", motivo))
    if beta.semanas < BETA_SEMANAS_MIN:
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


def tasa_impositiva(
    tasa: "float | None", pais: "str | None", motivo: "str | None" = None
) -> Supuesto:
    """La tasa efectiva de la empresa si se conoce, acotada porque un año con un
    ajuste fiscal puntual da tasas negativas o absurdas; si no, la legal de su país,
    con el motivo de `mercado.tasa_efectiva` si lo hubo."""
    if tasa is not None and math.isfinite(tasa):
        return Supuesto(
            _acotar(tasa, TASA_EFECTIVA_TOPES),
            {"fuente": "efectiva", "bruta": _redondeo(tasa)},
        )
    clave = _PAISES.get(pais or "", "otros")
    return Supuesto(
        TASA_LEGAL[clave], _con_motivo({"fuente": "legal", "pais": clave}, "motivo", motivo)
    )


def coste_deuda(fundamentos: Fundamentos, r_f: float) -> Supuesto:
    """Gasto financiero entre deuda, sin bajar de la tasa libre ni subir como un bono basura."""
    deuda = fundamentos.deuda_total
    intereses = fundamentos.ultimo.gasto_financiero
    # Un gasto financiero negativo es ingreso neto por intereses (DIS, FTV), no un
    # coste de la deuda: con `abs()` se leería como un tipo de interés que no existe.
    if not deuda > 0 or not (math.isfinite(intereses) and intereses > 0):
        return Supuesto(r_f, {"fuente": "sin_dato"})
    bruto = intereses / deuda
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


def crecimiento_ref(
    fundamentos: Fundamentos, consenso: "float | None", motivo: "str | None" = None
) -> Supuesto:
    """Media de la historia de tres años y del consenso a un año.

    Ninguna de las dos sirve sola: la historia arrastra fusiones y adquisiciones
    que no se repetirán, y el consenso sólo mira un año por delante. La
    procedencia dice cuál de las dos partes hubo, porque con una sola la cifra
    vale menos y la pantalla debe poder decirlo; y, si faltó el consenso, por
    qué (`motivo_consenso`, el motivo de `mercado.consenso`). Se llama así y no
    `motivo` porque lo que explica es la ausencia de una de las dos partes, no
    la de la cifra.
    """
    historico = _cagr(fundamentos)
    hay_historia = historico is not None and math.isfinite(historico)
    hay_consenso = consenso is not None and math.isfinite(consenso)
    sin_consenso = None if hay_consenso else motivo
    partes = [v for v, hay in ((historico, hay_historia), (consenso, hay_consenso)) if hay]
    if not partes:
        return Supuesto(None, _con_motivo({"fuente": "sin_dato"}, "motivo_consenso", sin_consenso))
    bruto = sum(partes) / len(partes)
    fuente = (
        "historia_y_consenso" if hay_historia and hay_consenso
        else "historia" if hay_historia
        else "consenso"
    )
    return Supuesto(
        _acotar(bruto, CRECIMIENTO_REF_TOPES),
        _con_motivo(
            {
                "fuente": fuente,
                "historico": _redondeo(historico),
                "consenso": _redondeo(consenso),
                "bruto": _redondeo(bruto),
            },
            "motivo_consenso",
            sin_consenso,
        ),
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
    """Parte del beneficio que se reparte, acotada a [0, 1]: repartir más de lo que
    se gana o menos que nada no es una política que se pueda proyectar. Sin dato,
    el respaldo del criterio."""
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
    motivos: "dict | None" = None,
    procedencia_r_f: "dict | None" = None,
) -> Supuestos:
    """Los supuestos del programa. Siempre los mismos para los mismos datos.

    `tasa` es la tasa efectiva anual y `consenso` el crecimiento de ingresos que
    el consenso espera a un año (`+1y`); cualquiera de las dos puede ser None.

    `motivos` trae, con las claves `beta`, `tasa` y `consenso`, lo que dijo
    `mercado` de cada dato. Cuando uno falta, su procedencia guarda por qué: un
    fallo de red parcial cambia la valoración (con CF, el coste del capital
    propio pasaba del 5,9 % al 8,4 %), y sin el motivo la pantalla le daba una
    causa falsa. Es opcional para no romper a quien llama sin red.

    `procedencia_r_f` dice de dónde salió la tasa libre; por defecto, del
    Tesoro de EE. UU. a 10 años. Para una emisora en pesos es el Bono M (ver
    `analizador.divisas`).
    """
    motivos = motivos if isinstance(motivos, dict) else {}
    b = beta_ajustada(beta, motivos.get("beta"))
    k_e = r_f + b.valor * PRIMA_RIESGO
    t = tasa_impositiva(tasa, perfil.pais, motivos.get("tasa"))
    if perfil.industria in INDUSTRIAS_FINANCIERAS:
        # En un banco o una aseguradora los intereses pagados incluyen los
        # depósitos, que son su materia prima y no financiación: el cociente
        # entre intereses y deuda no es un coste de la deuda (en BAC, GS y MS
        # sale por encima del coste del capital) y el WACC no significa nada.
        # El beneficio residual sólo usa `k_e`, que sí se calcula.
        k_d = Supuesto(None, {"fuente": "financiera"})
        wacc = Supuesto(None, {"fuente": "financiera"})
    else:
        k_d = coste_deuda(fundamentos, r_f)
        wacc = coste_capital(
            k_e, k_d.valor, t.valor, perfil.capitalizacion, fundamentos.deuda_total
        )
    return Supuestos(
        r_f=Supuesto(r_f, procedencia_r_f or {"fuente": "tesoro_10", "serie": BONO_10}),
        beta=b,
        prima=Supuesto(PRIMA_RIESGO, {"fuente": "damodaran", "fecha": PRIMA_RIESGO_FECHA}),
        k_e=Supuesto(k_e, {"fuente": "capm"}),
        k_d=k_d,
        t=t,
        wacc=wacc,
        g_ref=crecimiento_ref(fundamentos, consenso, motivos.get("consenso")),
        g_perpetuo=crecimiento_perpetuo(fundamentos.moneda, r_f),
        roe_ref=roe_referencia(fundamentos),
        payout=payout(perfil.payout),
    )


# Lo que el usuario puede mover. El coste del capital propio y el de capital no
# se mueven a mano: se recalculan de lo que sí se mueve, y moverlos sueltos
# dejaría en pantalla una tasa libre, una beta y una prima que no dan el coste
# que se usó.
MOVIBLES = ("r_f", "beta", "prima", "k_d", "t", "g_ref", "g_perpetuo", "roe_ref", "payout")
_HACEN_K_E = {"r_f", "beta", "prima"}
_HACEN_WACC = _HACEN_K_E | {"k_d", "t"}


def _numero_finito(nombre: str, valor: object) -> float:
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        raise ValueError(f"{nombre}: {valor!r} no es un número") from None
    if not math.isfinite(numero):
        raise ValueError(f"{nombre}: {valor!r} no es un número finito")
    return numero


def _recalculado(supuesto: Supuesto, valor: "float | None") -> Supuesto:
    return Supuesto(valor, {**supuesto.procedencia, "recalculado": True})


def aplicar(supuestos: Supuestos, cambios: dict) -> Supuestos:
    """Los supuestos con lo que el usuario movió, y lo que depende de ello recalculado.

    Lo movido lleva `{"fuente": "usuario", "programa": <lo que decía el
    programa>}`; lo recalculado conserva su fuente y gana `"recalculado": True`,
    para que la pantalla diga las dos cosas. **Lo movido no se guarda en ningún
    sitio**: lo que va al acta es siempre la valoración con los supuestos del
    programa, comparable entre actas.

    El coste de capital se recalcula con el peso de la deuda de su procedencia,
    que va redondeado a cuatro decimales: el error que eso mete es de
    diezmilésimas de punto. Un coste de la deuda «sin dato» es la tasa libre por
    definición, así que la sigue; uno medido, no.
    """
    if not cambios:
        return supuestos
    desconocidos = sorted(set(cambios) - set(MOVIBLES))
    if desconocidos:
        raise ValueError(f"No se pueden mover a mano: {', '.join(desconocidos)}")
    nuevos = {
        nombre: Supuesto(
            _numero_finito(nombre, valor),
            {"fuente": "usuario", "programa": getattr(supuestos, nombre).valor},
        )
        for nombre, valor in cambios.items()
    }
    s = replace(supuestos, **nuevos)
    if (
        "r_f" in cambios
        and "k_d" not in cambios
        and s.k_d.procedencia.get("fuente") == "sin_dato"
    ):
        s = replace(s, k_d=_recalculado(s.k_d, s.r_f.valor))
    if _HACEN_K_E & set(cambios):
        s = replace(s, k_e=_recalculado(s.k_e, s.r_f.valor + s.beta.valor * s.prima.valor))
    if _HACEN_WACC & set(cambios) and s.wacc.valor is not None:
        peso = s.wacc.procedencia.get("peso_deuda") or 0.0
        wacc = (1 - peso) * s.k_e.valor + peso * s.k_d.valor * (1 - s.t.valor)
        s = replace(s, wacc=_recalculado(s.wacc, wacc))
    return s


def movidos(supuestos: Supuestos) -> "tuple[str, ...]":
    """Los supuestos que movió el usuario, en el orden de `Supuestos`."""
    return tuple(
        campo.name
        for campo in fields(supuestos)
        if getattr(supuestos, campo.name).procedencia.get("fuente") == "usuario"
    )

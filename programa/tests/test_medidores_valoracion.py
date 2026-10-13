import ast
import copy
import html
import re
from datetime import date
from pathlib import Path

import pytest

import medidores
import medidores_valoracion as mv
import tema
from valoracion import criterio
from valoracion.mercado import Beta
from valoracion.motor import calcular
from valoracion.plano import a_dict, fallida
from valoracion.supuestos import deducir
from valoracion.votos import MOTIVOS, VEREDICTOS

from tests.dobles_valoracion import ejercicio, fundamentos, perfil
from tests.test_tema import contraste


def _valoracion(f=None, p=None, pilar=0.8) -> dict:
    f, p = f or fundamentos(), p or perfil()
    s = deducir(f, p, r_f=0.04, beta=None, tasa=0.25, consenso=None)
    return a_dict(calcular(f, p, s, pilar, date(2026, 10, 12)))


def _texto(salida: str) -> str:
    """Lo que se lee en pantalla: sin etiquetas, los spans de una fila separados por « | »."""
    salida = re.sub(r"</span>(?=<span)", " | ", salida)
    salida = salida.replace("</div>", "\n")
    return html.unescape(re.sub(r"<[^>]+>", "", salida)).strip()


def _lineas(salida: str) -> "list[str]":
    return _texto(salida).split("\n")


# --- Una valoración escrita a mano, para fijar el texto exacto ----------------


def _supuestos_fijos() -> dict:
    return {
        "r_f": {"valor": 0.0522, "procedencia": {"fuente": "tesoro_10", "serie": "^TNX"}},
        "beta": {
            "valor": 1.9976,
            "procedencia": {"fuente": "regresion", "indice": "^GSPC", "semanas": 104, "r2": 0.29, "bruta": 2.489},
        },
        "prima": {"valor": 0.042, "procedencia": {"fuente": "damodaran", "fecha": "2026-10-01"}},
        "k_e": {"valor": 0.136, "procedencia": {"fuente": "capm"}},
        "k_d": {"valor": 0.0522, "procedencia": {"fuente": "gasto_entre_deuda", "bruto": 0.0226}},
        "t": {"valor": 0.116, "procedencia": {"fuente": "efectiva", "bruta": 0.116}},
        "wacc": {"valor": 0.1357, "procedencia": {"fuente": "wacc", "peso_deuda": 0.0043, "deuda_declarada": True}},
        "g_ref": {
            "valor": 0.4,
            "procedencia": {"fuente": "historia_y_consenso", "historico": 1.0465, "consenso": 0.1573, "bruto": 0.6019},
        },
        "g_perpetuo": {"valor": 0.025, "procedencia": {"fuente": "criterio", "moneda": "USD"}},
        "roe_ref": {"valor": 0.1576, "procedencia": {"fuente": "mediana_historica", "anos": 5}},
        "payout": {"valor": 0.0071, "procedencia": {"fuente": "yfinance"}},
    }


def _fija(**cambios) -> dict:
    """Una valoración de flujos con cifras redondas, sin pasar por el motor."""
    base = {
        "version": "m1",
        "fecha": "2026-10-12",
        "estados_hasta": "2026-09-30",
        "moneda": "USD",
        "precio": 100.0,
        "precio_hora": "2026-10-12T19:59:00+00:00",
        "metodo": "flujos",
        "valor": {"pesimista": 80.5, "base": 1234.5, "optimista": 4321.0},
        "margen_seguridad": 0.2031,
        "implicito": {
            "magnitud": "crecimiento",
            "valor": 0.274,
            "referencia": 0.4,
            "margen": 0.2,
            "fuera_de_limites": None,
        },
        "epv": {"por_accion": 392.27, "parte_crecimiento": 0.5884},
        "votos": {
            "flujos": {"voto": "neutra", "motivo": None},
            "sin_crecimiento": {"voto": "neutra", "motivo": None},
            "pares": {"voto": "barata", "motivo": None},
        },
        "veredicto": "en_rango",
        "supuestos": _supuestos_fijos(),
    }
    return {**base, **cambios}


def _fija_residual(**cambios) -> dict:
    supuestos = _supuestos_fijos()
    supuestos["k_d"] = {"valor": None, "procedencia": {"fuente": "financiera"}}
    supuestos["wacc"] = {"valor": None, "procedencia": {"fuente": "financiera"}}
    de_un_banco = dict(
        metodo="residual",
        implicito={"magnitud": "roe", "valor": 0.1497, "referencia": 0.1584, "margen": 0.0792, "fuera_de_limites": None},
        epv=None,
        votos={
            "flujos": {"voto": "neutra", "motivo": None},
            "sin_crecimiento": {"voto": "no_aplica", "motivo": "financiera"},
            "pares": {"voto": "neutra", "motivo": None},
        },
        supuestos=supuestos,
    )
    return _fija(**{**de_un_banco, **cambios})


def _fila(valoracion: dict, clave: str) -> "tuple[str, str, str]":
    """(nombre, etiqueta, detalle) de la fila de un voto, tal como se lee."""
    orden = {"flujos": 1, "sin_crecimiento": 2, "pares": 3}[clave]
    nombre, etiqueta, detalle = _lineas(mv.resumen(valoracion))[orden].split(" | ")
    return nombre, etiqueta, detalle


def _detalle(valoracion: dict, clave: str) -> str:
    return _fila(valoracion, clave)[2]


# --- Las etiquetas ------------------------------------------------------------


def test_cada_veredicto_tiene_etiqueta():
    assert set(mv.VEREDICTO) == set(VEREDICTOS)


def test_cada_motivo_tiene_etiqueta():
    assert MOTIVOS <= set(mv.MOTIVO)


def test_no_hay_mas_motivos_que_los_que_escribe_el_paquete():
    # Una etiqueta de más es un texto que nadie puede ver y que se queda sin revisar.
    assert set(mv.MOTIVO) == MOTIVOS


@pytest.mark.parametrize("clave", sorted(mv.MOTIVO))
def test_ninguna_etiqueta_de_motivo_dice_no_aplica_ni_no_se_pudo(clave):
    # Junto a ella ya va el «No aplica» de la fila de un voto, o el «Sin
    # valoración:» de una fallida: repetirlo lee como un tartamudeo.
    etiqueta = mv.etiqueta_motivo(clave).lower()
    assert "no aplica" not in etiqueta
    assert "no se pudo" not in etiqueta


@pytest.mark.parametrize(
    ("clave", "idea"),
    [
        ("quema_caja", "quema caja"),
        ("ebit_negativo", "beneficio operativo negativo"),
        ("sin_historia", "años de historia"),
        ("wacc_bajo_crecimiento", "valor terminal explotaría"),
        ("sin_pares", "pares del sector"),
        ("sin_precio", "el precio"),
        ("sin_tasa_libre", "tasa libre de riesgo"),
        ("financiera", "beneficio residual"),
        ("patrimonio_negativo", "patrimonio negativo"),
        ("sin_beneficio_operativo", "beneficio operativo"),
        ("sin_flujo_libre", "flujo libre"),
        ("sin_red", "Yahoo Finance no devolvió datos"),
        ("sin_estados", "estados financieros de la SEC"),
        ("error_interno", "error interno"),
    ],
)
def test_cada_motivo_dice_de_que_se_trata(clave, idea):
    # No fija la redacción, sólo que la etiqueta habla de lo que debe.
    assert idea in mv.etiqueta_motivo(clave)


# Los motivos con los que puede terminar una valoración fallida: los de la red y
# los estados (`valorar`) y el que anota `ranking/run.py` cuando algo revienta.
_MOTIVOS_DE_UNA_FALLIDA = (
    "sin_red", "sin_precio", "sin_tasa_libre", "sin_estados", "sin_historia", "error_interno",
)


def test_las_fallidas_de_la_lista_existen():
    assert set(_MOTIVOS_DE_UNA_FALLIDA) <= MOTIVOS


@pytest.mark.parametrize("motivo", _MOTIVOS_DE_UNA_FALLIDA)
def test_una_fallida_lleva_un_solo_dos_puntos(motivo):
    texto = _texto(mv.resumen(fallida(motivo)))
    assert texto.startswith("Sin valoración: ")
    assert texto.count(":") == 1
    assert texto.endswith(".")


def test_la_fallida_de_la_red_se_lee_sin_dobles_dos_puntos():
    assert _texto(mv.resumen(fallida("sin_red"))) == (
        "Sin valoración: Yahoo Finance no devolvió datos "
        "(sin conexión, un error suyo o un símbolo que no conoce)."
    )


def test_el_motivo_de_una_financiera_habla_de_entidades_financieras():
    etiqueta = mv.etiqueta_motivo("financiera")
    assert "beneficio residual" in etiqueta
    assert "entidades financieras" in etiqueta
    assert "bancos y aseguradoras" not in etiqueta


def test_la_nota_es_la_del_spec():
    assert mv.NOTA == (
        "Un criterio transparente, no una previsión: no hay forma honesta de probar hacia atrás "
        "si acierta, porque las cifras de yfinance no dicen cuándo se publicaron y el universo "
        "arrastra sesgo de supervivencia."
    )


def test_la_lectura_del_margen_explica_por_que_un_margen_grande_puede_ser_en_rango():
    assert "El margen de seguridad mide la distancia al valor base. El voto de flujos no lo usa:" in mv.LECTURA_MARGEN
    assert "con una banda de ± la mitad de esa referencia" in mv.LECTURA_MARGEN
    assert "un margen grande puede convivir con «en rango»" in mv.LECTURA_MARGEN
    assert mv.LECTURA_MARGEN.endswith("cuando el crecimiento de referencia es alto.")


# Los colores que nombra el spec: verde para infravalorada, rojo para
# sobrevalorada, ámbar para mixtas y gris para en rango o sin datos.
@pytest.mark.parametrize(
    ("clave", "color"),
    [
        ("infravalorada", tema.VERDE),
        ("sobrevalorada", tema.ROJO),
        ("mixtas", tema.AMBAR),
        ("en_rango", tema.TEXTO_SUAVE),
        ("sin_datos", tema.TEXTO_SUAVE),
    ],
)
def test_el_color_de_cada_veredicto(clave, color):
    assert f'style="color:{color}"' in mv.distintivo({"veredicto": clave})


@pytest.mark.parametrize(
    ("clave", "etiqueta"),
    [
        ("infravalorada", "Infravalorada"),
        ("sobrevalorada", "Sobrevalorada"),
        ("mixtas", "Señales mixtas"),
        ("en_rango", "En rango"),
        ("sin_datos", "Sin datos suficientes"),
    ],
)
def test_el_distintivo_es_una_pildora_con_su_etiqueta(clave, etiqueta):
    assert mv.distintivo({"veredicto": clave}).endswith(f">{etiqueta}</span>")
    assert mv.distintivo({"veredicto": clave}).startswith('<span class="mpp-veredicto"')


@pytest.mark.parametrize(
    ("voto", "etiqueta", "color"),
    [
        ("barata", "Barata", tema.VERDE),
        ("neutra", "Neutra", tema.TEXTO_SUAVE),
        ("cara", "Cara", tema.ROJO),
        ("no_aplica", "No aplica", tema.TEXTO_SUAVE),
    ],
)
def test_el_color_y_la_etiqueta_de_cada_voto(voto, etiqueta, color):
    votos = {**_fija()["votos"], "flujos": {"voto": voto, "motivo": "sin_pares"}}
    salida = mv.resumen(_fija(votos=votos))
    assert f'<span class="mpp-val-etiqueta" style="color:{color}">{etiqueta}</span>' in salida


@pytest.mark.parametrize("clave", VEREDICTOS)
def test_el_distintivo_dice_el_veredicto(clave):
    assert mv.VEREDICTO[clave][0] in mv.distintivo({"version": "m1", "veredicto": clave})


@pytest.mark.parametrize(
    "valor",
    [
        None,
        fallida("sin_precio"),
        {"version": "m1", "veredicto": "otra"},
        {"veredicto": ["infravalorada"]},
        {"veredicto": {"a": 1}},
        {"veredicto": 3},
        "infravalorada",
        ["veredicto"],
    ],
)
def test_sin_valoracion_reconocible_no_hay_distintivo(valor):
    assert mv.distintivo(valor) == ""


# --- La cabecera ----------------------------------------------------------------


def test_la_cabecera_completa():
    assert _lineas(mv.resumen(_fija()))[0] == (
        "En rango | Valor por acción: pesimista 80.50 USD · base 1,234.50 USD · "
        "optimista 4,321.00 USD · margen de seguridad 20.3% | "
        "Calculada el 2026-10-12 con el precio de 100.00 USD "
        "(cotización del 2026-10-12 19:59 UTC) y estados hasta 2026-09-30"
    )


def test_un_margen_negativo_lleva_el_signo_menos():
    assert "margen de seguridad −44.4%" in mv.resumen(_fija(margen_seguridad=-0.4444))


@pytest.mark.parametrize(
    ("hora", "esperada"),
    [
        ("2026-10-12T19:59:00+00:00", "(cotización del 2026-10-12 19:59 UTC)"),
        ("2026-10-12T19:59:00Z", "(cotización del 2026-10-12 19:59 UTC)"),
        # Una hora con otra zona se pasa a UTC, que es lo que dice la etiqueta.
        ("2026-10-12T15:59:00-04:00", "(cotización del 2026-10-12 19:59 UTC)"),
        ("2026-10-13T01:30:00+02:00", "(cotización del 2026-10-12 23:30 UTC)"),
    ],
)
def test_la_cabecera_dice_de_cuando_es_el_precio(hora, esperada):
    assert esperada in _lineas(mv.resumen(_fija(precio_hora=hora)))[0]


@pytest.mark.parametrize(
    "hora",
    [None, "", "no es una hora", "2026-10-12T19:59:00", 20261012, ["2026-10-12T19:59:00+00:00"]],
    ids=["None", "vacia", "ilegible", "sin_zona", "numero", "lista"],
)
def test_sin_hora_legible_la_cabecera_no_inventa_el_parentesis(hora):
    cabecera = _lineas(mv.resumen(_fija(precio_hora=hora)))[0]
    assert "cotización" not in cabecera
    assert cabecera.endswith("con el precio de 100.00 USD y estados hasta 2026-09-30")


def test_sin_la_clave_de_la_hora_tampoco_hay_parentesis():
    valoracion = _fija()
    del valoracion["precio_hora"]
    assert "cotización" not in mv.resumen(valoracion)


def test_sin_rango_la_cabecera_lo_dice():
    assert _lineas(mv.resumen(_fija(valor=None)))[0].startswith(
        "En rango | Sin rango de valor. | Calculada el 2026-10-12 "
    )


def test_a_una_ficha_a_la_que_le_faltan_las_fechas_y_la_moneda_no_se_le_inventa_nada():
    valoracion = _fija()
    for clave in ("fecha", "estados_hasta", "moneda", "precio_hora"):
        del valoracion[clave]
    assert _lineas(mv.resumen(valoracion))[0] == (
        "En rango | Valor por acción: pesimista 80.50 · base 1,234.50 · optimista 4,321.00 · "
        "margen de seguridad 20.3% | Calculada el n/d con el precio de 100.00 y estados hasta n/d"
    )
    assert _detalle(valoracion, "sin_crecimiento") == (
        "sin crecer valdría 392.27; el 58.8% del precio es apuesta por el crecimiento"
    )


@pytest.mark.parametrize("moneda", [None, ["USD"], 840])
def test_una_moneda_que_no_es_texto_se_descarta(moneda):
    assert "con el precio de 100.00 y estados hasta" in mv.resumen(_fija(moneda=moneda, precio_hora=None))


# --- Las filas de los votos -----------------------------------------------------


def test_el_resumen_nombra_los_tres_votos():
    salida = mv.resumen(_valoracion())
    for nombre in mv.NOMBRE_VOTO.values():
        assert nombre in salida
    assert "estados hasta 2026-09-30" in salida


def test_los_tres_votos_van_en_su_orden():
    nombres = [_fila(_fija(), clave)[0] for clave in ("flujos", "sin_crecimiento", "pares")]
    assert nombres == ["Flujos (DCF e inverso)", "Sin crecimiento (EPV)", "Frente a sus pares"]


def test_el_resumen_de_un_banco_llama_beneficio_residual_a_los_flujos():
    p = perfil(industria="Banks - Regional")
    salida = mv.resumen(_valoracion(p=p))
    assert "Beneficio residual" in salida
    assert "Flujos (DCF e inverso)" not in salida
    assert mv.MOTIVO["financiera"] in salida


def test_una_empresa_con_flujos_no_se_llama_beneficio_residual():
    assert "Beneficio residual" not in mv.resumen(_fija())


def test_quemar_caja_se_explica_y_no_se_pone_a_cero():
    f = fundamentos(ejercicios=[ejercicio(2026 - i, flujo_operativo=50.0) for i in range(4)])
    salida = mv.resumen(_valoracion(f=f))
    assert mv.MOTIVO["quema_caja"] in salida


def test_un_voto_que_no_aplica_dice_por_que():
    votos = {**_fija()["votos"], "pares": {"voto": "no_aplica", "motivo": "sin_pares"}}
    assert _fila(_fija(votos=votos), "pares") == ("Frente a sus pares", "No aplica", mv.MOTIVO["sin_pares"])


# Flujos, crecimiento: el precio da por hecho un crecimiento (o una caída) y se
# compara con la referencia.
@pytest.mark.parametrize(
    ("implicito", "esperado"),
    [
        (
            {"valor": 0.274, "referencia": 0.4, "margen": 0.2, "fuera_de_limites": None},
            "el precio da por hecho que los ingresos crecerán un 27.4% al año durante 5 años; "
            "su referencia es 40.0% (banda de ±20.0 puntos)",
        ),
        (
            {"valor": 0.0, "referencia": 0.05, "margen": 0.05, "fuera_de_limites": None},
            "el precio da por hecho que los ingresos crecerán un 0.0% al año durante 5 años; "
            "su referencia es 5.0% (banda de ±5.0 puntos)",
        ),
        (
            {"valor": -0.052, "referencia": 0.021, "margen": 0.05, "fuera_de_limites": None},
            "el precio da por hecho que los ingresos caerán un 5.2% al año durante 5 años; "
            "su referencia es 2.1% (banda de ±5.0 puntos)",
        ),
        (
            {"valor": 0.02, "referencia": -0.043, "margen": 0.05, "fuera_de_limites": None},
            "el precio da por hecho que los ingresos crecerán un 2.0% al año durante 5 años; "
            "su referencia es una caída del 4.3% (banda de ±5.0 puntos)",
        ),
        (
            {"valor": -0.1, "referencia": -0.04, "margen": 0.05, "fuera_de_limites": None},
            "el precio da por hecho que los ingresos caerán un 10.0% al año durante 5 años; "
            "su referencia es una caída del 4.0% (banda de ±5.0 puntos)",
        ),
        (
            {"valor": 0.8, "referencia": 0.4, "margen": 0.2, "fuera_de_limites": "arriba"},
            "el precio da por hecho un crecimiento de más del 80.0% al año",
        ),
        (
            {"valor": -0.3, "referencia": 0.04, "margen": 0.05, "fuera_de_limites": "abajo"},
            "el precio es tan bajo que ni una caída del 30.0% al año lo explicaría",
        ),
        (
            {"valor": None, "referencia": 0.04, "margen": 0.05, "fuera_de_limites": None},
            "n/d",
        ),
        (
            # Una referencia de cero no es una caída.
            {"valor": 0.02, "referencia": 0.0, "margen": 0.05, "fuera_de_limites": None},
            "el precio da por hecho que los ingresos crecerán un 2.0% al año durante 5 años; "
            "su referencia es 0.0% (banda de ±5.0 puntos)",
        ),
        (
            {"valor": 0.02, "referencia": None, "margen": None, "fuera_de_limites": None},
            "el precio da por hecho que los ingresos crecerán un 2.0% al año durante 5 años; "
            "su referencia es n/d (banda de ±n/d)",
        ),
    ],
    ids=[
        "crece", "cero", "cae", "referencia_negativa", "cae_con_referencia_negativa",
        "arriba", "abajo", "sin_valor", "referencia_cero", "sin_referencia_ni_banda",
    ],
)
def test_el_texto_de_la_lectura_de_crecimiento(implicito, esperado):
    valoracion = _fija(implicito={"magnitud": "crecimiento", **implicito})
    assert _detalle(valoracion, "flujos") == esperado


@pytest.mark.parametrize(
    ("implicito", "esperado"),
    [
        (
            {"valor": 0.1497, "referencia": 0.1584, "margen": 0.0792, "fuera_de_limites": None},
            "el precio exige un ROE del 15.0%; su referencia es 15.8% (banda de ±7.9 puntos)",
        ),
        (
            # Un ROE de referencia negativo es una rentabilidad negativa, no una caída.
            {"valor": 0.05, "referencia": -0.04, "margen": 0.03, "fuera_de_limites": None},
            "el precio exige un ROE del 5.0%; su referencia es −4.0% (banda de ±3.0 puntos)",
        ),
        (
            {"valor": 0.6, "referencia": 0.15, "margen": 0.075, "fuera_de_limites": "arriba"},
            "el precio exige un ROE de más del 60.0%",
        ),
        (
            {"valor": -0.2, "referencia": 0.15, "margen": 0.075, "fuera_de_limites": "abajo"},
            "el precio es tan bajo que ni un ROE del −20.0% lo explicaría",
        ),
    ],
    ids=["normal", "referencia_negativa", "arriba", "abajo"],
)
def test_el_texto_de_la_lectura_de_roe(implicito, esperado):
    valoracion = _fija_residual(implicito={"magnitud": "roe", **implicito})
    assert _detalle(valoracion, "flujos") == esperado


@pytest.mark.parametrize(
    ("epv", "esperado"),
    [
        (
            {"por_accion": 392.27, "parte_crecimiento": 0.5884},
            "sin crecer valdría 392.27 USD; el 58.8% del precio es apuesta por el crecimiento",
        ),
        ({"por_accion": 392.27, "parte_crecimiento": 0.0}, "sin crecer valdría 392.27 USD"),
        # Un EPV por encima del precio da una parte negativa: no hay apuesta que contar.
        ({"por_accion": 1200.0, "parte_crecimiento": -0.3}, "sin crecer valdría 1,200.00 USD"),
        ({"por_accion": 392.27, "parte_crecimiento": None}, "sin crecer valdría 392.27 USD"),
        ({"por_accion": None, "parte_crecimiento": None}, "sin crecer valdría n/d"),
    ],
    ids=["con_apuesta", "cero", "negativa", "sin_parte", "sin_epv"],
)
def test_el_texto_del_valor_sin_crecimiento(epv, esperado):
    assert _detalle(_fija(epv=epv), "sin_crecimiento") == esperado


@pytest.mark.parametrize(
    ("voto", "esperado"),
    [
        ("barata", "múltiplos por debajo de los de su sector"),
        ("neutra", "múltiplos en línea con los de su sector"),
        ("cara", "múltiplos por encima de los de su sector"),
    ],
)
def test_el_texto_de_los_pares(voto, esperado):
    votos = {**_fija()["votos"], "pares": {"voto": voto, "motivo": None}}
    assert _detalle(_fija(votos=votos), "pares") == esperado


# --- Los supuestos ----------------------------------------------------------------


def test_el_resumen_completo_de_una_empresa():
    assert _texto(mv.resumen(_fija())) == "\n".join(
        [
            "En rango | Valor por acción: pesimista 80.50 USD · base 1,234.50 USD · "
            "optimista 4,321.00 USD · margen de seguridad 20.3% | "
            "Calculada el 2026-10-12 con el precio de 100.00 USD "
            "(cotización del 2026-10-12 19:59 UTC) y estados hasta 2026-09-30",
            "Flujos (DCF e inverso) | Neutra | el precio da por hecho que los ingresos crecerán "
            "un 27.4% al año durante 5 años; su referencia es 40.0% (banda de ±20.0 puntos)",
            "Sin crecimiento (EPV) | Neutra | sin crecer valdría 392.27 USD; el 58.8% del "
            "precio es apuesta por el crecimiento",
            "Frente a sus pares | Barata | múltiplos por debajo de los de su sector",
            "Supuestos del programa",
            "tasa libre: 5.2% · Tesoro de EE. UU. a 10 años (^TNX)",
            "beta: 2.00 · regresión semanal de 104 semanas contra ^GSPC (R² 0.29), con el ajuste de Blume",
            "prima de riesgo: 4.2% · Damodaran, prima implícita a 2026-10-01",
            "coste del capital propio: 13.6% · tasa libre más beta por prima",
            "coste de la deuda: 5.2% · gasto financiero entre deuda, acotado entre la tasa libre "
            "y esa tasa más 8.0 puntos",
            "impuestos: 11.6% · tasa efectiva de yfinance, acotada entre 0.0% y 35.0%",
            "coste de capital (deuda y capital propio): 13.6% · deuda 0.4% del capital",
            "crecimiento de referencia: 40.0% · media del crecimiento histórico de los ingresos "
            "(104.7%) y del consenso del próximo año (15.7%), acotada entre −10.0% y 40.0%",
            "crecimiento a perpetuidad: 2.5% · criterio fijo del programa para el USD",
        ]
    )


def test_el_resumen_completo_de_un_banco():
    assert _texto(mv.resumen(_fija_residual())) == "\n".join(
        [
            "En rango | Valor por acción: pesimista 80.50 USD · base 1,234.50 USD · "
            "optimista 4,321.00 USD · margen de seguridad 20.3% | "
            "Calculada el 2026-10-12 con el precio de 100.00 USD "
            "(cotización del 2026-10-12 19:59 UTC) y estados hasta 2026-09-30",
            "Beneficio residual | Neutra | el precio exige un ROE del 15.0%; su referencia es "
            "15.8% (banda de ±7.9 puntos)",
            "Sin crecimiento (EPV) | No aplica | se valora por beneficio residual (entidades financieras)",
            "Frente a sus pares | Neutra | múltiplos en línea con los de su sector",
            "Supuestos del programa",
            "tasa libre: 5.2% · Tesoro de EE. UU. a 10 años (^TNX)",
            "beta: 2.00 · regresión semanal de 104 semanas contra ^GSPC (R² 0.29), con el ajuste de Blume",
            "prima de riesgo: 4.2% · Damodaran, prima implícita a 2026-10-01",
            "coste del capital propio: 13.6% · tasa libre más beta por prima",
            "ROE de referencia: 15.8% · mediana de 5 años",
            "reparto de beneficios: 0.7% · según yfinance, acotado entre 0.0% y 100.0%",
            "crecimiento a perpetuidad: 2.5% · criterio fijo del programa para el USD",
        ]
    )


def test_los_supuestos_van_uno_por_linea_en_su_propio_bloque():
    salida = mv.resumen(_fija())
    bloque = salida[salida.index('<div class="mpp-val-sup">') :]
    assert bloque.count("<div>") == 9
    assert bloque.count('<div class="mpp-val-sup-titulo">') == 1


def test_un_banco_no_enseña_los_supuestos_que_no_usa():
    salida = mv.resumen(_valoracion(p=perfil(industria="Banks - Regional")))
    for sobra in ("coste de la deuda", "coste de capital (", "impuestos", "crecimiento de referencia"):
        assert sobra not in salida
    for falta in ("ROE de referencia", "reparto de beneficios", "coste del capital propio"):
        assert falta in salida


def test_una_industrial_no_enseña_el_roe_ni_el_reparto():
    salida = mv.resumen(_valoracion())
    for sobra in ("ROE de referencia", "reparto de beneficios"):
        assert sobra not in salida
    assert "coste de capital (deuda y capital propio)" in salida


def test_un_banco_con_coste_de_capital_nulo_no_enseña_n_d_de_lo_que_no_usa():
    salida = mv.resumen(_valoracion(p=perfil(industria="Banks - Regional")))
    assert "n/d" not in _texto(salida).split("Supuestos del programa")[1]


def test_los_supuestos_van_en_el_gris_del_tema():
    regla = re.search(r"\.mpp-val-sup \{[^}]*\}", mv.CSS).group(0)
    assert f"color:{tema.TEXTO_SUAVE}" in regla


def test_un_supuesto_que_falta_en_la_ficha_se_salta():
    supuestos = _supuestos_fijos()
    del supuestos["prima"]
    texto = _texto(mv.resumen(_fija(supuestos=supuestos)))
    assert "prima de riesgo" not in texto
    assert "tasa libre: 5.2%" in texto


def test_sin_supuestos_no_hay_bloque():
    salida = mv.resumen(_fija(supuestos={}))
    assert "mpp-val-sup" not in salida
    assert len(_lineas(salida)) == 4
    assert salida.endswith("múltiplos por debajo de los de su sector</span></div></div>")


def test_un_supuesto_sin_fuente_conocida_se_enseña_sin_origen():
    supuestos = {"r_f": {"valor": 0.0522, "procedencia": {"fuente": "otra"}}}
    assert _lineas(mv.resumen(_fija(supuestos=supuestos)))[-1] == "tasa libre: 5.2%"


def test_a_la_deuda_se_le_supone_declarada_si_la_ficha_no_dice_otra_cosa():
    assert mv.procedencia("wacc", {"procedencia": {"fuente": "wacc", "peso_deuda": 0.1}}) == "deuda 10.0% del capital"


def test_hasta_las_etiquetas_de_los_veredictos_y_los_votos_se_escapan(monkeypatch):
    monkeypatch.setitem(mv.VEREDICTO, "en_rango", ("<b>rango</b>", tema.TEXTO_SUAVE))
    monkeypatch.setitem(mv.VOTO, "barata", ("<i>barata</i>", tema.VERDE))
    salida = mv.resumen(_fija())
    assert "<b>" not in salida and "<i>" not in salida
    assert "&lt;b&gt;rango&lt;/b&gt;" in salida
    assert "&lt;i&gt;barata&lt;/i&gt;" in salida


# --- La procedencia -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("nombre", "procedencia", "esperado"),
    [
        ("r_f", {"fuente": "tesoro_10", "serie": "^TNX"}, "Tesoro de EE. UU. a 10 años (^TNX)"),
        (
            "beta",
            {"fuente": "regresion", "indice": "^GSPC", "semanas": 104, "r2": 0.4123},
            "regresión semanal de 104 semanas contra ^GSPC (R² 0.41), con el ajuste de Blume",
        ),
        (
            "beta",
            {"fuente": "regresion", "indice": "^GSPC", "semanas": 104, "r2": 0.4},
            "regresión semanal de 104 semanas contra ^GSPC (R² 0.40), con el ajuste de Blume",
        ),
        (
            "beta",
            {"fuente": "por_defecto"},
            "1.0 por defecto: no hubo regresión posible (historial corto o precios inválidos)",
        ),
        ("prima", {"fuente": "damodaran", "fecha": "2026-10-01"}, "Damodaran, prima implícita a 2026-10-01"),
        ("k_e", {"fuente": "capm"}, "tasa libre más beta por prima"),
        (
            "k_d",
            {"fuente": "gasto_entre_deuda", "bruto": 0.0226},
            "gasto financiero entre deuda, acotado entre la tasa libre y esa tasa más 8.0 puntos",
        ),
        ("k_d", {"fuente": "sin_dato"}, "sin deuda o sin gasto financiero declarado: la tasa libre"),
        (
            "k_d",
            {"fuente": "financiera"},
            "en un banco o una aseguradora los intereses incluyen los depósitos: no se calcula",
        ),
        ("t", {"fuente": "efectiva", "bruta": 0.116}, "tasa efectiva de yfinance, acotada entre 0.0% y 35.0%"),
        ("t", {"fuente": "legal", "pais": "MX"}, "tasa legal (MX)"),
        (
            "wacc",
            {"fuente": "financiera"},
            "en un banco o una aseguradora no se calcula: se valora con el coste del capital propio",
        ),
        ("wacc", {"fuente": "wacc", "peso_deuda": 0.0925, "deuda_declarada": True}, "deuda 9.2% del capital"),
        (
            "wacc",
            {"fuente": "wacc", "peso_deuda": 0.0, "deuda_declarada": False},
            "deuda 0.0% del capital; sin deuda declarada",
        ),
        (
            "g_ref",
            {"fuente": "historia_y_consenso", "historico": 0.042, "consenso": 0.001},
            "media del crecimiento histórico de los ingresos (4.2%) y del consenso del próximo año (0.1%), "
            "acotada entre −10.0% y 40.0%",
        ),
        (
            "g_ref",
            {"fuente": "historia", "historico": 0.042, "consenso": None},
            "crecimiento histórico de los ingresos (4.2%), sin consenso, acotado entre −10.0% y 40.0%",
        ),
        (
            "g_ref",
            {"fuente": "consenso", "historico": None, "consenso": 0.0311},
            "consenso del próximo año (3.1%), sin historia, acotado entre −10.0% y 40.0%",
        ),
        ("g_ref", {"fuente": "sin_dato"}, "sin historia ni consenso"),
        (
            "g_perpetuo",
            {"fuente": "criterio", "moneda": "MXN"},
            "criterio fijo del programa para el MXN",
        ),
        ("g_perpetuo", {"fuente": "recortado_a_r_f", "base": 0.025}, "recortado a la tasa libre de riesgo"),
        ("roe_ref", {"fuente": "mediana_historica", "anos": 5}, "mediana de 5 años"),
        ("roe_ref", {"fuente": "sin_dato"}, "sin años suficientes"),
        ("payout", {"fuente": "yfinance"}, "según yfinance, acotado entre 0.0% y 100.0%"),
        ("payout", {"fuente": "por_defecto"}, "sin dato: se supone el 50.0%"),
    ],
)
def test_el_texto_de_cada_procedencia(nombre, procedencia, esperado):
    assert mv.procedencia(nombre, {"valor": 0.1, "procedencia": procedencia}) == esperado


def test_una_procedencia_desconocida_no_revienta():
    assert mv.procedencia("beta", {"valor": 1.0, "procedencia": {"fuente": "otra"}}) == ""


@pytest.mark.parametrize(
    "supuesto",
    [None, "x", [], {"valor": 1.0}, {"procedencia": None}, {"procedencia": "x"}, {"procedencia": {"fuente": ["capm"]}}],
)
def test_una_procedencia_rota_da_vacio(supuesto):
    assert mv.procedencia("k_e", supuesto) == ""


def test_la_beta_dice_de_donde_sale():
    texto = mv.procedencia(
        "beta",
        {"valor": 1.33, "procedencia": {"fuente": "regresion", "indice": "^GSPC", "semanas": 104, "r2": 0.41}},
    )
    assert "104 semanas" in texto and "^GSPC" in texto and "Blume" in texto


def test_el_r2_de_una_beta_rota_es_n_d():
    texto = mv.procedencia(
        "beta", {"valor": 1.0, "procedencia": {"fuente": "regresion", "indice": "^GSPC", "semanas": 104, "r2": "x"}}
    )
    assert "(R² n/d)" in texto


def _sin_historia():
    """Un solo ejercicio: no hay CAGR, así que el crecimiento sólo puede venir del consenso."""
    return fundamentos(ejercicios=[ejercicio(2026)])


_BETA = Beta(bruta=1.4, r2=0.41, semanas=104, indice="^GSPC")

# Cada caso fabrica supuestos reales con `deducir`, no a mano: si el paquete
# empieza a escribir una fuente nueva, este test falla en vez de dejar que la
# pantalla muestre un supuesto sin explicar. Cada caso lleva su propio perfil
# porque un banco valorado con un perfil de industrial no es una valoración real.
_CASOS_DE_SUPUESTOS = {
    "empresa normal": (fundamentos(), perfil(), dict(tasa=0.25, consenso=0.08)),
    "sin tasa efectiva ni payout": (
        fundamentos(), perfil(payout=None, pais="Mexico"), dict(tasa=None, consenso=None)
    ),
    "sin deuda": (fundamentos(deuda_total=0.0), perfil(), dict(tasa=0.25, consenso=0.08)),
    "banco": (fundamentos(), perfil(industria="Banks - Regional"), dict(tasa=0.25, consenso=0.08)),
    "sólo consenso": (_sin_historia(), perfil(), dict(tasa=0.25, consenso=0.08)),
    "sólo historia": (fundamentos(), perfil(), dict(tasa=0.25, consenso=None)),
    "ni historia ni consenso": (_sin_historia(), perfil(), dict(tasa=0.25, consenso=None)),
    "con regresión de beta": (fundamentos(), perfil(), dict(beta=_BETA, tasa=0.25, consenso=0.08)),
}


@pytest.mark.parametrize("caso", _CASOS_DE_SUPUESTOS)
@pytest.mark.parametrize("r_f", [0.04, 0.02])
def test_todo_supuesto_que_se_puede_producir_tiene_procedencia_en_pantalla(caso, r_f):
    # Con r_f = 0,02 el crecimiento perpetuo (2,5 %) se recorta a la tasa libre.
    f, p, kwargs = _CASOS_DE_SUPUESTOS[caso]
    s = deducir(f, p, r_f=r_f, **{"beta": None, **kwargs})
    supuestos = a_dict(calcular(f, p, s, 0.8, date(2026, 10, 12)))["supuestos"]
    for nombre, supuesto in supuestos.items():
        assert mv.procedencia(nombre, supuesto) != "", (nombre, supuesto["procedencia"])


def _fuentes_que_escribe_el_paquete() -> "set[str]":
    """Cada `"fuente": "<literal>"` de supuestos.py y cada literal asignado a `fuente`.

    Se lee el árbol sintáctico y no el texto, para que un literal en un comentario
    no cuente y uno escrito en dos líneas tampoco se escape.
    """
    ruta = Path(__file__).resolve().parent.parent / "valoracion" / "supuestos.py"
    encontradas = set()
    for nodo in ast.walk(ast.parse(ruta.read_text(encoding="utf-8"))):
        valores = []
        if isinstance(nodo, ast.Dict):
            valores = [
                v for k, v in zip(nodo.keys, nodo.values)
                if isinstance(k, ast.Constant) and k.value == "fuente"
            ]
        elif isinstance(nodo, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "fuente" for t in nodo.targets
        ):
            valores = [nodo.value]
        for valor in valores:
            encontradas |= {
                n.value for n in ast.walk(valor)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)
            }
    return encontradas


def test_ninguna_fuente_nueva_se_queda_sin_texto():
    fuentes = _fuentes_que_escribe_el_paquete()
    # Si el lector dejara de encontrar fuentes, el resto del test pasaría en vacío.
    assert {"tesoro_10", "regresion", "historia_y_consenso", "financiera", "recortado_a_r_f"} <= fuentes
    for fuente in sorted(fuentes):
        con_texto = [
            nombre
            for nombre in mv._NOMBRE_SUPUESTO
            if mv.procedencia(nombre, {"procedencia": {"fuente": fuente}}) != ""
        ]
        assert con_texto, f"la fuente «{fuente}» de supuestos.py no tiene texto en la pantalla"


# --- Escapar lo que no es nuestro -----------------------------------------------------


def test_el_resumen_escapa_lo_que_no_es_suyo():
    valor = {**_valoracion(), "moneda": "<b>USD</b>"}
    salida = mv.resumen(valor)
    assert "<b>USD</b>" not in salida
    assert "&lt;b&gt;USD&lt;/b&gt;" in salida


def test_hasta_los_nombres_de_los_votos_se_escapan(monkeypatch):
    # Son constantes de este módulo, pero la regla es una sola: nada se pinta sin escapar.
    monkeypatch.setitem(mv.NOMBRE_VOTO, "pares", "<i>pares</i>")
    salida = mv.resumen(_fija())
    assert "<i>" not in salida
    assert "&lt;i&gt;pares&lt;/i&gt;" in salida


def test_una_fallida_con_un_motivo_raro_se_escapa():
    salida = mv.resumen({"version": "m1", "fecha": "2026-10-12", "motivo": "<x>"})
    assert "<x>" not in salida
    assert salida == '<div class="mpp-val">Sin valoración: &lt;x&gt;.</div>'


def _rica() -> dict:
    """Una valoración real en la que se pintan casi todos los textos que vienen de fuera."""
    f, p = fundamentos(), perfil()
    s = deducir(f, p, r_f=0.04, beta=_BETA, tasa=None, consenso=0.08)
    return a_dict(calcular(f, p, s, 0.8, date(2026, 10, 12)))


def _quema_caja() -> dict:
    f = fundamentos(ejercicios=[ejercicio(2026 - i, flujo_operativo=50.0) for i in range(4)])
    return _valoracion(f=f)


def _hojas_de_texto(objeto, ruta=()):
    if isinstance(objeto, dict):
        for clave, valor in objeto.items():
            yield from _hojas_de_texto(valor, (*ruta, clave))
    elif isinstance(objeto, str):
        yield ruta


def _con_hoja(objeto: dict, ruta: tuple, valor: str) -> dict:
    copia = copy.deepcopy(objeto)
    destino = copia
    for clave in ruta[:-1]:
        destino = destino[clave]
    destino[ruta[-1]] = valor
    return copia


_VALORACIONES_A_INYECTAR = {
    "rica": _rica(),
    "quema_caja": _quema_caja(),
    "banco": _valoracion(p=perfil(industria="Banks - Regional")),
    "fallida": fallida("sin_precio"),
}
_HOJAS = [
    (nombre, ruta)
    for nombre, valoracion in _VALORACIONES_A_INYECTAR.items()
    for ruta in _hojas_de_texto(valoracion)
]

# Las hojas de texto que SÍ se pintan: si una se dejara de escapar, saldría
# cruda. El resto se descarta o se lee (la hora, el veredicto) y no se pinta.
_SE_PINTAN = {
    ("rica", ("moneda",)),
    ("rica", ("fecha",)),
    ("rica", ("estados_hasta",)),
    ("rica", ("supuestos", "r_f", "procedencia", "serie")),
    ("rica", ("supuestos", "beta", "procedencia", "indice")),
    ("rica", ("supuestos", "prima", "procedencia", "fecha")),
    ("rica", ("supuestos", "t", "procedencia", "pais")),
    ("rica", ("supuestos", "g_perpetuo", "procedencia", "moneda")),
    ("quema_caja", ("votos", "flujos", "motivo")),
    ("banco", ("votos", "sin_crecimiento", "motivo")),
    ("fallida", ("motivo",)),
}


def test_la_inyeccion_toca_los_textos_que_se_pintan():
    # Guarda del propio test: cada hoja que se declara pintada existe de verdad.
    assert _SE_PINTAN <= set(_HOJAS)


@pytest.mark.parametrize(("nombre", "ruta"), _HOJAS, ids=[f"{n}:{'.'.join(r)}" for n, r in _HOJAS])
def test_ningun_texto_de_la_ficha_llega_crudo_a_la_pantalla(nombre, ruta):
    valoracion = _con_hoja(_VALORACIONES_A_INYECTAR[nombre], ruta, "<x>")
    salida = mv.resumen(valoracion) + mv.distintivo(valoracion)
    assert "<x>" not in salida
    if (nombre, ruta) in _SE_PINTAN:
        assert "&lt;x&gt;" in salida


# --- Una ficha corrupta no tumba la pantalla ---------------------------------------------


@pytest.mark.parametrize(
    "cambios",
    [
        {"votos": []},
        {"votos": "x"},
        {"votos": None},
        {"votos": {"flujos": "x", "sin_crecimiento": None, "pares": []}},
        {"votos": {"flujos": {"voto": ["cara"]}, "sin_crecimiento": {"voto": 3}, "pares": {"voto": {}}}},
        {"votos": {"flujos": {"voto": "no_aplica", "motivo": ["a"]}}},
        {"valor": "x"},
        {"valor": [1, 2]},
        {"valor": {"base": "x", "pesimista": None}},
        {"valor": 3},
        {"implicito": "x"},
        {"implicito": {"magnitud": ["roe"], "valor": "x", "fuera_de_limites": ["arriba"]}},
        {"implicito": {"magnitud": "roe", "valor": "x", "referencia": [], "margen": {}}},
        {"epv": [1]},
        {"epv": {"por_accion": "x", "parte_crecimiento": "y"}},
        {"supuestos": []},
        {"supuestos": "x"},
        {"supuestos": {"r_f": "x", "beta": None, "prima": [1], "k_e": {"valor": "0.1"}}},
        {"supuestos": {"beta": {"valor": "1.2", "procedencia": "x"}}},
        {"supuestos": {"r_f": {"valor": float("nan"), "procedencia": {"fuente": "tesoro_10"}}}},
        {"supuestos": {"r_f": {"valor": 10**400, "procedencia": {"fuente": ["tesoro_10"]}}}},
        {"margen_seguridad": "x"},
        {"margen_seguridad": True},
        {"precio": "x", "moneda": ["USD"]},
        {"precio": float("inf")},
        {"metodo": ["residual"]},
        {"fecha": None, "estados_hasta": None},
        {"precio_hora": float("nan")},
    ],
    ids=lambda c: next(iter(c)) + ":" + repr(next(iter(c.values())))[:30],
)
def test_una_ficha_corrupta_no_hace_reventar_el_resumen(cambios):
    salida = mv.resumen(_fija(**cambios))
    assert salida.startswith('<div class="mpp-val">') and salida.endswith("</div>")


@pytest.mark.parametrize("valor", [None, [], "x", 3])
def test_lo_que_no_es_una_valoracion_no_se_pinta(valor):
    assert mv.resumen(valor) == ""


def test_un_voto_con_valor_roto_se_lee_n_d():
    votos = {"flujos": {"voto": ["cara"]}, "sin_crecimiento": "x", "pares": {"voto": 3}}
    for clave in ("flujos", "sin_crecimiento", "pares"):
        _, etiqueta, _ = _fila(_fija(votos=votos), clave)
        assert etiqueta == "n/d"
    assert '<span class="mpp-val-etiqueta" style="color:' + tema.TEXTO_SUAVE + '">n/d</span>' in mv.resumen(
        _fija(votos=votos)
    )


def test_un_supuesto_con_valor_de_texto_se_lee_n_d():
    supuestos = {"r_f": {"valor": "0.05", "procedencia": {"fuente": "tesoro_10", "serie": "^TNX"}}}
    assert "tasa libre: n/d · Tesoro de EE. UU. a 10 años (^TNX)" in _texto(mv.resumen(_fija(supuestos=supuestos)))


def test_un_valor_que_no_es_un_diccionario_no_da_rango():
    assert "Sin rango de valor." in mv.resumen(_fija(valor="x"))


def test_un_numero_infinito_o_un_booleano_se_leen_n_d():
    assert "margen de seguridad n/d" in mv.resumen(_fija(margen_seguridad=float("inf")))
    assert "margen de seguridad n/d" in mv.resumen(_fija(margen_seguridad=True))


def test_una_ficha_sin_rango_sigue_siendo_una_valoracion():
    valoracion = _fija()
    del valoracion["valor"]
    salida = mv.resumen(valoracion)
    assert "Sin valoración" not in salida
    assert "Sin rango de valor." in salida


def test_lo_que_trae_motivo_y_no_veredicto_es_una_fallida_aunque_lleve_valor():
    assert _texto(mv.resumen({"motivo": "sin_precio", "valor": None})) == (
        "Sin valoración: Yahoo Finance no devolvió el precio."
    )


# --- Las dos funciones de respaldo ------------------------------------------------------


def test_una_fallida_dice_por_que():
    assert mv.MOTIVO["sin_precio"] in mv.resumen(fallida("sin_precio"))


def test_el_texto_de_una_fallida():
    texto = _texto(mv.resumen(fallida("sin_precio")))
    assert texto == "Sin valoración: Yahoo Finance no devolvió el precio."


def test_un_motivo_que_no_se_conoce_se_enseña_tal_cual():
    assert _texto(mv.resumen({"motivo": "motivo_nuevo"})) == "Sin valoración: motivo_nuevo."


@pytest.mark.parametrize("motivo", [None, ["sin_precio"], 3])
def test_una_fallida_sin_motivo_legible_dice_n_d(motivo):
    assert _texto(mv.resumen({"motivo": motivo})) == "Sin valoración: n/d."
    assert _texto(mv.resumen({})) == "Sin valoración: n/d."


def test_un_voto_que_no_se_conoce_se_pinta_n_d_en_el_gris():
    votos = {**_fija()["votos"], "pares": {"voto": "otro", "motivo": None}}
    salida = mv.resumen(_fija(votos=votos))
    assert f'<span class="mpp-val-etiqueta" style="color:{tema.TEXTO_SUAVE}">n/d</span>' in salida
    assert _detalle(_fija(votos=votos), "pares") == ""


# --- El color y el CSS ------------------------------------------------------------------


def _colores_de_texto() -> "dict[str, str]":
    colores = {f"CSS {c}": c for c in re.findall(r"#[0-9a-fA-F]{6}\b", mv.CSS)}
    colores.update({f"veredicto {k}": c for k, (_, c) in mv.VEREDICTO.items()})
    colores.update({f"voto {k}": c for k, (_, c) in mv.VOTO.items()})
    return colores


def test_el_css_usa_colores():
    # Guarda del test de debajo: si el patrón dejara de casar, no comprobaría nada.
    assert any(nombre.startswith("CSS ") for nombre in _colores_de_texto())


def test_todo_color_de_texto_contrasta_sobre_la_tarjeta():
    # WCAG AA para texto normal. `TEXTO_TENUE` se queda en 4.28:1 sobre la tarjeta.
    flojos = {
        nombre: round(contraste(color, tema.TARJETA), 2)
        for nombre, color in _colores_de_texto().items()
        if contraste(color, tema.TARJETA) < 4.5
    }
    assert not flojos, flojos


def test_ningun_texto_de_la_valoracion_usa_el_gris_tenue():
    assert tema.TEXTO_TENUE not in _colores_de_texto().values()
    assert tema.TEXTO_TENUE not in mv.resumen(_fija()) + mv.resumen(_fija_residual())


def test_el_css_es_una_hoja_de_estilo_completa():
    assert mv.CSS.startswith("<style>") and mv.CSS.endswith("</style>")


@pytest.mark.parametrize(
    ("selector", "color"),
    [
        (".mpp-val", tema.TEXTO),
        (".mpp-val-detalle", tema.TEXTO_SUAVE),
        (".mpp-val-sup", tema.TEXTO_SUAVE),
    ],
)
def test_el_color_de_cada_regla_de_texto(selector, color):
    regla = re.search(re.escape(selector) + r" \{([^}]*)\}", mv.CSS).group(1)
    assert re.search(r"(?:^|;)\s*color:(#[0-9a-fA-F]{6});", regla).group(1) == color


def test_el_css_no_esconde_nada():
    for prohibido in ("display:none", "display: none", "visibility:hidden", "position:fixed", "position: fixed"):
        assert prohibido not in mv.CSS, prohibido


def test_el_css_no_lleva_colores_escritos_a_mano():
    # Todo color sale de `tema`: se quitan los suyos y no debe quedar ningún otro.
    sin_tema = mv.CSS
    for valor in vars(tema).values():
        if isinstance(valor, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", valor):
            sin_tema = sin_tema.replace(valor, "")
    assert not re.findall(r"#[0-9a-fA-F]{3,8}\b", sin_tema)


# --- El glosario ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "termino",
    [
        "DCF",
        "DCF inverso",
        "EPV",
        "Beneficio residual",
        "Capex",
        "ROE",
        "Consenso",
        "Tasa libre de riesgo y prima de riesgo",
        "Beta, R² y Blume",
        "Coste de capital (WACC)",
        "coste del capital propio",
        "Crecimiento a perpetuidad y valor terminal",
        "Escenarios",
        "Margen de seguridad",
        "Veredicto",
    ],
)
def test_el_glosario_explica_cada_termino(termino):
    assert f"**{termino}**" in mv.glosario()


def test_el_glosario_avisa_de_que_el_capex_de_mantenimiento_no_se_separa():
    assert "ninguna fuente separa el capex de mantenimiento del de expansión" in mv.glosario()


def test_el_glosario_dice_de_que_beneficio_sale_el_epv():
    assert "si su beneficio operativo después de impuestos se mantuviera para siempre" in mv.glosario()
    assert "sus beneficios actuales" not in mv.glosario()


def test_el_glosario_dice_que_el_margen_no_es_el_de_graham():
    assert "(valor base − precio) / precio" in mv.glosario()
    assert "No es el de Graham, (valor − precio) / valor" in mv.glosario()


def test_el_glosario_explica_la_regla_del_veredicto():
    assert "dos votos en el mismo sentido" in mv.glosario()
    assert "Una «cara» con dos «neutra» es «en rango»" in mv.glosario()
    assert f"menos de {criterio.MIN_VOTOS} votos aplicables" in mv.glosario()
    assert mv.glosario().endswith("votos aplicables, sin datos suficientes.")


def test_el_glosario_cuenta_el_ajuste_de_blume_con_el_criterio():
    pasos = f"{(1 - criterio.BLUME[0]) * 100:.0f}% del camino hacia 1.0"
    assert pasos in mv.glosario()
    assert "R² bajo significa una beta ruidosa" in mv.glosario()


def test_el_glosario_nombra_a_todas_las_entidades_financieras():
    glosario = mv.glosario()
    assert "(bancos, aseguradoras y mercados de capitales)" in glosario
    assert "bancos y aseguradoras," not in glosario


def test_el_glosario_explica_de_donde_sale_el_rango():
    glosario = mv.glosario()
    assert "**Escenarios** (pesimista, base y optimista)" in glosario
    assert "sube 1 punto el coste de capital" in glosario
    assert "lo baja 1 punto" in glosario
    assert "es lo que hace tan ancho el rango" in glosario


def test_el_glosario_nombra_la_tasa_libre_y_la_prima():
    assert "Tesoro de EE. UU. a 10 años (^TNX)" in mv.glosario()
    assert "La prima de riesgo, que publica Damodaran" in mv.glosario()


def test_el_glosario_es_markdown_sin_etiquetas():
    entradas = [linea for linea in mv.glosario().split("\n") if linea]
    assert len(entradas) == 14
    assert all(linea.startswith("- **") for linea in entradas)
    assert "<" not in mv.glosario() and ">" not in mv.glosario()


def test_el_resumen_no_repite_el_glosario():
    # El glosario se pinta una vez por pantalla; si cada resumen lo llevara, serían quince.
    glosario = re.sub(r"\*\*", "", mv.glosario())
    for valoracion in (_fija(), _fija_residual(), fallida("sin_precio")):
        salida = _texto(mv.resumen(valoracion))
        for entrada in glosario.split("\n"):
            definicion = entrada.split(": ", 1)[1]
            assert definicion[:50] not in salida


# --- Los textos siguen al criterio ----------------------------------------------------------------
# Si un listón del criterio se enmienda, la pantalla tiene que cambiar con él:
# cada test cambia el valor en el módulo y mira que el texto lo siga.


def test_los_anos_proyectados_siguen_al_criterio(monkeypatch):
    monkeypatch.setattr(mv, "ANOS_ALTO_CRECIMIENTO", 7)
    detalle = _detalle(_fija(), "flujos")
    assert "durante 7 años" in detalle
    assert "durante 5 años" not in detalle


def test_los_limites_del_inverso_de_crecimiento_siguen_al_criterio(monkeypatch):
    monkeypatch.setattr(mv, "INVERSO_LIMITES", (-0.4, 0.9))
    base = {"magnitud": "crecimiento", "valor": 0.5, "referencia": 0.4, "margen": 0.2}
    arriba = _fija(implicito={**base, "fuera_de_limites": "arriba"})
    abajo = _fija(implicito={**base, "fuera_de_limites": "abajo"})
    assert _detalle(arriba, "flujos") == "el precio da por hecho un crecimiento de más del 90.0% al año"
    assert _detalle(abajo, "flujos") == "el precio es tan bajo que ni una caída del 40.0% al año lo explicaría"


def test_los_limites_del_inverso_de_roe_siguen_al_criterio(monkeypatch):
    monkeypatch.setattr(mv, "INVERSO_ROE_LIMITES", (-0.1, 0.7))
    base = {"magnitud": "roe", "valor": 0.5, "referencia": 0.15, "margen": 0.075}
    arriba = _fija_residual(implicito={**base, "fuera_de_limites": "arriba"})
    abajo = _fija_residual(implicito={**base, "fuera_de_limites": "abajo"})
    assert _detalle(arriba, "flujos") == "el precio exige un ROE de más del 70.0%"
    assert _detalle(abajo, "flujos") == "el precio es tan bajo que ni un ROE del −10.0% lo explicaría"


def test_los_topes_de_la_tasa_efectiva_siguen_al_criterio(monkeypatch):
    monkeypatch.setattr(mv, "TASA_EFECTIVA_TOPES", (0.05, 0.2))
    assert mv.procedencia("t", {"procedencia": {"fuente": "efectiva"}}) == (
        "tasa efectiva de yfinance, acotada entre 5.0% y 20.0%"
    )


@pytest.mark.parametrize("fuente", ["historia_y_consenso", "historia", "consenso"])
def test_los_topes_del_crecimiento_de_referencia_siguen_al_criterio(monkeypatch, fuente):
    monkeypatch.setattr(mv, "CRECIMIENTO_REF_TOPES", (-0.2, 0.5))
    texto = mv.procedencia("g_ref", {"procedencia": {"fuente": fuente, "historico": 0.1, "consenso": 0.1}})
    assert texto.endswith("entre −20.0% y 50.0%")


def test_el_tope_de_la_prima_de_la_deuda_sigue_al_criterio(monkeypatch):
    monkeypatch.setattr(mv, "COSTE_DEUDA_PRIMA_MAXIMA", 0.05)
    texto = mv.procedencia("k_d", {"procedencia": {"fuente": "gasto_entre_deuda"}})
    assert texto.endswith("esa tasa más 5.0 puntos")


def test_el_reparto_por_defecto_sigue_al_criterio(monkeypatch):
    monkeypatch.setattr(mv, "PAYOUT_SIN_DATO", 0.3)
    assert mv.procedencia("payout", {"procedencia": {"fuente": "por_defecto"}}) == "sin dato: se supone el 30.0%"


@pytest.mark.parametrize(
    ("holgura", "esperado"),
    [(0.01, "al menos 1 punto,"), (0.02, "al menos 2 puntos,"), (0.015, "al menos 1.5 puntos,")],
)
def test_la_holgura_de_gordon_sigue_al_criterio(monkeypatch, holgura, esperado):
    monkeypatch.setattr(mv, "HOLGURA_GORDON", holgura)
    assert esperado in mv.etiqueta_motivo("wacc_bajo_crecimiento")


def test_el_motivo_de_la_holgura_llega_a_la_fila_del_voto(monkeypatch):
    monkeypatch.setattr(mv, "HOLGURA_GORDON", 0.02)
    votos = {**_fija()["votos"], "flujos": {"voto": "no_aplica", "motivo": "wacc_bajo_crecimiento"}}
    assert "al menos 2 puntos," in _detalle(_fija(votos=votos), "flujos")


def test_los_votos_minimos_siguen_al_criterio(monkeypatch):
    monkeypatch.setattr(mv, "MIN_VOTOS", 3)
    assert "menos de 3 votos aplicables" in mv.glosario()


def test_el_ajuste_de_blume_sigue_al_criterio(monkeypatch):
    monkeypatch.setattr(mv, "BLUME", (0.5, 0.5))
    assert "un 50% del camino hacia 1.0" in mv.glosario()


@pytest.mark.parametrize(
    ("delta", "salto"), [(0.01, "1 punto"), (0.02, "2 puntos"), (0.005, "0.5 puntos")]
)
def test_el_salto_del_coste_de_capital_de_los_escenarios_sigue_al_criterio(monkeypatch, delta, salto):
    monkeypatch.setattr(mv, "DELTA_WACC_ESCENARIOS", delta)
    glosario = mv.glosario()
    assert f"sube {salto} el coste de capital" in glosario
    assert f"lo baja {salto}." in glosario


# --- La tarjeta --------------------------------------------------------------------------------

FICHA = {
    "puesto": 1,
    "ticker": "AAA",
    "sector_gics": "Information Technology",
    "compuesto": 1.2,
    "pilares": {"calidad": 0.5, "crecimiento": 0.1, "valoracion": -0.2, "solidez": 0.3},
    "cobertura": {
        "kpis_con_dato": 15,
        "pilares_con_dato": 4,
        "kpis_por_pilar": {"calidad": 7, "crecimiento": 3, "valoracion": 4, "solidez": 3},
    },
}


def test_la_tarjeta_lleva_el_distintivo():
    ficha = {**FICHA, "valoracion": {"version": "m1", "veredicto": "infravalorada"}}
    assert "Infravalorada" in medidores.tarjeta_candidato(ficha)


def test_el_distintivo_va_justo_despues_del_chip_del_sector():
    valoracion = {"version": "m1", "veredicto": "sobrevalorada"}
    tarjeta = medidores.tarjeta_candidato({**FICHA, "valoracion": valoracion})
    chip = '<span class="mpp-chip">Information Technology</span>'
    assert chip + mv.distintivo(valoracion) + '<span class="mpp-cab-der">' in tarjeta


def test_una_tarjeta_vieja_no_lleva_distintivo():
    assert "mpp-veredicto" not in medidores.tarjeta_candidato(FICHA)


@pytest.mark.parametrize("valoracion", [fallida("sin_precio"), "x", {"veredicto": ["mixtas"]}])
def test_una_tarjeta_con_valoracion_sin_veredicto_no_lleva_distintivo(valoracion):
    assert "mpp-veredicto" not in medidores.tarjeta_candidato({**FICHA, "valoracion": valoracion})

import json
import math
from dataclasses import replace
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

import medidores_valoracion
from valoracion import dcf, mercado, residual
from valoracion.mercado import Beta
from valoracion.motor import calcular, valorar
from valoracion.plano import a_dict, fallida
from valoracion.supuestos import deducir
from valoracion.votos import BARATA, CARA, MOTIVOS, NEUTRA, NO_APLICA, VEREDICTOS

from tests.dobles_valoracion import ejercicio, fundamentos, perfil

HOY = date(2026, 10, 12)
ACCIONES = 10.0
# Las cuentas a mano con los dobles: margen de flujo libre 0,215; k_e 0,082
# (0,04 + 1 × 0,042); peso de la deuda 200 / (1.000 + 200) = 1/6 con k_d 0,10;
# wacc = 5/6 × 0,082 + 1/6 × 0,10 × (1 − 0,25).
WACC = 5 / 6 * 0.082 + 1 / 6 * 0.10 * 0.75


def _supuestos(f=None, p=None, consenso=None):
    return deducir(f or fundamentos(), p or perfil(), r_f=0.04, beta=None, tasa=0.25, consenso=consenso)


def _con_precio(precio, **sobre):
    """El mismo perfil cotizando a otro precio: las acciones siguen siendo diez."""
    return perfil(precio=precio, capitalizacion=precio * ACCIONES, **sobre)


def _flujos_por_accion(g, wacc=WACC):
    return (dcf.valor_empresa(1000.0, 0.215, g, 0.025, wacc) - 200.0 + 50.0) / ACCIONES


def _datos_residual(s):
    return residual.DatosResidual(
        patrimonio=1000.0, k_e=s.k_e.valor, payout=s.payout.valor, g_perpetuo=s.g_perpetuo.valor, acciones=ACCIONES
    )


def test_una_empresa_corriente_se_valora_por_flujos():
    v = calcular(fundamentos(), perfil(), _supuestos(), pilar_valoracion=0.0, hoy=HOY)
    assert v.metodo == "flujos"
    assert set(v.votos) == {"flujos", "sin_crecimiento", "pares"}
    assert v.valor.pesimista < v.valor.base < v.valor.optimista
    assert v.veredicto in VEREDICTOS


def test_el_rango_y_el_valor_sin_crecimiento_con_las_cuentas_a_mano():
    v = calcular(fundamentos(), perfil(), _supuestos(), 0.0, HOY)
    assert v.valor.base == pytest.approx(_flujos_por_accion(0.0))
    # g_ref = 0 → holgura = max(0,05; 0) = 0,05, y ±1 punto de coste de capital.
    assert v.valor.pesimista == pytest.approx(_flujos_por_accion(-0.05, WACC + 0.01))
    assert v.valor.optimista == pytest.approx(_flujos_por_accion(0.05, WACC - 0.01))
    epv = (0.2 * 1000 * 0.75 / WACC - 200 + 50) / ACCIONES
    assert v.epv.por_accion == pytest.approx(epv)
    assert v.epv.parte_crecimiento == pytest.approx(1 - epv / 100)
    assert v.votos["sin_crecimiento"].voto == BARATA
    assert (v.implicito.magnitud, v.implicito.referencia, v.implicito.margen) == ("crecimiento", 0.0, 0.05)


def test_con_un_crecimiento_alto_la_holgura_es_la_mitad_de_la_referencia():
    # Historia 0 y consenso 0,40: g_ref = 0,20, y la holgura de 0,10 manda sobre
    # el mínimo de 0,05. La misma abre el rango y el voto.
    s = _supuestos(consenso=0.40)
    v = calcular(fundamentos(), perfil(), s, 0.0, HOY)
    assert s.g_ref.valor == pytest.approx(0.20)
    assert (v.implicito.referencia, v.implicito.margen) == (pytest.approx(0.20), pytest.approx(0.10))
    assert v.valor.base == pytest.approx(_flujos_por_accion(0.20))
    assert v.valor.pesimista == pytest.approx(_flujos_por_accion(0.10, WACC + 0.01))
    assert v.valor.optimista == pytest.approx(_flujos_por_accion(0.30, WACC - 0.01))


@pytest.mark.parametrize(
    "pilar, esperado",
    [(0.8, "infravalorada"), (0.0, "infravalorada"), (-0.8, "mixtas")],
)
def test_el_veredicto_cuenta_los_tres_votos(pilar, esperado):
    # Con estos dobles flujos y sin crecimiento son baratas; los pares deciden el resto.
    v = calcular(fundamentos(), perfil(), _supuestos(), pilar, HOY)
    assert v.veredicto == esperado


def test_cara_frente_a_sus_cuentas_y_a_su_sector_es_sobrevalorada():
    # El EPV nunca vota «cara»: la sobrevaloración exige que coincidan flujos y pares.
    v = calcular(fundamentos(), _con_precio(1_000_000.0), _supuestos(), -0.8, HOY)
    assert (v.votos["flujos"].voto, v.votos["sin_crecimiento"].voto, v.votos["pares"].voto) == (CARA, NEUTRA, CARA)
    assert v.veredicto == "sobrevalorada"


def test_un_banco_se_valora_por_beneficio_residual():
    p = perfil(industria="Banks - Regional")
    v = calcular(fundamentos(), p, _supuestos(p=p), pilar_valoracion=0.0, hoy=HOY)
    assert v.metodo == "residual"
    assert v.votos["sin_crecimiento"].voto == NO_APLICA
    assert v.votos["sin_crecimiento"].motivo == "financiera"
    assert v.implicito.magnitud == "roe"


def test_el_residual_con_las_cuentas_a_mano_y_sin_valor_sin_crecimiento():
    p = perfil(industria="Banks - Regional")
    s = _supuestos(p=p)
    v = calcular(fundamentos(), p, s, 0.0, HOY)
    datos = _datos_residual(s)
    assert v.valor.base == pytest.approx(residual.valor_por_accion(datos, 0.12))
    # roe_ref = 0,12 → holgura = max(0,03; 0,06) = 0,06, y ±1 punto de k_e.
    assert v.valor.pesimista == pytest.approx(residual.valor_por_accion(datos, 0.12 - 0.06, s.k_e.valor + 0.01))
    assert v.valor.optimista == pytest.approx(residual.valor_por_accion(datos, 0.12 + 0.06, s.k_e.valor - 0.01))
    assert v.epv is None
    assert (v.implicito.magnitud, v.implicito.referencia, v.implicito.margen) == ("roe", 0.12, 0.06)


@pytest.mark.parametrize(
    "industria, metodo",
    [
        # Su flujo de caja sí significa algo: se valoran por flujos.
        ("Credit Services", "flujos"),
        ("Insurance Brokers", "flujos"),
        ("Asset Management", "flujos"),
        # Su flujo de caja no significa nada: prestar es su operación.
        ("Banks - Diversified", "residual"),
        ("Insurance - Life", "residual"),
        ("Capital Markets", "residual"),
    ],
)
def test_la_industria_decide_el_metodo(industria, metodo):
    p = perfil(industria=industria)
    assert calcular(fundamentos(), p, _supuestos(p=p), 0.0, HOY).metodo == metodo


def test_una_industria_sin_dato_se_valora_por_flujos():
    p = perfil(industria=None)
    assert calcular(fundamentos(), p, _supuestos(p=p), 0.0, HOY).metodo == "flujos"


def test_una_empresa_que_quema_caja_no_vota_flujos():
    f = fundamentos(ejercicios=[ejercicio(2026 - i, flujo_operativo=50.0) for i in range(4)])
    v = calcular(f, perfil(), _supuestos(f=f), pilar_valoracion=0.0, hoy=HOY)
    assert (v.votos["flujos"].voto, v.votos["flujos"].motivo) == (NO_APLICA, "quema_caja")
    assert v.valor is None


def test_un_margen_de_flujo_libre_exactamente_cero_tambien_quema_caja():
    f = fundamentos(
        ejercicios=[
            ejercicio(2026 - i, flujo_operativo=100.0, capex=100.0, gasto_financiero=0.0) for i in range(4)
        ]
    )
    v = calcular(f, perfil(), _supuestos(f=f), 0.0, HOY)
    assert v.votos["flujos"].motivo == "quema_caja"


def test_sin_capex_declarado_en_ningun_ano_no_es_falta_de_historia():
    # LLY, COST, NEE, VZ o PEP tienen cinco años de ingresos y no declaran el
    # capex nunca: lo que falta es el flujo libre, no la historia.
    f = fundamentos(ejercicios=[ejercicio(2026 - i, capex=math.nan) for i in range(4)])
    v = calcular(f, perfil(), _supuestos(f=f), 0.0, HOY)
    assert (v.votos["flujos"].voto, v.votos["flujos"].motivo) == (NO_APLICA, "sin_flujo_libre")
    assert v.valor is None and v.implicito is None
    assert "sin_flujo_libre" in MOTIVOS
    # El beneficio operativo sí está declarado, y el EPV sigue votando.
    assert v.epv is not None and v.votos["sin_crecimiento"].voto == BARATA


def test_con_dos_anos_de_ingresos_pero_sin_capex_falta_el_flujo_libre():
    # El mínimo de historia son dos años con ingresos, y exactamente dos bastan.
    f = fundamentos(ejercicios=[ejercicio(2026, capex=math.nan), ejercicio(2025, capex=math.nan)])
    v = calcular(f, perfil(), _supuestos(f=f), 0.0, HOY)
    assert v.votos["flujos"].motivo == "sin_flujo_libre"


@pytest.mark.parametrize("anteriores", [math.nan, 0.0])
def test_con_un_solo_ano_de_ingresos_y_sin_capex_falta_la_historia(anteriores):
    # Sólo el último año tiene ingresos (los otros, sin declarar o a cero: una
    # empresa que aún no vendía): con menos de dos no hay historia de la que
    # decir que falta el flujo libre. Un año con ingresos cero no cuenta como
    # año con ingresos. El consenso da un crecimiento de referencia, pero no
    # un margen.
    f = fundamentos(
        ejercicios=[
            ejercicio(2026, capex=math.nan),
            ejercicio(2025, capex=math.nan, ingresos=anteriores),
            ejercicio(2024, capex=math.nan, ingresos=anteriores),
        ]
    )
    v = calcular(f, perfil(), _supuestos(f=f, consenso=0.10), 0.0, HOY)
    assert v.votos["flujos"].motivo == "sin_historia"


def test_sin_historia_en_flujos_y_en_residual():
    f = fundamentos(ejercicios=[ejercicio(2026)])
    v = calcular(f, perfil(), _supuestos(f=f), 0.0, HOY)
    assert (v.votos["flujos"].voto, v.votos["flujos"].motivo) == (NO_APLICA, "sin_historia")
    p = perfil(industria="Banks - Regional")
    v = calcular(f, p, _supuestos(f=f, p=p), 0.0, HOY)
    assert (v.votos["flujos"].voto, v.votos["flujos"].motivo) == (NO_APLICA, "sin_historia")


def test_con_un_solo_ejercicio_pero_con_consenso_sigue_faltando_la_historia():
    # El crecimiento de referencia sale del consenso, pero sin dos años no hay
    # margen de flujo libre que proyectar.
    f = fundamentos(ejercicios=[ejercicio(2026)])
    v = calcular(f, perfil(), _supuestos(f=f, consenso=0.10), 0.0, HOY)
    assert (v.votos["flujos"].voto, v.votos["flujos"].motivo) == (NO_APLICA, "sin_historia")
    assert v.valor is None


def test_sin_crecimiento_de_referencia_flujos_no_aplica_por_historia():
    # El cuarto ejercicio no declara ingresos: hay margen de tres años, pero el
    # crecimiento a tres años no se puede medir y no hay consenso.
    f = fundamentos(ejercicios=[ejercicio(2026), ejercicio(2025), ejercicio(2024), ejercicio(2023, ingresos=math.nan)])
    s = _supuestos(f=f)
    assert s.g_ref.valor is None
    v = calcular(f, perfil(), s, 0.0, HOY)
    assert (v.votos["flujos"].voto, v.votos["flujos"].motivo) == (NO_APLICA, "sin_historia")
    assert v.valor is None


def test_ingresos_del_ultimo_sin_declarar_flujos_no_aplica_por_historia():
    # Con consenso hay crecimiento de referencia, y sin los ingresos del último
    # año no hay de dónde proyectar: no puede salir un rango de NaN.
    f = fundamentos(ejercicios=[ejercicio(2026, ingresos=math.nan), ejercicio(2025), ejercicio(2024)])
    s = _supuestos(f=f, consenso=0.10)
    assert s.g_ref.valor == pytest.approx(0.10)
    v = calcular(f, perfil(), s, 0.0, HOY)
    assert (v.votos["flujos"].voto, v.votos["flujos"].motivo) == (NO_APLICA, "sin_historia")
    assert v.valor is None and v.implicito is None


def test_un_banco_con_patrimonio_negativo_no_vota_flujos():
    f = fundamentos(ejercicios=[ejercicio(2026, patrimonio_neto=-10.0), ejercicio(2025), ejercicio(2024)])
    p = perfil(industria="Banks - Regional")
    v = calcular(f, p, _supuestos(f=f, p=p), pilar_valoracion=0.0, hoy=HOY)
    assert v.votos["flujos"].motivo == "patrimonio_negativo"


def test_un_banco_con_patrimonio_cero_tampoco_vota_flujos():
    f = fundamentos(ejercicios=[ejercicio(2026, patrimonio_neto=0.0), ejercicio(2025), ejercicio(2024)])
    p = perfil(industria="Banks - Regional")
    v = calcular(f, p, _supuestos(f=f, p=p), 0.0, HOY)
    assert v.votos["flujos"].motivo == "patrimonio_negativo"


def test_un_banco_sin_patrimonio_declarado_no_es_un_banco_con_patrimonio_negativo():
    # NaN es «no declarado»: decir `patrimonio_negativo` afirmaría una cifra que
    # nadie ha visto.
    f = fundamentos(ejercicios=[ejercicio(2026, patrimonio_neto=math.nan), ejercicio(2025), ejercicio(2024)])
    p = perfil(industria="Banks - Regional")
    v = calcular(f, p, _supuestos(f=f, p=p), 0.0, HOY)
    assert (v.votos["flujos"].voto, v.votos["flujos"].motivo) == (NO_APLICA, "sin_historia")
    assert v.valor is None


@pytest.mark.parametrize(
    "ingresos, consenso",
    [
        ([1000.0] * 4, None),
        ([1331.0, 1210.0, 1100.0, 1000.0], 0.20),
        ([900.0, 1000.0, 1100.0, 1200.0], None),
    ],
)
def test_con_el_precio_igual_al_valor_base_flujos_vota_neutra(ingresos, consenso):
    # Referencia positiva del voto: si el precio es el valor base, el
    # crecimiento implícito es el de referencia, y eso tiene que ser neutra.
    f = fundamentos(ejercicios=[ejercicio(2026 - i, ingresos=v) for i, v in enumerate(ingresos)])
    s = _supuestos(f=f, consenso=consenso)
    base = calcular(f, perfil(), s, 0.0, HOY).valor.base
    acciones = perfil().capitalizacion / perfil().precio
    en_su_valor = perfil(precio=base, capitalizacion=base * acciones)
    assert calcular(f, en_su_valor, s, 0.0, HOY).votos["flujos"].voto == NEUTRA


@pytest.mark.parametrize(
    "g, esperado",
    [(0.03, NEUTRA), (0.12, CARA), (-0.08, BARATA)],
)
def test_flujos_vota_segun_el_crecimiento_que_el_precio_exige(g, esperado):
    # La banda neutra es g_ref ± 0,05 = ±0,05: un precio que exige un 3 % está
    # dentro, uno que exige un 12 % queda por encima y uno que exige un −8 %,
    # por debajo. Con la holgura a cero, el 3 % ya sería «cara».
    precio = _flujos_por_accion(g)
    v = calcular(fundamentos(), _con_precio(precio), _supuestos(), 0.0, HOY)
    assert v.implicito.valor == pytest.approx(g, abs=1e-6)
    assert v.votos["flujos"].voto == esperado


@pytest.mark.parametrize(
    "roe, esperado",
    [(0.14, NEUTRA), (0.20, CARA), (0.05, BARATA)],
)
def test_el_residual_vota_segun_el_roe_que_el_precio_exige(roe, esperado):
    # La banda neutra es roe_ref ± 0,06 = 0,06–0,18.
    p = perfil(industria="Banks - Regional")
    s = _supuestos(p=p)
    precio = residual.valor_por_accion(_datos_residual(s), roe)
    assert precio > 0
    v = calcular(fundamentos(), _con_precio(precio, industria="Banks - Regional"), s, 0.0, HOY)
    assert v.implicito.valor == pytest.approx(roe, abs=1e-6)
    assert v.votos["flujos"].voto == esperado


def test_un_precio_que_ningun_crecimiento_justifica_es_cara_y_lo_dice():
    # Por encima del valor con el mayor crecimiento permitido: no hay respuesta
    # dentro de los límites, y la lectura cuenta por qué lado se sale.
    v = calcular(fundamentos(), _con_precio(1_000_000.0), _supuestos(), 0.0, HOY)
    assert v.implicito.valor is None and v.implicito.fuera_de_limites == "arriba"
    assert v.votos["flujos"].voto == CARA


def test_un_precio_que_se_justifica_hasta_sin_crecer_es_barata_y_lo_dice():
    v = calcular(fundamentos(), _con_precio(0.01), _supuestos(), 0.0, HOY)
    assert v.implicito.valor is None and v.implicito.fuera_de_limites == "abajo"
    assert v.votos["flujos"].voto == BARATA


def test_un_precio_que_ningun_roe_justifica_es_cara_y_lo_dice():
    p = perfil(industria="Banks - Regional")
    v = calcular(fundamentos(), _con_precio(100_000.0, industria="Banks - Regional"), _supuestos(p=p), 0.0, HOY)
    assert v.implicito.magnitud == "roe"
    assert v.implicito.valor is None and v.implicito.fuera_de_limites == "arriba"
    assert v.votos["flujos"].voto == CARA


def test_sin_holgura_de_gordon_flujos_no_aplica():
    # Coste de capital por debajo del perpetuo + 1 punto: el valor terminal
    # explotaría. Es lo que hace segura la etiqueta genérica de
    # `votos.voto_implicito` para un inverso sin respuesta: el motor lo filtra
    # antes con su propio motivo.
    s = _supuestos()
    s = replace(s, wacc=replace(s.wacc, valor=s.g_perpetuo.valor + 0.005))
    v = calcular(fundamentos(), perfil(), s, 0.0, HOY)
    assert (v.votos["flujos"].voto, v.votos["flujos"].motivo) == (NO_APLICA, "wacc_bajo_crecimiento")
    assert v.valor is None


def test_un_banco_sin_holgura_de_gordon_flujos_no_aplica():
    p = perfil(industria="Banks - Regional")
    s = _supuestos(p=p)
    s = replace(s, k_e=replace(s.k_e, valor=s.g_perpetuo.valor + 0.005))
    v = calcular(fundamentos(), p, s, 0.0, HOY)
    assert v.votos["flujos"].motivo == "wacc_bajo_crecimiento"


def test_la_deuda_sin_declarar_cuenta_como_cero():
    sin = fundamentos(deuda_total=math.nan, efectivo=math.nan)
    cero = fundamentos(deuda_total=0.0, efectivo=0.0)
    con_nan = calcular(sin, perfil(), _supuestos(f=sin), 0.0, HOY)
    con_cero = calcular(cero, perfil(), _supuestos(f=cero), 0.0, HOY)
    assert math.isfinite(con_nan.valor.base)
    assert con_nan.valor.base == pytest.approx(con_cero.valor.base)
    assert con_nan.epv.por_accion == pytest.approx(con_cero.epv.por_accion)


def test_la_deuda_resta_y_el_efectivo_suma():
    a = calcular(fundamentos(deuda_total=200.0, efectivo=50.0), perfil(), _supuestos(), 0.0, HOY)
    con_mas_efectivo = calcular(fundamentos(deuda_total=200.0, efectivo=150.0), perfil(), _supuestos(), 0.0, HOY)
    assert con_mas_efectivo.valor.base - a.valor.base == pytest.approx(100.0 / ACCIONES)
    # Y el EPV pasa por las mismas cuentas (con la misma deuda, el mismo wacc).
    assert con_mas_efectivo.epv.por_accion - a.epv.por_accion == pytest.approx(100.0 / ACCIONES)


def test_el_margen_de_seguridad_es_relativo_al_precio():
    v = calcular(fundamentos(), perfil(), _supuestos(), 0.0, HOY)
    assert v.margen_seguridad == pytest.approx((v.valor.base - 100.0) / 100.0)


def test_la_moneda_de_la_valoracion_es_la_del_precio():
    p = perfil(moneda="MXN", moneda_estados="USD")
    v = calcular(fundamentos(), p, _supuestos(p=p), 0.0, HOY)
    assert v.moneda == "MXN"
    assert a_dict(v)["moneda"] == "MXN"


def test_la_valoracion_es_json_estricto_y_lleva_las_claves_del_spec():
    v = calcular(fundamentos(), perfil(), _supuestos(), float("nan"), HOY)
    plano = a_dict(v)
    json.dumps(plano, allow_nan=False)
    assert set(plano) == {
        "version", "fecha", "estados_hasta", "moneda", "precio", "precio_hora",
        "metodo", "valor", "margen_seguridad", "implicito", "epv", "votos",
        "veredicto", "supuestos",
    }
    assert plano["version"] == "m1" and plano["fecha"] == "2026-10-12"
    # La fecha de los estados con los que se valoró: en el Analizador (N) puede
    # ser vieja, y el número tiene que decir de cuándo son sus cifras.
    assert plano["estados_hasta"] == "2026-09-30"
    assert plano["votos"]["pares"] == {"voto": "no_aplica", "motivo": "sin_pares"}
    assert set(plano["supuestos"]["beta"]) == {"valor", "procedencia"}


def test_el_plano_lleva_el_contenido_de_cada_bloque():
    v = calcular(fundamentos(), perfil(), _supuestos(), 0.8, HOY)
    plano = a_dict(v)
    assert plano["valor"] == {"pesimista": v.valor.pesimista, "base": v.valor.base, "optimista": v.valor.optimista}
    assert plano["margen_seguridad"] == v.margen_seguridad
    assert plano["implicito"] == {
        "magnitud": "crecimiento",
        "valor": v.implicito.valor,
        "referencia": 0.0,
        "margen": 0.05,
        "fuera_de_limites": None,
    }
    # El crecimiento que exige el precio y el de referencia son dos cosas.
    assert plano["implicito"]["valor"] != plano["implicito"]["referencia"]
    assert plano["epv"] == {"por_accion": v.epv.por_accion, "parte_crecimiento": v.epv.parte_crecimiento}
    assert plano["precio"] == 100.0 and plano["moneda"] == "USD" and plano["metodo"] == "flujos"
    assert plano["precio_hora"] == "2026-10-12T19:59:00+00:00"
    assert plano["votos"] == {
        "flujos": {"voto": "barata", "motivo": None},
        "sin_crecimiento": {"voto": "barata", "motivo": None},
        "pares": {"voto": "barata", "motivo": None},
    }
    assert plano["veredicto"] == v.veredicto == "infravalorada"
    assert plano["supuestos"]["k_e"]["valor"] == v.supuestos.k_e.valor
    assert plano["supuestos"]["g_ref"]["procedencia"]["fuente"] == "historia"
    assert set(plano["supuestos"]) == {
        "r_f", "beta", "prima", "k_e", "k_d", "t", "wacc", "g_ref", "g_perpetuo", "roe_ref", "payout",
    }


def test_el_plano_de_un_banco_dice_residual_y_no_lleva_valor_sin_crecimiento():
    p = perfil(industria="Banks - Regional")
    s = _supuestos(p=p)
    plano = a_dict(calcular(fundamentos(), p, s, 0.0, HOY))
    json.dumps(plano, allow_nan=False)
    assert plano["metodo"] == "residual"
    assert plano["implicito"]["magnitud"] == "roe" and plano["implicito"]["referencia"] == pytest.approx(0.12)
    assert plano["epv"] is None
    assert plano["votos"]["sin_crecimiento"] == {"voto": "no_aplica", "motivo": "financiera"}
    # Sin coste de capital de empresa, a propósito: el residual sólo usa k_e.
    assert plano["supuestos"]["wacc"] == {"valor": None, "procedencia": {"fuente": "financiera"}}


def test_una_valoracion_sin_rango_va_con_valor_nulo():
    f = fundamentos(ejercicios=[ejercicio(2026 - i, flujo_operativo=50.0) for i in range(4)])
    plano = a_dict(calcular(f, perfil(), _supuestos(f=f), 0.0, HOY))
    json.dumps(plano, allow_nan=False)
    assert plano["valor"] is None and plano["margen_seguridad"] is None and plano["implicito"] is None


def test_un_nan_en_una_procedencia_se_escribe_como_null():
    v = calcular(fundamentos(), perfil(), _supuestos(), 0.0, HOY)
    sup = replace(v.supuestos, g_ref=replace(v.supuestos.g_ref, procedencia={"consenso": float("nan")}))
    plano = a_dict(replace(v, supuestos=sup))
    assert plano["supuestos"]["g_ref"]["procedencia"]["consenso"] is None
    json.dumps(plano, allow_nan=False)


def test_un_infinito_tambien_se_escribe_como_null():
    v = calcular(fundamentos(), perfil(), _supuestos(), 0.0, HOY)
    sup = replace(v.supuestos, g_ref=replace(v.supuestos.g_ref, procedencia={"consenso": float("inf")}))
    plano = a_dict(replace(v, supuestos=sup))
    assert plano["supuestos"]["g_ref"]["procedencia"]["consenso"] is None
    json.dumps(plano, allow_nan=False)


def test_un_escenario_sin_holgura_de_gordon_va_como_null_y_los_demas_no():
    s = _supuestos()
    # El escenario optimista (coste de capital −1 punto) pierde la holgura de Gordon.
    s = replace(s, wacc=replace(s.wacc, valor=s.g_perpetuo.valor + 0.015))
    v = calcular(fundamentos(), perfil(), s, 0.0, HOY)
    assert v.valor.optimista is None and v.valor.base is not None and v.valor.pesimista is not None
    plano = a_dict(v)
    json.dumps(plano, allow_nan=False)
    assert plano["valor"]["optimista"] is None and plano["valor"]["base"] is not None


def test_una_fallida_dice_su_motivo_y_nada_mas():
    assert fallida("sin_precio", HOY) == {"version": "m1", "fecha": "2026-10-12", "motivo": "sin_precio"}


@pytest.fixture
def red_doble():
    # Valores que no son los de por defecto de `deducir`, para que un dato que
    # `valorar` olvidara pasar cambie el resultado.
    beta = Beta(bruta=1.2, r2=0.3, semanas=104, indice="^GSPC")
    with (
        patch.object(mercado, "perfil", return_value=(perfil(), "ok")) as perfil_doble,
        patch.object(mercado, "tasa_libre", return_value=(0.045, "ok")) as tasa_libre,
        patch.object(mercado, "beta", return_value=(beta, "ok")) as beta_doble,
        patch.object(mercado, "tasa_efectiva", return_value=(0.18, "ok")) as tasa_efectiva,
        patch.object(mercado, "consenso", return_value=(0.12, "ok")) as consenso,
        patch("valoracion.motor.desde_sec", return_value=(fundamentos(), "ok")) as sec,
    ):
        yield {
            "perfil": perfil_doble,
            "tasa_libre": tasa_libre,
            "beta": beta_doble,
            "tasa_efectiva": tasa_efectiva,
            "consenso": consenso,
            "sec": sec,
            "beta_medida": beta,
        }


def test_valorar_compone_todo_sin_red(red_doble):
    plano = valorar("TST", 0.3, hoy=HOY)
    json.dumps(plano, allow_nan=False)
    assert plano["veredicto"] in VEREDICTOS
    assert plano["votos"]["pares"]["voto"] == "neutra"


def test_valorar_es_calcular_con_los_datos_de_la_red(red_doble, tmp_path):
    f, p = fundamentos(), perfil()
    s = deducir(f, p, 0.045, red_doble["beta_medida"], 0.18, 0.12)
    esperado = a_dict(calcular(f, p, s, 0.8, HOY))
    assert valorar("TST", 0.8, cache_dir=tmp_path, hoy=HOY) == esperado
    # Cada fuente se pregunta por el ticker que se valora, una sola vez.
    red_doble["perfil"].assert_called_once_with("TST")
    red_doble["beta"].assert_called_once_with("TST")
    red_doble["tasa_efectiva"].assert_called_once_with("TST")
    red_doble["sec"].assert_called_once_with("TST", cache_dir=tmp_path)
    red_doble["consenso"].assert_called_once_with("TST", "USD")


def _supuesto_y_texto(plano: dict, nombre: str) -> "tuple[dict, str]":
    """La procedencia guardada de un supuesto y lo que la pantalla dice de ella."""
    supuesto = plano["supuestos"][nombre]
    return supuesto["procedencia"], medidores_valoracion.resumen(plano)


def test_una_beta_que_no_llego_por_la_red_no_se_dice_historial_corto(red_doble):
    # Con CF, el coste del capital propio pasaba del 5,9 % al 8,4 % y la
    # pantalla lo atribuía a un historial corto que no existía.
    with patch.object(mercado, "beta", return_value=(None, "sin_red")):
        plano = valorar("TST", 0.3, hoy=HOY)
    procedencia, resumen = _supuesto_y_texto(plano, "beta")
    assert procedencia == {"fuente": "por_defecto", "motivo": "sin_red"}
    assert "historial corto" not in resumen
    assert "Yahoo Finance no devolvió datos" in resumen


def test_una_beta_sin_regresion_posible_sigue_diciendo_historial_corto(red_doble):
    with patch.object(mercado, "beta", return_value=(None, "sin_regresion")):
        plano = valorar("TST", 0.3, hoy=HOY)
    procedencia, resumen = _supuesto_y_texto(plano, "beta")
    assert procedencia == {"fuente": "por_defecto", "motivo": "sin_regresion"}
    assert "historial corto" in resumen


def test_una_tasa_efectiva_que_no_llego_por_la_red_lo_dice(red_doble):
    with patch.object(mercado, "tasa_efectiva", return_value=(None, "sin_red")):
        plano = valorar("TST", 0.3, hoy=HOY)
    procedencia, resumen = _supuesto_y_texto(plano, "t")
    assert procedencia == {"fuente": "legal", "pais": "US", "motivo": "sin_red"}
    assert "Yahoo Finance no devolvió datos de la tasa efectiva" in resumen


def test_un_consenso_que_no_llego_por_la_red_lo_dice(red_doble):
    with patch.object(mercado, "consenso", return_value=(None, "sin_red")):
        plano = valorar("TST", 0.3, hoy=HOY)
    procedencia, resumen = _supuesto_y_texto(plano, "g_ref")
    assert procedencia["fuente"] == "historia"
    assert procedencia["motivo_consenso"] == "sin_red"
    assert "sin consenso porque Yahoo Finance no devolvió datos" in resumen


def test_con_todo_lo_de_mercado_presente_la_procedencia_no_lleva_motivos(red_doble):
    plano = valorar("TST", 0.3, hoy=HOY)
    for nombre in ("beta", "t", "g_ref"):
        procedencia = plano["supuestos"][nombre]["procedencia"]
        assert "motivo" not in procedencia and "motivo_consenso" not in procedencia


def test_un_pilar_de_valoracion_igual_a_cero_sigue_siendo_un_cero(red_doble):
    # Cero es un pilar de valoración válido (ni barata ni cara frente a sus
    # pares), no «sin pares»: el trámite de `valorar` no puede tratarlo como
    # falso.
    plano = valorar("TST", 0.0, hoy=HOY)
    assert plano["votos"]["pares"] == {"voto": "neutra", "motivo": None}


def test_sin_precio_valorar_dice_por_que(red_doble):
    with patch.object(mercado, "perfil", return_value=(None, "sin_precio")):
        assert valorar("TST", 0.3, hoy=HOY) == {"version": "m1", "fecha": "2026-10-12", "motivo": "sin_precio"}


def test_sin_red_valorar_lo_distingue_de_un_ticker_sin_precio_y_no_sigue(red_doble):
    # Con la red caída cada ticker tarda en rendirse: quien recorre una lista
    # tiene que poder parar, y para eso necesita que el motivo sea otro.
    with patch.object(mercado, "perfil", return_value=(None, "sin_red")):
        assert valorar("TST", 0.3, hoy=HOY) == {"version": "m1", "fecha": "2026-10-12", "motivo": "sin_red"}
    assert "sin_red" in MOTIVOS
    red_doble["tasa_libre"].assert_not_called()
    red_doble["sec"].assert_not_called()


def test_un_simbolo_que_yahoo_no_conoce_tambien_se_dice_sin_red(tmp_path, monkeypatch):
    # `mercado.perfil` devuelve `(None, "sin_red")` cuando `info` llega sin
    # ninguna clave de identidad, y eso es también lo que parece un símbolo
    # inexistente con la red sana. Desde fuera no se distinguen, y la decisión
    # queda escrita aquí, en la frontera donde se toma.
    monkeypatch.setattr(mercado, "RAIZ_CACHE", tmp_path)
    doble = MagicMock()
    doble.info = {"trailingPegRatio": 1.2}
    with patch.object(mercado.yf, "Ticker", return_value=doble), patch(
        "valoracion.motor.desde_sec", return_value=(None, "sin_estados")
    ) as sec:
        assert valorar("ZZZZQ", 0.3, hoy=HOY) == {"version": "m1", "fecha": "2026-10-12", "motivo": "sin_red"}
    sec.assert_not_called()


def test_sin_tasa_libre_valorar_dice_por_que(red_doble):
    with patch.object(mercado, "tasa_libre", return_value=(None, "sin_tasa_libre")):
        assert valorar("TST", 0.3, hoy=HOY)["motivo"] == "sin_tasa_libre"


def test_sin_estados_valorar_dice_por_que(red_doble):
    with patch("valoracion.motor.desde_sec", return_value=(None, "sin_estados")):
        assert valorar("TST", 0.3, hoy=HOY) == {"version": "m1", "fecha": "2026-10-12", "motivo": "sin_estados"}


def test_los_estados_sin_historia_se_dicen_con_el_motivo_de_la_fuente(red_doble):
    with patch("valoracion.motor.desde_sec", return_value=(None, "sin_historia")):
        assert valorar("TST", 0.3, hoy=HOY) == {"version": "m1", "fecha": "2026-10-12", "motivo": "sin_historia"}


def test_sin_precio_ni_tasa_libre_valorar_dice_sin_precio(red_doble):
    # El orden de las comprobaciones es el de lo que cada una cuesta y exige.
    with patch.object(mercado, "perfil", return_value=(None, "sin_precio")), patch.object(
        mercado, "tasa_libre", return_value=(None, "sin_tasa_libre")
    ):
        assert valorar("TST", 0.3, hoy=HOY)["motivo"] == "sin_precio"


def test_sin_tasa_libre_ni_estados_valorar_dice_sin_tasa_libre(red_doble):
    with patch.object(mercado, "tasa_libre", return_value=(None, "sin_tasa_libre")), patch(
        "valoracion.motor.desde_sec", return_value=(None, "sin_estados")
    ):
        assert valorar("TST", 0.3, hoy=HOY)["motivo"] == "sin_tasa_libre"

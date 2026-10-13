import json
import math
from dataclasses import replace
from datetime import date
from unittest.mock import patch

import pytest

from valoracion import mercado
from valoracion.motor import calcular, valorar
from valoracion.plano import a_dict, fallida
from valoracion.supuestos import deducir
from valoracion.votos import NEUTRA, NO_APLICA, VEREDICTOS

from tests.dobles_valoracion import ejercicio, fundamentos, perfil

HOY = date(2026, 10, 12)


def _supuestos(f=None, p=None, consenso=None):
    return deducir(f or fundamentos(), p or perfil(), r_f=0.04, beta=None, tasa=0.25, consenso=consenso)


def test_una_empresa_corriente_se_valora_por_flujos():
    v = calcular(fundamentos(), perfil(), _supuestos(), pilar_valoracion=0.0, hoy=HOY)
    assert v.metodo == "flujos"
    assert set(v.votos) == {"flujos", "sin_crecimiento", "pares"}
    assert v.valor.pesimista < v.valor.base < v.valor.optimista
    assert v.veredicto in VEREDICTOS


def test_un_banco_se_valora_por_beneficio_residual():
    p = perfil(industria="Banks - Regional")
    v = calcular(fundamentos(), p, _supuestos(p=p), pilar_valoracion=0.0, hoy=HOY)
    assert v.metodo == "residual"
    assert v.votos["sin_crecimiento"].voto == NO_APLICA
    assert v.votos["sin_crecimiento"].motivo == "financiera"
    assert v.implicito.magnitud == "roe"


def test_una_empresa_que_quema_caja_no_vota_flujos():
    f = fundamentos(ejercicios=[ejercicio(2026 - i, flujo_operativo=50.0) for i in range(4)])
    v = calcular(f, perfil(), _supuestos(f=f), pilar_valoracion=0.0, hoy=HOY)
    assert (v.votos["flujos"].voto, v.votos["flujos"].motivo) == (NO_APLICA, "quema_caja")
    assert v.valor is None


def test_un_banco_con_patrimonio_negativo_no_vota_flujos():
    f = fundamentos(ejercicios=[ejercicio(2026, patrimonio_neto=-10.0), ejercicio(2025), ejercicio(2024)])
    p = perfil(industria="Banks - Regional")
    v = calcular(f, p, _supuestos(f=f, p=p), pilar_valoracion=0.0, hoy=HOY)
    assert v.votos["flujos"].motivo == "patrimonio_negativo"


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


def test_el_margen_de_seguridad_es_relativo_al_precio():
    v = calcular(fundamentos(), perfil(), _supuestos(), 0.0, HOY)
    assert v.margen_seguridad == pytest.approx((v.valor.base - 100.0) / 100.0)


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


def test_un_nan_en_una_procedencia_se_escribe_como_null():
    v = calcular(fundamentos(), perfil(), _supuestos(), 0.0, HOY)
    sup = replace(v.supuestos, g_ref=replace(v.supuestos.g_ref, procedencia={"consenso": float("nan")}))
    plano = a_dict(replace(v, supuestos=sup))
    assert plano["supuestos"]["g_ref"]["procedencia"]["consenso"] is None
    json.dumps(plano, allow_nan=False)


def test_una_fallida_dice_su_motivo_y_nada_mas():
    assert fallida("sin_precio", HOY) == {"version": "m1", "fecha": "2026-10-12", "motivo": "sin_precio"}


@pytest.fixture
def red_doble():
    with patch.object(mercado, "perfil", return_value=(perfil(), "ok")), patch.object(
        mercado, "tasa_libre", return_value=(0.04, "ok")
    ), patch.object(mercado, "beta", return_value=(None, "sin_regresion")), patch.object(
        mercado, "tasa_efectiva", return_value=(0.25, "ok")
    ), patch.object(mercado, "consenso", return_value=(None, "sin_consenso")), patch(
        "valoracion.motor.desde_sec", return_value=(fundamentos(), "ok")
    ):
        yield


def test_valorar_compone_todo_sin_red(red_doble):
    plano = valorar("TST", 0.3, hoy=HOY)
    json.dumps(plano, allow_nan=False)
    assert plano["veredicto"] in VEREDICTOS
    assert plano["votos"]["pares"]["voto"] == "neutra"


def test_sin_precio_valorar_dice_por_que(red_doble):
    with patch.object(mercado, "perfil", return_value=(None, "sin_red")):
        assert valorar("TST", 0.3, hoy=HOY)["motivo"] == "sin_precio"


def test_sin_tasa_libre_valorar_dice_por_que(red_doble):
    with patch.object(mercado, "tasa_libre", return_value=(None, "sin_tasa_libre")):
        assert valorar("TST", 0.3, hoy=HOY)["motivo"] == "sin_tasa_libre"


def test_sin_estados_valorar_dice_por_que(red_doble):
    with patch("valoracion.motor.desde_sec", return_value=(None, "sin_estados")):
        assert valorar("TST", 0.3, hoy=HOY)["motivo"] == "sin_estados"

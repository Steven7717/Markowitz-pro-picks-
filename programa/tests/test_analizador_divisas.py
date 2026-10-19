import math
from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest

from analizador import divisas
from analizador.divisas import (
    Divisa,
    adr_dudosa,
    cociente_adr,
    convertir,
    moneda_de_valoracion,
    perfil_en,
)
from seguimiento.banxico import Serie
from tests.dobles_valoracion import ejercicio, fundamentos, perfil


@pytest.mark.parametrize(
    "estados, esperado", [("USD", "USD"), ("MXN", "MXN"), ("TWD", "USD"), ("CAD", "USD")]
)
def test_la_moneda_de_la_valoracion(estados, esperado):
    assert moneda_de_valoracion(estados) == esperado


def test_convertir_multiplica_todo_lo_que_es_dinero():
    f = fundamentos(ejercicios=[ejercicio(2025, gasto_financiero=float("nan"))])
    c = convertir(f, 0.031, "USD")
    e, o = c.ultimo, f.ultimo
    assert c.moneda == "USD"
    assert e.ingresos == pytest.approx(o.ingresos * 0.031)
    assert e.capex == pytest.approx(o.capex * 0.031)
    assert e.patrimonio_neto == pytest.approx(o.patrimonio_neto * 0.031)
    assert c.deuda_total == pytest.approx(f.deuda_total * 0.031)
    assert c.efectivo == pytest.approx(f.efectivo * 0.031)
    assert e.fin == o.fin
    # «No declarado» sigue siendo «no declarado».
    assert math.isnan(e.gasto_financiero)


def test_convertir_a_la_misma_moneda_no_cambia_nada():
    f = fundamentos()
    assert convertir(f, 1.0, "USD") is f


def test_el_precio_se_lleva_a_la_moneda_de_la_valoracion():
    p = perfil_en(perfil(precio=100.0, capitalizacion=1000.0, moneda="CAD"), 0.7, "USD")
    assert (p.precio, p.capitalizacion, p.moneda, p.moneda_estados) == (70.0, 700.0, "USD", "USD")


def test_en_londres_la_capitalizacion_va_en_libras_y_el_precio_en_peniques():
    # SHEL.L el 2026-10-14: precio 3.911,5 peniques, capitalización 222.520
    # millones de libras y 5.688,9 millones de acciones. Capitalización ÷ precio
    # sin corregir da las acciones entre cien.
    shel = perfil(precio=3911.5, capitalizacion=222_519_934_976.0, moneda="GBp")
    p = perfil_en(shel, 0.013237, "USD")
    assert p.precio == pytest.approx(3911.5 * 0.013237)
    assert p.capitalizacion / p.precio == pytest.approx(5_688_864_370.0, rel=1e-6)


def test_el_cociente_de_la_adr():
    # TSM: yfinance da el recuento en base ADR, así que cuadra.
    tsm = perfil(precio=430.0, capitalizacion=2_230_183_788_544.0)
    assert cociente_adr(5_186_474_013.0, tsm) == pytest.approx(1.0, abs=1e-3)
    assert not adr_dudosa(cociente_adr(5_186_474_013.0, tsm))
    # Con el recuento de acciones ordinarias, cinco por ADR, saltaría el aviso.
    assert adr_dudosa(cociente_adr(5 * 5_186_474_013.0, tsm))


def test_sin_recuento_no_hay_cociente():
    assert cociente_adr(float("nan"), perfil()) is None
    assert cociente_adr(None, perfil()) is None
    assert not adr_dudosa(None)


def _cambio(tipos):
    def tipo_de_cambio(origen, destino):
        if (origen, destino) in tipos:
            return tipos[(origen, destino)]
        return (1.0, "ok") if origen == destino else (None, "sin_red")

    return tipo_de_cambio


def test_tsm_se_valora_en_dolares_con_los_estados_convertidos():
    cambio = _cambio({("TWD", "USD"): (0.031, "ok")})
    with patch.object(divisas.mercado, "tipo_de_cambio", side_effect=cambio):
        d, motivo = divisas.divisa("TWD", "USD")
    assert motivo == "ok"
    assert d == Divisa("TWD", "USD", "USD", 0.031, 1.0, "^GSPC")
    assert d.convertida


def test_walmex_se_valora_en_pesos_contra_el_ipc_sin_convertir():
    with patch.object(divisas.mercado, "tipo_de_cambio", side_effect=_cambio({})):
        d, _ = divisas.divisa("MXN", "MXN")
    assert d == Divisa("MXN", "MXN", "MXN", 1.0, 1.0, "^MXX")
    assert not d.convertida


def test_sin_tipo_de_cambio_no_hay_divisa_y_se_dice_por_que():
    with patch.object(divisas.mercado, "tipo_de_cambio", side_effect=_cambio({})):
        assert divisas.divisa("CAD", "CAD") == (None, "sin_red")


def test_la_divisa_como_diccionario_dice_si_falta_la_prima_pais():
    d = Divisa("TWD", "USD", "USD", 0.031, 1.0, "^GSPC")
    assert d.a_dict() == {
        "moneda_estados": "TWD",
        "moneda_precio": "USD",
        "moneda_valoracion": "USD",
        "tipo_estados": 0.031,
        "tipo_precio": 1.0,
        "indice_beta": "^GSPC",
        "sin_prima_pais": True,
    }


def test_el_bono_m_es_el_ultimo_dato_en_tanto_por_uno_con_su_fecha():
    datos = pd.Series([9.10, 9.25], index=pd.DatetimeIndex(["2026-08-27", "2026-09-24"]))
    with patch.object(divisas.banxico, "traer", return_value=Serie(datos, "ok")) as traer:
        assert divisas.bono_m("t" * 64, hoy=date(2026, 10, 14)) == (
            pytest.approx(0.0925),
            "ok",
            date(2026, 9, 24),
        )
    serie, desde, hasta, clave = traer.call_args.args
    assert serie == "SF44071" and hasta == date(2026, 10, 14)
    assert (hasta - desde).days == divisas.DIAS_BONO_M


def test_sin_token_el_bono_m_lo_dice():
    with patch.object(divisas.banxico, "traer", return_value=Serie(None, "sin_token")):
        assert divisas.bono_m("") == (None, "sin_token", None)


def test_sin_subasta_en_la_ventana_no_hay_bono_m():
    vacia = pd.Series([], index=pd.DatetimeIndex([]), dtype=float)
    with patch.object(divisas.banxico, "traer", return_value=Serie(vacia, "ok")):
        assert divisas.bono_m("t" * 64) == (None, "sin_dato", None)

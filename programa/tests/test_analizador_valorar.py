"""La valoración de cualquier ticker, con la red sustituida."""

import json
from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest

from analizador import valorar as v
from analizador.divisas import Divisa
from analizador.resolver import Resuelto
from tests.dobles_valoracion import fundamentos, perfil
from valoracion.mercado import Beta

USD = Divisa("USD", "USD", "USD", 1.0, 1.0, "^GSPC")
MXN = Divisa("MXN", "MXN", "MXN", 1.0, 1.0, "^MXX")


def _entradas(**sobre):
    valores = dict(
        ticker="TST",
        fundamentos=fundamentos(),
        perfil=perfil(),
        divisa=USD,
        r_f=0.05,
        procedencia_r_f={"fuente": "tesoro_10", "serie": "^TNX"},
        motivo_r_f="ok",
        beta=Beta(1.1, 0.4, 104, "^GSPC"),
        tasa=0.21,
        consenso=0.10,
        motivos={"beta": "ok", "tasa": "ok", "consenso": "ok"},
        cociente_adr=None,
    )
    valores.update(sobre)
    return v.Entradas(**valores)


def test_la_valoracion_con_los_supuestos_del_programa_es_json_estricto_y_lleva_la_divisa():
    plano = v.valorar(_entradas(), 0.6, hoy=date(2026, 10, 14))
    json.dumps(plano, allow_nan=False)
    assert plano["version"] == "m1" and "veredicto" in plano
    assert plano["divisa"] == {**USD.a_dict(), "sin_prima_pais": False}
    assert plano["votos"]["pares"]["voto"] == "barata"


def test_con_cambios_la_valoracion_es_la_de_los_deslizadores():
    sin = v.valorar(_entradas(), None)
    con = v.valorar(_entradas(), None, cambios={"g_ref": 0.30})
    assert con["supuestos"]["g_ref"]["procedencia"]["fuente"] == "usuario"
    assert con["valor"]["base"] > sin["valor"]["base"]


def test_valorar_es_puro_mismas_entradas_mismo_resultado():
    e = _entradas()
    assert v.valorar(e, 0.1, hoy=date(2026, 10, 14)) == v.valorar(e, 0.1, hoy=date(2026, 10, 14))


def test_una_emisora_en_pesos_sin_bono_m_no_se_valora_hasta_que_se_pone_la_tasa():
    e = _entradas(divisa=MXN, r_f=None, motivo_r_f="sin_token",
                  procedencia_r_f={"fuente": "bono_m_10", "serie": "SF44071", "fecha": None})
    assert v.valorar(e, None)["motivo"] == "sin_bono_m"
    con_tasa = v.valorar(e, None, cambios={"r_f": 0.092})
    assert con_tasa["supuestos"]["r_f"] == {
        "valor": 0.092,
        "procedencia": {"fuente": "usuario", "programa": None},
    }
    assert "veredicto" in con_tasa


def test_sin_tasa_libre_en_dolares_el_motivo_es_el_de_siempre():
    assert v.valorar(_entradas(r_f=None, motivo_r_f="sin_tasa_libre"), None)["motivo"] == "sin_tasa_libre"


def test_una_tasa_puesta_a_mano_que_no_es_un_numero_se_rechaza():
    e = _entradas(divisa=MXN, r_f=None)
    with pytest.raises(ValueError):
        v.valorar(e, None, cambios={"r_f": "nueve"})


def test_la_sensibilidad_usa_los_mismos_datos_que_el_voto():
    e = _entradas()
    tabla = v.sensibilidad(e, None)
    plano = v.valorar(e, None)
    assert tabla.valores[2][2] == pytest.approx(plano["valor"]["base"])


def test_sin_holgura_de_gordon_hay_tabla_con_la_casilla_central_vacia():
    e = _entradas()
    tabla = v.sensibilidad(e, {"g_perpetuo": 0.085})
    assert tabla is not None
    assert tabla.valores[2][2] is None
    assert any(valor is not None for fila in tabla.valores for valor in fila)


def test_una_financiera_no_tiene_tabla_de_sensibilidad():
    e = _entradas(perfil=perfil(industria="Banks - Regional"))
    assert v.sensibilidad(e, None) is None


# --- `entradas`, con la red sustituida ---------------------------------------


class _Red:
    """Lo que cada función de red devolvería, por nombre."""

    def __init__(self, **sobre):
        self.respuestas = dict(
            perfil=(perfil(), "ok"),
            tasa_libre=(0.05, "ok"),
            beta=(Beta(1.1, 0.4, 104, "^GSPC"), "ok"),
            tasa_efectiva=(0.21, "ok"),
            consenso=(0.10, "ok"),
            estados=(None, "sin_red"),
        )
        self.respuestas.update(sobre)
        self.llamadas = []

    def __enter__(self):
        self._parches = []
        for nombre, respuesta in self.respuestas.items():
            parche = patch.object(v.mercado, nombre, side_effect=self._registrar(nombre, respuesta))
            parche.start()
            self._parches.append(parche)
        return self

    def __exit__(self, *_):
        for parche in self._parches:
            parche.stop()

    def _registrar(self, nombre, respuesta):
        def llamada(*args):
            self.llamadas.append((nombre, args))
            return respuesta

        return llamada


SEC = Resuelto("MU", "sec", None, None)


def test_una_empresa_de_la_sec_se_valora_con_edgar_en_dolares():
    with _Red() as red, patch.object(v, "desde_sec", return_value=(fundamentos(), "ok")):
        e, motivo = v.entradas(SEC)
    assert motivo == "ok"
    assert e.divisa == USD
    assert e.procedencia_r_f == {"fuente": "tesoro_10", "serie": "^TNX"}
    assert ("beta", ("MU", "^GSPC", None)) in red.llamadas


def test_sin_perfil_no_hay_entradas():
    with _Red(perfil=(None, "sin_red")):
        assert v.entradas(SEC) == (None, "sin_red")
    with _Red(perfil=(None, "sin_precio")):
        assert v.entradas(SEC) == (None, "sin_precio")


def _estados_walmex():
    def hoja(fechas, filas):
        return pd.DataFrame(filas, index=[pd.Timestamp(f) for f in fechas]).T

    anios = ["2025-12-31", "2024-12-31", "2023-12-31", "2022-12-31"]
    return {
        "quarterly_income_stmt": hoja(["2026-06-30"], {"Diluted Average Shares": [17.16e9]}),
        "quarterly_balance_sheet": pd.DataFrame(),
        "quarterly_cashflow": pd.DataFrame(),
        "income_stmt": hoja(anios, {
            "Total Revenue": [1.011e12, 9.575e11, 8.857e11, 8.182e11],
            "Operating Income": [7.849e10, 7.736e10, 7.328e10, 6.801e10],
            "Net Income Common Stockholders": [4.989e10, 5.383e10, 5.159e10, 4.897e10],
            "Interest Expense": [9.115e9, 8.593e9, 7.837e9, 7.05e9],
        }),
        "balance_sheet": hoja(anios, {
            "Stockholders Equity": [2.356e11, 2.329e11, 1.991e11, 2.025e11],
            "Total Debt": [8.085e10, 7.973e10, 7.525e10, 6.984e10],
            "Cash And Cash Equivalents": [2.859e10, 3.651e10, 4.067e10, 4.743e10],
        }),
        "cashflow": hoja(anios, {
            "Operating Cash Flow": [8.244e10, 7.264e10, 8.512e10, 6.447e10],
            "Capital Expenditure": [-3.898e10, -3.476e10, -2.879e10, -2.13e10],
        }),
    }


WALMEX = Resuelto("WALMEX.MX", "sin_sec", None, None)
PERFIL_WALMEX = perfil(
    ticker="WALMEX.MX", precio=47.71, capitalizacion=8.2158e11, moneda="MXN",
    moneda_estados="MXN", industria="Discount Stores", pais="Mexico",
)


def test_walmex_se_valora_en_pesos_con_el_bono_m_y_contra_el_ipc():
    red = _Red(perfil=(PERFIL_WALMEX, "ok"), estados=(_estados_walmex(), "ok"),
               tipo_de_cambio=(1.0, "ok"))
    with red, patch.object(v.divisas, "bono_m", return_value=(0.0925, "ok", date(2026, 9, 24))):
        e, motivo = v.entradas(WALMEX)
    assert motivo == "ok"
    assert e.divisa.moneda_valoracion == "MXN" and e.divisa.indice_beta == "^MXX"
    assert e.r_f == 0.0925
    assert e.procedencia_r_f == {"fuente": "bono_m_10", "serie": "SF44071", "fecha": "2026-09-24"}
    assert ("beta", ("WALMEX.MX", "^MXX", None)) in red.llamadas
    assert e.fundamentos.fuente == "yfinance" and len(e.fundamentos.ejercicios) == 4
    assert e.cociente_adr == pytest.approx(17.16e9 / (8.2158e11 / 47.71), rel=1e-3)
    plano = v.valorar(e, None)
    assert plano["supuestos"]["r_f"]["procedencia"]["fuente"] == "bono_m_10"
    assert plano["moneda"] == "MXN"


def test_sin_token_de_banxico_walmex_tiene_entradas_pero_no_valoracion():
    red = _Red(perfil=(PERFIL_WALMEX, "ok"), estados=(_estados_walmex(), "ok"),
               tipo_de_cambio=(1.0, "ok"))
    with red, patch.object(v.divisas, "bono_m", return_value=(None, "sin_token", None)):
        e, motivo = v.entradas(WALMEX)
    assert motivo == "ok" and e.r_f is None and e.motivo_r_f == "sin_token"
    assert v.valorar(e, None)["motivo"] == "sin_bono_m"


def test_tsm_convierte_los_estados_a_dolares_y_compara_el_consenso_en_su_moneda():
    perfil_tsm = perfil(ticker="TSM", precio=430.0, capitalizacion=2.23e12,
                        moneda="USD", moneda_estados="TWD", pais="Taiwan")

    def tipo_de_cambio(origen, destino):
        return {("TWD", "USD"): (0.031, "ok"), ("USD", "USD"): (1.0, "ok")}[(origen, destino)]

    tsm = Resuelto("TSM", "extranjera_sec", None, None)
    red = _Red(perfil=(perfil_tsm, "ok"), estados=(_estados_walmex(), "ok"))
    with red, patch.object(v.mercado, "tipo_de_cambio", side_effect=tipo_de_cambio):
        e, _ = v.entradas(tsm)
    assert e.divisa.convertida and e.divisa.moneda_valoracion == "USD"
    assert e.fundamentos.moneda == "USD"
    assert e.fundamentos.ultimo.ingresos == pytest.approx(1.011e12 * 0.031)
    assert ("consenso", ("TSM", "TWD")) in red.llamadas
    assert v.valorar(e, None)["divisa"]["sin_prima_pais"] is True


def test_una_adr_en_dolares_con_estados_en_pesos_regresa_su_precio_en_pesos():
    perfil_amx = perfil(ticker="AMX", precio=22.885, capitalizacion=6.83e10, moneda="USD",
                        moneda_estados="MXN", pais="Mexico")

    def tipo_de_cambio(origen, destino):
        return {("MXN", "MXN"): (1.0, "ok"), ("USD", "MXN"): (18.40, "ok")}[(origen, destino)]

    amx = Resuelto("AMX", "extranjera_sec", None, None)
    red = _Red(perfil=(perfil_amx, "ok"), estados=(_estados_walmex(), "ok"))
    with red, patch.object(v.mercado, "tipo_de_cambio", side_effect=tipo_de_cambio), \
            patch.object(v.divisas, "bono_m", return_value=(0.0925, "ok", date(2026, 9, 24))):
        e, _ = v.entradas(amx)
    assert e.divisa.moneda_valoracion == "MXN"
    assert ("beta", ("AMX", "^MXX", "USDMXN=X")) in red.llamadas
    # En pesos el Bono M ya lleva el riesgo de México.
    assert v.valorar(e, None)["divisa"]["sin_prima_pais"] is False


def test_una_extranjera_que_presenta_en_dolares_tambien_va_sin_prima_pais():
    teva = _entradas(perfil=perfil(pais="Israel"))
    assert v.valorar(teva, None)["divisa"]["sin_prima_pais"] is True


def test_sin_tipo_de_cambio_no_hay_entradas():
    perfil_cad = perfil(ticker="RY.TO", moneda="CAD", moneda_estados="CAD")
    red = _Red(perfil=(perfil_cad, "ok"), estados=(_estados_walmex(), "ok"))
    with red, patch.object(v.mercado, "tipo_de_cambio", return_value=(None, "sin_red")):
        assert v.entradas(Resuelto("RY.TO", "sin_sec", None, None)) == (None, "sin_red")


def test_sin_estados_de_yahoo_no_hay_entradas():
    with _Red(perfil=(PERFIL_WALMEX, "ok"), estados=(None, "sin_red")):
        assert v.entradas(WALMEX) == (None, "sin_red")

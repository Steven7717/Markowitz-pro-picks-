"""Los deslizadores de la valoración: qué se mueve, entre qué cifras y qué cuenta como movido."""

import pytest

from analizador import deslizadores as d
from analizador import valorar as v
from tests.dobles_valoracion import perfil
from tests.test_analizador_valorar import _en_pesos, _entradas


def test_en_una_de_flujos_se_mueven_los_supuestos_del_dcf():
    assert d.movibles(d.metodo(_entradas())) == ("r_f", "beta", "prima", "k_d", "t", "g_ref", "g_perpetuo")


def test_en_una_financiera_no_se_mueven_la_deuda_ni_los_impuestos():
    banco = _entradas(perfil=perfil(industria="Banks - Regional"))
    assert d.metodo(banco) == "residual"
    assert d.movibles("residual") == ("r_f", "beta", "prima", "roe_ref", "payout", "g_perpetuo")


def test_los_deslizadores_no_dependen_de_la_pantalla():
    # La lista de supuestos de cada método es de la valoración, no de un
    # módulo de textos: los deslizadores y la lista de debajo leen la misma.
    import ast
    import inspect

    import medidores_valoracion
    from valoracion import supuestos

    arbol = ast.parse(inspect.getsource(d))
    importados = {n.module for n in ast.walk(arbol) if isinstance(n, ast.ImportFrom)}
    assert "medidores_valoracion" not in importados
    assert medidores_valoracion.SUPUESTOS_DE is supuestos.SUPUESTOS_DE


def test_lo_derivado_nunca_tiene_deslizador():
    for metodo in ("flujos", "residual"):
        assert not {"k_e", "wacc"} & set(d.movibles(metodo))


def test_un_porcentaje_se_ensena_en_puntos_y_la_beta_tal_cual():
    assert d.a_pantalla("r_f", 0.0412) == pytest.approx(4.12)
    assert d.de_pantalla("r_f", 4.12) == pytest.approx(0.0412)
    assert d.a_pantalla("beta", 1.13) == 1.13


def test_el_recorrido_se_ensancha_para_que_quepa_la_cifra_del_programa():
    r = d.rango("beta", 3.4)
    assert (r.minimo, r.maximo, r.porcentaje) == (-1.0, 3.4, False)
    r = d.rango("g_ref", 0.05)
    assert (r.minimo, r.maximo) == pytest.approx((-20.0, 60.0))
    assert r.formato.endswith("%%")
    assert d.rango("g_ref", None).maximo == pytest.approx(60.0)
    # Por abajo también: una beta medida de −1,5 no se queda en −1.
    assert d.rango("beta", -1.5).minimo == -1.5


def test_las_cifras_del_programa_son_las_de_sus_supuestos():
    e = _entradas()
    s = v.supuestos_de(e)
    assert d.del_programa(e) == {n: getattr(s, n).valor for n in d.movibles("flujos")}


def test_sin_tasa_libre_no_hay_cifras_hasta_que_se_pone_a_mano():
    sin = _en_pesos(r_f=None, motivo_r_f="sin_token")
    assert d.del_programa(sin) is None
    programa = d.del_programa(sin, 0.09)
    assert programa["r_f"] == 0.09
    # Lo demás se deduce con ella: el crecimiento perpetuo no la pasa.
    assert programa["g_perpetuo"] <= 0.09


def test_una_tasa_a_mano_que_rompe_las_formulas_se_rechaza():
    with pytest.raises(ValueError):
        d.del_programa(_en_pesos(r_f=None, motivo_r_f="sin_token"), -0.50)


def test_un_deslizador_sin_tocar_no_cuenta_como_movido():
    e = _entradas()
    programa = d.del_programa(e)
    en_pantalla = {n: d.a_pantalla(n, valor) for n, valor in programa.items()}
    assert d.cambios(en_pantalla, programa) == {}
    # Y la valoración es la del programa, sin un solo «movido por ti».
    assert v.valorar(e, 0.4, d.cambios(en_pantalla, programa)) == v.valorar(e, 0.4)


def test_el_redondeo_de_ida_y_vuelta_no_cuenta_como_movido():
    # 0,029 × 100 ÷ 100 no da 0,029 en coma flotante.
    assert d.a_pantalla("g_perpetuo", 0.029) / 100 != 0.029
    assert d.cambios({"g_perpetuo": d.a_pantalla("g_perpetuo", 0.029)}, {"g_perpetuo": 0.029}) == {}


def test_lo_movido_llega_en_tanto_por_uno():
    e = _entradas()
    programa = d.del_programa(e)
    en_pantalla = {n: d.a_pantalla(n, valor) for n, valor in programa.items()}
    en_pantalla["g_ref"] = 30.0
    en_pantalla["beta"] = 1.5
    assert d.cambios(en_pantalla, programa) == {"g_ref": pytest.approx(0.30), "beta": 1.5}


def test_una_casilla_vacia_no_cuenta_y_una_cifra_sin_programa_si():
    assert d.cambios({"g_ref": None}, {"g_ref": 0.05}) == {}
    assert d.cambios({"roe_ref": 12.0}, {"roe_ref": None}) == {"roe_ref": pytest.approx(0.12)}


def test_la_tasa_puesta_a_mano_va_siempre():
    assert d.cambios({}, {"r_f": 0.09}, r_f_a_mano=0.09) == {"r_f": 0.09}


def test_los_movidos_salen_de_supuestos_movidos():
    e = _entradas()
    assert d.nombres_movidos(e, {}) == ()
    assert d.nombres_movidos(e, {"beta": 1.5, "g_ref": 0.30}) == ("beta", "g_ref")
    assert d.nombres_movidos(_en_pesos(r_f=None, motivo_r_f="sin_token"), {"r_f": 0.09}) == ("r_f",)
    # Sin tasa libre y sin ponerla a mano no hay supuestos, ni movidos.
    assert d.nombres_movidos(_en_pesos(r_f=None, motivo_r_f="sin_token"), {}) == ()

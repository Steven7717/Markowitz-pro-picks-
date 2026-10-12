"""El criterio no se prueba por sus valores --esos los fija el spec-- sino por
su coherencia: limites ordenados, monedas cubiertas, y la frontera de la lista
de financieras, que es donde un descuido cambia el metodo de valoracion."""

import pytest

from valoracion import criterio as c


def test_la_proyeccion_dura_diez_anos():
    assert c.ANOS_ALTO_CRECIMIENTO + c.ANOS_CONVERGENCIA == 10


def test_el_crecimiento_perpetuo_cubre_las_dos_monedas_que_se_valoran():
    assert set(c.CRECIMIENTO_PERPETUO) == {"USD", "MXN"}


def test_la_tasa_legal_tiene_respaldo_para_cualquier_pais():
    assert {"US", "MX", "otros"} <= set(c.TASA_LEGAL)


@pytest.mark.parametrize(
    "limites",
    [
        c.TASA_EFECTIVA_TOPES,
        c.CRECIMIENTO_REF_TOPES,
        c.INVERSO_LIMITES,
        c.INVERSO_ROE_LIMITES,
    ],
)
def test_los_limites_estan_ordenados(limites):
    bajo, alto = limites
    assert bajo < alto


def test_blume_deja_una_beta_de_uno_en_uno():
    a, b = c.BLUME
    assert a * 1.0 + b == pytest.approx(1.0)


def test_credit_services_y_los_corredores_no_son_financieras():
    # Visa, Mastercard y PayPal viven en Credit Services: su flujo de caja si
    # significa algo. Un corredor de seguros no tiene balance de riesgo.
    assert "Credit Services" not in c.INDUSTRIAS_FINANCIERAS
    assert "Insurance Brokers" not in c.INDUSTRIAS_FINANCIERAS
    assert "Asset Management" not in c.INDUSTRIAS_FINANCIERAS


def test_bancos_y_aseguradoras_de_riesgo_son_financieras():
    assert {
        "Banks - Diversified",
        "Banks - Regional",
        "Insurance - Life",
        "Insurance - Property & Casualty",
    } <= c.INDUSTRIAS_FINANCIERAS

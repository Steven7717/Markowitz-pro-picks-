"""El criterio no se prueba por sus valores (esos los fija el spec) sino por
su coherencia: límites ordenados, monedas cubiertas, constantes que se
respetan entre sí y la frontera de la lista de financieras, que es donde un
descuido cambia el método de valoración."""

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
    ids=["tasa_efectiva", "crecimiento_ref", "inverso", "inverso_roe"],
)
def test_los_limites_estan_ordenados(limites):
    bajo, alto = limites
    assert bajo < alto


def test_blume_deja_una_beta_de_uno_en_uno():
    a, b = c.BLUME
    assert a * 1.0 + b == pytest.approx(1.0)


# --- Invariantes entre constantes ---------------------------------------------
# Cada una vigila una pareja de valores que el spec fija por separado pero que
# sólo funcionan juntos: si alguien mueve una sin la otra, el fallo aparece
# aquí y no como un veredicto raro semanas después.


def test_el_crecimiento_de_referencia_cabe_dentro_de_los_limites_del_inverso():
    # La bisección del DCF inverso busca el crecimiento implícito dentro de
    # INVERSO_LIMITES; si un crecimiento que el propio criterio considera
    # válido cae fuera, no hay raíz que acotar.
    bajo, alto = c.INVERSO_LIMITES
    for g in c.CRECIMIENTO_REF_TOPES:
        assert bajo < g < alto


def test_el_crecimiento_perpetuo_cabe_dentro_de_los_limites_del_inverso():
    bajo, alto = c.INVERSO_LIMITES
    for g in c.CRECIMIENTO_PERPETUO.values():
        assert bajo < g < alto


def test_la_tasa_legal_cabe_dentro_de_los_topes_de_la_tasa_efectiva():
    # La tasa legal es el respaldo de la efectiva: no puede quedar fuera del
    # rango que se le exige a la efectiva.
    bajo, alto = c.TASA_EFECTIVA_TOPES
    for tasa in c.TASA_LEGAL.values():
        assert bajo <= tasa <= alto


def test_el_minimo_de_semanas_de_beta_es_menor_que_la_ventana():
    assert c.BETA_SEMANAS_MIN < c.BETA_SEMANAS


def test_el_minimo_de_votos_cabe_entre_los_tres_que_hay():
    assert 1 <= c.MIN_VOTOS <= 3


def test_la_holgura_de_gordon_es_positiva():
    assert c.HOLGURA_GORDON > 0


# --- Frontera de las financieras ----------------------------------------------


def test_credit_services_y_los_corredores_no_son_financieras():
    # Visa, Mastercard y PayPal viven en Credit Services: su flujo de caja sí
    # significa algo. Un corredor de seguros no tiene balance de riesgo.
    assert "Credit Services" not in c.INDUSTRIAS_FINANCIERAS
    assert "Insurance Brokers" not in c.INDUSTRIAS_FINANCIERAS
    assert "Asset Management" not in c.INDUSTRIAS_FINANCIERAS


def test_la_lista_de_financieras_es_exactamente_esta():
    # Se fija entera, no por inclusión: añadir una industria cambia el método
    # de valoración de todas sus empresas y tiene que ser una decisión visible.
    assert c.INDUSTRIAS_FINANCIERAS == frozenset(
        {
            "Banks - Diversified",
            "Banks - Regional",
            "Insurance - Life",
            "Insurance - Property & Casualty",
            "Insurance - Diversified",
            "Insurance - Reinsurance",
            "Insurance - Specialty",
            "Capital Markets",
            "Mortgage Finance",
        }
    )

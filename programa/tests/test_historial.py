"""El compromiso entre cuántos activos llevas y cuánta historia comparten."""

import numpy as np
import pandas as pd
import pytest

from historial import Escalon, escalera, motivo_de

FECHAS = pd.bdate_range("2020-01-01", periods=200)


def _serie(desde: int = 0, hasta: int | None = None, huecos: list[int] | None = None):
    """Una serie de precios viva entre dos posiciones, con huecos si se piden."""
    s = pd.Series(np.linspace(100.0, 200.0, len(FECHAS)), index=FECHAS)
    s.iloc[:desde] = np.nan
    if hasta is not None:
        s.iloc[hasta:] = np.nan
    for i in huecos or []:
        s.iloc[i] = np.nan
    return s


def _precios(**columnas) -> pd.DataFrame:
    return pd.DataFrame(columnas)


# ── Por qué un activo recorta la muestra ──────────────────────────────────────

def test_un_activo_que_cotiza_desde_hace_poco_es_arranque_tardio():
    """PLTR desde 2020-10 no es una serie rota: es una empresa joven.

    El dato anterior a su salida a bolsa no existe, y llamarlo «incompleto»
    manda a buscar un fallo donde no lo hay.
    """
    assert motivo_de(_serie(desde=150), FECHAS[-1]) == "arranque"


def test_una_serie_entera_no_recorta_nada():
    assert motivo_de(_serie(), FECHAS[-1]) == "completa"


def test_una_serie_que_se_corta_antes_del_final_esta_interrumpida():
    """La firma de una fuente rota, que es lo que le pasaba a AVB.

    Medido el 2026-09-13: yfinance devolvia 27 precios de 251 para AVB, todos
    entre el 17-jul y el 24-ago, y nada despues. No es una empresa joven ni una
    serie con huecos: es una isla.
    """
    assert motivo_de(_serie(desde=100, hasta=130), FECHAS[-1]) == "interrumpida"


def test_una_serie_agujereada_por_dentro_son_huecos():
    agujeros = list(range(20, 60, 2))  # la mitad de un tramo largo
    assert motivo_de(_serie(huecos=agujeros), FECHAS[-1]) == "huecos"


def test_un_hueco_suelto_no_convierte_una_serie_en_agujereada():
    assert motivo_de(_serie(huecos=[37]), FECHAS[-1]) == "completa"


def test_una_serie_vacia_se_dice_vacia():
    vacia = pd.Series(np.nan, index=FECHAS)
    assert motivo_de(vacia, FECHAS[-1]) == "sin datos"


# ── La escalera ───────────────────────────────────────────────────────────────

def test_con_todas_las_series_enteras_la_escalera_tiene_un_solo_peldano():
    """No hay nada que ofrecer: quitar activos no daría ni una fecha más."""
    esc = escalera(_precios(AAA=_serie(), BBB=_serie(), CCC=_serie()))
    assert len(esc) == 1
    assert esc[0].fuera == ()
    assert esc[0].observaciones == len(FECHAS)
    assert esc[0].corta is None


def test_el_primer_peldano_es_la_cartera_entera():
    esc = escalera(_precios(AAA=_serie(), BBB=_serie(), JOVEN=_serie(desde=150)))
    assert esc[0].fuera == ()
    assert esc[0].activos == 3
    assert esc[0].observaciones == 50


def test_el_peldano_nombra_a_quien_corta_la_muestra_y_desde_cuando():
    esc = escalera(_precios(AAA=_serie(), BBB=_serie(), JOVEN=_serie(desde=150)))
    assert esc[0].corta == "JOVEN"
    assert esc[0].motivo == "arranque"
    assert esc[0].desde == str(FECHAS[150].date())


def test_quitar_al_mas_joven_devuelve_la_historia_de_los_demas():
    esc = escalera(_precios(AAA=_serie(), BBB=_serie(), JOVEN=_serie(desde=150)))
    assert len(esc) == 2
    assert esc[1].fuera == ("JOVEN",)
    assert esc[1].activos == 2
    assert esc[1].observaciones == len(FECHAS)


def test_la_escalera_baja_de_uno_en_uno_por_orden_de_dano():
    """Cada peldaño quita al que más historia está costando en ese momento."""
    esc = escalera(_precios(
        VIEJA=_serie(), OTRA=_serie(),
        MEDIA=_serie(desde=80), JOVEN=_serie(desde=150),
    ))
    assert [e.fuera for e in esc] == [(), ("JOVEN",), ("JOVEN", "MEDIA")]
    assert [e.observaciones for e in esc] == [50, 120, 200]


def test_la_escalera_para_antes_de_quedarse_sin_cartera():
    """Con menos de dos activos no hay nada que repartir."""
    esc = escalera(_precios(A=_serie(desde=150), B=_serie(desde=80), C=_serie()))
    assert all(e.activos >= 2 for e in esc)


def test_se_puede_exigir_un_minimo_de_activos_mayor():
    esc = escalera(
        _precios(A=_serie(), B=_serie(), C=_serie(desde=80), D=_serie(desde=150)),
        minimo_activos=3,
    )
    assert all(e.activos >= 3 for e in esc)


def test_una_fuente_interrumpida_sale_la_primera_porque_es_la_que_mas_cuesta():
    """AVB costaba 56 veces la muestra; un activo joven, el doble."""
    esc = escalera(_precios(
        AAA=_serie(), BBB=_serie(),
        JOVEN=_serie(desde=100), ROTA=_serie(desde=150, hasta=160),
    ))
    assert esc[1].fuera == ("ROTA",)
    assert esc[0].corta == "ROTA"
    assert esc[0].motivo == "interrumpida"


def test_cada_peldano_gana_observaciones_sobre_el_anterior():
    esc = escalera(_precios(
        AAA=_serie(), BBB=_serie(),
        MEDIA=_serie(desde=80), JOVEN=_serie(desde=150),
    ))
    for antes, despues in zip(esc, esc[1:]):
        assert despues.observaciones > antes.observaciones


def test_un_marco_vacio_no_tiene_escalera():
    assert escalera(pd.DataFrame()) == []


def test_con_un_solo_activo_no_hay_escalera():
    assert escalera(_precios(AAA=_serie())) == []


# ── Lo que la pantalla necesita saber ─────────────────────────────────────────

def test_el_escalon_dice_cuanto_se_gana_respecto_al_primero():
    esc = escalera(_precios(AAA=_serie(), BBB=_serie(), JOVEN=_serie(desde=150)))
    assert esc[1].observaciones / esc[0].observaciones == pytest.approx(4.0)


def test_los_activos_que_se_quedan_fuera_se_acumulan():
    esc = escalera(_precios(
        A=_serie(), B=_serie(), C=_serie(desde=80), D=_serie(desde=150),
    ))
    for antes, despues in zip(esc, esc[1:]):
        assert set(antes.fuera) < set(despues.fuera)


def test_el_escalon_es_inmutable():
    e = Escalon(fuera=("X",), activos=2, observaciones=10,
                corta=None, motivo=None, desde=None, hasta=None)
    with pytest.raises(Exception):
        e.activos = 3


def test_perder_las_ultimas_fechas_ya_cuenta_como_interrumpida():
    """Dos es el margen de un puente; a la tercera la fuente esta fallando.

    Se cuenta en periodos y no en dias para que el umbral valga igual con datos
    diarios que mensuales: con una tolerancia de veinte, AVB pasaba por empresa
    joven en el horizonte mensual en vez de por fuente rota.
    """
    assert motivo_de(_serie(hasta=len(FECHAS) - 2), FECHAS[-1]) == "completa"
    assert motivo_de(_serie(hasta=len(FECHAS) - 6), FECHAS[-1]) == "interrumpida"


# ── El aviso por activo, donde la escalera no llega ───────────────────────────

from data import tickers_con_huecos
from historial import Cobertura, avisos_de_cobertura


def test_una_fuente_rota_se_avisa_aunque_la_escalera_calle_por_ser_dos_activos():
    """El hueco que deja la escalera: con dos activos no culpa a nadie.

    `_peldano` se para en seco cuando quitar a alguien dejaria menos de dos
    activos, asi que devuelve un unico peldano con `corta` en None y la pantalla
    no llega a pintarse. Dos activos es el minimo que el optimizador acepta, o
    sea el caso mas corriente que existe: AVB entra con 10 de sus 200 fechas y
    lo unico que el usuario lee es «datos insuficientes», sin saber cual de los
    dos lo provoca.
    """
    p = _precios(AAA=_serie(), AVB=_serie(desde=150, hasta=160))
    assert escalera(p)[0].corta is None

    aviso, = avisos_de_cobertura(p, {"AVB": 0.05})
    assert aviso.ticker == "AVB"
    assert aviso.motivo == "interrumpida"
    assert aviso.cobertura == 0.05


def test_dos_series_rotas_en_las_mismas_fechas_se_avisan_aunque_la_escalera_calle():
    """Quitar a una sola no gana ni una fecha, asi que la escalera no culpa a nadie.

    La escalera busca a quien mas historia cuesta **quitandolo de uno en uno**.
    Si dos activos fallan las mismas fechas, ninguno de los dos gana nada por
    separado y el aviso entero desaparece, con las dos series igual de rotas.
    """
    p = _precios(AAA=_serie(), ROTA=_serie(desde=150, hasta=160),
                 OTRA=_serie(desde=150, hasta=160))
    assert escalera(p)[0].corta is None

    avisos = avisos_de_cobertura(p, {"ROTA": 0.05, "OTRA": 0.05})
    assert [a.ticker for a in avisos] == ["OTRA", "ROTA"]


def test_un_activo_joven_no_se_avisa_por_mucho_que_cubra_poco():
    """PLTR cubre el 25% del horizonte y no le pasa nada.

    Es la razon de ser de `motivo_de`, y el aviso que se retiro de esta misma
    pantalla: llamar «serie incompleta» a una empresa que no cotizaba manda a
    buscar un fallo donde no lo hay. El dato anterior a su salida a bolsa no
    existe, y de eso ya habla la escalera como lo que es --un compromiso--.
    """
    p = _precios(AAA=_serie(), PLTR=_serie(desde=150))
    assert avisos_de_cobertura(p, {"PLTR": 0.25}) == []


def test_se_avisa_primero_del_que_menos_cubre():
    p = _precios(AAA=_serie(), MENOS=_serie(desde=150, hasta=160),
                 MAS=_serie(desde=20, hasta=60, huecos=[30, 31, 32, 33, 34, 35]))
    avisos = avisos_de_cobertura(p, {"MAS": 0.17, "MENOS": 0.05})
    assert [a.ticker for a in avisos] == ["MENOS", "MAS"]


def test_el_aviso_dice_entre_que_fechas_cotizo():
    """Para «la fuente dejo de dar precios»: la ultima es el dato que sirve."""
    p = _precios(AAA=_serie(), AVB=_serie(desde=150, hasta=160))
    aviso, = avisos_de_cobertura(p, {"AVB": 0.05})
    assert aviso.desde == str(FECHAS[150].date())
    assert aviso.hasta == str(FECHAS[159].date())


def test_sin_nadie_bajo_el_minimo_no_hay_avisos():
    assert avisos_de_cobertura(_precios(AAA=_serie(), BBB=_serie()), {}) == []


def test_un_marco_vacio_no_avisa_de_nada():
    assert avisos_de_cobertura(pd.DataFrame(), {"AAA": 0.1}) == []


def test_un_ticker_que_no_esta_en_los_precios_no_avisa():
    """Los descartados enteros ya los cuenta `invalid_tickers`, y van aparte."""
    assert avisos_de_cobertura(_precios(AAA=_serie()), {"ZZZZ": 0.0}) == []


def test_el_aviso_es_inmutable():
    c = Cobertura(ticker="X", cobertura=0.1, motivo="huecos", desde=None, hasta=None)
    with pytest.raises(Exception):
        c.cobertura = 0.9


def test_lo_que_mide_data_py_es_lo_que_llega_al_aviso():
    """Las dos mitades, juntas: quien mide la cobertura y quien decide si duele.

    `tickers_con_huecos` sabia desde el principio que AVB traia 27 precios de
    250 y nadie leia su respuesta. Este test es la costura: lo que sale de
    `data.py` entra en el aviso tal cual, con el mismo numero.
    """
    fechas = pd.bdate_range("2025-01-01", periods=250)
    completa = pd.Series(np.linspace(100, 130, 250), index=fechas)
    rota = pd.Series(np.nan, index=fechas)
    rota.iloc[:27] = np.linspace(200, 210, 27)
    p = pd.DataFrame({"AAA": completa, "AVB": rota})

    aviso, = avisos_de_cobertura(p, tickers_con_huecos(p))
    assert aviso.ticker == "AVB"
    assert aviso.cobertura == pytest.approx(27 / 250)
    assert aviso.motivo == "interrumpida"


def test_el_escalon_dice_hasta_cuando_cotizo_el_que_corta():
    """«Los ultimos precios son de…» necesita la ultima fecha, no la primera.

    El peldano solo llevaba `desde` --la primera cotizacion-- y la pantalla la
    pintaba detras de «la fuente deja de dar precios suyos; los ultimos son de»,
    anunciando el dia en que la serie **empezo** como el dia en que se corto.
    Con AVB eso decia el 17 de julio cuando el ultimo precio era del 24 de
    agosto: el usuario que fuera a comprobarlo miraba el mes equivocado.
    """
    esc = escalera(_precios(AAA=_serie(), BBB=_serie(),
                            ROTA=_serie(desde=150, hasta=160)))
    assert esc[0].corta == "ROTA"
    assert esc[0].motivo == "interrumpida"
    assert esc[0].desde == str(FECHAS[150].date())
    assert esc[0].hasta == str(FECHAS[159].date())

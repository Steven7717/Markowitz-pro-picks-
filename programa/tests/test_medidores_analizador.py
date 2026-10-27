"""Las palabras del Analizador.

Cada clave que escribe `analizador/` tiene su etiqueta, y cada etiqueta culpa a
quien toca: un motivo es una afirmación (la lección de M y de N1). Las tablas se
contrastan contra las cadenas que aparecen de verdad en el código, para que una
etiqueta no hable de una clave que nadie escribe.
"""

import ast
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

import medidores_analizador as ma
from analizador.analisis import Analisis
from analizador.referencia import Frescura, Referencia
from analizador.resolver import Identidad
from aprobacion.carga import MOTIVOS_EN_CASTELLANO
from fundamentals.sectors import load_sectors
from noticias.agenda import Evento
from noticias.hechos import Hecho
from ranking.criterio import TOPE_POR_SECTOR
from tests.test_analizador_valorar import _en_pesos
from tests.test_medidores_valoracion import _fija, _fija_residual
from valoracion.dcf import Ano, Proyeccion, Sensibilidad

RAIZ = Path(__file__).resolve().parent.parent


def _literales(*rutas: str) -> set:
    """Las cadenas escritas en esos ficheros: las claves que el código puede devolver."""
    salida = set()
    for ruta in rutas:
        arbol = ast.parse((RAIZ / ruta).read_text(encoding="utf-8"))
        salida |= {
            n.value for n in ast.walk(arbol)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
        }
    return salida


def identidad(ticker="MU", moneda="USD", pais="United States",
              nombre="Micron Technology, Inc.", bolsa="NMS", precio=100.0):
    return Identidad(ticker, "EQUITY", nombre, bolsa, moneda, moneda, "Technology",
                     "Semiconductors", pais, precio, "2026-10-26T20:00:00+00:00")


# Las claves de `Analisis.motivo`: `resolver.resolver`, `resolver.clase_de`,
# `resolver.formularios_sec`, `mercado._traer` y `analisis.analizar`.
MOTIVOS_DEL_ANALISIS = {
    "sin_red", "tipo_no_soportado", "sin_red_edgar", "sin_identidad_edgar", "error_interno",
}
# Las de `Analisis.motivo_referencia`: las de su docstring, de `kpis` y de `mercado`.
MOTIVOS_DE_LA_REFERENCIA = {
    "sin_panel", "sin_sector", "sector_sin_pares", "sin_estados", "sin_historia",
    "sin_precio", "sin_trimestres_comparables", "sin_red", "error_interno",
}
# Las de `Entradas.motivo_r_f` que no son «ok»: Banxico, `divisas.bono_m` y el Tesoro.
MOTIVOS_DE_LA_TASA = {
    "sin_token", "token_invalido", "sin_red", "respuesta_rara", "sin_dato", "sin_tasa_libre",
}


def test_cada_clase_tiene_su_etiqueta_y_su_fuente_de_datos():
    assert set(ma.CLASE) == set(ma.FUENTE_DE_DATOS) == {"sec", "extranjera_sec", "sin_sec", "etf"}


def test_cada_motivo_del_analisis_tiene_etiqueta_y_existe_en_el_codigo():
    assert set(ma.MOTIVO_ANALISIS) == MOTIVOS_DEL_ANALISIS
    escritos = _literales("analizador/resolver.py", "analizador/analisis.py", "valoracion/mercado.py")
    assert MOTIVOS_DEL_ANALISIS <= escritos


def test_cada_motivo_de_la_referencia_tiene_etiqueta_y_existe_en_el_codigo():
    assert set(ma.MOTIVO_REFERENCIA) == MOTIVOS_DE_LA_REFERENCIA
    escritos = _literales("analizador/analisis.py", "analizador/kpis.py", "valoracion/mercado.py")
    assert MOTIVOS_DE_LA_REFERENCIA <= escritos


def test_cada_motivo_de_la_tasa_tiene_etiqueta_y_existe_en_el_codigo():
    assert set(ma.MOTIVO_TASA) == MOTIVOS_DE_LA_TASA
    escritos = _literales("seguimiento/banxico.py", "analizador/divisas.py", "valoracion/mercado.py")
    assert MOTIVOS_DE_LA_TASA <= escritos


def test_sin_red_no_afirma_que_yahoo_no_conozca_el_ticker():
    # Enmienda del spec: desde fuera de `mercado` no se distingue un símbolo
    # desconocido de una conexión caída (ZZZZQ, en el recorrido de N1).
    texto = ma.MOTIVO_ANALISIS["sin_red"]
    assert "sin conexión" in texto and "no conoce" in texto


def test_sin_historia_en_la_ficha_habla_de_trimestres_y_no_de_anos():
    assert "trimestre" in ma.MOTIVO_REFERENCIA["sin_historia"]
    assert "año" not in ma.MOTIVO_REFERENCIA["sin_historia"]


def test_sin_trimestres_comparables_culpa_al_panel_y_no_a_la_empresa():
    assert "panel" in ma.MOTIVO_REFERENCIA["sin_trimestres_comparables"]


def test_el_error_interno_de_la_fila_no_dice_que_fallo_la_valoracion():
    assert "valorar" not in ma.MOTIVO_ANALISIS["error_interno"]


@pytest.mark.parametrize(
    "tabla, clave",
    [
        (ma.MOTIVO_ANALISIS, "sin_identidad_edgar"),
        (ma.MOTIVO_TASA, "sin_token"),
        (ma.MOTIVO_TASA, "token_invalido"),
    ],
)
def test_lo_que_arregla_el_usuario_dice_donde(tabla, clave):
    assert "Perfil y ajustes" in tabla[clave]


def test_una_clave_desconocida_se_ensena_tal_cual_y_una_que_no_es_texto_no():
    assert ma.etiqueta(ma.MOTIVO_ANALISIS, "motivo_nuevo") == "motivo_nuevo"
    assert ma.etiqueta(ma.MOTIVO_ANALISIS, ["sin_red"]) == "n/d"
    assert ma.etiqueta(ma.MOTIVO_ANALISIS, None) == "n/d"


@pytest.mark.parametrize("codigo", sorted(MOTIVOS_EN_CASTELLANO))
def test_la_exclusion_usa_las_frases_de_revisar_candidatos(codigo):
    texto = ma.etiqueta_exclusion(codigo)
    assert texto.endswith(MOTIVOS_EN_CASTELLANO[codigo])
    assert "dejarían fuera" in texto


def test_una_exclusion_desconocida_se_dice_entre_comillas():
    assert "«guarda_nueva»" in ma.etiqueta_exclusion("guarda_nueva")


def test_el_nombre_largo_deja_ver_un_ticker_mal_partido():
    # `separar("BRK B")` da BRK y B, y B es Barrick, no la clase B de Berkshire.
    b = Analisis("B", "sec", identidad("B", nombre="Barrick Mining Corporation"), None)
    assert ma.nombre(b) == "Barrick Mining Corporation"
    assert ma.nombre(Analisis("ZZZZQ", None, None, "sin_red")) == "—"
    assert ma.nombre(Analisis("X", "sec", identidad("X", nombre=None), None)) == "—"


def test_una_ene_se_sugiere_con_el_ampersand_de_yahoo():
    aviso = ma.aviso_invalidos(["PEÑOLES.MX", "A..B"])
    assert "PE&OLES.MX" in aviso and "A..B" in aviso
    assert ma.aviso_invalidos(["A..B"]) == "Sin forma de ticker, y no se analizan: A..B."


@pytest.mark.parametrize(
    "ticker, pista",
    [("MKC.V", "MKC-V"), ("SHEL.L", "SHEL-L"), ("WALMEX.MX", None), ("MU", None), ("BRK-B", None)],
)
def test_un_sufijo_de_una_letra_puede_ser_una_clase_de_accion(ticker, pista):
    sugerencia = ma.sugerencia_sin_red(ticker)
    assert (sugerencia is None) == (pista is None)
    if pista:
        assert pista in sugerencia


def test_la_fila_de_un_ticker_sin_clase_dice_por_que_y_da_la_pista():
    assert "MKC-V" in ma.motivo_de_la_fila(Analisis("MKC.V", None, None, "sin_red"))
    assert ma.motivo_de_la_fila(Analisis("ZZZZQ", None, None, "sin_red")) == (
        ma.MOTIVO_ANALISIS["sin_red"]
    )
    assert ma.motivo_de_la_fila(Analisis("^GSPC", None, None, "tipo_no_soportado")) == (
        ma.MOTIVO_ANALISIS["tipo_no_soportado"]
    )


# --- La ficha frente al sector ----------------------------------------------


def ficha(pilar=0.4, puesto=1):
    return {
        "ticker": "MU",
        "sector_gics": "Information Technology",
        "puesto": puesto,
        "compuesto": None if puesto is None else 1.2,
        "pilares": {"calidad": 0.5, "crecimiento": 0.1, "valoracion": pilar, "solidez": 0.2},
        "destacados": [],
        "flojos": [],
        "cobertura": {
            "kpis_con_dato": 14,
            "pilares_con_dato": 4,
            "kpis_por_pilar": {"calidad": 7, "crecimiento": 3, "valoracion": 4, "solidez": 3},
        },
        "desplazo_a": [],
    }


def referencia(puesto=1, supervivientes=423, exclusion=None, en_panel=True, pilar=0.4, posteriores=0):
    return Referencia(
        ficha(pilar, puesto), None if puesto is None else 1.2, puesto,
        supervivientes, exclusion, en_panel, posteriores,
    )


def analisis(ticker="MU", clase="sec", ref=None, motivo_referencia=None, valoracion=None,
             entradas=None, fuente_sector="sp500", **ident):
    return Analisis(ticker, clase, identidad(ticker, **ident), None, "Information Technology",
                    fuente_sector, ref, motivo_referencia, entradas, valoracion)


def test_el_puesto_es_el_global_entre_las_que_pasan_las_guardas():
    assert ma.puesto(referencia(25, 423)) == "25 de 423"
    assert ma.puesto(referencia(None, 423, "historia_corta")) == "—"
    assert ma.puesto(None) == "—"
    assert ma.puesto_en_tarjeta(referencia(25, 423)) == "Puesto global 25 de 423"
    assert ma.puesto_en_tarjeta(referencia(None, 423, "historia_corta")) == "Fuera del ranking"


def test_la_nota_del_puesto_dice_que_es_global_y_por_que_puede_no_coincidir():
    nota = ma.nota_puesto(referencia(25, 423), "MU")
    assert "global" in nota and f"tope de {TOPE_POR_SECTOR} por sector" in nota
    assert "una más" not in nota


def test_una_insertada_se_cuenta_a_si_misma_y_se_dice_que_no_es_un_error():
    nota = ma.nota_puesto(referencia(25, 424, en_panel=False), "TSM")
    assert "424" in nota and "TSM" in nota and "no es un error" in nota


def test_la_celda_frente_al_sector():
    assert ma.frente_al_sector(analisis(clase="etf")) == "—"
    assert ma.frente_al_sector(analisis(motivo_referencia="sin_panel")).startswith("sin ficha: ")
    assert ma.frente_al_sector(analisis(ref=referencia(None, 423, "pilar_sin_datos"))) == (
        "fuera: " + MOTIVOS_EN_CASTELLANO["pilar_sin_datos"]
    )
    assert ma.frente_al_sector(analisis(ref=referencia(25, 424, en_panel=False))) == "25 de 424"


def test_historia_corta_con_el_panel_atrasado_culpa_al_panel():
    a = analisis("WALMEX.MX", "sin_sec", ref=referencia(None, 423, "historia_corta", False, posteriores=2))
    texto = ma.texto_exclusion(a)
    assert texto.startswith("Las guardas") and "panel el que se quedó atrás" in texto


def test_historia_corta_de_una_de_yahoo_apunta_a_las_que_publican_cada_semestre():
    a = analisis("NESN.SW", "sin_sec", ref=referencia(None, 423, "historia_corta", False))
    assert "cada semestre" in ma.texto_exclusion(a)


def test_historia_corta_de_una_de_la_sec_no_se_inventa_la_causa():
    texto = ma.texto_exclusion(analisis(ref=referencia(None, 423, "historia_corta", False)))
    assert "semestre" not in texto and "panel" not in texto
    assert ma.texto_exclusion(analisis(ref=referencia())) is None


def test_otra_guarda_no_hereda_la_causa_de_historia_corta():
    # Las dos causas explican `historia_corta`; pegadas a otra guarda mentirían.
    a = analisis("NESN.SW", "sin_sec", ref=referencia(None, 423, "pilar_sin_datos", False, posteriores=2))
    texto = ma.texto_exclusion(a)
    assert "semestre" not in texto and "panel" not in texto


def _votos(pares="neutra", motivo=None):
    return {
        "flujos": {"voto": "neutra", "motivo": None},
        "sin_crecimiento": {"voto": "neutra", "motivo": None},
        "pares": {"voto": pares, "motivo": motivo},
    }


def test_brk_b_no_vota_por_sus_multiplos_y_no_por_falta_de_pares():
    # Task 17 de N1: el XBRL de Berkshire no trae recuento ni BPA diluidos.
    a = analisis("BRK-B", ref=referencia(None, 423, "pilar_sin_datos", pilar=None),
                 valoracion=_fija(votos=_votos("no_aplica", "sin_pares")))
    texto = ma.detalle_pares(a)
    assert "no por falta de pares" in texto and "múltiplos" in texto


def test_una_excluida_que_vota_lo_dice():
    a = analisis("JPM", ref=referencia(None, 423, "pilar_sin_datos", pilar=0.3),
                 valoracion=_fija(votos=_votos("neutra")))
    texto = ma.detalle_pares(a)
    assert "vota con su pilar" in texto and MOTIVOS_EN_CASTELLANO["pilar_sin_datos"] in texto


def test_sin_ficha_el_voto_de_pares_remite_a_su_causa():
    a = analisis(motivo_referencia="sin_precio", valoracion=_fija(votos=_votos("no_aplica", "sin_pares")))
    texto = ma.detalle_pares(a)
    assert "no hay ficha frente al sector" in texto and ma.MOTIVO_REFERENCIA["sin_precio"] in texto


def test_sin_ficha_y_sin_motivo_no_se_inventa_una_causa():
    assert ma.detalle_pares(analisis()) is None
    # Un ETF no tiene ficha frente al sector ni la echa en falta.
    assert ma.detalle_pares(analisis(clase="etf", motivo_referencia="sin_panel")) is None


def test_una_excluida_que_no_vota_no_dice_que_vota():
    a = analisis("JPM", ref=referencia(None, 423, "pilar_sin_datos", pilar=0.3),
                 valoracion=_fija(votos=_votos("no_aplica", "sin_pares")))
    assert ma.detalle_pares(a) is None


def test_con_ficha_sin_guarda_y_con_pilar_no_hay_nada_que_anadir():
    assert ma.detalle_pares(analisis(ref=referencia(), valoracion=_fija())) is None
    assert ma.detalle_pares(analisis(clase="etf")) is None


def test_un_veredicto_sin_valor_base_lleva_su_rotulo():
    # 7203.T en la Task 17 de N1: quema caja por su financiera cautiva.
    votos = {**_votos(), "flujos": {"voto": "no_aplica", "motivo": "quema_caja"}}
    texto = ma.sin_valor_base(_fija(valor=None, votos=votos))
    assert "no valor base" in texto and "quema caja" in texto
    assert ma.sin_valor_base(_fija()) is None
    assert ma.sin_valor_base({"version": "m1", "motivo": "sin_red"}) is None
    assert ma.sin_valor_base(None) is None


def test_sin_valor_base_de_un_banco_culpa_al_beneficio_residual():
    votos = {**_votos(), "flujos": {"voto": "no_aplica", "motivo": "quema_caja"}}
    texto = ma.sin_valor_base(_fija_residual(valor=None, votos=votos))
    assert "beneficio residual" in texto and "el de flujos" not in texto


# --- Los avisos de un ticker --------------------------------------------------


def _con_divisa(sin_prima: bool) -> dict:
    return _fija(divisa={"moneda_precio": "USD", "tipo_precio": 1.0, "sin_prima_pais": sin_prima})


def test_sin_prima_pais_solo_fuera_del_sp500():
    tsm = analisis("TSM", "extranjera_sec", valoracion=_con_divisa(True), fuente_sector="yahoo", pais="Taiwan")
    assert "Taiwan" in ma.aviso_sin_prima_pais(tsm)
    # GRMN está domiciliada en Suiza y se valora exactamente como en M.
    grmn = analisis("GRMN", valoracion=_con_divisa(True), fuente_sector="sp500", pais="Switzerland")
    assert ma.aviso_sin_prima_pais(grmn) is None
    assert ma.aviso_sin_prima_pais(analisis(valoracion=_con_divisa(False), fuente_sector="yahoo")) is None


def test_el_pais_de_yahoo_se_escapa():
    raro = analisis("TSM", "extranjera_sec", valoracion=_con_divisa(True), fuente_sector="yahoo",
                    pais="[Taiwan](http://x)")
    assert "[Taiwan](http://x)" not in ma.aviso_sin_prima_pais(raro)


def test_la_misma_empresa_solo_en_el_sic_de_la_bmv():
    sp500 = set(load_sectors())
    assert "AAPL" in ma.aviso_misma_empresa("AAPL.MX", sp500)
    # T.TO es TELUS y T es AT&T: en otras bolsas el mismo símbolo es otra empresa.
    assert ma.aviso_misma_empresa("T.TO", sp500) is None
    assert ma.aviso_misma_empresa("WALMEX.MX", sp500) is None
    assert ma.aviso_misma_empresa("AAPL", sp500) is None


def test_una_preferente_se_reconoce_por_su_forma():
    assert ma.aviso_preferente("JPM-PC") and ma.aviso_preferente("T-PA")
    assert ma.aviso_preferente("BRK-B") is None and ma.aviso_preferente("MU") is None
    # Ninguna del S&P 500 tiene esa forma: no hay falsos positivos en el panel.
    assert [t for t in load_sectors() if ma.aviso_preferente(t)] == []


def test_el_recuento_de_una_adr_que_no_cuadra_se_avisa():
    assert "5.00" in ma.aviso_adr(5.0)
    assert ma.aviso_adr(1.0) is None and ma.aviso_adr(None) is None


def test_el_panel_atrasado_se_avisa():
    con_filas = analisis("TSM", "extranjera_sec", ref=referencia(25, 424, en_panel=False, posteriores=1))
    assert "2026Q2" in ma.aviso_panel_atrasado(con_filas, "2026Q2")
    sin_ninguna = analisis("TSM", "extranjera_sec", motivo_referencia="sin_trimestres_comparables")
    assert ma.aviso_panel_atrasado(sin_ninguna, "2026Q2")
    assert ma.aviso_panel_atrasado(analisis(ref=referencia()), "2026Q2") is None
    assert ma.aviso_panel_atrasado(con_filas, None) is None


def test_el_bono_m_viejo_se_avisa_y_el_reciente_no():
    procedencia = {"fuente": "bono_m_10", "serie": "SF44071", "fecha": "2026-09-24"}
    assert ma.aviso_bono_m(procedencia, date(2026, 10, 26)) is None
    texto = ma.aviso_bono_m(procedencia, date(2026, 11, 25))
    assert "24/09/2026" in texto and "62 días" in texto
    assert ma.aviso_bono_m({"fuente": "tesoro_10", "serie": "^TNX"}, date(2027, 1, 1)) is None
    # El `^TNX` caduca por su cuenta a los siete días: su fecha no se avisa aquí.
    assert ma.aviso_bono_m({"fuente": "tesoro_10", "fecha": "2026-09-24"}, date(2027, 1, 1)) is None
    assert ma.aviso_bono_m({"fuente": "bono_m_10", "fecha": None}, date(2027, 1, 1)) is None


def test_los_avisos_llevan_su_forma_corta_y_la_larga():
    entradas = SimpleNamespace(cociente_adr=5.0, procedencia_r_f={"fuente": "tesoro_10"})
    a = analisis("AAPL.MX", "sin_sec", entradas=entradas, valoracion=_con_divisa(False),
                 fuente_sector="yahoo", moneda="MXN")
    cortos = [corto for corto, _ in ma.avisos(a, set(load_sectors()), "2026Q2", date(2026, 10, 26))]
    assert cortos == ["misma empresa que AAPL", "recuento de acciones dudoso"]
    assert all(largo for _, largo in ma.avisos(a, set(load_sectors()), "2026Q2", date(2026, 10, 26)))


# --- La moneda del precio -----------------------------------------------------


def _amx() -> dict:
    """AMX: cotiza en dólares y se valora en pesos, a 20 pesos por dólar."""
    return _fija(
        moneda="MXN",
        precio=500.0,
        valor={"pesimista": 300.0, "base": 600.0, "optimista": None},
        epv={"por_accion": 400.0, "parte_crecimiento": 0.1},
        margen_seguridad=0.2,
        divisa={"moneda_precio": "USD", "moneda_valoracion": "MXN", "tipo_precio": 20.0},
    )


def test_los_valores_se_ensenan_en_la_moneda_del_precio():
    original = _amx()
    v = ma.en_moneda_del_precio(original)
    assert v["moneda"] == "USD"
    assert v["precio"] == pytest.approx(25.0)
    assert v["valor"] == {"pesimista": pytest.approx(15.0), "base": pytest.approx(30.0), "optimista": None}
    assert v["epv"]["por_accion"] == pytest.approx(20.0)
    # El margen es un cociente, y el crecimiento implícito una tasa: no cambian.
    assert v["margen_seguridad"] == 0.2 and v["implicito"] == original["implicito"]
    # Lo guardado no se toca: es lo que va al acta.
    assert original["moneda"] == "MXN" and original["valor"]["base"] == 600.0


def test_una_cotizacion_en_peniques_vuelve_a_peniques():
    # SHEL.L: 67,92 $ de valor base son 5.079,9 peniques (N1).
    shel = _fija(precio=54.0, valor={"pesimista": None, "base": 67.92, "optimista": None},
                 divisa={"moneda_precio": "GBp", "moneda_valoracion": "USD", "tipo_precio": 0.01337})
    v = ma.en_moneda_del_precio(shel)
    assert v["moneda"] == "GBp"
    assert v["valor"]["base"] == pytest.approx(67.92 / 0.01337)


def test_una_fallida_toma_la_moneda_de_su_divisa():
    # `fallida("sin_bono_m")` no lleva moneda: sale de la divisa (revisión final de N1).
    fallida_ = {"version": "m1", "fecha": "2026-10-26", "motivo": "sin_bono_m",
                "divisa": {"moneda_precio": "MXN", "tipo_precio": 1.0}}
    assert ma.en_moneda_del_precio(fallida_)["moneda"] == "MXN"


@pytest.mark.parametrize("tipo", [None, 0.0, -1.0, "20", float("nan")])
def test_sin_un_tipo_valido_no_se_convierte_nada(tipo):
    amx = _amx()
    amx["divisa"] = {**amx["divisa"], "tipo_precio": tipo}
    assert ma.en_moneda_del_precio(amx) == amx
    assert ma.en_moneda_del_precio(None) is None


def test_sin_divisa_o_sin_su_moneda_no_se_convierte_nada():
    # Las valoraciones de M no llevan `divisa`: ya están en la moneda del precio.
    de_m = _fija()
    assert ma.en_moneda_del_precio(de_m) == de_m
    sin_moneda = _amx()
    sin_moneda["divisa"] = {"tipo_precio": 20.0}
    assert ma.en_moneda_del_precio(sin_moneda) == sin_moneda


# --- Los deslizadores y sus tablas ----------------------------------------------


def test_la_etiqueta_de_un_deslizador_dice_su_unidad():
    assert ma.etiqueta_deslizador("beta") == "Beta"
    assert ma.etiqueta_deslizador("g_ref") == "Crecimiento de referencia (%)"


def test_la_lista_de_lo_movido_se_lee_en_castellano():
    assert ma.lista_de_supuestos(("beta",)) == "beta"
    assert ma.lista_de_supuestos(("beta", "g_ref")) == "beta y crecimiento de referencia"
    # «e» y no «y» delante de una i.
    assert ma.lista_de_supuestos(("beta", "g_ref", "t")) == (
        "beta, crecimiento de referencia e impuestos"
    )
    # Con «hi» también «e»; con «ie» o «hie», diptongo, se queda la «y».
    assert ma._y(["agua", "hilo"]) == "agua e hilo"
    assert ma._y(["agua", "hielo"]) == "agua y hielo"
    assert ma._y(["agua", "iodo"]) == "agua e iodo" and ma._y(["agua", "ion"]) == "agua e ion"


def test_sin_tasa_libre_se_dice_por_que_y_que_hacer():
    texto = ma.falta_tasa(_en_pesos(r_f=None, motivo_r_f="sin_token"))
    assert ma.MOTIVO_TASA["sin_token"] in texto and "Bono M" in texto and "no se guarda" in texto


def test_la_sensibilidad_va_en_la_moneda_del_precio_y_marca_la_base():
    s = Sensibilidad(
        waccs=(0.07, 0.08, 0.09),
        gs=(0.02, 0.025, 0.03),
        valores=((40.0, 50.0, None), (30.0, 36.0, 44.0), (24.0, 28.0, 33.0)),
    )
    columnas, filas = ma.tabla_sensibilidad(s, 20.0, "USD")
    assert columnas[2] == "2.5% (base)" and filas[1][0] == "8.0% (base)"
    assert filas[1][2] == "1.80 USD"
    assert filas[0][3] == "—"


def test_la_proyeccion_va_en_millones_con_el_terminal_al_final():
    p = Proyeccion((Ano(1, 0.2, 1.2e9, 1.8e8, 1.65e8),), 2.5e9)
    columnas, filas = ma.tabla_proyeccion(p, "USD")
    assert columnas[2] == "Ingresos (USD)"
    assert filas[0] == ["1", "20.0%", "1,200 M", "180 M", "165 M"]
    assert filas[-1] == ["Terminal", "—", "—", "—", "2,500 M"]


def test_una_cifra_que_no_es_un_numero_se_lee_n_d():
    p = Proyeccion((Ano(1, 0.2, float("nan"), None, -1.65e8),), 2.5e9)
    _, filas = ma.tabla_proyeccion(p, "USD")
    assert filas[0][2:] == ["n/d", "n/d", "−165 M"]


# --- La fila del resumen ------------------------------------------------------

HOY = date(2026, 10, 26)
SP500 = {"MU", "AAPL", "GRMN"}


def test_la_fila_de_un_ticker_analizado():
    a = analisis(ref=referencia(1, 423), valoracion=_fija(), precio=877.55)
    evento = Evento("MU", "resultados", date(2026, 12, 17), "Resultados")
    fila = ma.fila(a, evento, SP500, "2026Q2", HOY)
    assert list(fila) == list(ma.COLUMNAS)
    assert fila["Ticker"] == "MU" and fila["Nombre"] == "Micron Technology, Inc."
    assert fila["Clase"] == "SEC (10-K)"
    assert fila["Precio"] == "877.55 USD"
    assert fila["Hora del precio"] == "26/10/2026 20:00 UTC"
    assert fila["Valor base"] == "1,234.50 USD" and fila["Margen de seguridad"] == "20.3%"
    assert fila["Veredicto"] == "En rango"
    assert fila["Frente al sector"] == "1 de 423"
    assert fila["Próximo evento"] == "Resultados, 17/12/2026 (en 52 días)"
    assert fila["Avisos"] == "—"


def test_la_fila_de_un_ticker_sin_clase_lo_dice_y_no_inventa_el_resto():
    fila = ma.fila(Analisis("ZZZZQ", None, None, "sin_red"), None, SP500, None, HOY)
    assert fila["Avisos"] == ma.MOTIVO_ANALISIS["sin_red"]
    assert {fila[c] for c in ma.COLUMNAS if c not in ("Ticker", "Avisos")} == {"—"}


def test_sin_identidad_de_edgar_la_fila_conserva_el_nombre_y_el_precio():
    a = Analisis("MU", None, identidad(), "sin_identidad_edgar")
    fila = ma.fila(a, None, SP500, None, HOY)
    assert fila["Nombre"] == "Micron Technology, Inc." and fila["Precio"] == "100.00 USD"
    assert "Perfil" in fila["Avisos"]


def test_el_valor_de_la_fila_va_en_la_moneda_del_precio():
    amx = analisis("AMX", "extranjera_sec", valoracion=_amx(), fuente_sector="yahoo", precio=25.0)
    assert ma.fila(amx, None, SP500, None, HOY)["Valor base"] == "30.00 USD"


def test_una_fallida_por_el_bono_m_dice_el_motivo_concreto():
    fallida = {"version": "m1", "fecha": "2026-10-26", "motivo": "sin_bono_m",
               "divisa": {"moneda_precio": "MXN", "tipo_precio": 1.0}}
    entradas = SimpleNamespace(motivo_r_f="sin_token", cociente_adr=None, procedencia_r_f={})
    a = analisis("WALMEX.MX", "sin_sec", valoracion=fallida, entradas=entradas, fuente_sector="yahoo", moneda="MXN")
    fila = ma.fila(a, None, SP500, None, HOY)
    assert fila["Veredicto"] == "Sin valoración"
    assert ma.MOTIVO_TASA["sin_token"] in fila["Avisos"]


def test_los_avisos_cortos_van_en_la_fila():
    tsm = analisis("TSM", "extranjera_sec", ref=referencia(25, 424, en_panel=False, posteriores=1),
                   valoracion=_con_divisa(True), fuente_sector="yahoo", pais="Taiwan")
    assert ma.fila(tsm, None, SP500, "2026Q2", HOY)["Avisos"] == "sin prima por riesgo país; panel atrasado"


def test_un_etf_no_tiene_veredicto_ni_sector():
    spy = analisis("SPY", "etf", fuente_sector=None)
    fila = ma.fila(spy, None, SP500, None, HOY)
    assert (fila["Clase"], fila["Veredicto"], fila["Frente al sector"]) == ("ETF", "—", "—")


def test_la_hora_del_precio_sin_zona_no_se_inventa():
    assert ma.hora_del_precio("2026-10-26T20:00:00+00:00") == "26/10/2026 20:00 UTC"
    assert ma.hora_del_precio("2026-10-26T20:00:00") == "—"
    assert ma.hora_del_precio(None) == "—"


def test_la_leyenda_glosa_lo_que_no_se_explica_solo():
    leyenda = ma.leyenda_resumen()
    for termino in ("Margen de seguridad", "Frente al sector", "pilares", "no se refresca solo"):
        assert termino in leyenda


# --- Lo que viene y las noticias ------------------------------------------------


def test_lo_que_viene_en_orden_y_sin_los_punteros_sin_fecha():
    eventos = [
        Evento("MU", "resultados", date(2026, 12, 17), "Resultados"),
        Evento(None, "macro", None, "FOMC"),
        Evento("TSM", "dividendo", date(2026, 11, 2), "Fecha de pago"),
    ]
    assert [e.ticker for e in ma.proximos(eventos)] == ["TSM", "MU"]
    assert ma.proximo(eventos).ticker == "TSM"
    assert ma.proximo([]) is None


def _hecho(cuando, material, url):
    return Hecho("MU", ("2.02",), ("Resultados",), url, cuando, False, material)


def test_los_hechos_se_reparten_por_material_y_del_mas_nuevo_al_mas_viejo():
    a = _hecho(date(2026, 9, 1), True, "a")
    b = _hecho(date(2026, 10, 1), True, "b")
    c = _hecho(date(2026, 8, 1), False, "c")
    destacados, plegados = ma.repartir_hechos([a, c, b])
    assert [h.url for h in destacados] == ["b", "a"] and [h.url for h in plegados] == ["c"]


def test_el_recorte_dice_cuantos_quedan_fuera():
    assert ma.recorte(list(range(45))) == (list(range(ma.TOPE_NOTICIAS)), 5)
    assert ma.recorte([1, 2]) == ([1, 2], 0)


@pytest.mark.parametrize("clase, esperado", [("VIDEO", "Vídeo"), ("video", "Vídeo"), ("STORY", "Story"), ("", "")])
def test_el_formato_de_la_noticia_se_pinta_tal_cual_menos_el_video(clase, esperado):
    assert ma.formato_noticia(clase) == esperado


def test_solo_las_de_la_sec_tienen_hechos():
    assert ma.fuentes_de("sec") == ("agenda", "hechos", "prensa")
    for clase in ("extranjera_sec", "sin_sec", "etf"):
        assert ma.fuentes_de(clase) == ("agenda", "prensa")
        assert ma.sin_hechos(clase)
    assert "6-K" in ma.sin_hechos("extranjera_sec")
    assert ma.sin_hechos("sec") is None


def test_la_hora_de_cada_descarga_se_dice_y_lo_caducado_tambien():
    reciente = datetime.now(timezone.utc) - timedelta(minutes=5)
    linea = ma.linea_de_hora("hechos", reciente, True)
    assert linea.startswith("**Hechos (8-K)**") and "hace 5 min" in linea and "cada hora" in linea
    assert "lo último que había guardado" in ma.linea_de_hora("hechos", reciente, False)
    assert ma.linea_de_hora("prensa", None, False) == "**Prensa**: no se pudo traer nada."


def test_un_etf_solo_tiene_tres_pestanas():
    assert ma.pestanas_de("etf") == ("Resumen", "Gráfico", "Noticias y calendario")
    assert ma.pestanas_de("sin_sec") == ma.PESTANAS
    assert "Valoración" in ma.PESTANAS and "Fundamentales" in ma.PESTANAS


# --- La identidad, contra quién se compara y el panel ---------------------------


def test_la_identidad_dice_clase_fuente_sector_y_monedas():
    divisa = SimpleNamespace(moneda_estados="TWD", moneda_valoracion="USD", moneda_precio="USD")
    entradas = SimpleNamespace(divisa=divisa)
    tsm = analisis("TSM", "extranjera_sec", entradas=entradas, fuente_sector="yahoo", pais="Taiwan")
    texto = ma.ficha_de_identidad(tsm)
    assert "SEC, extranjera" in texto and "Yahoo" in texto
    assert "Information Technology" in texto
    assert "TWD" in texto and "convertidos a USD" in texto


def test_contra_quien_se_compara_y_con_que_panel():
    mu = analisis(ref=referencia(1, 423))
    assert ma.contra_quien(mu, 70, date(2026, 10, 16)).startswith(
        "Comparada con las otras 69 empresas del S&P 500 de Information Technology"
    )
    tsm = analisis("TSM", "extranjera_sec", ref=referencia(25, 424, en_panel=False),
                   fuente_sector="yahoo", pais="Taiwan")
    texto = ma.contra_quien(tsm, 70, date(2026, 10, 16))
    assert "con las 70 empresas" in texto and "riesgo país" in texto


def test_la_fecha_del_panel_y_la_de_los_candidatos():
    hora = datetime(2026, 10, 16, 12, 0)
    texto = ma.fecha_del_panel(date(2026, 10, 16), "2026Q3", Frescura(hora, hora))
    assert "16/10/2026" in texto and "2026Q3" in texto and "candidatos son del 16/10/2026" in texto
    assert "ejemplo" in ma.fecha_del_panel(date(2026, 10, 16), "2026Q3", Frescura(hora, None))


def test_los_textos_del_panel_dicen_lo_que_hay_que_saber():
    assert "sin tocar tus candidatos" in ma.SIN_PANEL
    assert "Revisar candidatos" in ma.PANEL_POSTERIOR
    assert "Rehacer" in ma.PANEL_ATRASADO
    assert "salidas/panel.parquet" in ma.AYUDA_PANEL and "añadidos" in ma.AYUDA_PANEL


# --- Los casos de borde de la fila, la identidad y el panel ---------------------


def test_la_hora_del_precio_se_pasa_a_utc_y_lo_ilegible_no_se_inventa():
    assert ma.hora_del_precio("2026-10-26T16:00:00-04:00") == "26/10/2026 20:00 UTC"
    assert ma.hora_del_precio("ayer por la tarde") == "—"


def test_sin_precio_o_sin_valor_base_la_fila_dice_raya_y_no_n_d():
    sin_precio = analisis(precio=None)
    assert ma.fila(sin_precio, None, SP500, None, HOY)["Precio"] == "—"
    sin_base = analisis(valoracion=_fija(valor=None, margen_seguridad=None))
    fila = ma.fila(sin_base, None, SP500, None, HOY)
    assert (fila["Valor base"], fila["Margen de seguridad"]) == ("—", "—")
    assert fila["Veredicto"] == "En rango"


def test_una_fallida_por_el_bono_m_sin_entradas_no_revienta():
    fallida = {"version": "m1", "fecha": "2026-10-26", "motivo": "sin_bono_m"}
    a = analisis("WALMEX.MX", "sin_sec", valoracion=fallida, fuente_sector="yahoo", moneda="MXN")
    fila = ma.fila(a, None, SP500, None, HOY)
    assert fila["Veredicto"] == "Sin valoración"
    assert fila["Avisos"].startswith(ma.medidores_valoracion.etiqueta_motivo("sin_bono_m"))


def test_la_identidad_de_un_etf_no_habla_de_sector():
    assert "Sector" not in ma.ficha_de_identidad(analisis("SPY", "etf", fuente_sector=None))


def test_la_identidad_sin_sector_ni_identidad_lo_dice_sin_reventar():
    sin = Analisis("XYZ", "sin_sec", None, None, None, "sin_sector")
    texto = ma.ficha_de_identidad(sin)
    assert "sin sector GICS" in texto and "Cotiza" not in texto


def test_la_identidad_de_una_que_se_valora_en_otra_moneda_que_la_del_precio():
    divisa = SimpleNamespace(moneda_estados="MXN", moneda_valoracion="MXN", moneda_precio="USD")
    amx = analisis("AMX", "extranjera_sec", entradas=SimpleNamespace(divisa=divisa), fuente_sector="yahoo")
    assert "**Se valora** en MXN" in ma.ficha_de_identidad(amx)


def test_las_monedas_de_la_identidad_se_escapan():
    divisa = SimpleNamespace(moneda_estados="T*D", moneda_valoracion="USD", moneda_precio="USD")
    raro = analisis("TSM", "extranjera_sec", entradas=SimpleNamespace(divisa=divisa), fuente_sector="yahoo")
    assert "T*D" not in ma.ficha_de_identidad(raro)


def test_una_del_sp500_domiciliada_fuera_no_lleva_el_aviso_del_riesgo_pais():
    # GRMN está en Suiza y en el panel: se compara como las demás.
    grmn = analisis("GRMN", ref=referencia(30, 423), fuente_sector="sp500", pais="Switzerland")
    assert "riesgo país" not in ma.contra_quien(grmn, 70, date(2026, 10, 16))

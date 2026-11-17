import json
import logging
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import numpy as np
import pandas as pd
import pyarrow as pa
import pytest

from fundamentals.kpis import TODOS_LOS_KPIS
from ranking.filings import Riesgos
from ranking.llm import Narrativa, Riesgo
from ranking.llm import redactar_con_cache as redactar_con_cache_real
from ranking.run import Resultado, construir_ranking, contexto, guardar
from ranking.verificacion import sin_digitos
from tests.dobles_valoracion import fundamentos, perfil
from valoracion.motor import calcular
from valoracion.plano import a_dict
from valoracion.supuestos import deducir


@pytest.fixture(autouse=True)
def valoracion_doble():
    """La valoración sale a yfinance; aquí no se prueba ella, sino dónde cae.

    Autouse porque `construir_ranking` valora por defecto: sin esto, cada test
    de este fichero saldría a la red quince veces.
    """
    with patch(
        "ranking.run.valorar",
        return_value={"version": "m1", "fecha": "2026-10-12", "motivo": "sin_precio"},
    ) as doble:
        yield doble


SECTORES = {"Tech": 6, "Financials": 6, "Health": 6}


def panel_y_metadatos():
    """Panel con la forma de build_panel(con_zscore=True): 18 empresas, 4 trimestres."""
    generador = np.random.default_rng(11)
    trimestres = ["2024Q3", "2024Q4", "2025Q1", "2025Q2"]
    filas, indice, meta = [], [], []
    for sector, cuantas in SECTORES.items():
        for numero in range(cuantas):
            ticker = f"{sector[:2].upper()}{numero}"
            meta.append({"ticker": ticker, "sector_gics": sector})
            for trimestre in trimestres:
                fila = {kpi: 1.0 for kpi in TODOS_LOS_KPIS}
                fila.update(
                    {
                        f"z_{kpi}": v
                        for kpi, v in zip(
                            TODOS_LOS_KPIS, generador.normal(size=len(TODOS_LOS_KPIS))
                        )
                    }
                )
                fila["trimestre"] = trimestre
                filas.append(fila)
                indice.append(
                    (ticker, pd.Period(trimestre, freq="Q").end_time.normalize())
                )
    panel = pd.DataFrame(
        filas, index=pd.MultiIndex.from_tuples(indice, names=["ticker", "periodo"])
    )
    return panel, pd.DataFrame(meta).set_index("ticker")


RIESGOS = Riesgos(
    ticker="TE0",
    formulario="10-K",
    fecha="2025-10-31",
    accession="0000-25-000001",
    seccion="Item 1A",
    texto="We depend on a limited number of suppliers.",
    caracteres_totales=42,
    recortado=False,
)


@pytest.fixture
def sin_red():
    panel, metadatos = panel_y_metadatos()
    with patch("ranking.run.build_panel", return_value=(panel, metadatos, None)), patch(
        "ranking.run.cargar_riesgos", return_value=RIESGOS
    ):
        yield


def test_devuelve_como_mucho_el_tamano_del_top(sin_red):
    resultado = construir_ranking(con_llm=False, n=5)
    assert len(resultado.fichas) == 5
    assert [f["puesto"] for f in resultado.fichas] == [1, 2, 3, 4, 5]


def test_respeta_el_tope_sectorial(sin_red):
    resultado = construir_ranking(con_llm=False, n=15, tope=3)
    por_sector = pd.Series([f["sector_gics"] for f in resultado.fichas]).value_counts()
    assert por_sector.max() <= 3


def test_sin_llm_todas_las_fichas_son_de_plantilla(sin_red):
    resultado = construir_ranking(con_llm=False, n=5)
    assert {f["generada_por"] for f in resultado.fichas} == {"plantilla"}
    assert all(f["narrativa"] is None for f in resultado.fichas)


def test_con_llm_falso_no_llega_a_invocar_al_modelo(sin_red, tmp_path):
    # El test anterior no muerde solo: en este entorno sin ANTHROPIC_API_KEY,
    # incluso si `con_llm` se ignorase por completo y _con_narrativa se
    # llamara siempre, redactar_con_cache real degrada a None sin llave y la
    # ficha sale "plantilla" de todas formas -- mismo resultado, bug invisible.
    # Comprobado: forzar `if True:` en vez de `if con_llm:` en construir_ranking
    # deja test_sin_llm_todas_las_fichas_son_de_plantilla en verde igualmente.
    # Este test cierra ese hueco inyectando un cliente falso que SÍ produciría
    # una narrativa real si se le llamara, y comprueba que no se le llama.
    cliente = ClienteFalso(Narrativa(tesis="No debería llegar a usarse", riesgos=[]))
    with patch("ranking.run.redactar_con_cache", _con_cliente_falso(cliente)):
        resultado = construir_ranking(con_llm=False, n=3, cache_dir=tmp_path)
    assert cliente.llamadas == []
    assert {f["generada_por"] for f in resultado.fichas} == {"plantilla"}
    assert all(f["narrativa"] is None for f in resultado.fichas)


def test_el_ranking_es_reproducible(sin_red):
    primera = construir_ranking(con_llm=False, n=5)
    segunda = construir_ranking(con_llm=False, n=5)
    assert [f["ticker"] for f in primera.fichas] == [f["ticker"] for f in segunda.fichas]


# Calculado con el código de antes de la inclinación macro (eca3a11) y con el de
# ahora: idénticos hasta el último decimal. Si este test cae, sin macro el Top ya
# no es el que era, y eso es un fallo aunque todo lo demás siga en verde.
TOP_SIN_MACRO = [
    ("FI0", 1.5277407203319124),
    ("TE5", 1.2745897681749936),
    ("HE0", 1.142848207672796),
    ("TE3", 1.0119970412965922),
    ("HE3", 1.0037226790998488),
    ("FI2", 0.5848483650684606),
    ("HE2", 0.4635822463899281),
    ("TE4", 0.24477981988547357),
    ("FI1", 0.0038554024305262635),
]


def test_el_top_sin_macro_es_el_de_antes_de_la_inclinacion(sin_red):
    resultado = construir_ranking(con_llm=False, n=15)
    assert [f["ticker"] for f in resultado.fichas] == [t for t, _ in TOP_SIN_MACRO]
    assert [f["compuesto"] for f in resultado.fichas] == pytest.approx(
        [c for _, c in TOP_SIN_MACRO]
    )


def test_cuenta_las_exclusiones_por_motivo(sin_red):
    resultado = construir_ranking(con_llm=False, n=5)
    assert isinstance(resultado.exclusiones, dict)
    assert sum(resultado.exclusiones.values()) + len(resultado.tabla) == 18


def test_guardar_escribe_las_tres_salidas(sin_red, tmp_path: Path):
    resultado = construir_ranking(con_llm=False, n=5)
    guardar(resultado, tmp_path)

    assert (tmp_path / "ranking.csv").exists()
    assert (tmp_path / "informe.md").exists()

    fichas = json.loads((tmp_path / "fichas.json").read_text(encoding="utf-8"))
    assert len(fichas) == 5
    assert fichas[0]["narrativa"] is None

    # No sólo que existan: que lleven lo que dicen llevar. ranking.csv es el
    # universo completo que sobrevivió a las guardas (18 aquí, no los 5 del
    # top), e informe.md nombra al primer puesto.
    filas_csv = pd.read_csv(tmp_path / "ranking.csv")
    assert len(filas_csv) == len(resultado.tabla)
    texto_informe = (tmp_path / "informe.md").read_text(encoding="utf-8")
    assert f"## 1. {resultado.fichas[0]['ticker']}" in texto_informe


# --- Los metadatos de la corrida: el contrato con el sub-proyecto C -------


def test_el_resultado_lleva_los_metadatos_de_la_corrida(sin_red):
    resultado = construir_ranking(con_llm=False, n=5, tope=3)
    corrida = resultado.corrida
    assert corrida["universo"] == "sp500"
    assert corrida["tamano_top"] == 5
    assert corrida["tope_por_sector"] == 3
    assert corrida["con_llm"] is False
    assert corrida["n_supervivientes"] == len(resultado.tabla)
    assert corrida["n_panel"] == corrida["n_supervivientes"] + sum(
        resultado.exclusiones.values()
    )
    assert corrida["exclusiones"] == resultado.exclusiones


def test_guardar_escribe_corrida_json(sin_red, tmp_path: Path):
    resultado = construir_ranking(con_llm=False, n=5)
    guardar(resultado, tmp_path)

    corrida = json.loads((tmp_path / "corrida.json").read_text(encoding="utf-8"))
    assert corrida["n_supervivientes"] == len(resultado.tabla)
    assert corrida["tamano_top"] == 5


def test_corrida_json_es_json_estricto(sin_red, tmp_path: Path):
    # Mismo contrato que fichas.json: un NaN se escribiria como el literal
    # `NaN`, que ningun parser estricto acepta. n_panel viene de una suma de
    # enteros de pandas, que es justo donde se cuela un float.
    resultado = construir_ranking(con_llm=False, n=5)
    resultado.corrida["n_panel"] = float("nan")
    with pytest.raises(ValueError):
        guardar(resultado, tmp_path)


def test_corrida_con_una_exclusion_real_n_panel_la_incluye():
    # sin_red no genera exclusiones (las 18 sobreviven), asi que
    # test_el_resultado_lleva_los_metadatos_de_la_corrida cumple su propia
    # asercion de n_panel aunque la implementacion olvide sumar las
    # exclusiones: 0 supervivientes + 0 excluidos no distingue nada. Este
    # test reutiliza el escenario de sector_desconocido (que sí produce una
    # exclusion real) para que la suma tenga algo que sumar de verdad.
    panel, metadatos = panel_y_metadatos()
    metadatos = metadatos.copy()
    metadatos.loc["TE0", "sector_gics"] = None
    with patch("ranking.run.build_panel", return_value=(panel, metadatos, None)):
        resultado = construir_ranking(con_llm=False, n=15)
    corrida = resultado.corrida
    assert corrida["exclusiones"] == {"sector_desconocido": 1}
    assert corrida["n_supervivientes"] == 17
    assert corrida["n_panel"] == 18
    assert corrida["n_panel"] == corrida["n_supervivientes"] + sum(
        corrida["exclusiones"].values()
    )


def test_corrida_registra_el_universo_cuando_source_es_una_lista_de_tickers(sin_red):
    # El acta del gate va a copiar corrida["universo"] entero: tiene que
    # distinguir "corri el S&P 500" de "corri una lista mia", no colapsar
    # ambas en el mismo texto.
    resultado = construir_ranking(source=["AAA", "BBB"], con_llm=False, n=5)
    assert resultado.corrida["universo"] == "2 tickers"


# --- El contrato de fichas.json: JSON estricto, sin NaN -------------------


def test_guardar_revienta_si_una_ficha_trae_nan_en_vez_de_escribir_json_invalido(
    tmp_path: Path,
):
    # fichas.json es el contrato con el sub-proyecto C (Task 8). json.dumps
    # acepta un NaN por defecto y lo escribe como el literal `NaN`, que no es
    # JSON válido. allow_nan=False en guardar() es lo que fija esa garantía en
    # el sitio donde importa -- el escritor de verdad, no sólo en las fichas
    # que ya se sabía que eran serializables (tests/test_ranking_fichas.py).
    ficha_con_nan = {
        "ticker": "AAA",
        "sector_gics": "Information Technology",
        "puesto": 1,
        "compuesto": float("nan"),
        "pilares": {},
        "destacados": [],
        "flojos": [],
        "cobertura": {"kpis_con_dato": 0, "pilares_con_dato": 0},
        "desplazo_a": [],
        "generada_por": "plantilla",
        "narrativa": None,
    }
    resultado = Resultado(
        tabla=pd.DataFrame(),
        fichas=[ficha_con_nan],
        exclusiones={},
        cobertura_panel=None,
        corrida={},
    )
    with pytest.raises(ValueError):
        guardar(resultado, tmp_path)
    # Nada a medio escribir: json.dumps revienta antes de que write_text corra.
    assert not (tmp_path / "fichas.json").exists()


# --- El agujero grande: el camino con_llm=True no lo probaba nadie --------


class ClienteFalso:
    """Devuelve las narrativas que se le den, una por llamada.

    Mismo patrón que tests/test_ranking_llm.py: spec= en los MagicMock para
    que un método que redactar() no llama de verdad falle con AttributeError
    en vez de devolver un Mock silencioso.
    """

    def __init__(self, *respuestas):
        self.respuestas = list(respuestas)
        self.llamadas = []
        self.messages = MagicMock(spec=["parse"])
        self.messages.parse = self._parse

    def _parse(self, **kwargs):
        self.llamadas.append(kwargs)
        siguiente = self.respuestas.pop(0)
        if isinstance(siguiente, Exception):
            raise siguiente
        return MagicMock(spec=["parsed_output"], parsed_output=siguiente)


def _con_cliente_falso(cliente):
    """Sustituye ranking.run.redactar_con_cache por la función real de
    ranking/llm.py con un ClienteFalso inyectado -- así se prueba la
    integración de verdad (inyección de `fuente`, verificación de citas
    contra el texto de Riesgos) sin tocar la red ni requerir ANTHROPIC_API_KEY.
    """

    def _fn(contexto, fuente, cache_dir=None):
        return redactar_con_cache_real(contexto, fuente, cache_dir=cache_dir, cliente=cliente)

    return _fn


def test_con_llm_la_ficha_lleva_narrativa_con_procedencia_completa(sin_red, tmp_path):
    cliente = ClienteFalso(
        Narrativa(
            tesis="Negocio sólido y bien valorado",
            riesgos=[
                Riesgo(
                    afirmacion="Depende de pocos proveedores",
                    cita="depend on a limited number of suppliers",
                )
            ],
        )
    )
    with patch("ranking.run.redactar_con_cache", _con_cliente_falso(cliente)):
        resultado = construir_ranking(con_llm=True, n=1, cache_dir=tmp_path)

    ficha = resultado.fichas[0]
    # redactar_con_cache sólo devuelve {tesis, riesgos}: la procedencia la
    # tiene que inyectar _con_narrativa desde el Riesgos de filings.py. Sin
    # ella, cada cita del informe queda sin forma de localizarse en el
    # filing -- la promesa entera del sub-proyecto.
    assert ficha["generada_por"] != "plantilla"
    assert ficha["narrativa"] is not None
    assert ficha["narrativa"]["fuente"] == {
        "formulario": RIESGOS.formulario,
        "fecha": RIESGOS.fecha,
        "accession": RIESGOS.accession,
        "seccion": RIESGOS.seccion,
        "caracteres_enviados": len(RIESGOS.texto),
        "recortado": RIESGOS.recortado,
    }
    assert ficha["narrativa"]["riesgos"][0]["verificada"] is True
    # Y la valoración viaja en la misma ficha: las dos mitades no se pisan.
    assert ficha["valoracion"]["version"] == "m1"


def test_una_empresa_sin_item_1a_cae_a_plantilla_sin_abortar_la_corrida(sin_red):
    # cargar_riesgos devuelve None cuando el filing no tiene sección
    # extraíble. La corrida entera no debe abortar por eso: la empresa se
    # queda con la ficha de plantilla, como cualquier compañía sin con_llm.
    with patch("ranking.run.cargar_riesgos", return_value=None):
        resultado = construir_ranking(con_llm=True, n=3)
    assert len(resultado.fichas) == 3
    assert {f["generada_por"] for f in resultado.fichas} == {"plantilla"}
    assert all(f["narrativa"] is None for f in resultado.fichas)


def test_una_narrativa_no_producible_cae_a_plantilla_sin_abortar_la_corrida(sin_red):
    # redactar_con_cache devuelve None cuando el modelo no logra producir una
    # narrativa que pase la verificación (tras el reintento). Mismo trato que
    # la ausencia de Item 1A: plantilla, sin abortar.
    with patch("ranking.run.redactar_con_cache", return_value=None):
        resultado = construir_ranking(con_llm=True, n=3)
    assert len(resultado.fichas) == 3
    assert {f["generada_por"] for f in resultado.fichas} == {"plantilla"}
    assert all(f["narrativa"] is None for f in resultado.fichas)


def test_el_contexto_no_lleva_ni_un_digito():
    # contexto usa descriptor() precisamente para que no haya ninguna cifra
    # que el modelo pueda copiar a la tesis o a una afirmación. Nadie lo
    # comprobaba: sin_digitos ya existe en ranking/verificacion.py para esto.
    ficha = {
        "ticker": "AAA",
        "sector_gics": "Information Technology",
        "pilares": {
            "calidad": 1.9,
            "crecimiento": -0.3,
            "valoracion": 0.1,
            "solidez": None,
        },
        "destacados": [{"kpi": "roic", "valor": 0.31, "z": 2.4}],
        "flojos": [{"kpi": "per", "valor": 34.2, "z": 2.0}],
    }
    assert sin_digitos(contexto(ficha))


# --- La pregunta en frío: universos degenerados no deben mentir -----------


def test_una_empresa_sin_sector_se_excluye_como_sector_desconocido_no_generico():
    # El plan llamaba a marcar_sin_pares con dos argumentos; la firma real
    # pide tres porque agrupar "sector desconocido" y "sin pares suficientes"
    # bajo una sola etiqueta pone una afirmación falsa en el informe. Este
    # test comprueba la etiqueta concreta, no sólo que algo se excluya.
    panel, metadatos = panel_y_metadatos()
    metadatos = metadatos.copy()
    metadatos.loc["TE0", "sector_gics"] = None
    with patch("ranking.run.build_panel", return_value=(panel, metadatos, None)):
        resultado = construir_ranking(con_llm=False, n=15)
    assert resultado.exclusiones.get("sector_desconocido") == 1


def test_panel_vacio_no_revienta():
    # La forma real que build_panel devuelve para un universo vacío (ver
    # fundamentals/run.py): un DataFrame sin filas pero con las columnas de
    # los KPIs y "trimestre", nunca un DataFrame sin columnas en absoluto.
    vacio = pd.DataFrame(columns=[*TODOS_LOS_KPIS, "trimestre"], dtype="float64")
    metadatos_vacio = pd.DataFrame(columns=["sector_gics"])
    with patch("ranking.run.build_panel", return_value=(vacio, metadatos_vacio, None)):
        resultado = construir_ranking(con_llm=False, n=5)
    assert resultado.fichas == []
    assert resultado.tabla.empty
    assert resultado.exclusiones == {}
    assert resultado.panel is None


def test_menos_candidatos_que_el_top_no_revienta_ni_rellena():
    # Un solo sector con menos empresas que MIN_PARES (3): zscore_within_sector
    # no puede calcular dispersión, así que nadie de ese sector obtiene
    # compuesto y nadie entra en el top, aunque se pida n=15.
    generador = np.random.default_rng(3)
    trimestres = ["2024Q3", "2024Q4", "2025Q1", "2025Q2"]
    filas, indice, meta = [], [], []
    for numero in range(2):
        ticker = f"SOLO{numero}"
        meta.append({"ticker": ticker, "sector_gics": "Utilities"})
        for trimestre in trimestres:
            fila = {kpi: 1.0 for kpi in TODOS_LOS_KPIS}
            fila.update(
                {
                    f"z_{kpi}": v
                    for kpi, v in zip(
                        TODOS_LOS_KPIS, generador.normal(size=len(TODOS_LOS_KPIS))
                    )
                }
            )
            fila["trimestre"] = trimestre
            filas.append(fila)
            indice.append((ticker, pd.Period(trimestre, freq="Q").end_time.normalize()))
    panel = pd.DataFrame(
        filas, index=pd.MultiIndex.from_tuples(indice, names=["ticker", "periodo"])
    )
    metadatos = pd.DataFrame(meta).set_index("ticker")
    with patch("ranking.run.build_panel", return_value=(panel, metadatos, None)):
        resultado = construir_ranking(con_llm=False, n=15)
    assert resultado.fichas == []
    assert resultado.exclusiones.get("sector_sin_pares") == 2


# --- La valoración en cada ficha: se adjunta, no puntúa -------------------


def test_cada_ficha_lleva_su_valoracion(sin_red, valoracion_doble):
    resultado = construir_ranking(con_llm=False, n=5)
    assert all("valoracion" in ficha for ficha in resultado.fichas)
    # Llamadas enteras, no argumento a argumento: un tercer argumento de más
    # (o una llamada de más) también tiene que fallar.
    esperadas = [call(f["ticker"], f["pilares"]["valoracion"]) for f in resultado.fichas]
    assert valoracion_doble.call_args_list == esperadas


def test_la_valoracion_no_cambia_ni_el_orden_ni_la_nota(sin_red):
    con = construir_ranking(con_llm=False, n=5)
    sin = construir_ranking(con_llm=False, n=5, con_valoracion=False)
    sin_la_clave = [{k: v for k, v in f.items() if k != "valoracion"} for f in con.fichas]
    assert sin_la_clave == sin.fichas
    assert con.tabla.equals(sin.tabla)


def test_sin_valoracion_no_se_sale_a_valorar(sin_red, valoracion_doble):
    resultado = construir_ranking(con_llm=False, n=5, con_valoracion=False)
    assert all("valoracion" not in ficha for ficha in resultado.fichas)
    valoracion_doble.assert_not_called()


def test_una_valoracion_que_revienta_no_tumba_la_corrida(sin_red, valoracion_doble):
    valoracion_doble.side_effect = RuntimeError("un defecto del motor")
    resultado = construir_ranking(con_llm=False, n=5)
    assert {f["valoracion"]["motivo"] for f in resultado.fichas} == {"error_interno"}


def test_un_defecto_al_valorar_deja_traza_en_el_log(sin_red, valoracion_doble, caplog):
    # La ficha dice `error_interno` pero no por qué: la causa tiene que quedar
    # en el log, con el traceback, o el defecto se vuelve invisible.
    valoracion_doble.side_effect = RuntimeError("un defecto del motor")
    with caplog.at_level(logging.ERROR, logger="ranking.run"):
        resultado = construir_ranking(con_llm=False, n=1)
    assert "falló por un defecto del motor" in caplog.text
    assert resultado.fichas[0]["ticker"] in caplog.text
    assert "RuntimeError" in caplog.text


def test_sin_tasa_libre_se_deja_de_preguntar_tras_el_primero(sin_red, valoracion_doble):
    valoracion_doble.return_value = {"version": "m1", "fecha": "2026-10-12", "motivo": "sin_tasa_libre"}
    resultado = construir_ranking(con_llm=False, n=5)
    assert valoracion_doble.call_count == 1
    assert {f["valoracion"]["motivo"] for f in resultado.fichas} == {"sin_tasa_libre"}


def test_sin_red_se_deja_de_preguntar_tras_dos_seguidos(sin_red, valoracion_doble):
    valoracion_doble.return_value = {"version": "m1", "fecha": "2026-10-12", "motivo": "sin_red"}
    resultado = construir_ranking(con_llm=False, n=5)
    assert valoracion_doble.call_count == 2
    assert {f["valoracion"]["motivo"] for f in resultado.fichas} == {"sin_red"}


def test_un_sin_red_suelto_no_corta_a_los_demas(sin_red, valoracion_doble):
    # Un símbolo que Yahoo no conoce da `sin_red` con la red sana.
    buena = {"version": "m1", "fecha": "2026-10-12", "motivo": "sin_estados"}
    rara = {"version": "m1", "fecha": "2026-10-12", "motivo": "sin_red"}
    valoracion_doble.side_effect = [rara, buena, rara, buena, buena]
    construir_ranking(con_llm=False, n=5)
    assert valoracion_doble.call_count == 5


def test_un_fallo_de_una_empresa_no_corta_las_demas(sin_red, valoracion_doble):
    valoracion_doble.return_value = {"version": "m1", "fecha": "2026-10-12", "motivo": "sin_estados"}
    construir_ranking(con_llm=False, n=5)
    assert valoracion_doble.call_count == 5


def _valoracion_real() -> dict:
    """Una valoración como la que escribe el motor: la salida de `a_dict`.

    El doble por defecto es una fallida de tres claves; ésta lleva el plano
    entero (votos, supuestos, rango), que es donde se podría colar un NaN.
    """
    f, p = fundamentos(), perfil()
    supuestos = deducir(f, p, r_f=0.04, beta=None, tasa=0.25, consenso=None)
    return a_dict(calcular(f, p, supuestos, 0.0, date(2026, 10, 12)))


def test_guardar_con_una_valoracion_real_sigue_siendo_json_estricto(sin_red, valoracion_doble, tmp_path):
    plano = _valoracion_real()
    valoracion_doble.return_value = plano
    guardar(construir_ranking(con_llm=False, n=5), tmp_path)
    fichas = json.loads((tmp_path / "fichas.json").read_text(encoding="utf-8"))
    assert [f["valoracion"] for f in fichas] == [plano] * 5


# --- El panel de referencia del Analizador ----------------------------------


def test_el_resultado_lleva_el_panel_crudo_con_su_sector(sin_red):
    resultado = construir_ranking(con_llm=False, n=5)
    panel = resultado.panel
    # Sin los z: se recalculan al insertar una empresa que no estaba.
    assert not any(str(c).startswith("z_") for c in panel.columns)
    assert {"trimestre", "sector_gics", *TODOS_LOS_KPIS} <= set(panel.columns)
    assert list(panel.index.names) == ["ticker", "periodo"]
    assert panel.xs("TE0", level="ticker")["sector_gics"].unique().tolist() == ["Tech"]


def test_guardar_escribe_el_panel_en_parquet(sin_red, tmp_path: Path):
    resultado = construir_ranking(con_llm=False, n=5)
    guardar(resultado, tmp_path)
    leido = pd.read_parquet(tmp_path / "panel.parquet")
    # Entero y con el índice que reconstruye el Analizador: en el panel de
    # prueba todos los KPIs valen 1.0, así que comparar una celda acertaría
    # con cualquier fila.
    leido["periodo"] = pd.to_datetime(leido["periodo"])
    pd.testing.assert_frame_equal(
        leido.set_index(["ticker", "periodo"]).sort_index(), resultado.panel.sort_index()
    )


def test_sin_panel_no_se_escribe_parquet(sin_red, tmp_path: Path):
    resultado = construir_ranking(con_llm=False, n=5)
    resultado.panel = None
    guardar(resultado, tmp_path)
    assert not (tmp_path / "panel.parquet").exists()
    assert (tmp_path / "fichas.json").exists()


@pytest.mark.parametrize("sin_panel", [None, pd.DataFrame()], ids=["none", "vacio"])
def test_sin_panel_se_borra_el_de_la_corrida_anterior(sin_red, tmp_path: Path, sin_panel):
    """El parquet viejo junto a fichas nuevas sería una referencia que ya no
    corresponde a los candidatos."""
    guardar(construir_ranking(con_llm=False, n=5), tmp_path)
    assert (tmp_path / "panel.parquet").exists()
    resultado = construir_ranking(con_llm=False, n=5)
    resultado.panel = sin_panel
    guardar(resultado, tmp_path)
    assert not (tmp_path / "panel.parquet").exists()
    assert (tmp_path / "fichas.json").exists()


def test_si_el_panel_no_se_puede_convertir_se_guardan_las_fichas_sin_panel(
    sin_red, tmp_path: Path, caplog
):
    """El panel es prescindible y las fichas no: un fallo de pyarrow al
    convertirlo no puede tumbar `guardar`, porque la vista de candidatos sólo
    captura `CorridaAbortada` y enseñaría una traza sin limpiar lo marcado. La
    carpeta queda sin panel, no con el viejo, y la causa va al log."""
    (tmp_path / "fichas.json").write_text("[]", encoding="utf-8")
    (tmp_path / "panel.parquet").write_bytes(b"viejo")
    resultado = construir_ranking(con_llm=False, n=5)
    # Un `TypeError` de pyarrow, que no es ni `OSError` ni `ValueError`: es lo
    # que da una columna de objetos con tipos mezclados.
    error = pa.ArrowTypeError("Expected bytes, got a 'float' object")
    with (
        patch.object(pd.DataFrame, "to_parquet", side_effect=error),
        caplog.at_level(logging.ERROR, logger="ranking.run"),
    ):
        guardar(resultado, tmp_path)
    fichas = json.loads((tmp_path / "fichas.json").read_text(encoding="utf-8"))
    assert fichas == json.loads(json.dumps(resultado.fichas))
    assert not (tmp_path / "panel.parquet").exists()
    assert "panel" in caplog.text and "ArrowTypeError" in caplog.text


def test_si_falla_la_escritura_del_panel_se_guardan_las_fichas_sin_panel(
    sin_red, tmp_path: Path, caplog
):
    """Un fallo del disco ya con las fichas nuevas escritas (un bloqueo de
    Windows al abrir el fichero) deja la carpeta sin panel, que el Analizador
    sabe tratar, y no con el de la corrida anterior; y no lanza, por lo mismo
    que el de arriba."""
    (tmp_path / "fichas.json").write_text("[]", encoding="utf-8")
    (tmp_path / "panel.parquet").write_bytes(b"viejo")
    resultado = construir_ranking(con_llm=False, n=5)
    escribir = Path.write_bytes

    def falla_el_panel(ruta, datos):
        if ruta.name == "panel.parquet":
            raise PermissionError("bloqueado")
        return escribir(ruta, datos)

    with (
        patch.object(Path, "write_bytes", falla_el_panel),
        caplog.at_level(logging.ERROR, logger="ranking.run"),
    ):
        guardar(resultado, tmp_path)
    fichas = json.loads((tmp_path / "fichas.json").read_text(encoding="utf-8"))
    assert fichas == json.loads(json.dumps(resultado.fichas))
    assert not (tmp_path / "panel.parquet").exists()
    assert "panel" in caplog.text and "PermissionError" in caplog.text


# --- La inclinación macro (sub-proyecto P) ----------------------------

from datetime import date as _date

from macro.criterio import INCLINACION
from macro.fase import Fase


def _fase(clave="recuperacion"):
    return Fase(clave, None, _date(2026, 10, 1), 99.5, 0.3, 4)


def test_sin_macro_la_corrida_dice_none_y_nadie_lleva_ajuste(sin_red):
    sin = construir_ranking(con_llm=False, n=5)
    assert sin.corrida["macro"] is None
    assert all(f["ajuste_macro"] == 0.0 for f in sin.fichas)


def test_con_macro_la_corrida_registra_region_fase_y_movimientos(sin_red):
    neutro = construir_ranking(con_llm=False, n=5)
    con = construir_ranking(con_llm=False, n=5, macro=_fase(), region="usa")
    bloque = con.corrida["macro"]
    assert bloque["region"] == "usa" and bloque["fase"] == "recuperacion"
    assert bloque["mes_dato"] == "2026-10-01" and bloque["inclinacion"] == INCLINACION
    antes = {f["ticker"] for f in neutro.fichas}
    despues = {f["ticker"] for f in con.fichas}
    assert set(bloque["entradas"]) == despues - antes
    assert set(bloque["salidas"]) == antes - despues


def test_con_macro_las_financieras_llevan_su_ajuste_y_el_compuesto_no_cambia(sin_red):
    neutro = {f["ticker"]: f["compuesto"] for f in construir_ranking(con_llm=False, n=15).fichas}
    con = construir_ranking(con_llm=False, n=15, macro=_fase(), region="usa")
    for ficha in con.fichas:
        esperado = INCLINACION if ficha["sector_gics"] == "Financials" else 0.0
        assert ficha["ajuste_macro"] == esperado
        if ficha["ticker"] in neutro:
            assert ficha["compuesto"] == neutro[ficha["ticker"]]


def test_una_inclinacion_grande_mete_financieras_en_el_top(sin_red, monkeypatch):
    """Con una inclinación exagerada se ve que de verdad se aplica antes de seleccionar."""
    import ranking.score as score

    monkeypatch.setattr(score, "INCLINACION", 10.0)
    con = construir_ranking(con_llm=False, n=3, tope=3, macro=_fase(), region="usa")
    assert {f["sector_gics"] for f in con.fichas} == {"Financials"}


def test_una_fase_sin_clave_no_se_acepta(sin_red):
    with pytest.raises(ValueError):
        construir_ranking(
            con_llm=False, n=5,
            macro=Fase(None, "indeterminada", _date(2026, 10, 1), 100.0, 0.0, 0),
            region="usa",
        )


def test_una_region_desconocida_no_se_acepta(sin_red):
    with pytest.raises(ValueError):
        construir_ranking(con_llm=False, n=5, macro=_fase(), region="marte")


def test_la_corrida_con_macro_es_json_estricto(sin_red, tmp_path):
    guardar(construir_ranking(con_llm=False, n=5, macro=_fase(), region="usa"), tmp_path)
    corrida = json.loads((tmp_path / "corrida.json").read_text(encoding="utf-8"))
    bloque = corrida["macro"]
    assert bloque["fase"] == "recuperacion"
    assert bloque["mes_dato"] == "2026-10-01"
    assert bloque["inclinacion"] == INCLINACION
    assert isinstance(bloque["entradas"], list) and isinstance(bloque["salidas"], list)


def test_una_inclinacion_grande_mueve_de_verdad_entradas_y_salidas(sin_red, monkeypatch):
    import ranking.score as score

    neutro = {f["ticker"] for f in construir_ranking(con_llm=False, n=3, tope=3).fichas}
    monkeypatch.setattr(score, "INCLINACION", 10.0)
    con = construir_ranking(con_llm=False, n=3, tope=3, macro=_fase(), region="usa")
    bloque = con.corrida["macro"]
    inclinado = {f["ticker"] for f in con.fichas}
    sector = {f["ticker"]: f["sector_gics"] for f in con.fichas}
    assert bloque["entradas"] and bloque["salidas"]
    assert all(sector[t] == "Financials" for t in bloque["entradas"])
    assert set(bloque["salidas"]) == neutro - inclinado
    assert bloque["entradas"] == sorted(bloque["entradas"])
    assert bloque["salidas"] == sorted(bloque["salidas"])


def test_con_macro_none_explicito_el_resultado_es_identico(sin_red):
    base = construir_ranking(con_llm=False, n=15)
    explicito = construir_ranking(con_llm=False, n=15, macro=None, region=None)
    assert base.fichas == explicito.fichas
    pd.testing.assert_frame_equal(base.tabla, explicito.tabla)


def test_sin_macro_los_compuestos_de_las_fichas_van_en_orden_no_creciente(sin_red):
    compuestos = [f["compuesto"] for f in construir_ranking(con_llm=False, n=15).fichas]
    assert compuestos == sorted(compuestos, reverse=True)

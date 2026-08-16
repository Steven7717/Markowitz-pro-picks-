import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from fundamentals.kpis import TODOS_LOS_KPIS
from ranking.filings import Riesgos
from ranking.llm import Narrativa, Riesgo
from ranking.llm import redactar_con_cache as redactar_con_cache_real
from ranking.run import Resultado, _contexto, construir_ranking, guardar
from ranking.verificacion import sin_digitos

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
    # _contexto usa descriptor() precisamente para que no haya ninguna cifra
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
    assert sin_digitos(_contexto(ficha))


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

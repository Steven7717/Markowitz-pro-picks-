import numpy as np
import pandas as pd
import plotly.graph_objects as go
from charts import (
    plot_efficient_frontier,
    plot_weights_pie,
    plot_correlation_heatmap,
    plot_comparison,
)


def _sim_df() -> pd.DataFrame:
    rng = np.random.default_rng(0)
    n = 200
    sharpe = rng.uniform(0.5, 2.5, n)
    return pd.DataFrame({
        "ret": rng.uniform(0.05, 0.30, n),
        "vol": rng.uniform(0.05, 0.35, n),
        "sharpe": sharpe,
        # Con exceso positivo el criterio del optimizador ES el Sharpe, asi que
        # aqui las dos columnas coinciden. `simulate_portfolios` la escribe
        # siempre y la frontera la exige: sin ella el grafico volveria a
        # colorear por un cociente que no ordena en mercado bajista.
        "criterio": sharpe,
    })


def _returns() -> pd.DataFrame:
    rng = np.random.default_rng(0)
    return pd.DataFrame(
        rng.normal(0.001, 0.015, (252, 3)),
        columns=["AAPL", "MSFT", "GOOGL"],
    )


def test_plot_efficient_frontier_returns_figure():
    fig = plot_efficient_frontier(
        sim_df=_sim_df(),
        optimal={"annual_return": 0.18, "annual_vol": 0.14, "sharpe": 1.3, "weights": np.array([0.5, 0.3, 0.2])},
        benchmark={"annual_return": 0.12, "annual_vol": 0.16, "sharpe": 0.75},
        equal_weight={"annual_return": 0.13, "annual_vol": 0.15, "sharpe": 0.87},
        tickers=["AAPL", "MSFT", "GOOGL"],
    )
    assert isinstance(fig, go.Figure)
    assert len(fig.data) >= 3


def test_plot_efficient_frontier_no_benchmark():
    fig = plot_efficient_frontier(
        sim_df=_sim_df(),
        optimal={"annual_return": 0.18, "annual_vol": 0.14, "sharpe": 1.3, "weights": np.array([0.5, 0.3, 0.2])},
        benchmark=None,
        equal_weight={"annual_return": 0.13, "annual_vol": 0.15, "sharpe": 0.87},
        tickers=["AAPL", "MSFT", "GOOGL"],
    )
    assert isinstance(fig, go.Figure)


def test_plot_weights_pie_returns_figure():
    fig = plot_weights_pie(np.array([0.5, 0.3, 0.2]), ["AAPL", "MSFT", "GOOGL"])
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 1


def test_plot_correlation_heatmap_returns_figure():
    fig = plot_correlation_heatmap(_returns())
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 1


def test_plot_comparison_returns_figure():
    fig = plot_comparison(
        tickers=["AAPL", "MSFT", "GOOGL"],
        opt_weights=np.array([0.5, 0.3, 0.2]),
        ew_weights=np.array([1/3, 1/3, 1/3]),
        opt_ret=0.18,
        ew_ret=0.13,
        opt_vol=0.14,
        ew_vol=0.15,
    )
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 2


# ── The chart must name the strategy actually plotted ─────────────────────────

def _frontier(**kw):
    return plot_efficient_frontier(
        sim_df=_sim_df(),
        optimal={"annual_return": 0.18, "annual_vol": 0.14, "sharpe": 1.3,
                 "weights": np.array([0.5, 0.3, 0.2])},
        benchmark=None,
        equal_weight={"annual_return": 0.13, "annual_vol": 0.15, "sharpe": 0.87},
        tickers=["AAPL", "MSFT", "GOOGL"],
        **kw,
    )


def test_frontier_marker_defaults_to_a_generic_optimum_label():
    names = [t.name for t in _frontier().data]
    assert any("Óptimo" in n for n in names)


def test_frontier_marker_uses_the_supplied_strategy_label():
    names = [t.name for t in _frontier(strategy_label="Mínima varianza").data]
    assert any("Mínima varianza" in n for n in names)


def test_frontier_marker_still_shows_the_sharpe_ratio():
    names = [t.name for t in _frontier(strategy_label="Paridad de riesgo").data]
    assert any("Sharpe" in n for n in names)


def test_la_tarta_no_escribe_los_pesos_nulos_en_notacion_cientifica():
    """Un activo que se queda fuera pesa 7.7e-16, no 0, y se veía como tal.

    `textinfo="label+percent"` deja el formato al de por defecto de Plotly, que
    es de dígitos significativos (`~%`): al lado del ticker salía
    «CSGP 7.67e-16%», que no se lee como «cero» sino como un fallo. Con
    decimales fijos sale «0.0%», que es lo que ese peso es.
    """
    fig = plot_weights_pie(np.array([0.6, 0.4, 7.67e-16]), ["AAA", "BBB", "CCC"])
    trazo = fig.data[0]
    assert trazo.texttemplate is not None, "sin plantilla el formato lo elige Plotly"
    assert "%{percent:." in trazo.texttemplate


def test_la_tarta_sigue_etiquetando_cada_porcion_con_su_ticker():
    trazo = plot_weights_pie(np.array([0.5, 0.5]), ["AAA", "BBB"]).data[0]
    assert "%{label}" in trazo.texttemplate


def test_la_tarta_no_deja_dos_formatos_compitiendo():
    """`textinfo` y `texttemplate` se pisan; que quede sólo el que manda."""
    trazo = plot_weights_pie(np.array([0.5, 0.5]), ["AAA", "BBB"]).data[0]
    assert trazo.textinfo is None


# ── R1 · La nube y la estrella tienen que hablar del mismo criterio ───────────
#
# Medido con el caso bajista de tres activos: la estrella «Máximo Sharpe» salía
# con Sharpe -1,16 mientras la nube simulada llegaba a -0,26, o sea que el 98,1%
# de los 10.000 puntos tenía un Sharpe MAYOR que la cartera que el programa
# acababa de elegir, y el punto más brillante de la escala era el del 46% de
# volatilidad — exactamente el que el arreglo del optimizador acababa de quitar.
# Media pantalla decía una cosa y la otra media la contraria.

RF_ANUAL = 0.04

# Dos carteras que sólo se pueden ordenar bien con el criterio correcto:
# ninguna supera a las letras, y el cociente de Sharpe premia a la volátil
# (-0,043 contra -0,083) porque agrandar el denominador de un número negativo
# lo acerca a cero.
_TRANQUILA = {"ret": 0.03, "vol": 0.12}   # exceso -0,01 · Sharpe -0,0833
_VOLATIL = {"ret": 0.02, "vol": 0.46}     # exceso -0,02 · Sharpe -0,0435
TRANQUILA, VOLATIL = 0, 1


def _nube_bajista() -> pd.DataFrame:
    filas = []
    for punto in (_TRANQUILA, _VOLATIL):
        exceso = punto["ret"] - RF_ANUAL
        filas.append({
            "ret": punto["ret"],
            "vol": punto["vol"],
            "sharpe": exceso / punto["vol"],
            "criterio": exceso * punto["vol"],
        })
    return pd.DataFrame(filas)


def _senala_como_mejor(fig) -> int:
    """El índice del punto que la escala de color pinta como el mejor de todos.

    Leerlo así y no mirar la columna elegida es lo que hace al test hablar de lo
    que el usuario ve: con la escala invertida, el valor más bajo es el que sale
    más brillante.
    """
    marcador = fig.data[0].marker
    valores = np.asarray(marcador.color, dtype=float)
    return int(np.argmin(valores) if marcador.reversescale else np.argmax(valores))


def _bajista(**kw):
    optimal = {"annual_return": 0.03, "annual_vol": 0.12, "sharpe": -0.0833,
               "weights": np.array([1.0, 0.0, 0.0])}
    optimal.update(kw.pop("optimal", {}))
    return plot_efficient_frontier(
        sim_df=_nube_bajista(),
        optimal=optimal,
        benchmark=None,
        equal_weight={"annual_return": 0.025, "annual_vol": 0.20, "sharpe": -0.075},
        tickers=["AAA", "BBB", "CCC"],
        strategy_label="Máximo Sharpe (Markowitz)",
        **kw,
    )


def test_la_nube_no_senala_como_mejor_la_cartera_mas_volatil_de_las_que_pierden():
    """El Sharpe clásico ordenaba al revés justo donde deja de ordenar."""
    assert _senala_como_mejor(_bajista()) == TRANQUILA


def test_sin_prima_la_escala_de_color_es_la_volatilidad_y_lo_dice():
    """Si la cartera se eligió por mínima varianza, el color tiene que serlo.

    Colorear por un cociente cuando la cartera se eligió por otra cosa es el
    mismo fallo de origen: la escala promete un orden que no es el que se usó.
    """
    fig = _bajista(optimal={"sin_prima": True})
    assert _senala_como_mejor(fig) == TRANQUILA
    assert "olatilidad" in fig.data[0].marker.colorbar.title.text


def test_sin_prima_la_estrella_cae_donde_la_escala_pinta_mejor():
    """La estrella no puede quedar por debajo del 98% de la nube.

    Sin prima la cartera se elige por mínima varianza y la nube es una muestra
    del mismo conjunto factible, así que la estrella tiene que ser el punto de
    menos volatilidad de todo el gráfico — que es justo lo que el color señala.
    """
    fig = _bajista(optimal={"sin_prima": True})
    nube = fig.data[0]
    mejor = _senala_como_mejor(fig)
    estrella = [t for t in fig.data if t.marker.symbol == "star"][0]
    assert float(nube.x[mejor]) == float(np.asarray(nube.x, dtype=float).min())
    assert float(estrella.x[0]) <= float(np.asarray(nube.x, dtype=float).min())


def test_sin_prima_la_leyenda_no_promete_un_sharpe():
    """«Máximo Sharpe (Sharpe: -1,16)» sobre una cartera de mínima varianza."""
    nombres = [t.name for t in _bajista(optimal={"sin_prima": True}).data]
    assert not any("Sharpe:" in n for n in nombres), nombres


def test_sin_prima_la_leyenda_da_la_volatilidad_que_si_decidio():
    estrella = [t for t in _bajista(optimal={"sin_prima": True}).data
                if t.marker.symbol == "star"][0]
    assert "12" in estrella.name and "%" in estrella.name


def test_con_prima_la_leyenda_sigue_dando_el_sharpe():
    """El caso normal no se toca: con prima, el criterio ES el Sharpe."""
    estrella = [t for t in _bajista().data if t.marker.symbol == "star"][0]
    assert "Sharpe" in estrella.name


def test_sin_prima_el_titulo_explica_por_que_el_color_cambia():
    assert "prima" in _bajista(optimal={"sin_prima": True}).layout.title.text.lower()

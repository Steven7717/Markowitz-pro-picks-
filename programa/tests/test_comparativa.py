"""Enfrentar portafolios sin fundir dos que se llaman igual."""

from pathlib import Path

import comparativa
from cartera import Entrada, Portafolio, Posicion


def _portafolio(nombre: str, pesos: dict[str, float], fecha: str) -> Portafolio:
    return Portafolio(
        nombre=nombre,
        fecha=fecha,
        posiciones=[Posicion(ticker=t, peso=p) for t, p in pesos.items()],
        horizonte="1 Mes",
        estrategia="max_sharpe",
        peso_min=0.0,
        peso_max=0.3,
        permitir_cortos=False,
        shrinkage=True,
    )


def _entrada(nombre: str, pesos: dict[str, float], fecha: str, fichero: str) -> Entrada:
    return Entrada(ruta=Path("portafolios") / fichero,
                   portafolio=_portafolio(nombre, pesos, fecha), error=None)


def test_two_portfolios_with_the_same_name_get_different_labels():
    # Mismo nombre y mismo minuto: `fecha_legible` no lleva segundos, asi que
    # la etiqueta que habia no los distinguia y el diccionario fundia los dos.
    entradas = [
        _entrada("Mi cartera", {"AAPL": 0.6, "MSFT": 0.4},
                 "2026-09-10T10:52:38", "2026-09-10-105238-mi-cartera.json"),
        _entrada("Mi cartera", {"AAPL": 0.2, "NVDA": 0.8},
                 "2026-09-10T10:52:51", "2026-09-10-105251-mi-cartera.json"),
    ]

    etiquetas = comparativa.etiquetar(entradas)

    assert len(etiquetas) == 2


def test_a_unique_name_keeps_the_label_readable():
    # El desempate solo aparece cuando hace falta: en el caso normal la
    # etiqueta sigue siendo el nombre y la fecha, que es lo que se lee bien.
    entradas = [
        _entrada("Conservadora", {"AAPL": 1.0},
                 "2026-09-10T10:52:38", "2026-09-10-105238-conservadora.json"),
        _entrada("Agresiva", {"NVDA": 1.0},
                 "2026-09-11T09:00:00", "2026-09-11-090000-agresiva.json"),
    ]

    etiquetas = comparativa.etiquetar(entradas)

    assert "Conservadora · 10/09/2026 10:52" in etiquetas
    assert "Agresiva · 11/09/2026 09:00" in etiquetas


def test_broken_files_are_left_out_of_the_comparison():
    entradas = [
        _entrada("Buena", {"AAPL": 1.0}, "2026-09-10T10:00:00", "buena.json"),
        Entrada(ruta=Path("portafolios/rota.json"), portafolio=None, error="JSON roto"),
    ]

    assert list(comparativa.etiquetar(entradas)) == ["Buena · 10/09/2026 10:00"]


def test_the_weights_matrix_keeps_both_portfolios_apart():
    # El defecto: la matriz se indexaba por `p.nombre`, asi que dos guardados
    # con el mismo nombre colapsaban en una sola columna con las filas
    # mezcladas de ambos y pesos que sumaban 140%.
    entradas = [
        _entrada("Mi cartera", {"AAPL": 0.6, "MSFT": 0.4},
                 "2026-09-10T10:52:38", "a.json"),
        _entrada("Mi cartera", {"AAPL": 0.2, "NVDA": 0.8},
                 "2026-09-10T10:52:51", "b.json"),
    ]
    etiquetas = comparativa.etiquetar(entradas)

    filas = comparativa.matriz_de_pesos(etiquetas)

    columnas = [c for c in filas[0] if c != "Ticker"]
    assert len(columnas) == 2
    por_ticker = {fila["Ticker"]: fila for fila in filas}
    assert por_ticker["AAPL"][columnas[0]] == "60.00%"
    assert por_ticker["AAPL"][columnas[1]] == "20.00%"


def test_an_asset_missing_from_a_portfolio_shows_a_dash_not_a_zero():
    # Un cero significaria "se considero y se le dio peso nulo"; en la mayoria
    # de los casos ni siquiera estaba en la lista de entrada.
    entradas = [
        _entrada("Una", {"AAPL": 1.0}, "2026-09-10T10:00:00", "a.json"),
        _entrada("Otra", {"NVDA": 1.0}, "2026-09-11T10:00:00", "b.json"),
    ]

    filas = comparativa.matriz_de_pesos(comparativa.etiquetar(entradas))

    por_ticker = {fila["Ticker"]: fila for fila in filas}
    assert por_ticker["AAPL"]["Otra · 11/09/2026 10:00"] == "—"
    assert por_ticker["NVDA"]["Una · 10/09/2026 10:00"] == "—"


def test_one_shared_asset_is_written_in_the_singular():
    # Decia "1 activos aparecen en todos".
    entradas = [
        _entrada("Una", {"AAPL": 0.5, "MSFT": 0.5}, "2026-09-10T10:00:00", "a.json"),
        _entrada("Otra", {"AAPL": 0.5, "NVDA": 0.5}, "2026-09-11T10:00:00", "b.json"),
    ]

    frase = comparativa.frase_de_cobertura(comparativa.etiquetar(entradas))

    assert frase.startswith("1 activo aparece en todos los portafolios elegidos, de 3")


def test_three_shared_assets_are_written_in_the_plural():
    entradas = [
        _entrada("Una", {"AAPL": 0.4, "MSFT": 0.3, "NVDA": 0.3},
                 "2026-09-10T10:00:00", "a.json"),
        _entrada("Otra", {"AAPL": 0.5, "MSFT": 0.3, "NVDA": 0.2},
                 "2026-09-11T10:00:00", "b.json"),
        _entrada("Tercera", {"AAPL": 0.4, "MSFT": 0.4, "NVDA": 0.2},
                 "2026-09-12T10:00:00", "c.json"),
    ]

    frase = comparativa.frase_de_cobertura(comparativa.etiquetar(entradas))

    assert frase.startswith("3 activos aparecen en todos los portafolios elegidos, de 3")

from datetime import date

from noticias import agenda

# Forma real de yfinance 1.6.0 `.calendar`, sondeada el 2026-09-08.
CALENDARIO = {
    "Dividend Date": date(2026, 8, 12),
    "Ex-Dividend Date": date(2026, 8, 9),
    "Earnings Date": [date(2026, 10, 29)],     # LISTA, aunque traiga una
    "Earnings High": 2.07,
    "Earnings Low": 1.93,
    "Earnings Average": 1.98124,
}


def test_saca_los_tres_eventos():
    salida = agenda.desde_calendario("AAPL", CALENDARIO, hoy=date(2026, 8, 1))
    clases = {e.clase for e in salida}
    assert clases == {"resultados", "ex-dividendo", "dividendo"}


def test_earnings_date_es_una_lista_aunque_traiga_uno():
    """Tratarla como fecha suelta da un evento con una lista dentro."""
    salida = agenda.desde_calendario("AAPL", CALENDARIO, hoy=date(2026, 8, 1))
    resultados = [e for e in salida if e.clase == "resultados"][0]
    assert resultados.cuando == date(2026, 10, 29)


def test_el_eps_estimado_viaja_en_el_detalle():
    salida = agenda.desde_calendario("AAPL", CALENDARIO, hoy=date(2026, 8, 1))
    resultados = [e for e in salida if e.clase == "resultados"][0]
    assert "1.98" in resultados.detalle


def test_una_fecha_ausente_no_inventa_evento():
    """Sin fecha no hay evento. Un date() por defecto seria una afirmacion."""
    salida = agenda.desde_calendario("AAPL", {"Earnings Date": []}, hoy=date(2026, 9, 8))
    assert salida == ()


def test_un_calendario_vacio_no_revienta():
    assert agenda.desde_calendario("AAPL", {}, hoy=date(2026, 9, 8)) == ()
    assert agenda.desde_calendario("AAPL", None, hoy=date(2026, 9, 8)) == ()


def test_los_eventos_pasados_no_salen():
    """El bloque se llama 'lo que viene'. Un ex-dividendo de hace un mes no."""
    salida = agenda.desde_calendario("AAPL", CALENDARIO, hoy=date(2026, 9, 8))
    assert all(e.cuando >= date(2026, 9, 8) for e in salida)
    assert {e.clase for e in salida} == {"resultados"}


def test_ordena_por_fecha_ascendente():
    """Al reves que las noticias: aqui lo mas cercano es lo mas urgente."""
    calendario = dict(CALENDARIO, **{
        "Ex-Dividend Date": date(2026, 11, 5),
        "Dividend Date": date(2026, 11, 20),
    })
    salida = agenda.desde_calendario("AAPL", calendario, hoy=date(2026, 9, 8))
    fechas = [e.cuando for e in salida]
    assert fechas == sorted(fechas)
    assert len(fechas) == 3

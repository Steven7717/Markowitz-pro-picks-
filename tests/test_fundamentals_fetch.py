from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from fundamentals.fetch import CoverageReport, _cache_path, load_facts


def _facts(ticker: str, n: int = 12) -> pd.DataFrame:
    """Tabla larga con la forma que devuelve facts.to_dataframe()."""
    fechas = pd.date_range("2023-03-31", periods=n, freq="QE")
    return pd.DataFrame(
        {
            "concept": ["us-gaap:Revenues"] * n,
            "value": [str(100.0 + i) for i in range(n)],
            "numeric_value": [100.0 + i for i in range(n)],
            "unit": ["USD"] * n,
            "period_type": ["duration"] * n,
            "period_start": fechas - pd.Timedelta(days=89),
            "period_end": fechas,
            "fiscal_year": [f.year for f in fechas],
            "fiscal_period": [f"Q{(f.month - 1) // 3 + 1}" for f in fechas],
        }
    )


@pytest.fixture
def cache_dir(tmp_path: Path) -> Path:
    return tmp_path / "cache"


def test_returns_facts_per_ticker_and_a_coverage_report(cache_dir):
    with patch("fundamentals.fetch._fetch_facts", side_effect=_facts):
        hechos, cobertura = load_facts(["AAA", "BBB"], cache_dir=cache_dir)
    assert sorted(hechos) == ["AAA", "BBB"]
    assert isinstance(cobertura, CoverageReport)
    assert cobertura.included == ["AAA", "BBB"]


def test_an_unresolvable_ticker_is_reported_separately_from_a_network_failure(cache_dir):
    """Un ticker que no existe y una caida de SEC son problemas distintos.

    Medido durante el diseno: AEP no aparece en el mapa oficial ticker->CIK de
    SEC. Confundirlo con un fallo de red esconderia una caida real.
    """
    def falla(ticker):
        if ticker == "BBB":
            raise LookupError("sin CIK")
        raise RuntimeError("boom")

    with patch("fundamentals.fetch._fetch_facts", side_effect=falla), \
         patch("fundamentals.fetch.time.sleep"):
        _, cobertura = load_facts(["AAA", "BBB"], cache_dir=cache_dir, max_retries=1)
    assert cobertura.unresolved_cik == ["BBB"]
    assert cobertura.failed_download == ["AAA"]


def test_a_transient_failure_is_retried(cache_dir):
    intentos = {"n": 0}

    def flaky(ticker):
        intentos["n"] += 1
        if intentos["n"] == 1:
            raise RuntimeError("transient")
        return _facts(ticker)

    with patch("fundamentals.fetch._fetch_facts", side_effect=flaky), \
         patch("fundamentals.fetch.time.sleep"):
        _, cobertura = load_facts(["AAA"], cache_dir=cache_dir, max_retries=3)
    assert intentos["n"] == 2
    assert cobertura.included == ["AAA"]


def test_the_second_call_reads_from_cache_without_downloading(cache_dir):
    with patch("fundamentals.fetch._fetch_facts", side_effect=_facts) as primera:
        load_facts(["AAA"], cache_dir=cache_dir)
    assert primera.call_count == 1

    with patch("fundamentals.fetch._fetch_facts") as segunda:
        hechos, cobertura = load_facts(["AAA"], cache_dir=cache_dir)
    assert segunda.call_count == 0
    assert cobertura.included == ["AAA"]
    assert not hechos["AAA"].empty


def test_a_corrupted_cache_file_is_recovered_by_re_downloading(cache_dir):
    """Una corrida matada a media escritura deja un parquet truncado.

    Es el defecto que envenenaba todas las corridas siguientes en el estudio D.
    """
    with patch("fundamentals.fetch._fetch_facts", side_effect=_facts):
        load_facts(["AAA"], cache_dir=cache_dir)

    fichero = next(cache_dir.glob("*.parquet"))
    fichero.write_bytes(b"not a valid parquet file")

    with patch("fundamentals.fetch._fetch_facts", side_effect=_facts):
        hechos, cobertura = load_facts(["AAA"], cache_dir=cache_dir)
    assert cobertura.included == ["AAA"]
    assert not hechos["AAA"].empty


def test_the_cached_frame_survives_the_round_trip(cache_dir):
    """Si el parquet pierde columnas, el panel sale vacio en la segunda corrida."""
    with patch("fundamentals.fetch._fetch_facts", side_effect=_facts):
        primero, _ = load_facts(["AAA"], cache_dir=cache_dir)
    with patch("fundamentals.fetch._fetch_facts"):
        segundo, _ = load_facts(["AAA"], cache_dir=cache_dir)

    esperadas = {"concept", "numeric_value", "period_type", "period_start", "period_end"}
    assert esperadas <= set(segundo["AAA"].columns)
    assert len(segundo["AAA"]) == len(primero["AAA"])


def test_the_cache_key_does_not_depend_on_process_local_hashing(cache_dir):
    """Python aleatoriza el hash de strings entre procesos; una clave asi nunca acierta."""
    import hashlib

    esperado = hashlib.md5(b"AAA").hexdigest()[:12]
    assert _cache_path(cache_dir, "AAA").name == f"facts_{esperado}.parquet"


def test_each_ticker_is_cached_separately(cache_dir):
    """Los trimestrales llegan escalonados; una cache por universo se invalidaria entera."""
    with patch("fundamentals.fetch._fetch_facts", side_effect=_facts):
        load_facts(["AAA", "BBB"], cache_dir=cache_dir)
    assert len(list(cache_dir.glob("*.parquet"))) == 2


def test_refresh_bypasses_the_cache_and_downloads_again(cache_dir):
    """Refrescar tiene que ser posible sin borrar ficheros a mano."""
    with patch("fundamentals.fetch._fetch_facts", side_effect=_facts):
        load_facts(["AAA"], cache_dir=cache_dir)

    with patch("fundamentals.fetch._fetch_facts", side_effect=_facts) as otra:
        load_facts(["AAA"], cache_dir=cache_dir, refresh=True)
    assert otra.call_count == 1


def test_refresh_is_off_by_default(cache_dir):
    """Un refresco automatico cambiaria los numeros entre dos corridas sin avisar."""
    with patch("fundamentals.fetch._fetch_facts", side_effect=_facts):
        load_facts(["AAA"], cache_dir=cache_dir)

    with patch("fundamentals.fetch._fetch_facts") as ninguna:
        load_facts(["AAA"], cache_dir=cache_dir)
    assert ninguna.call_count == 0


def test_coverage_summary_names_every_category(cache_dir):
    with patch("fundamentals.fetch._fetch_facts", side_effect=_facts):
        _, cobertura = load_facts(["AAA"], cache_dir=cache_dir)
    resumen = cobertura.summary()
    for etiqueta in ("solicitados", "incluidos", "sin CIK", "sin sector", "sin precio"):
        assert etiqueta in resumen

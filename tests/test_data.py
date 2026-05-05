from data import parse_tickers, HORIZON_CONFIG, DEFAULT_HORIZON


def test_parse_tickers_comma_separated():
    assert parse_tickers("AAPL, MSFT, GOOGL") == ["AAPL", "MSFT", "GOOGL"]


def test_parse_tickers_space_separated():
    assert parse_tickers("AAPL MSFT GOOGL") == ["AAPL", "MSFT", "GOOGL"]


def test_parse_tickers_mixed_delimiters():
    assert parse_tickers("AAPL, MSFT GOOGL,AMZN") == ["AAPL", "MSFT", "GOOGL", "AMZN"]


def test_parse_tickers_converts_to_uppercase():
    assert parse_tickers("aapl msft") == ["AAPL", "MSFT"]


def test_parse_tickers_empty_string():
    assert parse_tickers("") == []


def test_parse_tickers_only_whitespace():
    assert parse_tickers("   ") == []


def test_horizon_config_has_all_six_horizons():
    expected = {"1 Semana", "1 Mes", "3 Meses", "6 Meses", "1 Año", "3 Años"}
    assert set(HORIZON_CONFIG.keys()) == expected


def test_horizon_config_entries_have_required_fields():
    for key, cfg in HORIZON_CONFIG.items():
        assert "period" in cfg, f"{key} missing 'period'"
        assert "interval" in cfg, f"{key} missing 'interval'"
        assert "periods_per_year" in cfg, f"{key} missing 'periods_per_year'"
        assert cfg["periods_per_year"] in (12, 52, 252), f"{key} has unexpected periods_per_year"


def test_default_horizon_exists_in_config():
    assert DEFAULT_HORIZON in HORIZON_CONFIG

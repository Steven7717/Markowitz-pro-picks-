"""Las actas dicen si la corrida llevaba macro: la pantalla, con `AppTest`."""

import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

GUION = str(Path(__file__).resolve().parent / "guion_vista.py")
CORRIDA = {"universo": "sp500", "n_panel": 480, "n_supervivientes": 300, "con_llm": False}


def _acta(directorio: Path, nombre: str, corrida: dict) -> None:
    acta = {"fecha": "2026-11-16T10:00:00", "corrida": corrida, "aprobados": [], "no_aprobados": []}
    (directorio / nombre).write_text(json.dumps(acta), encoding="utf-8")


@pytest.mark.parametrize(
    "macro, esperado",
    [
        (None, "sin macro"),
        ({"foo": 1}, "sin macro"),
        ({"region": "usa", "fase": "expansion", "mes_dato": "2026-10-01"},
         "con macro: Expansión (Estados Unidos, oct 2026)"),
    ],
)
def test_cada_acta_dice_si_hubo_macro(monkeypatch, tmp_path, macro, esperado):
    corrida = dict(CORRIDA) if macro is None else {**CORRIDA, "macro": macro}
    _acta(tmp_path, "2026-11-16_100000.json", corrida)
    monkeypatch.setattr("aprobacion.acta.ACTAS", tmp_path)
    monkeypatch.setenv("GUION_VISTA", "actas.py")
    at = AppTest.from_file(GUION, default_timeout=30)
    at.run()
    assert not at.exception, at.exception
    assert any(c.value.endswith(" · " + esperado) for c in at.caption), [c.value for c in at.caption]

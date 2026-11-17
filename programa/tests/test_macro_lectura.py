# tests/test_macro_lectura.py
from datetime import date
from types import SimpleNamespace

import pandas as pd

from macro import lectura
from macro.contexto import ContextoUSA
from macro.estado import Estado
from macro.fase import Fase


def _estado(region="usa"):
    serie = pd.Series(
        [100.5, 100.6, 100.7, 100.8],
        index=pd.period_range("2026-07", periods=4, freq="M").to_timestamp(),
    )
    return Estado(region, serie, Fase("expansion", None, date(2026, 10, 1), 100.8, 0.3, 4), None, None, False)


class _Cliente:
    def __init__(self):
        self.llamadas = 0
        self.messages = SimpleNamespace(parse=self._parse)

    def _parse(self, **kwargs):
        self.llamadas += 1
        self.ultimo = kwargs
        return SimpleNamespace(
            parsed_output=lectura.SalidaLectura(explicacion="Crece.", vigilar=["El empleo."]),
            usage=SimpleNamespace(input_tokens=1000, output_tokens=500),
        )


def test_el_prompt_lleva_fase_region_sectores_y_contexto():
    texto = lectura.contexto_prompt(_estado(), ContextoUSA(0.8, False, 0.1, False, 0.03))
    assert "Expansión" in texto and "Estados Unidos" in texto
    assert "Tecnología" in texto and "curva" in texto.lower()


def test_sin_contexto_usa_no_lo_inventa():
    texto = lectura.contexto_prompt(_estado("mex"), None)
    assert "curva" not in texto.lower()


def test_leer_llama_una_vez_y_la_segunda_sale_del_archivo(tmp_path):
    cliente = _Cliente()
    primera = lectura.leer(_estado(), None, raiz=tmp_path, cliente=cliente)
    assert primera.explicacion == "Crece." and primera.coste_usd > 0
    segunda = lectura.leer(_estado(), None, raiz=tmp_path, cliente=cliente)
    assert cliente.llamadas == 1
    assert segunda.explicacion == "Crece." and segunda.coste_usd == 0.0


def test_sin_fase_no_se_llama(tmp_path):
    cliente = _Cliente()
    vacio = Estado("usa", None, None, "sin_red", None, False)
    r = lectura.leer(vacio, None, raiz=tmp_path, cliente=cliente)
    assert cliente.llamadas == 0 and r.problema

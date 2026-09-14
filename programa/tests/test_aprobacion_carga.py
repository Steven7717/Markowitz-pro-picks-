import json
from pathlib import Path

import pytest

from aprobacion import carga
from aprobacion.carga import (
    ContratoRoto,
    FaltanFichas,
    cargar_candidatos,
    resumen_corrida,
)

FICHA = {
    "ticker": "AAA",
    "sector_gics": "Information Technology",
    "puesto": 1,
    "compuesto": 1.42,
    "pilares": {"calidad": 1.9, "crecimiento": 0.4, "valoracion": -0.2, "solidez": 1.1},
    "destacados": [{"kpi": "roic", "valor": 0.31, "z": 2.4}],
    "flojos": [{"kpi": "per", "valor": 34.2, "z": 2.0}],
    "cobertura": {"kpis_con_dato": 14, "pilares_con_dato": 4},
    "desplazo_a": ["BBB"],
    "generada_por": "plantilla",
    "narrativa": None,
}

CORRIDA = {
    "fecha": "2026-08-15",
    "universo": "sp500",
    "n_panel": 502,
    "n_supervivientes": 425,
    "exclusiones": {"pilar_sin_datos": 72, "datos_rancios": 2},
    "tope_por_sector": 3,
    "tamano_top": 15,
    "con_llm": False,
}


def escribir(directorio: Path, fichas=None, corrida=None) -> Path:
    directorio.mkdir(parents=True, exist_ok=True)
    if fichas is not None:
        (directorio / "fichas.json").write_text(
            json.dumps(fichas, ensure_ascii=False), encoding="utf-8"
        )
    if corrida is not None:
        (directorio / "corrida.json").write_text(
            json.dumps(corrida, ensure_ascii=False), encoding="utf-8"
        )
    return directorio


def test_carga_las_fichas_y_la_corrida(tmp_path: Path):
    directorio = escribir(tmp_path, fichas=[FICHA], corrida=CORRIDA)
    candidatos = cargar_candidatos(directorio)
    assert [f["ticker"] for f in candidatos.fichas] == ["AAA"]
    assert candidatos.corrida["n_supervivientes"] == 425


def test_sin_fichas_dice_que_comando_correr(tmp_path: Path):
    with pytest.raises(FaltanFichas) as error:
        cargar_candidatos(tmp_path)
    assert "construir_ranking" in str(error.value)


def test_una_ficha_a_la_que_le_falta_un_campo_nombra_el_campo(tmp_path: Path):
    incompleta = {k: v for k, v in FICHA.items() if k != "compuesto"}
    directorio = escribir(tmp_path, fichas=[incompleta], corrida=CORRIDA)
    with pytest.raises(ContratoRoto) as error:
        cargar_candidatos(directorio)
    assert "compuesto" in str(error.value)


def test_un_fichas_json_truncado_falla_visible(tmp_path: Path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "fichas.json").write_text("[{esto no es json", encoding="utf-8")
    with pytest.raises(ContratoRoto):
        cargar_candidatos(tmp_path)


def test_sin_corrida_json_se_puede_revisar_igual(tmp_path: Path):
    # El salidas/ que existe hoy se genero antes de que corrida.json
    # existiera: este camino se ejercita desde el primer dia.
    directorio = escribir(tmp_path, fichas=[FICHA])
    candidatos = cargar_candidatos(directorio)
    assert candidatos.corrida is None
    assert len(candidatos.fichas) == 1


def test_una_corrida_json_rota_no_se_ignora_en_silencio(tmp_path: Path):
    # Ausente y roto no son lo mismo: ausente significa "lo genero un B
    # antiguo", roto significa que algo fallo y hay que verlo.
    directorio = escribir(tmp_path, fichas=[FICHA], corrida={"universo": "sp500"})
    with pytest.raises(ContratoRoto) as error:
        cargar_candidatos(directorio)
    assert "n_supervivientes" in str(error.value)


def test_un_puesto_que_no_es_entero_no_se_acepta(tmp_path: Path):
    # ficha_numerica siempre escribe int(puesto); un puesto que no es entero
    # solo puede venir de un fichas.json corrompido o editado a mano, y
    # corrompe el orden de la lista sin que se note a simple vista.
    con_puesto_texto = {**FICHA, "puesto": "primero"}
    directorio = escribir(tmp_path, fichas=[con_puesto_texto], corrida=CORRIDA)
    with pytest.raises(ContratoRoto) as error:
        cargar_candidatos(directorio)
    assert "puesto" in str(error.value)


def test_dos_fichas_con_el_mismo_ticker_no_se_aceptan(tmp_path: Path):
    duplicada = {**FICHA, "puesto": 2}
    directorio = escribir(tmp_path, fichas=[FICHA, duplicada], corrida=CORRIDA)
    with pytest.raises(ContratoRoto) as error:
        cargar_candidatos(directorio)
    assert "AAA" in str(error.value)


def test_una_corrida_con_mas_supervivientes_que_panel_no_se_acepta(tmp_path: Path):
    # Si esto pasara sin comprobar, resumen_corrida calcularia un numero de
    # excluidas negativo y se lo mostraria al revisor tal cual.
    invertida = {**CORRIDA, "n_panel": 100, "n_supervivientes": 900}
    directorio = escribir(tmp_path, fichas=[FICHA], corrida=invertida)
    with pytest.raises(ContratoRoto) as error:
        cargar_candidatos(directorio)
    assert "n_supervivientes" in str(error.value)
    assert "n_panel" in str(error.value)


def test_un_ticker_vacio_no_se_acepta(tmp_path: Path):
    # ticker es un campo de identidad, igual que puesto: una ficha sin
    # ticker se pintaria sin nombre y el acta guardaria una entrada sin
    # identificador, silenciosamente. No se valida la forma del ticker (eso
    # es cosa de la tarea que agrega empresas a mano) -- solo que no este
    # vacio, que es lo que este fichero, escrito por B, nunca produciria.
    sin_ticker = {**FICHA, "ticker": ""}
    directorio = escribir(tmp_path, fichas=[sin_ticker], corrida=CORRIDA)
    with pytest.raises(ContratoRoto) as error:
        cargar_candidatos(directorio)
    assert "ticker" in str(error.value)


def test_el_resumen_nombra_las_exclusiones_y_su_peso():
    texto = resumen_corrida(CORRIDA)
    assert "502" in texto
    assert "425" in texto
    # El motivo sigue estando; lo que ya no esta es el identificador del codigo
    # fuente. Ver `test_el_resumen_no_imprime_los_codigos_del_codigo_fuente`.
    assert "pilar" in texto


def test_el_resumen_calcula_bien_cuantas_quedaron_excluidas():
    # 502 - 425 = 77. Comprobar solo que "502" y "425" aparecen (como hace el
    # test anterior) no distingue "panel menos supervivientes" de su inverso:
    # ambos numeros de entrada siguen apareciendo en el texto aunque la resta
    # este invertida y el resultado sea negativo. Este test si lo distingue.
    texto = resumen_corrida(CORRIDA)
    assert "77" in texto
    assert "-77" not in texto


def test_el_resumen_sin_corrida_lo_dice_en_vez_de_callarlo():
    texto = resumen_corrida(None)
    assert "sin contexto" in texto.lower()


def test_el_resumen_con_cero_exclusiones_no_deja_la_frase_coja():
    # Ver ranking/informe.py:render, misma logica alli para la seccion de
    # exclusiones del informe: una frase vacia detras de "excluidas 0:" se
    # leeria como que algo se rompio, que es lo contrario de lo que paso.
    sin_exclusiones = {**CORRIDA, "n_panel": 18, "n_supervivientes": 18, "exclusiones": {}}
    texto = resumen_corrida(sin_exclusiones)
    assert "excluidas 0: ." not in texto
    assert "ninguna" in texto.lower()


# --- Los codigos de `ranking/score.py`, en castellano ------------------------
#
# `resumen_corrida` imprimia los identificadores del codigo fuente tal cual:
# «Quedaron excluidas 79: pilar_sin_datos (74), datos_rancios (2),
# cobertura_insuficiente (2), historia_corta (1)». Es la primera frase que lee
# el revisor y la unica que le dice de donde sale la lista que esta mirando.
#
# Los codigos nacen en `ranking/score.py`, que no es de este paquete, asi que la
# traduccion vive aqui: donde se pinta.


def test_el_resumen_no_imprime_los_codigos_del_codigo_fuente():
    texto = resumen_corrida(CORRIDA)
    assert "pilar_sin_datos" not in texto
    assert "datos_rancios" not in texto
    assert "_" not in texto


def test_el_resumen_sigue_diciendo_cuantas_por_cada_motivo():
    """Traducir no puede perder la cuenta: la proporcion entre motivos es lo
    que dice si la lista esta sesgada por un sector que reporta distinto."""
    texto = resumen_corrida(CORRIDA)
    assert "72" in texto
    assert "2" in texto


def test_cada_codigo_de_las_guardas_tiene_traduccion():
    """El saboteador: un motivo nuevo en `ranking/score.py` sin traduccion aqui
    tumba esto, en vez de colarse en pantalla como identificador."""
    codigos = {
        "historia_corta",
        "datos_rancios",
        "pilar_sin_datos",
        "cobertura_insuficiente",
        "sector_desconocido",
        "sector_sin_pares",
        "sin_dispersion_sectorial",
    }
    faltan = codigos - set(carga.MOTIVOS_EN_CASTELLANO)
    assert faltan == set()


def test_un_motivo_desconocido_se_dice_en_vez_de_desaparecer():
    """Si alguien anade un motivo y se olvida de traducirlo, la cuenta tiene que
    seguir cuadrando: perder la fila seria mentir sobre cuantas se excluyeron."""
    raro = {**CORRIDA, "exclusiones": {"un_motivo_nuevo": 3}}
    texto = resumen_corrida(raro)
    assert "3" in texto
    assert "un_motivo_nuevo" in texto


def test_el_resumen_esta_acentuado():
    texto = resumen_corrida(CORRIDA)
    assert "generó" not in texto  # esta rama es la otra
    assert "sobrevivieron" in texto


def test_el_resumen_sin_corrida_esta_acentuado():
    texto = resumen_corrida(None)
    assert "generó" in texto
    assert "cuántas" in texto
    assert "asi que" not in texto


# --- Una ficha vieja no puede reventar la lista a mitad ----------------------


def test_la_cobertura_de_una_ficha_sin_el_campo_no_revienta():
    """`vistas/candidatos.py` indexaba `ficha["cobertura"]["kpis_con_dato"]`
    directo, mientras `medidores.tarjeta_candidato` y `medidores._nota_pilar`
    usan `.get(...)` y explican en su docstring que las fichas antiguas se
    pintan sin ellos. `_CAMPOS_FICHA` valida que `cobertura` exista pero no su
    contenido, asi que una `fichas.json` vieja pasaba la validacion y reventaba
    con `KeyError` **a mitad de la lista**, con tarjetas ya pintadas.

    El escenario ya existe en el repo: `salidas_ejemplo/fichas.json` trae
    `kpis_con_dato` pero no `kpis_por_pilar`.
    """
    assert carga.kpis_con_dato({"cobertura": {}}) is None
    assert carga.kpis_con_dato({}) is None
    assert carga.kpis_con_dato({"cobertura": None}) is None


def test_la_cobertura_de_una_ficha_normal_sale_entera():
    assert carga.kpis_con_dato(FICHA) == 14


def test_una_cobertura_que_no_es_un_numero_se_trata_como_ausente():
    """Pintar la barra con una cadena la haria reventar igual. Ausente y
    corrupto se pintan igual --sin medidor-- porque en los dos casos lo que no
    hay es el numero."""
    assert carga.kpis_con_dato({"cobertura": {"kpis_con_dato": "muchos"}}) is None
    assert carga.kpis_con_dato({"cobertura": {"kpis_con_dato": True}}) is None

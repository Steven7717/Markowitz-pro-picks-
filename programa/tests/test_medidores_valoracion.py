import ast
import copy
import html
import re
from datetime import date
from pathlib import Path

import pytest

import medidores
import medidores_valoracion as mv
import tema
from valoracion import criterio
from valoracion.mercado import Beta
from valoracion.motor import calcular
from valoracion.plano import a_dict, fallida
from valoracion.supuestos import deducir
from valoracion.votos import MOTIVOS, VEREDICTOS

from tests.dobles_valoracion import ejercicio, fundamentos, perfil
from tests.test_tema import contraste


def _valoracion(f=None, p=None, pilar=0.8) -> dict:
    f, p = f or fundamentos(), p or perfil()
    s = deducir(f, p, r_f=0.04, beta=None, tasa=0.25, consenso=None)
    return a_dict(calcular(f, p, s, pilar, date(2026, 10, 12)))


def _texto(salida: str) -> str:
    """Lo que se lee en pantalla: sin etiquetas, los spans de una fila separados por « | »."""
    salida = re.sub(r"</span>(?=<span)", " | ", salida)
    salida = salida.replace("</div>", "\n")
    return html.unescape(re.sub(r"<[^>]+>", "", salida)).strip()


def _lineas(salida: str) -> "list[str]":
    return _texto(salida).split("\n")


# --- Una valoración escrita a mano, para fijar el texto exacto ----------------


def _supuestos_fijos() -> dict:
    return {
        "r_f": {"valor": 0.0522, "procedencia": {"fuente": "tesoro_10", "serie": "^TNX"}},
        "beta": {
            "valor": 1.9976,
            "procedencia": {"fuente": "regresion", "indice": "^GSPC", "semanas": 104, "r2": 0.29, "bruta": 2.489},
        },
        "prima": {"valor": 0.042, "procedencia": {"fuente": "damodaran", "fecha": "2026-10-01"}},
        "k_e": {"valor": 0.136, "procedencia": {"fuente": "capm"}},
        "k_d": {"valor": 0.0522, "procedencia": {"fuente": "gasto_entre_deuda", "bruto": 0.0226}},
        "t": {"valor": 0.116, "procedencia": {"fuente": "efectiva", "bruta": 0.116}},
        "wacc": {"valor": 0.1357, "procedencia": {"fuente": "wacc", "peso_deuda": 0.0043, "deuda_declarada": True}},
        "g_ref": {
            "valor": 0.4,
            "procedencia": {"fuente": "historia_y_consenso", "historico": 1.0465, "consenso": 0.1573, "bruto": 0.6019},
        },
        "g_perpetuo": {"valor": 0.025, "procedencia": {"fuente": "criterio", "moneda": "USD"}},
        "roe_ref": {"valor": 0.1576, "procedencia": {"fuente": "mediana_historica", "anos": 5}},
        "payout": {"valor": 0.0071, "procedencia": {"fuente": "yfinance"}},
    }


def _fija(**cambios) -> dict:
    """Una valoración de flujos con cifras redondas, sin pasar por el motor."""
    base = {
        "version": "m1",
        "fecha": "2026-10-12",
        "estados_hasta": "2026-09-30",
        "moneda": "USD",
        "precio": 100.0,
        "precio_hora": "2026-10-12T19:59:00+00:00",
        "metodo": "flujos",
        "valor": {"pesimista": 80.5, "base": 1234.5, "optimista": 4321.0},
        "margen_seguridad": 0.2031,
        "implicito": {
            "magnitud": "crecimiento",
            "valor": 0.274,
            "referencia": 0.4,
            "margen": 0.2,
            "fuera_de_limites": None,
        },
        "epv": {"por_accion": 392.27, "parte_crecimiento": 0.5884},
        "votos": {
            "flujos": {"voto": "neutra", "motivo": None},
            "sin_crecimiento": {"voto": "neutra", "motivo": None},
            "pares": {"voto": "barata", "motivo": None},
        },
        "veredicto": "en_rango",
        "supuestos": _supuestos_fijos(),
    }
    return {**base, **cambios}


def _fija_residual(**cambios) -> dict:
    supuestos = _supuestos_fijos()
    supuestos["k_d"] = {"valor": None, "procedencia": {"fuente": "financiera"}}
    supuestos["wacc"] = {"valor": None, "procedencia": {"fuente": "financiera"}}
    de_un_banco = dict(
        metodo="residual",
        implicito={"magnitud": "roe", "valor": 0.1497, "referencia": 0.1584, "margen": 0.0792, "fuera_de_limites": None},
        epv=None,
        votos={
            "flujos": {"voto": "neutra", "motivo": None},
            "sin_crecimiento": {"voto": "no_aplica", "motivo": "financiera"},
            "pares": {"voto": "neutra", "motivo": None},
        },
        supuestos=supuestos,
    )
    return _fija(**{**de_un_banco, **cambios})


def _fila(valoracion: dict, clave: str) -> "tuple[str, str, str]":
    """(nombre, etiqueta, detalle) de la fila de un voto, tal como se lee."""
    orden = {"flujos": 1, "sin_crecimiento": 2, "pares": 3}[clave]
    nombre, etiqueta, detalle = _lineas(mv.resumen(valoracion))[orden].split(" | ")
    return nombre, etiqueta, detalle


def _detalle(valoracion: dict, clave: str) -> str:
    return _fila(valoracion, clave)[2]


# --- Las etiquetas ------------------------------------------------------------


def test_cada_veredicto_tiene_etiqueta():
    assert set(mv.VEREDICTO) == set(VEREDICTOS)


def test_cada_motivo_tiene_etiqueta():
    assert MOTIVOS <= set(mv.MOTIVO)


def test_no_hay_mas_motivos_que_los_que_escribe_el_paquete():
    # Una etiqueta de más es un texto que nadie puede ver y que se queda sin revisar.
    assert set(mv.MOTIVO) == MOTIVOS


@pytest.mark.parametrize("clave", sorted(mv.MOTIVO))
def test_ninguna_etiqueta_de_motivo_dice_no_aplica_ni_no_se_pudo(clave):
    # Junto a ella ya va el «No aplica» de la fila de un voto, o el «Sin
    # valoración:» de una fallida: repetirlo lee como un tartamudeo.
    etiqueta = mv.etiqueta_motivo(clave).lower()
    assert "no aplica" not in etiqueta
    assert "no se pudo" not in etiqueta


@pytest.mark.parametrize(
    ("clave", "idea"),
    [
        ("quema_caja", "quema caja"),
        ("ebit_negativo", "beneficio operativo negativo"),
        ("sin_historia", "años de historia"),
        ("wacc_bajo_crecimiento", "valor terminal explotaría"),
        ("sin_pares", "pares del sector"),
        ("sin_precio", "el precio"),
        ("sin_tasa_libre", "tasa libre de riesgo"),
        ("financiera", "beneficio residual"),
        ("patrimonio_negativo", "patrimonio negativo"),
        ("sin_beneficio_operativo", "beneficio operativo"),
        ("sin_flujo_libre", "flujo libre"),
        ("sin_red", "Yahoo Finance no devolvió datos"),
        ("sin_estados", "estados financieros de la SEC"),
        ("error_interno", "error interno"),
        ("sin_bono_m", "Bono M"),
    ],
)
def test_cada_motivo_dice_de_que_se_trata(clave, idea):
    # No fija la redacción, sólo que la etiqueta habla de lo que debe.
    assert idea in mv.etiqueta_motivo(clave)


# Los motivos con los que puede terminar una valoración fallida: los de la red y
# los estados (`valorar`) y el que anota `ranking/run.py` cuando algo revienta.
_MOTIVOS_DE_UNA_FALLIDA = (
    "sin_red", "sin_precio", "sin_tasa_libre", "sin_estados", "sin_historia", "error_interno",
    "sin_bono_m",
)


def test_las_fallidas_de_la_lista_existen():
    assert set(_MOTIVOS_DE_UNA_FALLIDA) <= MOTIVOS


@pytest.mark.parametrize("motivo", _MOTIVOS_DE_UNA_FALLIDA)
def test_una_fallida_lleva_un_solo_dos_puntos(motivo):
    texto = _texto(mv.resumen(fallida(motivo)))
    assert texto.startswith("Sin valoración: ")
    assert texto.count(":") == 1
    assert texto.endswith(".")


def test_la_fallida_de_la_red_se_lee_sin_dobles_dos_puntos():
    assert _texto(mv.resumen(fallida("sin_red"))) == (
        "Sin valoración: Yahoo Finance no devolvió datos "
        "(sin conexión, un error suyo o un símbolo que no conoce)."
    )


def test_el_error_interno_dice_que_es_del_programa_sin_repetir_el_aviso():
    # Dentro de la ficha tiene que entenderse solo; encima de la lista ya lo
    # acompaña el pie del defecto, que dice qué hacer.
    etiqueta = mv.etiqueta_motivo("error_interno")
    assert "del programa" in etiqueta
    assert "avisar" not in etiqueta


def test_el_motivo_de_una_financiera_habla_de_entidades_financieras():
    etiqueta = mv.etiqueta_motivo("financiera")
    assert "beneficio residual" in etiqueta
    assert "entidades financieras" in etiqueta
    assert "bancos y aseguradoras" not in etiqueta


def test_la_nota_es_la_del_spec():
    # En M los estados vienen de la SEC, no de yfinance; y el panel guarda la
    # última cifra que publicó cada empresa (`fundamentals/panel.py`, `keep="last"`).
    assert mv.NOTA == (
        "Un criterio transparente, no una previsión: no hay forma honesta de probar hacia atrás "
        "si acierta, porque las cifras guardadas son las últimas que publicó cada empresa, no las "
        "que se conocían en su día, y el universo arrastra sesgo de supervivencia."
    )


def test_la_lectura_del_margen_explica_por_que_un_margen_grande_puede_ser_en_rango():
    lectura = mv.lectura_margen()
    assert "El margen de seguridad mide la distancia al valor base. El voto de flujos no lo usa:" in lectura
    assert "compara el crecimiento que el precio exige con su referencia" in lectura
    assert "con una banda de ± la mitad de esa referencia y nunca menos de 5 puntos" in lectura
    assert "un margen grande puede convivir con «en rango»" in lectura
    assert lectura.endswith("cuando el crecimiento de referencia es alto.")


def test_la_lectura_del_margen_de_un_banco_habla_del_roe():
    lectura = mv.lectura_margen_roe()
    assert "El margen de seguridad mide la distancia al valor base." in lectura
    assert "compara el ROE que el precio exige con el ROE de referencia" in lectura
    assert "con una banda de ± la mitad de esa referencia y nunca menos de 3 puntos" in lectura
    assert "un margen grande puede convivir con «en rango»" in lectura
    assert lectura.endswith("cuando el ROE de referencia es alto.")
    assert "crecimiento" not in lectura


# --- El pie y el título del bloque en la ficha -----------------------------------


@pytest.mark.parametrize("valoracion", [None, "x", [], 3])
def test_sin_valoracion_reconocible_no_hay_pie(valoracion):
    assert mv.pie(valoracion) == []


@pytest.mark.parametrize("motivo", _MOTIVOS_DE_UNA_FALLIDA)
def test_una_fallida_no_lleva_pie(motivo):
    # Sin rango ni votos no hay margen que explicar, y la nota sobre el criterio
    # sobra junto a una valoración que no llegó a hacerse.
    assert mv.pie(fallida(motivo)) == []


def test_una_valoracion_sin_veredicto_no_lleva_pie():
    assert mv.pie({"version": "m1", "metodo": "flujos"}) == []


def test_el_pie_de_una_de_flujos_explica_el_margen_por_el_crecimiento():
    assert mv.pie(_fija()) == [mv.lectura_margen(), mv.NOTA]


def test_el_pie_de_una_financiera_explica_el_margen_por_el_roe():
    assert mv.pie(_fija_residual()) == [mv.lectura_margen_roe(), mv.NOTA]


@pytest.mark.parametrize("metodo", ["otro", ["residual"], {"flujos": 1}, None])
def test_con_un_metodo_desconocido_el_pie_es_solo_la_nota(metodo):
    assert mv.pie(_fija(metodo=metodo)) == [mv.NOTA]


def test_una_valoracion_sin_metodo_lleva_solo_la_nota():
    valoracion = _fija()
    del valoracion["metodo"]
    assert mv.pie(valoracion) == [mv.NOTA]


@pytest.mark.parametrize("fabrica", [_fija, _fija_residual])
@pytest.mark.parametrize("margen", [None, "x", float("nan")])
def test_con_veredicto_pero_sin_margen_el_pie_es_solo_la_nota(fabrica, margen):
    # Si el voto de flujos no aplica (sin flujo libre, quema caja, valor
    # terminal que explotaría, sin historia), no hay rango ni margen, pero el
    # EPV y los pares siguen dando veredicto: LLY, COST, NEE, VZ y PEP en la
    # corrida real. Explicar un margen que no se enseña confunde.
    assert mv.pie(fabrica(valor=None, margen_seguridad=margen)) == [mv.NOTA]


def test_el_titulo_remite_al_glosario_cuando_hay_algo_que_leer():
    for valoracion in (_fija(), _fija_residual()):
        titulo = mv.titulo(valoracion)
        assert titulo.startswith("**Valor intrínseco**")
        assert f"«{mv.TITULO_GLOSARIO}»" in titulo


@pytest.mark.parametrize(
    "valoracion", [None, "x", fallida("sin_red"), {"version": "m1"}]
)
def test_sin_veredicto_el_titulo_no_remite_al_glosario(valoracion):
    titulo = mv.titulo(valoracion)
    assert titulo.startswith("**Valor intrínseco**")
    assert mv.TITULO_GLOSARIO not in titulo


def test_el_desplegable_del_glosario_nombra_el_bloque():
    assert "valor intrínseco" in mv.TITULO_GLOSARIO


@pytest.mark.parametrize("valoracion", [None, _fija(), _fija_residual()])
def test_el_bloque_no_se_llama_como_el_pilar_de_valoracion(valoracion):
    # Tres líneas más arriba, en la misma ficha, está el pilar «valoración» del
    # score, y el voto «Frente a sus pares» es ese mismo pilar.
    assert "aloraci" not in mv.titulo(valoracion) + mv.TITULO_GLOSARIO


def test_el_titulo_no_cuenta_lecturas_ni_votos():
    # «Cuatro lecturas que dan tres votos» es falso para una financiera: tres y dos.
    for valoracion in (_fija(), _fija_residual()):
        assert "lecturas" not in mv.titulo(valoracion)
        assert "votos" not in mv.titulo(valoracion)


# --- El aviso común, encima de la lista -------------------------------------------


def _calculadas(n: int) -> list:
    return [_fija() for _ in range(n)]


def _fallidas(motivo: str, n: int) -> list:
    return [fallida(motivo) for _ in range(n)]


def test_los_motivos_de_corrida_existen():
    assert set(mv.MOTIVOS_DE_CORRIDA) <= MOTIVOS
    assert set(mv.MOTIVOS_DE_CORRIDA) == {"sin_red", "sin_tasa_libre"}


def test_la_tasa_libre_corta_a_la_primera_y_la_red_a_la_segunda():
    assert mv.MOTIVOS_DE_CORRIDA["sin_tasa_libre"] == 1
    assert mv.MOTIVOS_DE_CORRIDA["sin_red"] == 2


def test_el_minimo_de_sin_red_es_el_del_corte_de_la_corrida():
    # El módulo no importa `ranking.run` (arrastra pandas y la IA), así que el 2
    # se repite: este test es lo que impide que los dos se separen.
    corte = (Path(__file__).parent.parent / "ranking" / "run.py").read_text(encoding="utf-8")
    assert f"sin_red_seguidos >= {mv.MOTIVOS_DE_CORRIDA['sin_red']}" in corte


def test_los_pies_del_aviso_son_distintos():
    assert mv._PIE_REGENERAR != mv._PIE_DEFECTO


def test_el_pie_de_regenerar_no_empuja_a_perder_la_narrativa():
    # Las narrativas se guardan por contenido (`ranking.llm.redactar_con_cache`):
    # regenerar con IA sobre los mismos datos no paga nada, y sin IA las pierde.
    assert "en el mismo modo" in mv._PIE_REGENERAR
    assert "caché" in mv._PIE_REGENERAR
    assert "sin IA" not in mv._PIE_REGENERAR
    assert "costar" not in mv._PIE_REGENERAR


@pytest.mark.parametrize("motivo", ["sin_tasa_libre", "sin_red", "sin_estados"])
def test_si_todas_fallan_por_lo_mismo_se_dice_una_vez(motivo):
    aviso = mv.aviso_comun(_fallidas(motivo, 15))
    assert aviso.startswith(f"No se pudo valorar ningún candidato: {mv.etiqueta_motivo(motivo)}. ")
    assert aviso.endswith(mv._PIE_REGENERAR)
    assert aviso.count(mv._PIE_REGENERAR) == 1


def test_si_todas_fallan_por_un_defecto_no_se_invita_a_regenerar_sin_mas():
    aviso = mv.aviso_comun(_fallidas("error_interno", 15))
    assert aviso.startswith(
        f"No se pudo valorar ningún candidato: {mv.etiqueta_motivo('error_interno')}. "
    )
    assert aviso.endswith(mv._PIE_DEFECTO)
    assert mv._PIE_REGENERAR not in aviso


def test_el_pie_del_defecto_dice_como_ver_el_detalle():
    # La consola va oculta y no se guarda; cerrar sólo la pestaña deja el
    # servidor vivo 90 s, y abrir otro entonces lo manda al puerto 8502.
    assert "no se guarda" in mv._PIE_DEFECTO
    assert "«Salir del programa»" in mv._PIE_DEFECTO
    assert "«Iniciar App.bat»" in mv._PIE_DEFECTO
    assert "en el mismo modo" in mv._PIE_DEFECTO


def test_un_corte_a_mitad_de_corrida_se_cuenta():
    # El caso típico del corte de `ranking/run.py`: cuatro valoradas, y al fallar
    # la tasa libre las once que quedaban heredan el motivo sin preguntar.
    aviso = mv.aviso_comun(_calculadas(4) + _fallidas("sin_tasa_libre", 11))
    assert aviso.startswith(
        f"11 de 15 candidatos sin valorar: {mv.etiqueta_motivo('sin_tasa_libre')}. "
    )
    assert aviso.endswith(mv._PIE_REGENERAR)
    assert aviso.count(mv._PIE_REGENERAR) == 1


def test_varios_motivos_de_corrida_van_de_mas_a_menos_frecuente_con_un_solo_pie():
    valoraciones = (
        _calculadas(2) + _fallidas("sin_red", 2) + _calculadas(2) + _fallidas("sin_tasa_libre", 9)
    )
    assert mv.aviso_comun(valoraciones) == (
        f"9 de 15 candidatos sin valorar: {mv.etiqueta_motivo('sin_tasa_libre')}. "
        f"2 de 15 candidatos sin valorar: {mv.etiqueta_motivo('sin_red')}. "
        f"{mv._PIE_REGENERAR}"
    )


def test_dos_sin_red_separados_no_son_un_corte():
    # El corte de `ranking/run.py` exige dos seguidos: separados, son dos
    # símbolos que Yahoo no conoce, y regenerar no los arregla.
    motivos = ("sin_red", "sin_estados", "sin_red", "sin_estados", "sin_estados")
    assert mv.aviso_comun([fallida(m) for m in motivos]) is None


def test_una_racha_de_sin_red_es_un_corte_y_se_cuentan_todas():
    # La racha decide si hubo corte; la cuenta, cuántas fichas lo llevan.
    valoraciones = _calculadas(1) + _fallidas("sin_red", 3) + _calculadas(1) + _fallidas("sin_red", 1)
    assert mv.aviso_comun(valoraciones).startswith(
        f"4 de 6 candidatos sin valorar: {mv.etiqueta_motivo('sin_red')}. "
    )


def test_tras_una_valorada_el_corte_por_red_avisa():
    assert mv.aviso_comun(_calculadas(1) + _fallidas("sin_red", 14)).startswith(
        "14 de 15 candidatos sin valorar: "
    )


def test_un_sin_red_suelto_es_de_la_empresa_y_no_de_la_corrida():
    # Para `ranking/run.py` un `sin_red` aislado es un símbolo que Yahoo no
    # conoce: regenerar no lo arregla, y su ficha ya lo dice.
    assert mv.aviso_comun(_calculadas(14) + _fallidas("sin_red", 1)) is None
    con_corte = _calculadas(3) + _fallidas("sin_red", 1) + _fallidas("sin_tasa_libre", 11)
    aviso = mv.aviso_comun(con_corte)
    assert aviso.startswith("11 de 15 candidatos sin valorar: ")
    assert mv.etiqueta_motivo("sin_red") not in aviso


def test_un_fallo_suelto_de_empresa_se_ve_en_su_ficha_y_no_arriba():
    assert mv.aviso_comun(_calculadas(14) + _fallidas("sin_estados", 1)) is None
    assert mv.aviso_comun(_calculadas(10) + _fallidas("error_interno", 5)) is None


def test_un_fallo_suelto_no_tapa_el_corte():
    valoraciones = _fallidas("error_interno", 1) + _fallidas("sin_tasa_libre", 14)
    assert mv.aviso_comun(valoraciones).startswith("14 de 15 candidatos sin valorar: ")


@pytest.mark.parametrize("valoraciones", [[], [None] * 15, _calculadas(15)])
def test_sin_fallidas_no_hay_aviso(valoraciones):
    assert mv.aviso_comun(valoraciones) is None


@pytest.mark.parametrize("motivo", [["sin_red"], {"a": 1}, 3, None])
def test_un_motivo_que_no_es_texto_no_cuenta_ni_revienta(motivo):
    rota = {"version": "m1", "motivo": motivo}
    assert mv.aviso_comun([rota] * 15) is None
    assert mv.aviso_comun(_calculadas(14) + [rota]) is None
    assert mv.aviso_comun([rota] + _fallidas("sin_tasa_libre", 14)).startswith(
        "14 de 15 candidatos sin valorar: "
    )


@pytest.mark.parametrize("entrada", ["x", ["sin_red"], 3])
def test_una_entrada_que_no_es_un_diccionario_cuenta_como_sin_valoracion(entrada):
    assert mv.aviso_comun([entrada] * 15) is None


def test_el_aviso_usa_las_etiquetas_de_los_motivos(monkeypatch):
    monkeypatch.setattr(mv, "etiqueta_motivo", lambda clave: f"[{clave}]")
    assert mv.aviso_comun(_fallidas("sin_red", 15)).startswith(
        "No se pudo valorar ningún candidato: [sin_red]. "
    )
    assert mv.aviso_comun(_calculadas(4) + _fallidas("sin_tasa_libre", 11)).startswith(
        "11 de 15 candidatos sin valorar: [sin_tasa_libre]. "
    )


# Los colores que nombra el spec: verde para infravalorada, rojo para
# sobrevalorada, ámbar para mixtas y gris para en rango o sin datos.
@pytest.mark.parametrize(
    ("clave", "color"),
    [
        ("infravalorada", tema.VERDE),
        ("sobrevalorada", tema.ROJO),
        ("mixtas", tema.AMBAR),
        ("en_rango", tema.TEXTO_SUAVE),
        ("sin_datos", tema.TEXTO_SUAVE),
    ],
)
def test_el_color_de_cada_veredicto(clave, color):
    assert f'style="color:{color}"' in mv.distintivo({"veredicto": clave})


@pytest.mark.parametrize(
    ("clave", "etiqueta"),
    [
        ("infravalorada", "Infravalorada"),
        ("sobrevalorada", "Sobrevalorada"),
        ("mixtas", "Señales mixtas"),
        ("en_rango", "En rango"),
        ("sin_datos", "Sin datos suficientes"),
    ],
)
def test_el_distintivo_es_una_pildora_con_su_etiqueta(clave, etiqueta):
    assert mv.distintivo({"veredicto": clave}).endswith(f">{etiqueta}</span>")
    assert mv.distintivo({"veredicto": clave}).startswith('<span class="mpp-veredicto"')


@pytest.mark.parametrize(
    ("voto", "etiqueta", "color"),
    [
        ("barata", "Barata", tema.VERDE),
        ("neutra", "Neutra", tema.TEXTO_SUAVE),
        ("cara", "Cara", tema.ROJO),
        ("no_aplica", "No aplica", tema.TEXTO_SUAVE),
    ],
)
def test_el_color_y_la_etiqueta_de_cada_voto(voto, etiqueta, color):
    votos = {**_fija()["votos"], "flujos": {"voto": voto, "motivo": "sin_pares"}}
    salida = mv.resumen(_fija(votos=votos))
    assert f'<span class="mpp-val-etiqueta" style="color:{color}">{etiqueta}</span>' in salida


@pytest.mark.parametrize("clave", VEREDICTOS)
def test_el_distintivo_dice_el_veredicto(clave):
    assert mv.VEREDICTO[clave][0] in mv.distintivo({"version": "m1", "veredicto": clave})


@pytest.mark.parametrize(
    "valor",
    [
        None,
        fallida("sin_precio"),
        {"version": "m1", "veredicto": "otra"},
        {"veredicto": ["infravalorada"]},
        {"veredicto": {"a": 1}},
        {"veredicto": 3},
        "infravalorada",
        ["veredicto"],
    ],
)
def test_sin_valoracion_reconocible_no_hay_distintivo(valor):
    assert mv.distintivo(valor) == ""


# --- La cabecera ----------------------------------------------------------------


def test_la_cabecera_completa():
    assert _lineas(mv.resumen(_fija()))[0] == (
        "En rango | Valor por acción: pesimista 80.50 USD · base 1,234.50 USD · "
        "optimista 4,321.00 USD · margen de seguridad 20.3% | "
        "Calculada el 2026-10-12 con el precio de 100.00 USD "
        "(cotización del 2026-10-12 19:59 UTC) y estados hasta 2026-09-30"
    )


def test_un_margen_negativo_lleva_el_signo_menos():
    assert "margen de seguridad −44.4%" in mv.resumen(_fija(margen_seguridad=-0.4444))


@pytest.mark.parametrize(
    ("hora", "esperada"),
    [
        ("2026-10-12T19:59:00+00:00", "(cotización del 2026-10-12 19:59 UTC)"),
        ("2026-10-12T19:59:00Z", "(cotización del 2026-10-12 19:59 UTC)"),
        # Una hora con otra zona se pasa a UTC, que es lo que dice la etiqueta.
        ("2026-10-12T15:59:00-04:00", "(cotización del 2026-10-12 19:59 UTC)"),
        ("2026-10-13T01:30:00+02:00", "(cotización del 2026-10-12 23:30 UTC)"),
    ],
)
def test_la_cabecera_dice_de_cuando_es_el_precio(hora, esperada):
    assert esperada in _lineas(mv.resumen(_fija(precio_hora=hora)))[0]


@pytest.mark.parametrize(
    "hora",
    [None, "", "no es una hora", "2026-10-12T19:59:00", 20261012, ["2026-10-12T19:59:00+00:00"]],
    ids=["None", "vacia", "ilegible", "sin_zona", "numero", "lista"],
)
def test_sin_hora_legible_la_cabecera_no_inventa_el_parentesis(hora):
    cabecera = _lineas(mv.resumen(_fija(precio_hora=hora)))[0]
    assert "cotización" not in cabecera
    assert cabecera.endswith("con el precio de 100.00 USD y estados hasta 2026-09-30")


def test_sin_la_clave_de_la_hora_tampoco_hay_parentesis():
    valoracion = _fija()
    del valoracion["precio_hora"]
    assert "cotización" not in mv.resumen(valoracion)


def test_sin_rango_la_cabecera_lo_dice():
    assert _lineas(mv.resumen(_fija(valor=None)))[0].startswith(
        "En rango | Sin rango de valor. | Calculada el 2026-10-12 "
    )


_GORDON = "wacc_bajo_crecimiento"


@pytest.mark.parametrize(
    ("valor", "explicacion"),
    [
        ({"pesimista": 80.5, "base": 1234.5, "optimista": None}, "el optimista falta: en ese escenario, "),
        ({"pesimista": None, "base": 1234.5, "optimista": 4321.0}, "el pesimista falta: en ese escenario, "),
        (
            {"pesimista": None, "base": 1234.5, "optimista": None},
            "el pesimista y el optimista faltan: en esos escenarios, ",
        ),
    ],
)
def test_un_rango_incompleto_dice_por_que(valor, explicacion):
    # El spec: si un escenario no cumple la holgura de Gordon, el rango «se pinta
    # incompleto, diciendo por qué».
    cabecera = _lineas(mv.resumen(_fija(valor=valor)))[0]
    assert "n/d" in cabecera
    assert explicacion + mv.etiqueta_motivo(_GORDON) in cabecera


def test_un_rango_completo_no_habla_de_gordon():
    assert mv.etiqueta_motivo(_GORDON) not in mv.resumen(_fija())


@pytest.mark.parametrize("base", [None, "x"])
def test_sin_valor_base_no_se_explica_ningun_extremo(base):
    # Sin base no hay escenario de referencia: lo que falta ya no es un extremo.
    valor = {"pesimista": 80.5, "base": base, "optimista": None}
    assert mv.etiqueta_motivo(_GORDON) not in mv.resumen(_fija(valor=valor))


def test_a_una_ficha_a_la_que_le_faltan_las_fechas_y_la_moneda_no_se_le_inventa_nada():
    valoracion = _fija()
    for clave in ("fecha", "estados_hasta", "moneda", "precio_hora"):
        del valoracion[clave]
    assert _lineas(mv.resumen(valoracion))[0] == (
        "En rango | Valor por acción: pesimista 80.50 · base 1,234.50 · optimista 4,321.00 · "
        "margen de seguridad 20.3% | Calculada el n/d con el precio de 100.00 y estados hasta n/d"
    )
    assert _detalle(valoracion, "sin_crecimiento") == (
        "sin crecer valdría 392.27; el 58.8% del precio es apuesta por el crecimiento"
    )


@pytest.mark.parametrize("moneda", [None, ["USD"], 840])
def test_una_moneda_que_no_es_texto_se_descarta(moneda):
    assert "con el precio de 100.00 y estados hasta" in mv.resumen(_fija(moneda=moneda, precio_hora=None))


# --- Las filas de los votos -----------------------------------------------------


def test_el_resumen_nombra_los_tres_votos():
    salida = mv.resumen(_valoracion())
    for nombre in mv.NOMBRE_VOTO.values():
        assert nombre in salida
    assert "estados hasta 2026-09-30" in salida


def test_los_tres_votos_van_en_su_orden():
    nombres = [_fila(_fija(), clave)[0] for clave in ("flujos", "sin_crecimiento", "pares")]
    assert nombres == ["Flujos (DCF e inverso)", "Sin crecimiento (EPV)", "Frente a sus pares"]


def test_el_resumen_de_un_banco_llama_beneficio_residual_a_los_flujos():
    p = perfil(industria="Banks - Regional")
    salida = mv.resumen(_valoracion(p=p))
    assert "Beneficio residual" in salida
    assert "Flujos (DCF e inverso)" not in salida
    assert mv.MOTIVO["financiera"] in salida


def test_una_empresa_con_flujos_no_se_llama_beneficio_residual():
    assert "Beneficio residual" not in mv.resumen(_fija())


def test_quemar_caja_se_explica_y_no_se_pone_a_cero():
    f = fundamentos(ejercicios=[ejercicio(2026 - i, flujo_operativo=50.0) for i in range(4)])
    salida = mv.resumen(_valoracion(f=f))
    assert mv.MOTIVO["quema_caja"] in salida


def test_un_voto_que_no_aplica_dice_por_que():
    votos = {**_fija()["votos"], "pares": {"voto": "no_aplica", "motivo": "sin_pares"}}
    assert _fila(_fija(votos=votos), "pares") == ("Frente a sus pares", "No aplica", mv.MOTIVO["sin_pares"])


# Flujos, crecimiento: el precio da por hecho un crecimiento (o una caída) y se
# compara con la referencia.
@pytest.mark.parametrize(
    ("implicito", "esperado"),
    [
        (
            {"valor": 0.274, "referencia": 0.4, "margen": 0.2, "fuera_de_limites": None},
            "el precio da por hecho que los ingresos crecerán un 27.4% al año durante 5 años; "
            "su referencia es 40.0% (banda de ±20.0 puntos)",
        ),
        (
            {"valor": 0.0, "referencia": 0.05, "margen": 0.05, "fuera_de_limites": None},
            "el precio da por hecho que los ingresos crecerán un 0.0% al año durante 5 años; "
            "su referencia es 5.0% (banda de ±5.0 puntos)",
        ),
        (
            {"valor": -0.052, "referencia": 0.021, "margen": 0.05, "fuera_de_limites": None},
            "el precio da por hecho que los ingresos caerán un 5.2% al año durante 5 años; "
            "su referencia es 2.1% (banda de ±5.0 puntos)",
        ),
        (
            {"valor": 0.02, "referencia": -0.043, "margen": 0.05, "fuera_de_limites": None},
            "el precio da por hecho que los ingresos crecerán un 2.0% al año durante 5 años; "
            "su referencia es una caída del 4.3% (banda de ±5.0 puntos)",
        ),
        (
            {"valor": -0.1, "referencia": -0.04, "margen": 0.05, "fuera_de_limites": None},
            "el precio da por hecho que los ingresos caerán un 10.0% al año durante 5 años; "
            "su referencia es una caída del 4.0% (banda de ±5.0 puntos)",
        ),
        (
            {"valor": 0.8, "referencia": 0.4, "margen": 0.2, "fuera_de_limites": "arriba"},
            "el precio da por hecho un crecimiento de más del 80.0% al año",
        ),
        (
            {"valor": -0.3, "referencia": 0.04, "margen": 0.05, "fuera_de_limites": "abajo"},
            "el precio es tan bajo que ni una caída del 30.0% al año lo explicaría",
        ),
        (
            {"valor": None, "referencia": 0.04, "margen": 0.05, "fuera_de_limites": None},
            "n/d",
        ),
        (
            # Una referencia de cero no es una caída.
            {"valor": 0.02, "referencia": 0.0, "margen": 0.05, "fuera_de_limites": None},
            "el precio da por hecho que los ingresos crecerán un 2.0% al año durante 5 años; "
            "su referencia es 0.0% (banda de ±5.0 puntos)",
        ),
        (
            {"valor": 0.02, "referencia": None, "margen": None, "fuera_de_limites": None},
            "el precio da por hecho que los ingresos crecerán un 2.0% al año durante 5 años; "
            "su referencia es n/d (banda de ±n/d)",
        ),
    ],
    ids=[
        "crece", "cero", "cae", "referencia_negativa", "cae_con_referencia_negativa",
        "arriba", "abajo", "sin_valor", "referencia_cero", "sin_referencia_ni_banda",
    ],
)
def test_el_texto_de_la_lectura_de_crecimiento(implicito, esperado):
    valoracion = _fija(implicito={"magnitud": "crecimiento", **implicito})
    assert _detalle(valoracion, "flujos") == esperado


@pytest.mark.parametrize(
    ("implicito", "esperado"),
    [
        (
            {"valor": 0.1497, "referencia": 0.1584, "margen": 0.0792, "fuera_de_limites": None},
            "el precio exige un ROE del 15.0%; su referencia es 15.8% (banda de ±7.9 puntos)",
        ),
        (
            # Un ROE de referencia negativo es una rentabilidad negativa, no una caída.
            {"valor": 0.05, "referencia": -0.04, "margen": 0.03, "fuera_de_limites": None},
            "el precio exige un ROE del 5.0%; su referencia es −4.0% (banda de ±3.0 puntos)",
        ),
        (
            {"valor": 0.6, "referencia": 0.15, "margen": 0.075, "fuera_de_limites": "arriba"},
            "el precio exige un ROE de más del 60.0%",
        ),
        (
            {"valor": -0.2, "referencia": 0.15, "margen": 0.075, "fuera_de_limites": "abajo"},
            "el precio es tan bajo que ni un ROE del −20.0% lo explicaría",
        ),
    ],
    ids=["normal", "referencia_negativa", "arriba", "abajo"],
)
def test_el_texto_de_la_lectura_de_roe(implicito, esperado):
    valoracion = _fija_residual(implicito={"magnitud": "roe", **implicito})
    assert _detalle(valoracion, "flujos") == esperado


@pytest.mark.parametrize(
    ("epv", "esperado"),
    [
        (
            {"por_accion": 392.27, "parte_crecimiento": 0.5884},
            "sin crecer valdría 392.27 USD; el 58.8% del precio es apuesta por el crecimiento",
        ),
        ({"por_accion": 392.27, "parte_crecimiento": 0.0}, "sin crecer valdría 392.27 USD"),
        # Un EPV por encima del precio da una parte negativa: no hay apuesta que contar.
        ({"por_accion": 1200.0, "parte_crecimiento": -0.3}, "sin crecer valdría 1,200.00 USD"),
        ({"por_accion": 392.27, "parte_crecimiento": None}, "sin crecer valdría 392.27 USD"),
        ({"por_accion": None, "parte_crecimiento": None}, "sin crecer valdría n/d"),
    ],
    ids=["con_apuesta", "cero", "negativa", "sin_parte", "sin_epv"],
)
def test_el_texto_del_valor_sin_crecimiento(epv, esperado):
    assert _detalle(_fija(epv=epv), "sin_crecimiento") == esperado


@pytest.mark.parametrize(
    ("voto", "esperado"),
    [
        ("barata", "múltiplos por debajo de los de su sector"),
        ("neutra", "múltiplos en línea con los de su sector"),
        ("cara", "múltiplos por encima de los de su sector"),
    ],
)
def test_el_texto_de_los_pares(voto, esperado):
    votos = {**_fija()["votos"], "pares": {"voto": voto, "motivo": None}}
    assert _detalle(_fija(votos=votos), "pares") == esperado


# --- Los supuestos ----------------------------------------------------------------


def test_el_resumen_completo_de_una_empresa():
    assert _texto(mv.resumen(_fija())) == "\n".join(
        [
            "En rango | Valor por acción: pesimista 80.50 USD · base 1,234.50 USD · "
            "optimista 4,321.00 USD · margen de seguridad 20.3% | "
            "Calculada el 2026-10-12 con el precio de 100.00 USD "
            "(cotización del 2026-10-12 19:59 UTC) y estados hasta 2026-09-30",
            "Flujos (DCF e inverso) | Neutra | el precio da por hecho que los ingresos crecerán "
            "un 27.4% al año durante 5 años; su referencia es 40.0% (banda de ±20.0 puntos)",
            "Sin crecimiento (EPV) | Neutra | sin crecer valdría 392.27 USD; el 58.8% del "
            "precio es apuesta por el crecimiento",
            "Frente a sus pares | Barata | múltiplos por debajo de los de su sector",
            "Supuestos del programa",
            "tasa libre: 5.2% · Tesoro de EE. UU. a 10 años (^TNX)",
            "beta: 2.00 · regresión semanal de 104 semanas contra ^GSPC (R² 0.29), con el ajuste de Blume",
            "prima de riesgo: 4.2% · Damodaran, prima implícita a 2026-10-01",
            "coste del capital propio: 13.6% · tasa libre más beta por prima",
            "coste de la deuda: 5.2% · gasto financiero entre deuda, acotado entre la tasa libre "
            "y esa tasa más 8.0 puntos",
            "impuestos: 11.6% · tasa efectiva de yfinance, acotada entre 0.0% y 35.0%",
            "coste de capital (deuda y capital propio): 13.6% · deuda 0.4% del capital",
            "crecimiento de referencia: 40.0% · media del crecimiento histórico de los ingresos "
            "(104.7%) y del consenso del próximo año (15.7%), acotada entre −10.0% y 40.0%",
            "crecimiento a perpetuidad: 2.5% · criterio fijo del programa para el USD",
        ]
    )


def test_el_resumen_completo_de_un_banco():
    assert _texto(mv.resumen(_fija_residual())) == "\n".join(
        [
            "En rango | Valor por acción: pesimista 80.50 USD · base 1,234.50 USD · "
            "optimista 4,321.00 USD · margen de seguridad 20.3% | "
            "Calculada el 2026-10-12 con el precio de 100.00 USD "
            "(cotización del 2026-10-12 19:59 UTC) y estados hasta 2026-09-30",
            "Beneficio residual | Neutra | el precio exige un ROE del 15.0%; su referencia es "
            "15.8% (banda de ±7.9 puntos)",
            "Sin crecimiento (EPV) | No aplica | se valora por beneficio residual (entidades financieras)",
            "Frente a sus pares | Neutra | múltiplos en línea con los de su sector",
            "Supuestos del programa",
            "tasa libre: 5.2% · Tesoro de EE. UU. a 10 años (^TNX)",
            "beta: 2.00 · regresión semanal de 104 semanas contra ^GSPC (R² 0.29), con el ajuste de Blume",
            "prima de riesgo: 4.2% · Damodaran, prima implícita a 2026-10-01",
            "coste del capital propio: 13.6% · tasa libre más beta por prima",
            "ROE de referencia: 15.8% · mediana de 5 años",
            "reparto de beneficios: 0.7% · según yfinance, acotado entre 0.0% y 100.0%",
            "crecimiento a perpetuidad: 2.5% · criterio fijo del programa para el USD",
        ]
    )


def test_los_supuestos_van_uno_por_linea_en_su_propio_bloque():
    salida = mv.resumen(_fija())
    bloque = salida[salida.index('<div class="mpp-val-sup">') :]
    assert bloque.count("<div>") == 9
    assert bloque.count('<div class="mpp-val-sup-titulo">') == 1


def test_un_banco_no_enseña_los_supuestos_que_no_usa():
    salida = mv.resumen(_valoracion(p=perfil(industria="Banks - Regional")))
    for sobra in ("coste de la deuda", "coste de capital (", "impuestos", "crecimiento de referencia"):
        assert sobra not in salida
    for falta in ("ROE de referencia", "reparto de beneficios", "coste del capital propio"):
        assert falta in salida


def test_una_industrial_no_enseña_el_roe_ni_el_reparto():
    salida = mv.resumen(_valoracion())
    for sobra in ("ROE de referencia", "reparto de beneficios"):
        assert sobra not in salida
    assert "coste de capital (deuda y capital propio)" in salida


def test_un_banco_con_coste_de_capital_nulo_no_enseña_n_d_de_lo_que_no_usa():
    salida = mv.resumen(_valoracion(p=perfil(industria="Banks - Regional")))
    assert "n/d" not in _texto(salida).split("Supuestos del programa")[1]


def test_los_supuestos_van_en_el_gris_del_tema():
    regla = re.search(r"\.mpp-val-sup \{[^}]*\}", mv.CSS).group(0)
    assert f"color:{tema.TEXTO_SUAVE}" in regla


def test_un_supuesto_que_falta_en_la_ficha_se_salta():
    supuestos = _supuestos_fijos()
    del supuestos["prima"]
    texto = _texto(mv.resumen(_fija(supuestos=supuestos)))
    assert "prima de riesgo" not in texto
    assert "tasa libre: 5.2%" in texto


def test_sin_supuestos_no_hay_bloque():
    salida = mv.resumen(_fija(supuestos={}))
    assert "mpp-val-sup" not in salida
    assert len(_lineas(salida)) == 4
    assert salida.endswith("múltiplos por debajo de los de su sector</span></div></div>")


def test_un_supuesto_sin_fuente_conocida_se_enseña_sin_origen():
    supuestos = {"r_f": {"valor": 0.0522, "procedencia": {"fuente": "otra"}}}
    assert _lineas(mv.resumen(_fija(supuestos=supuestos)))[-1] == "tasa libre: 5.2%"


def test_a_la_deuda_se_le_supone_declarada_si_la_ficha_no_dice_otra_cosa():
    assert mv.procedencia("wacc", {"procedencia": {"fuente": "wacc", "peso_deuda": 0.1}}) == "deuda 10.0% del capital"


def test_hasta_las_etiquetas_de_los_veredictos_y_los_votos_se_escapan(monkeypatch):
    monkeypatch.setitem(mv.VEREDICTO, "en_rango", ("<b>rango</b>", tema.TEXTO_SUAVE))
    monkeypatch.setitem(mv.VOTO, "barata", ("<i>barata</i>", tema.VERDE))
    salida = mv.resumen(_fija())
    assert "<b>" not in salida and "<i>" not in salida
    assert "&lt;b&gt;rango&lt;/b&gt;" in salida
    assert "&lt;i&gt;barata&lt;/i&gt;" in salida


# --- La procedencia -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("nombre", "procedencia", "esperado"),
    [
        ("r_f", {"fuente": "tesoro_10", "serie": "^TNX"}, "Tesoro de EE. UU. a 10 años (^TNX)"),
        (
            "beta",
            {"fuente": "regresion", "indice": "^GSPC", "semanas": 104, "r2": 0.4123},
            "regresión semanal de 104 semanas contra ^GSPC (R² 0.41), con el ajuste de Blume",
        ),
        (
            "beta",
            {"fuente": "regresion", "indice": "^GSPC", "semanas": 104, "r2": 0.4},
            "regresión semanal de 104 semanas contra ^GSPC (R² 0.40), con el ajuste de Blume",
        ),
        (
            "beta",
            {"fuente": "por_defecto"},
            "1.0 por defecto: no hubo regresión posible (historial corto o precios inválidos)",
        ),
        (
            "beta",
            {"fuente": "por_defecto", "motivo": "sin_regresion"},
            "1.0 por defecto: no hubo regresión posible (historial corto o precios inválidos)",
        ),
        (
            "beta",
            {"fuente": "por_defecto", "motivo": "sin_red"},
            "1.0 por defecto, porque Yahoo Finance no devolvió datos para la regresión",
        ),
        (
            "beta",
            {"fuente": "por_defecto", "motivo": ["sin_red"]},
            "1.0 por defecto: no hubo regresión posible (historial corto o precios inválidos)",
        ),
        ("prima", {"fuente": "damodaran", "fecha": "2026-10-01"}, "Damodaran, prima implícita a 2026-10-01"),
        ("k_e", {"fuente": "capm"}, "tasa libre más beta por prima"),
        (
            "k_d",
            {"fuente": "gasto_entre_deuda", "bruto": 0.0226},
            "gasto financiero entre deuda, acotado entre la tasa libre y esa tasa más 8.0 puntos",
        ),
        ("k_d", {"fuente": "sin_dato"}, "sin deuda o sin gasto financiero declarado: la tasa libre"),
        (
            "k_d",
            {"fuente": "financiera"},
            "en un banco o una aseguradora los intereses incluyen los depósitos: no se calcula",
        ),
        ("t", {"fuente": "efectiva", "bruta": 0.116}, "tasa efectiva de yfinance, acotada entre 0.0% y 35.0%"),
        ("t", {"fuente": "legal", "pais": "MX"}, "tasa legal de México"),
        ("t", {"fuente": "legal", "pais": "US"}, "tasa legal de EE. UU."),
        ("t", {"fuente": "legal", "pais": "otros"}, "tasa legal genérica para otros países"),
        # Una clave que la pantalla no conoce se enseña tal cual: mejor que esconderla.
        ("t", {"fuente": "legal", "pais": "BR"}, "tasa legal (BR)"),
        (
            "t",
            {"fuente": "legal", "pais": "US", "motivo": "sin_red"},
            "tasa legal de EE. UU., porque Yahoo Finance no devolvió datos de la tasa efectiva",
        ),
        ("t", {"fuente": "legal", "pais": "US", "motivo": "sin_tasa_efectiva"}, "tasa legal de EE. UU."),
        (
            "wacc",
            {"fuente": "financiera"},
            "en un banco o una aseguradora no se calcula: se valora con el coste del capital propio",
        ),
        ("wacc", {"fuente": "wacc", "peso_deuda": 0.0925, "deuda_declarada": True}, "deuda 9.2% del capital"),
        (
            "wacc",
            {"fuente": "wacc", "peso_deuda": 0.0, "deuda_declarada": False},
            "deuda 0.0% del capital; sin deuda declarada",
        ),
        (
            "g_ref",
            {"fuente": "historia_y_consenso", "historico": 0.042, "consenso": 0.001},
            "media del crecimiento histórico de los ingresos (4.2%) y del consenso del próximo año (0.1%), "
            "acotada entre −10.0% y 40.0%",
        ),
        (
            "g_ref",
            {"fuente": "historia", "historico": 0.042, "consenso": None},
            "crecimiento histórico de los ingresos (4.2%), sin consenso, acotado entre −10.0% y 40.0%",
        ),
        (
            "g_ref",
            {"fuente": "consenso", "historico": None, "consenso": 0.0311},
            "consenso del próximo año (3.1%), sin historia, acotado entre −10.0% y 40.0%",
        ),
        (
            "g_ref",
            {"fuente": "historia", "historico": 0.042, "consenso": None, "motivo_consenso": "sin_red"},
            "crecimiento histórico de los ingresos (4.2%), sin consenso porque Yahoo Finance no "
            "devolvió datos, acotado entre −10.0% y 40.0%",
        ),
        (
            "g_ref",
            {"fuente": "historia", "historico": 0.042, "consenso": None, "motivo_consenso": "sin_consenso"},
            "crecimiento histórico de los ingresos (4.2%), sin consenso, acotado entre −10.0% y 40.0%",
        ),
        ("g_ref", {"fuente": "sin_dato"}, "sin historia ni consenso"),
        (
            "g_ref",
            {"fuente": "sin_dato", "motivo_consenso": "sin_red"},
            "sin historia, y sin consenso porque Yahoo Finance no devolvió datos",
        ),
        ("g_ref", {"fuente": "sin_dato", "motivo_consenso": "sin_consenso"}, "sin historia ni consenso"),
        (
            "g_perpetuo",
            {"fuente": "criterio", "moneda": "MXN"},
            "criterio fijo del programa para el MXN",
        ),
        ("g_perpetuo", {"fuente": "recortado_a_r_f", "base": 0.025}, "recortado a la tasa libre de riesgo"),
        ("roe_ref", {"fuente": "mediana_historica", "anos": 5}, "mediana de 5 años"),
        ("roe_ref", {"fuente": "sin_dato"}, "sin años suficientes"),
        ("payout", {"fuente": "yfinance"}, "según yfinance, acotado entre 0.0% y 100.0%"),
        ("payout", {"fuente": "por_defecto"}, "sin dato: se supone el 50.0%"),
    ],
)
def test_el_texto_de_cada_procedencia(nombre, procedencia, esperado):
    assert mv.procedencia(nombre, {"valor": 0.1, "procedencia": procedencia}) == esperado


def test_cada_tasa_legal_del_criterio_tiene_su_nombre_en_pantalla():
    # «tasa legal (otros)» enseñaba una clave interna.
    assert set(mv._PAIS_LEGAL) == set(criterio.TASA_LEGAL)


def test_una_procedencia_desconocida_no_revienta():
    assert mv.procedencia("beta", {"valor": 1.0, "procedencia": {"fuente": "otra"}}) == ""


@pytest.mark.parametrize(
    "supuesto",
    [None, "x", [], {"valor": 1.0}, {"procedencia": None}, {"procedencia": "x"}, {"procedencia": {"fuente": ["capm"]}}],
)
def test_una_procedencia_rota_da_vacio(supuesto):
    assert mv.procedencia("k_e", supuesto) == ""


def test_la_beta_dice_de_donde_sale():
    texto = mv.procedencia(
        "beta",
        {"valor": 1.33, "procedencia": {"fuente": "regresion", "indice": "^GSPC", "semanas": 104, "r2": 0.41}},
    )
    assert "104 semanas" in texto and "^GSPC" in texto and "Blume" in texto


def test_el_r2_de_una_beta_rota_es_n_d():
    texto = mv.procedencia(
        "beta", {"valor": 1.0, "procedencia": {"fuente": "regresion", "indice": "^GSPC", "semanas": 104, "r2": "x"}}
    )
    assert "(R² n/d)" in texto


def _sin_historia():
    """Un solo ejercicio: no hay CAGR, así que el crecimiento sólo puede venir del consenso."""
    return fundamentos(ejercicios=[ejercicio(2026)])


_BETA = Beta(bruta=1.4, r2=0.41, semanas=104, indice="^GSPC")

# Cada caso fabrica supuestos reales con `deducir`, no a mano: si el paquete
# empieza a escribir una fuente nueva, este test falla en vez de dejar que la
# pantalla muestre un supuesto sin explicar. Cada caso lleva su propio perfil
# porque un banco valorado con un perfil de industrial no es una valoración real.
_CASOS_DE_SUPUESTOS = {
    "empresa normal": (fundamentos(), perfil(), dict(tasa=0.25, consenso=0.08)),
    "sin tasa efectiva ni payout": (
        fundamentos(), perfil(payout=None, pais="Mexico"), dict(tasa=None, consenso=None)
    ),
    "sin deuda": (fundamentos(deuda_total=0.0), perfil(), dict(tasa=0.25, consenso=0.08)),
    "banco": (fundamentos(), perfil(industria="Banks - Regional"), dict(tasa=0.25, consenso=0.08)),
    "sólo consenso": (_sin_historia(), perfil(), dict(tasa=0.25, consenso=0.08)),
    "sólo historia": (fundamentos(), perfil(), dict(tasa=0.25, consenso=None)),
    "ni historia ni consenso": (_sin_historia(), perfil(), dict(tasa=0.25, consenso=None)),
    "con regresión de beta": (fundamentos(), perfil(), dict(beta=_BETA, tasa=0.25, consenso=0.08)),
}


@pytest.mark.parametrize("caso", _CASOS_DE_SUPUESTOS)
@pytest.mark.parametrize("r_f", [0.04, 0.02])
def test_todo_supuesto_que_se_puede_producir_tiene_procedencia_en_pantalla(caso, r_f):
    # Con r_f = 0,02 el crecimiento perpetuo (2,5 %) se recorta a la tasa libre.
    f, p, kwargs = _CASOS_DE_SUPUESTOS[caso]
    s = deducir(f, p, r_f=r_f, **{"beta": None, **kwargs})
    supuestos = a_dict(calcular(f, p, s, 0.8, date(2026, 10, 12)))["supuestos"]
    for nombre, supuesto in supuestos.items():
        assert mv.procedencia(nombre, supuesto) != "", (nombre, supuesto["procedencia"])


def _fuentes_que_escribe_el_paquete() -> "set[str]":
    """Cada `"fuente": "<literal>"` de supuestos.py y cada literal asignado a `fuente`.

    Se lee el árbol sintáctico y no el texto, para que un literal en un comentario
    no cuente y uno escrito en dos líneas tampoco se escape.
    """
    ruta = Path(__file__).resolve().parent.parent / "valoracion" / "supuestos.py"
    encontradas = set()
    for nodo in ast.walk(ast.parse(ruta.read_text(encoding="utf-8"))):
        valores = []
        if isinstance(nodo, ast.Dict):
            valores = [
                v for k, v in zip(nodo.keys, nodo.values)
                if isinstance(k, ast.Constant) and k.value == "fuente"
            ]
        elif isinstance(nodo, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "fuente" for t in nodo.targets
        ):
            valores = [nodo.value]
        for valor in valores:
            encontradas |= {
                n.value for n in ast.walk(valor)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)
            }
    return encontradas


def test_ninguna_fuente_nueva_se_queda_sin_texto():
    fuentes = _fuentes_que_escribe_el_paquete()
    # Si el lector dejara de encontrar fuentes, el resto del test pasaría en vacío.
    assert {"tesoro_10", "regresion", "historia_y_consenso", "financiera", "recortado_a_r_f"} <= fuentes
    for fuente in sorted(fuentes):
        con_texto = [
            nombre
            for nombre in mv._NOMBRE_SUPUESTO
            if mv.procedencia(nombre, {"procedencia": {"fuente": fuente}}) != ""
        ]
        assert con_texto, f"la fuente «{fuente}» de supuestos.py no tiene texto en la pantalla"


# --- Escapar lo que no es nuestro -----------------------------------------------------


def test_el_resumen_escapa_lo_que_no_es_suyo():
    valor = {**_valoracion(), "moneda": "<b>USD</b>"}
    salida = mv.resumen(valor)
    assert "<b>USD</b>" not in salida
    assert "&lt;b&gt;USD&lt;/b&gt;" in salida


def test_hasta_los_nombres_de_los_votos_se_escapan(monkeypatch):
    # Son constantes de este módulo, pero la regla es una sola: nada se pinta sin escapar.
    monkeypatch.setitem(mv.NOMBRE_VOTO, "pares", "<i>pares</i>")
    salida = mv.resumen(_fija())
    assert "<i>" not in salida
    assert "&lt;i&gt;pares&lt;/i&gt;" in salida


def test_una_fallida_con_un_motivo_raro_se_escapa():
    salida = mv.resumen({"version": "m1", "fecha": "2026-10-12", "motivo": "<x>"})
    assert "<x>" not in salida
    assert salida == '<div class="mpp-val">Sin valoración: &lt;x&gt;.</div>'


def _rica() -> dict:
    """Una valoración real en la que se pintan casi todos los textos que vienen de fuera."""
    f, p = fundamentos(), perfil()
    s = deducir(f, p, r_f=0.04, beta=_BETA, tasa=None, consenso=0.08)
    return a_dict(calcular(f, p, s, 0.8, date(2026, 10, 12)))


def _quema_caja() -> dict:
    f = fundamentos(ejercicios=[ejercicio(2026 - i, flujo_operativo=50.0) for i in range(4)])
    return _valoracion(f=f)


def _hojas_de_texto(objeto, ruta=()):
    if isinstance(objeto, dict):
        for clave, valor in objeto.items():
            yield from _hojas_de_texto(valor, (*ruta, clave))
    elif isinstance(objeto, str):
        yield ruta


def _con_hoja(objeto: dict, ruta: tuple, valor: str) -> dict:
    copia = copy.deepcopy(objeto)
    destino = copia
    for clave in ruta[:-1]:
        destino = destino[clave]
    destino[ruta[-1]] = valor
    return copia


_VALORACIONES_A_INYECTAR = {
    "rica": _rica(),
    "quema_caja": _quema_caja(),
    "banco": _valoracion(p=perfil(industria="Banks - Regional")),
    "fallida": fallida("sin_precio"),
}
_HOJAS = [
    (nombre, ruta)
    for nombre, valoracion in _VALORACIONES_A_INYECTAR.items()
    for ruta in _hojas_de_texto(valoracion)
]

# Las hojas de texto que SÍ se pintan: si una se dejara de escapar, saldría
# cruda. El resto se descarta o se lee (la hora, el veredicto) y no se pinta.
_SE_PINTAN = {
    ("rica", ("moneda",)),
    ("rica", ("fecha",)),
    ("rica", ("estados_hasta",)),
    ("rica", ("supuestos", "r_f", "procedencia", "serie")),
    ("rica", ("supuestos", "beta", "procedencia", "indice")),
    ("rica", ("supuestos", "prima", "procedencia", "fecha")),
    ("rica", ("supuestos", "t", "procedencia", "pais")),
    ("rica", ("supuestos", "g_perpetuo", "procedencia", "moneda")),
    ("quema_caja", ("votos", "flujos", "motivo")),
    ("banco", ("votos", "sin_crecimiento", "motivo")),
    ("fallida", ("motivo",)),
}


def test_la_inyeccion_toca_los_textos_que_se_pintan():
    # Guarda del propio test: cada hoja que se declara pintada existe de verdad.
    assert _SE_PINTAN <= set(_HOJAS)


@pytest.mark.parametrize(("nombre", "ruta"), _HOJAS, ids=[f"{n}:{'.'.join(r)}" for n, r in _HOJAS])
def test_ningun_texto_de_la_ficha_llega_crudo_a_la_pantalla(nombre, ruta):
    valoracion = _con_hoja(_VALORACIONES_A_INYECTAR[nombre], ruta, "<x>")
    salida = mv.resumen(valoracion) + mv.distintivo(valoracion)
    assert "<x>" not in salida
    if (nombre, ruta) in _SE_PINTAN:
        assert "&lt;x&gt;" in salida


# --- Una ficha corrupta no tumba la pantalla ---------------------------------------------


@pytest.mark.parametrize(
    "cambios",
    [
        {"votos": []},
        {"votos": "x"},
        {"votos": None},
        {"votos": {"flujos": "x", "sin_crecimiento": None, "pares": []}},
        {"votos": {"flujos": {"voto": ["cara"]}, "sin_crecimiento": {"voto": 3}, "pares": {"voto": {}}}},
        {"votos": {"flujos": {"voto": "no_aplica", "motivo": ["a"]}}},
        {"valor": "x"},
        {"valor": [1, 2]},
        {"valor": {"base": "x", "pesimista": None}},
        {"valor": 3},
        {"implicito": "x"},
        {"implicito": {"magnitud": ["roe"], "valor": "x", "fuera_de_limites": ["arriba"]}},
        {"implicito": {"magnitud": "roe", "valor": "x", "referencia": [], "margen": {}}},
        {"epv": [1]},
        {"epv": {"por_accion": "x", "parte_crecimiento": "y"}},
        {"supuestos": []},
        {"supuestos": "x"},
        {"supuestos": {"r_f": "x", "beta": None, "prima": [1], "k_e": {"valor": "0.1"}}},
        {"supuestos": {"beta": {"valor": "1.2", "procedencia": "x"}}},
        {"supuestos": {"r_f": {"valor": float("nan"), "procedencia": {"fuente": "tesoro_10"}}}},
        {"supuestos": {"r_f": {"valor": 10**400, "procedencia": {"fuente": ["tesoro_10"]}}}},
        {"margen_seguridad": "x"},
        {"margen_seguridad": True},
        {"precio": "x", "moneda": ["USD"]},
        {"precio": float("inf")},
        {"metodo": ["residual"]},
        {"fecha": None, "estados_hasta": None},
        {"precio_hora": float("nan")},
    ],
    ids=lambda c: next(iter(c)) + ":" + repr(next(iter(c.values())))[:30],
)
def test_una_ficha_corrupta_no_hace_reventar_el_resumen(cambios):
    salida = mv.resumen(_fija(**cambios))
    assert salida.startswith('<div class="mpp-val">') and salida.endswith("</div>")


@pytest.mark.parametrize("valor", [None, [], "x", 3])
def test_lo_que_no_es_una_valoracion_no_se_pinta(valor):
    assert mv.resumen(valor) == ""


def test_un_voto_con_valor_roto_se_lee_n_d():
    votos = {"flujos": {"voto": ["cara"]}, "sin_crecimiento": "x", "pares": {"voto": 3}}
    for clave in ("flujos", "sin_crecimiento", "pares"):
        _, etiqueta, _ = _fila(_fija(votos=votos), clave)
        assert etiqueta == "n/d"
    assert '<span class="mpp-val-etiqueta" style="color:' + tema.TEXTO_SUAVE + '">n/d</span>' in mv.resumen(
        _fija(votos=votos)
    )


def test_un_supuesto_con_valor_de_texto_se_lee_n_d():
    supuestos = {"r_f": {"valor": "0.05", "procedencia": {"fuente": "tesoro_10", "serie": "^TNX"}}}
    assert "tasa libre: n/d · Tesoro de EE. UU. a 10 años (^TNX)" in _texto(mv.resumen(_fija(supuestos=supuestos)))


def test_un_valor_que_no_es_un_diccionario_no_da_rango():
    assert "Sin rango de valor." in mv.resumen(_fija(valor="x"))


def test_un_numero_infinito_o_un_booleano_se_leen_n_d():
    assert "margen de seguridad n/d" in mv.resumen(_fija(margen_seguridad=float("inf")))
    assert "margen de seguridad n/d" in mv.resumen(_fija(margen_seguridad=True))


def test_una_ficha_sin_rango_sigue_siendo_una_valoracion():
    valoracion = _fija()
    del valoracion["valor"]
    salida = mv.resumen(valoracion)
    assert "Sin valoración" not in salida
    assert "Sin rango de valor." in salida


def test_lo_que_trae_motivo_y_no_veredicto_es_una_fallida_aunque_lleve_valor():
    assert _texto(mv.resumen({"motivo": "sin_precio", "valor": None})) == (
        "Sin valoración: Yahoo Finance no devolvió el precio."
    )


# --- Las dos funciones de respaldo ------------------------------------------------------


def test_una_fallida_dice_por_que():
    assert mv.MOTIVO["sin_precio"] in mv.resumen(fallida("sin_precio"))


def test_el_texto_de_una_fallida():
    texto = _texto(mv.resumen(fallida("sin_precio")))
    assert texto == "Sin valoración: Yahoo Finance no devolvió el precio."


def test_un_motivo_que_no_se_conoce_se_enseña_tal_cual():
    assert _texto(mv.resumen({"motivo": "motivo_nuevo"})) == "Sin valoración: motivo_nuevo."


@pytest.mark.parametrize("motivo", [None, ["sin_precio"], 3])
def test_una_fallida_sin_motivo_legible_dice_n_d(motivo):
    assert _texto(mv.resumen({"motivo": motivo})) == "Sin valoración: n/d."
    assert _texto(mv.resumen({})) == "Sin valoración: n/d."


def test_un_voto_que_no_se_conoce_se_pinta_n_d_en_el_gris():
    votos = {**_fija()["votos"], "pares": {"voto": "otro", "motivo": None}}
    salida = mv.resumen(_fija(votos=votos))
    assert f'<span class="mpp-val-etiqueta" style="color:{tema.TEXTO_SUAVE}">n/d</span>' in salida
    assert _detalle(_fija(votos=votos), "pares") == ""


# --- El color y el CSS ------------------------------------------------------------------


def _colores_de_texto() -> "dict[str, str]":
    colores = {f"CSS {c}": c for c in re.findall(r"#[0-9a-fA-F]{6}\b", mv.CSS)}
    colores.update({f"veredicto {k}": c for k, (_, c) in mv.VEREDICTO.items()})
    colores.update({f"voto {k}": c for k, (_, c) in mv.VOTO.items()})
    return colores


def test_el_css_usa_colores():
    # Guarda del test de debajo: si el patrón dejara de casar, no comprobaría nada.
    assert any(nombre.startswith("CSS ") for nombre in _colores_de_texto())


def test_todo_color_de_texto_contrasta_sobre_la_tarjeta():
    # WCAG AA para texto normal. `TEXTO_TENUE` se queda en 4.28:1 sobre la tarjeta.
    flojos = {
        nombre: round(contraste(color, tema.TARJETA), 2)
        for nombre, color in _colores_de_texto().items()
        if contraste(color, tema.TARJETA) < 4.5
    }
    assert not flojos, flojos


def test_ningun_texto_de_la_valoracion_usa_el_gris_tenue():
    assert tema.TEXTO_TENUE not in _colores_de_texto().values()
    assert tema.TEXTO_TENUE not in mv.resumen(_fija()) + mv.resumen(_fija_residual())


def test_el_css_es_una_hoja_de_estilo_completa():
    assert mv.CSS.startswith("<style>") and mv.CSS.endswith("</style>")


@pytest.mark.parametrize(
    ("selector", "color"),
    [
        (".mpp-val", tema.TEXTO),
        (".mpp-val-detalle", tema.TEXTO_SUAVE),
        (".mpp-val-sup", tema.TEXTO_SUAVE),
    ],
)
def test_el_color_de_cada_regla_de_texto(selector, color):
    regla = re.search(re.escape(selector) + r" \{([^}]*)\}", mv.CSS).group(1)
    assert re.search(r"(?:^|;)\s*color:(#[0-9a-fA-F]{6});", regla).group(1) == color


def test_el_css_no_esconde_nada():
    for prohibido in ("display:none", "display: none", "visibility:hidden", "position:fixed", "position: fixed"):
        assert prohibido not in mv.CSS, prohibido


def test_el_css_no_lleva_colores_escritos_a_mano():
    # Todo color sale de `tema`: se quitan los suyos y no debe quedar ningún otro.
    sin_tema = mv.CSS
    for valor in vars(tema).values():
        if isinstance(valor, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", valor):
            sin_tema = sin_tema.replace(valor, "")
    assert not re.findall(r"#[0-9a-fA-F]{3,8}\b", sin_tema)


# --- El glosario ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "termino",
    [
        "Las lecturas y los votos",
        "Frente a sus pares",
        "DCF",
        "DCF inverso",
        "EPV",
        "Beneficio residual",
        "Capex",
        "ROE",
        "Consenso",
        "Tasa libre de riesgo y prima de riesgo",
        "Beta, R² y Blume",
        "Coste de capital (WACC)",
        "coste del capital propio",
        "Crecimiento a perpetuidad y valor terminal",
        "Escenarios",
        "Margen de seguridad",
        "Veredicto",
    ],
)
def test_el_glosario_explica_cada_termino(termino):
    assert f"**{termino}**" in mv.glosario()


def test_el_glosario_empieza_por_las_lecturas_y_los_votos():
    entradas = mv.glosario().split("\n")
    assert entradas[0].startswith("- **Las lecturas y los votos**: ")
    assert entradas[1].startswith("- **Frente a sus pares**: ")


def test_el_glosario_dice_que_lectura_da_cada_voto():
    lecturas = mv.glosario().split("\n")[0]
    # El voto lo da el inverso y el rango del DCF es su contexto (`valoracion/votos.py`).
    assert "dan un solo voto" in lecturas
    assert f"«{mv.NOMBRE_VOTO['flujos']}»: lo decide el inverso, y el DCF da el rango" in lecturas
    assert f"«{mv.NOMBRE_VOTO['sin_crecimiento']}», que nunca vota «cara»" in lecturas
    assert f"«{mv.NOMBRE_VOTO['pares']}»" in lecturas


def test_el_glosario_dice_que_una_financiera_tiene_tres_lecturas_y_dos_votos():
    lecturas = mv.glosario().split("\n")[0]
    assert "el beneficio residual y su inverso (el ROE que el precio exige)" in lecturas
    assert "«Beneficio residual», lo decide el inverso, y el beneficio residual da el rango" in lecturas
    assert "No hay voto sin crecimiento: tres lecturas y dos votos." in lecturas


def test_el_glosario_dice_que_el_voto_de_pares_es_el_pilar_de_valoracion():
    pares = mv.glosario().split("\n")[1]
    assert "es el pilar «valoración» del score" in pares
    assert "«barata» con una puntuación de +0.5 o más" in pares
    assert "«cara» con −0.5 o menos" in pares


def test_el_glosario_avisa_de_que_el_capex_de_mantenimiento_no_se_separa():
    assert "ninguna fuente separa el capex de mantenimiento del de expansión" in mv.glosario()


def test_el_glosario_dice_de_que_beneficio_sale_el_epv():
    assert "si su beneficio operativo después de impuestos se mantuviera para siempre" in mv.glosario()
    assert "sus beneficios actuales" not in mv.glosario()


def test_el_glosario_dice_que_el_margen_no_es_el_de_graham():
    assert "(valor base − precio) / precio" in mv.glosario()
    assert "No es el de Graham, (valor − precio) / valor" in mv.glosario()


def test_el_glosario_explica_la_regla_del_veredicto():
    assert "dos votos en el mismo sentido" in mv.glosario()
    assert "Una «cara» con dos «neutra» es «en rango»" in mv.glosario()
    assert f"menos de {criterio.MIN_VOTOS} votos aplicables" in mv.glosario()
    assert mv.glosario().endswith("votos aplicables, sin datos suficientes.")


def test_el_glosario_cuenta_el_ajuste_de_blume_con_el_criterio():
    pasos = f"{(1 - criterio.BLUME[0]) * 100:.0f}% del camino hacia 1.0"
    assert pasos in mv.glosario()
    assert "R² bajo significa una beta ruidosa" in mv.glosario()


def test_el_glosario_nombra_a_todas_las_entidades_financieras():
    glosario = mv.glosario()
    assert "(bancos, aseguradoras y mercados de capitales)" in glosario
    assert "bancos y aseguradoras," not in glosario


def test_el_glosario_explica_de_donde_sale_el_rango():
    glosario = mv.glosario()
    assert "**Escenarios** (pesimista, base y optimista)" in glosario
    assert "sube 1 punto el coste de capital" in glosario
    assert "lo baja 1 punto" in glosario
    assert "es lo que hace tan ancho el rango" in glosario


def test_el_glosario_nombra_la_tasa_libre_y_la_prima():
    assert "Tesoro de EE. UU. a 10 años (^TNX)" in mv.glosario()
    assert "La prima de riesgo, que publica Damodaran" in mv.glosario()


def test_el_glosario_es_markdown_sin_etiquetas():
    entradas = [linea for linea in mv.glosario().split("\n") if linea]
    assert len(entradas) == 16
    assert all(linea.startswith("- **") for linea in entradas)
    assert "<" not in mv.glosario() and ">" not in mv.glosario()


def test_el_resumen_no_repite_el_glosario():
    # El glosario se pinta una vez por pantalla; si cada resumen lo llevara, serían quince.
    glosario = re.sub(r"\*\*", "", mv.glosario())
    for valoracion in (_fija(), _fija_residual(), fallida("sin_precio")):
        salida = _texto(mv.resumen(valoracion))
        for entrada in glosario.split("\n"):
            definicion = entrada.split(": ", 1)[1]
            assert definicion[:50] not in salida


# --- Los textos siguen al criterio ----------------------------------------------------------------
# Si un listón del criterio se enmienda, la pantalla tiene que cambiar con él:
# cada test cambia el valor en el módulo y mira que el texto lo siga.


def test_los_anos_proyectados_siguen_al_criterio(monkeypatch):
    monkeypatch.setattr(mv, "ANOS_ALTO_CRECIMIENTO", 7)
    detalle = _detalle(_fija(), "flujos")
    assert "durante 7 años" in detalle
    assert "durante 5 años" not in detalle


def test_los_limites_del_inverso_de_crecimiento_siguen_al_criterio(monkeypatch):
    monkeypatch.setattr(mv, "INVERSO_LIMITES", (-0.4, 0.9))
    base = {"magnitud": "crecimiento", "valor": 0.5, "referencia": 0.4, "margen": 0.2}
    arriba = _fija(implicito={**base, "fuera_de_limites": "arriba"})
    abajo = _fija(implicito={**base, "fuera_de_limites": "abajo"})
    assert _detalle(arriba, "flujos") == "el precio da por hecho un crecimiento de más del 90.0% al año"
    assert _detalle(abajo, "flujos") == "el precio es tan bajo que ni una caída del 40.0% al año lo explicaría"


def test_los_limites_del_inverso_de_roe_siguen_al_criterio(monkeypatch):
    monkeypatch.setattr(mv, "INVERSO_ROE_LIMITES", (-0.1, 0.7))
    base = {"magnitud": "roe", "valor": 0.5, "referencia": 0.15, "margen": 0.075}
    arriba = _fija_residual(implicito={**base, "fuera_de_limites": "arriba"})
    abajo = _fija_residual(implicito={**base, "fuera_de_limites": "abajo"})
    assert _detalle(arriba, "flujos") == "el precio exige un ROE de más del 70.0%"
    assert _detalle(abajo, "flujos") == "el precio es tan bajo que ni un ROE del −10.0% lo explicaría"


def test_los_topes_de_la_tasa_efectiva_siguen_al_criterio(monkeypatch):
    monkeypatch.setattr(mv, "TASA_EFECTIVA_TOPES", (0.05, 0.2))
    assert mv.procedencia("t", {"procedencia": {"fuente": "efectiva"}}) == (
        "tasa efectiva de yfinance, acotada entre 5.0% y 20.0%"
    )


@pytest.mark.parametrize("fuente", ["historia_y_consenso", "historia", "consenso"])
def test_los_topes_del_crecimiento_de_referencia_siguen_al_criterio(monkeypatch, fuente):
    monkeypatch.setattr(mv, "CRECIMIENTO_REF_TOPES", (-0.2, 0.5))
    texto = mv.procedencia("g_ref", {"procedencia": {"fuente": fuente, "historico": 0.1, "consenso": 0.1}})
    assert texto.endswith("entre −20.0% y 50.0%")


def test_el_tope_de_la_prima_de_la_deuda_sigue_al_criterio(monkeypatch):
    monkeypatch.setattr(mv, "COSTE_DEUDA_PRIMA_MAXIMA", 0.05)
    texto = mv.procedencia("k_d", {"procedencia": {"fuente": "gasto_entre_deuda"}})
    assert texto.endswith("esa tasa más 5.0 puntos")


def test_el_reparto_por_defecto_sigue_al_criterio(monkeypatch):
    monkeypatch.setattr(mv, "PAYOUT_SIN_DATO", 0.3)
    assert mv.procedencia("payout", {"procedencia": {"fuente": "por_defecto"}}) == "sin dato: se supone el 30.0%"


@pytest.mark.parametrize(
    ("holgura", "esperado"),
    [(0.01, "al menos 1 punto,"), (0.02, "al menos 2 puntos,"), (0.015, "al menos 1.5 puntos,")],
)
def test_la_holgura_de_gordon_sigue_al_criterio(monkeypatch, holgura, esperado):
    monkeypatch.setattr(mv, "HOLGURA_GORDON", holgura)
    assert esperado in mv.etiqueta_motivo("wacc_bajo_crecimiento")


def test_el_motivo_de_la_holgura_llega_a_la_fila_del_voto(monkeypatch):
    monkeypatch.setattr(mv, "HOLGURA_GORDON", 0.02)
    votos = {**_fija()["votos"], "flujos": {"voto": "no_aplica", "motivo": "wacc_bajo_crecimiento"}}
    assert "al menos 2 puntos," in _detalle(_fija(votos=votos), "flujos")


def test_los_votos_minimos_siguen_al_criterio(monkeypatch):
    monkeypatch.setattr(mv, "MIN_VOTOS", 3)
    assert "menos de 3 votos aplicables" in mv.glosario()


def test_el_umbral_de_los_pares_sigue_al_criterio(monkeypatch):
    monkeypatch.setattr(mv, "UMBRAL_PARES", 0.75)
    pares = mv.glosario().split("\n")[1]
    assert "+0.75 o más" in pares
    assert "−0.75 o menos" in pares
    assert "0.5 " not in pares


def test_el_margen_minimo_del_voto_de_flujos_sigue_al_criterio(monkeypatch):
    monkeypatch.setattr(mv, "MARGEN_MINIMO", 0.04)
    assert "nunca menos de 4 puntos" in mv.lectura_margen()
    assert mv.pie(_fija())[0] == mv.lectura_margen()


def test_el_margen_minimo_del_voto_del_roe_sigue_al_criterio(monkeypatch):
    monkeypatch.setattr(mv, "MARGEN_ROE_MINIMO", 0.02)
    assert "nunca menos de 2 puntos" in mv.lectura_margen_roe()
    assert "nunca menos de 2 puntos" in mv.pie(_fija_residual())[0]


def test_el_ajuste_de_blume_sigue_al_criterio(monkeypatch):
    monkeypatch.setattr(mv, "BLUME", (0.5, 0.5))
    assert "un 50% del camino hacia 1.0" in mv.glosario()


@pytest.mark.parametrize(
    ("delta", "salto"), [(0.01, "1 punto"), (0.02, "2 puntos"), (0.005, "0.5 puntos")]
)
def test_el_salto_del_coste_de_capital_de_los_escenarios_sigue_al_criterio(monkeypatch, delta, salto):
    monkeypatch.setattr(mv, "DELTA_WACC_ESCENARIOS", delta)
    glosario = mv.glosario()
    assert f"sube {salto} el coste de capital" in glosario
    assert f"lo baja {salto}." in glosario


# --- La tarjeta --------------------------------------------------------------------------------

FICHA = {
    "puesto": 1,
    "ticker": "AAA",
    "sector_gics": "Information Technology",
    "compuesto": 1.2,
    "pilares": {"calidad": 0.5, "crecimiento": 0.1, "valoracion": -0.2, "solidez": 0.3},
    "cobertura": {
        "kpis_con_dato": 15,
        "pilares_con_dato": 4,
        "kpis_por_pilar": {"calidad": 7, "crecimiento": 3, "valoracion": 4, "solidez": 3},
    },
}


def test_la_tarjeta_lleva_el_distintivo():
    ficha = {**FICHA, "valoracion": {"version": "m1", "veredicto": "infravalorada"}}
    assert "Infravalorada" in medidores.tarjeta_candidato(ficha)


def test_el_distintivo_va_justo_despues_del_chip_del_sector():
    valoracion = {"version": "m1", "veredicto": "sobrevalorada"}
    tarjeta = medidores.tarjeta_candidato({**FICHA, "valoracion": valoracion})
    chip = '<span class="mpp-chip">Information Technology</span>'
    assert chip + mv.distintivo(valoracion) + '<span class="mpp-cab-der">' in tarjeta


@pytest.mark.parametrize(
    "valoracion",
    [{"veredicto": "infravalorada"}, {"version": 1, "veredicto": "infravalorada"}],
    ids=["sin_version", "version_no_texto"],
)
def test_la_tarjeta_exige_lo_mismo_que_el_bloque(valoracion):
    # Editada a mano y sin `version`, la ficha pintaba la píldora mientras el
    # bloque decía «ficha de una versión anterior»: los dos leen con `valoracion_de`.
    assert "mpp-veredicto" not in medidores.tarjeta_candidato({**FICHA, "valoracion": valoracion})


def test_una_tarjeta_vieja_no_lleva_distintivo():
    assert "mpp-veredicto" not in medidores.tarjeta_candidato(FICHA)


@pytest.mark.parametrize("valoracion", [fallida("sin_precio"), "x", {"veredicto": ["mixtas"]}])
def test_una_tarjeta_con_valoracion_sin_veredicto_no_lleva_distintivo(valoracion):
    assert "mpp-veredicto" not in medidores.tarjeta_candidato({**FICHA, "valoracion": valoracion})


# --- Las fuentes nuevas del Analizador ----------------------------------------


def test_la_tasa_libre_del_bono_m_dice_su_serie_su_fecha_y_lo_que_no_resta():
    supuesto = {
        "valor": 0.0925,
        "procedencia": {"fuente": "bono_m_10", "serie": "SF44071", "fecha": "2026-09-24"},
    }
    texto = mv.procedencia("r_f", supuesto)
    assert "Bono M a 10 años" in texto
    assert "SF44071" in texto and "2026-09-24" in texto
    assert "diferencial soberano" in texto


@pytest.mark.parametrize(
    "nombre, programa, esperado",
    [
        ("g_ref", 0.2, "movido por ti; el programa decía 20.0%"),
        ("beta", 0.9, "movido por ti; el programa decía 0.90"),
        ("r_f", None, "puesto por ti"),
    ],
)
def test_un_supuesto_movido_dice_lo_que_decia_el_programa(nombre, programa, esperado):
    supuesto = {"valor": 0.1, "procedencia": {"fuente": "usuario", "programa": programa}}
    assert mv.procedencia(nombre, supuesto) == esperado


def test_lo_recalculado_con_los_supuestos_del_usuario_lo_dice():
    supuesto = {"valor": 0.1, "procedencia": {"fuente": "capm", "recalculado": True}}
    assert mv.procedencia("k_e", supuesto) == (
        "tasa libre más beta por prima (recalculado con tus supuestos)"
    )

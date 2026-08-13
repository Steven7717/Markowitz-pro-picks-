"""Control negativo y referencia positiva del score.

Estándares #2 y #3 del proyecto: ruido con la misma forma que la señal, y algo
que el aparato debe detectar si funciona.
"""

import numpy as np
import pandas as pd

from fundamentals.kpis import TODOS_LOS_KPIS
from ranking.score import (
    aplicar_guardas,
    compuesto,
    marcar_sin_pares,
    puntuaciones_por_pilar,
)

SECTORES = ["Tech", "Financials", "Health", "Energy"]
EMPRESAS_POR_SECTOR = 20


def universo_sintetico(semilla: int) -> tuple[pd.DataFrame, pd.Series]:
    """Medias z aleatorias, con cobertura desigual por sector.

    Financials pierde los cinco KPIs que dependen del beneficio operativo, igual
    que en el panel real: bancos y aseguradoras no lo publican.
    """
    generador = np.random.default_rng(semilla)
    sin_operativo = (
        "margen_bruto",
        "margen_operativo",
        "ev_ebitda",
        "cobertura_intereses",
        "deuda_neta_ebitda",
    )
    filas, indice, sectores = [], [], []
    for sector in SECTORES:
        for numero in range(EMPRESAS_POR_SECTOR):
            fila = dict(zip(TODOS_LOS_KPIS, generador.normal(size=len(TODOS_LOS_KPIS))))
            if sector == "Financials":
                for kpi in sin_operativo:
                    fila[kpi] = np.nan
            filas.append(fila)
            indice.append(f"{sector[:2].upper()}{numero:02d}")
            sectores.append(sector)
    medias = pd.DataFrame(
        filas,
        index=pd.Index(indice, name="ticker"),
        columns=list(TODOS_LOS_KPIS),
    )
    return medias, pd.Series(sectores, index=medias.index)


def puntuar(medias: pd.DataFrame, sectores: pd.Series) -> pd.Series:
    pilares, conteo = puntuaciones_por_pilar(medias)
    historial = pd.DataFrame(
        {"trimestres": 4, "ultimo_trimestre": "2025Q2"}, index=medias.index
    )
    motivos = aplicar_guardas(pilares, conteo, historial, "2025Q2")
    puntos = compuesto(pilares, motivos, sectores)
    marcar_sin_pares(motivos, puntos, sectores)
    return puntos


def test_control_negativo_el_score_no_premia_la_cobertura():
    """Con KPIs puro ruido, el sector de menos cobertura no puede dominar.

    Si un compuesto calculado sobre menos KPIs sale sistemáticamente más
    extremo, las cabeceras del ranking serían empresas por publicar menos
    líneas, no por ser mejores. El resultado sería indistinguible a ojo de uno
    correcto: de ahí que haga falta medirlo.
    """
    apariciones = []
    for semilla in range(40):
        medias, sectores = universo_sintetico(semilla)
        puntos = puntuar(medias, sectores).dropna()
        cabeza = puntos.sort_values(ascending=False).head(15).index
        apariciones.append((sectores.reindex(cabeza) == "Financials").sum())

    proporcion = np.mean(apariciones) / 15
    esperado = 1 / len(SECTORES)
    # La tolerancia sale del ruido medido, no del ojo. Sobre estas 40 semillas
    # el error estándar de la proporción es ~0,009, el caso correcto queda a
    # 0,002 de lo esperado, y desactivar la re-estandarización de compuesto()
    # lo lleva a ~0,073 (Financials pasa del 25% al 33% del top). 0,04 separa
    # los dos casos con margen por ambos lados.
    #
    # Una tolerancia de 0,10 —la que tenía este test al escribirse— dejaba
    # pasar el caso roto: el control existía y no controlaba nada.
    assert abs(proporcion - esperado) < 0.04, (
        f"Financials ocupa {proporcion:.1%} del top con datos aleatorios, "
        f"cuando por tamaño le corresponde {esperado:.0%}"
    )


def test_referencia_positiva_la_empresa_dominante_sale_primera():
    """Si el aparato no detecta esto, no detecta nada.

    No es un test de signos: TE00 gana con calidad, crecimiento y solidez aunque
    valoración lo penalice, así que pasaría igual con los signos rotos. Los
    signos los fijan los tests de test_ranking_score.py.
    """
    medias, sectores = universo_sintetico(semilla=0)
    medias.loc["TE00"] = 5.0

    puntos = puntuar(medias, sectores)

    assert puntos.idxmax() == "TE00"


def test_el_score_es_reproducible():
    medias, sectores = universo_sintetico(semilla=7)
    assert puntuar(medias, sectores).equals(puntuar(medias, sectores))

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from fundamentals.run import build_panel
from ranking.criterio import TAMANO_TOP, TOPE_POR_SECTOR, TRIMESTRES_VENTANA
from ranking.fichas import descriptor, ficha_numerica
from ranking.filings import cargar_riesgos
from ranking.informe import render
from ranking.llm import redactar_con_cache
from ranking.score import (
    aplicar_guardas,
    compuesto,
    marcar_sin_pares,
    media_ventana,
    puntuaciones_por_pilar,
)
from ranking.seleccion import desplazamientos_por_ticker, seleccionar


@dataclass
class Resultado:
    """Everything a run produced, including what it left out and why."""

    tabla: pd.DataFrame
    fichas: list[dict]
    exclusiones: dict[str, int]
    cobertura_panel: object
    corrida: dict


def _contexto(ficha: dict) -> str:
    """Describe the candidate to the model in words, with no digits to echo."""
    lineas = [
        f"Empresa: {ficha['ticker']}, sector {ficha['sector_gics']}.",
        "Frente a sus pares del mismo sector:",
    ]
    for pilar, valor in ficha["pilares"].items():
        if valor is not None:
            lineas.append(f"- {pilar}: {descriptor(valor)}")
    lineas.append("Puntos más fuertes: " + ", ".join(i["kpi"] for i in ficha["destacados"]))
    lineas.append("Puntos más flojos: " + ", ".join(i["kpi"] for i in ficha["flojos"]))
    return "\n".join(lineas)


def _con_narrativa(ficha: dict, cache_dir: Path | None) -> dict:
    """Attach the qualitative half when it can be produced and verified."""
    riesgos = cargar_riesgos(ficha["ticker"])
    if riesgos is None:
        return ficha

    narrativa = redactar_con_cache(_contexto(ficha), riesgos.texto, cache_dir=cache_dir)
    if narrativa is None:
        return ficha

    narrativa["fuente"] = {
        "formulario": riesgos.formulario,
        "fecha": riesgos.fecha,
        "accession": riesgos.accession,
        "seccion": riesgos.seccion,
        "caracteres_enviados": len(riesgos.texto),
        "recortado": riesgos.recortado,
    }
    return {**ficha, "narrativa": narrativa, "generada_por": "sonnet-5"}


def construir_ranking(
    source: str | list[str] = "sp500",
    con_llm: bool = True,
    n: int = TAMANO_TOP,
    tope: int = TOPE_POR_SECTOR,
    cache_dir: Path | None = None,
) -> Resultado:
    """Panel in, ranked candidates out.

    A company that fails at any stage is recorded and skipped, never aborting
    the run — the same policy fundamentals already applies to downloads.
    """
    panel, metadatos, cobertura = build_panel(source, con_zscore=True)
    sectores = metadatos["sector_gics"]

    z, valores, historial = media_ventana(panel, n=TRIMESTRES_VENTANA)
    pilares, conteo = puntuaciones_por_pilar(z)

    trimestre_max = str(panel["trimestre"].max())
    motivos = aplicar_guardas(pilares, conteo, historial, trimestre_max)
    puntos = compuesto(pilares, motivos, sectores)
    # Tres argumentos, no dos: marcar_sin_pares necesita `sectores` para
    # distinguir sector_desconocido / sector_sin_pares / sin_dispersion_sectorial
    # entre sí -- ver ranking/score.py:marcar_sin_pares.
    motivos = marcar_sin_pares(motivos, puntos, sectores)

    elegidas, desplazadas = seleccionar(puntos, sectores, tope=tope, n=n)
    mapa = desplazamientos_por_ticker(desplazadas)

    fichas = []
    for fila in elegidas.itertuples(index=False):
        ficha = ficha_numerica(
            ticker=fila.ticker,
            sector=fila.sector,
            puesto=fila.puesto,
            compuesto=fila.compuesto,
            pilares=pilares.loc[fila.ticker],
            conteo=conteo.loc[fila.ticker],
            z=z.loc[fila.ticker],
            valores=valores.loc[fila.ticker],
            desplazo_a=mapa.get(fila.ticker, []),
        )
        if con_llm:
            ficha = _con_narrativa(ficha, cache_dir)
        fichas.append(ficha)

    tabla = pilares.join(puntos.rename("compuesto")).join(motivos.rename("exclusion"))
    tabla["sector_gics"] = sectores.reindex(tabla.index)
    tabla["kpis_con_dato"] = conteo.sum(axis=1)

    supervivientes = tabla.loc[motivos.isna()]
    exclusiones = motivos.dropna().value_counts().to_dict()

    return Resultado(
        tabla=supervivientes,
        fichas=fichas,
        exclusiones=exclusiones,
        cobertura_panel=cobertura,
        # Los metadatos se construyen aqui y no en guardar() porque aqui estan
        # en alcance los parametros de la corrida. guardar() se queda tonto: no
        # calcula nada, solo escribe lo que ya se decidio.
        corrida={
            "fecha": date.today().isoformat(),
            "universo": source if isinstance(source, str) else f"{len(source)} tickers",
            "n_panel": int(len(supervivientes) + sum(exclusiones.values())),
            "n_supervivientes": int(len(supervivientes)),
            "exclusiones": {motivo: int(n) for motivo, n in exclusiones.items()},
            "tope_por_sector": int(tope),
            "tamano_top": int(n),
            "con_llm": bool(con_llm),
        },
    )


def guardar(resultado: Resultado, destino: Path) -> None:
    """Write the four outputs. fichas.json is the contract with sub-project C.

    allow_nan=False on the json.dumps call is that contract, fixed in Task 8
    (see tests/test_ranking_fichas.py:test_la_ficha_es_serializable_a_json_estricto):
    json.dumps accepts a NaN by default and writes it as the bare literal
    `NaN`, which is not valid JSON and a strict parser rejects. Without this
    flag here, the writer would silently drop the guarantee the fichas
    themselves are built to uphold.
    """
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)

    resultado.tabla.to_csv(destino / "ranking.csv")
    (destino / "fichas.json").write_text(
        json.dumps(resultado.fichas, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    (destino / "informe.md").write_text(
        render(resultado.fichas, resultado.exclusiones), encoding="utf-8"
    )
    (destino / "corrida.json").write_text(
        json.dumps(resultado.corrida, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )

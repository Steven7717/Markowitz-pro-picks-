import json
import logging
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
from valoracion.motor import valorar
from valoracion.plano import fallida


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


def _valoracion(ticker: str, pilar_valoracion: "float | None") -> dict:
    """La valoración de una ficha, o por qué no la tiene.

    Una empresa que falla al valorarse se anota y la corrida sigue: es la
    política de la descarga de fundamentales. Y un defecto del propio motor
    tampoco tumba el ranking, pero no se calla: la ficha queda con
    `error_interno` y el traceback va al log de la consola. La ficha sólo dice
    que hubo un error, no cuál; la causa está en el log.
    """
    try:
        return valorar(ticker, pilar_valoracion)
    except Exception:
        logging.getLogger(__name__).exception(
            "La valoración de %s falló por un defecto del motor, no por falta de datos", ticker
        )
        return fallida("error_interno")


def construir_ranking(
    source: str | list[str] = "sp500",
    con_llm: bool = True,
    n: int = TAMANO_TOP,
    tope: int = TOPE_POR_SECTOR,
    cache_dir: Path | None = None,
    con_valoracion: bool = True,
) -> Resultado:
    """Panel in, ranked candidates out.

    A company that fails at any stage is recorded and skipped — the same policy
    fundamentals applies to downloads. The one thing that does abort is
    `CorridaAbortada` from `fundamentals.fetch`, which is not a company failing
    but the source being gone; it is left to propagate on purpose, so the caller
    can say why instead of showing an empty ranking.

    `con_valoracion` adjunta a cada ficha su valoración (`valoracion/`). No toca
    el score ni la selección: se calcula sobre las ya elegidas y sólo se
    enseña. Si la red o la tasa libre faltan, deja de preguntar: un
    `sin_tasa_libre` corta en el acto y un `sin_red` al segundo seguido, y las
    fichas que quedan heredan ese motivo sin llamar al motor.
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

    # Sin red o sin tasa libre, las quince fallarían igual, y con una red que no
    # contesta cada intento tarda unos 21 s (la cifra está en el docstring de
    # `valorar`): cinco minutos para nada. Se deja de preguntar, como hace el cortacircuitos
    # de `fundamentals/fetch.py`. La tasa libre es la misma para todas, así que
    # basta un fallo. `sin_red` exige dos seguidos: un símbolo que Yahoo no
    # conoce también da `sin_red`, y uno solo no puede apagar a los demás.
    corte: "str | None" = None
    sin_red_seguidos = 0

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
        if con_valoracion:
            # La valoración no toca el score: se calcula sobre las ya elegidas
            # y sólo se enseña. Ver el spec de M, «Integración».
            if corte is None:
                valoracion = _valoracion(fila.ticker, ficha["pilares"].get("valoracion"))
                motivo = valoracion.get("motivo")
                sin_red_seguidos = sin_red_seguidos + 1 if motivo == "sin_red" else 0
                if motivo == "sin_tasa_libre" or sin_red_seguidos >= 2:
                    corte = motivo
            else:
                valoracion = fallida(corte)
            ficha = {**ficha, "valoracion": valoracion}
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

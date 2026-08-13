import pandas as pd

from ranking.criterio import TAMANO_TOP, TOPE_POR_SECTOR


def seleccionar(
    compuestos: pd.Series,
    sectores: pd.Series,
    tope: int = TOPE_POR_SECTOR,
    n: int = TAMANO_TOP,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Walk the global order, admitting a company unless its sector is full.

    Returns (elegidas, desplazadas). The second frame is not a debugging aid: a
    sector cap that silently reshapes the list would be invisible in the output,
    so it records every company that would have ranked in the unrestricted top
    n but was kept out by its sector's cap, together with the tickers that
    blocked it. A company outside the unrestricted top n was never going to be
    selected regardless of the cap, so it is not "displaced" by it.

    Ties break on ticker, so two runs over the same panel return the same list.
    Without it the system would stop being auditable for a silly reason.
    """
    tabla = pd.DataFrame(
        {
            "ticker": list(compuestos.index),
            "compuesto": compuestos.to_numpy(),
            "sector": sectores.reindex(compuestos.index).to_numpy(),
        }
    ).dropna(subset=["compuesto"])

    tabla = tabla.sort_values(
        ["compuesto", "ticker"], ascending=[False, True], kind="mergesort"
    )
    tabla["puesto_global"] = range(1, len(tabla) + 1)

    elegidas: list[dict] = []
    desplazadas: list[dict] = []
    ocupacion: dict[str, list[str]] = {}

    for fila in tabla.itertuples(index=False):
        if len(elegidas) >= n:
            break
        ocupadas = ocupacion.setdefault(fila.sector, [])
        if len(ocupadas) >= tope:
            # Sólo cuenta como desplazada si habría entrado en el top sin el
            # tope. Sin esta condición, un sector copado registraría a todos
            # los que bloqueó alguna vez, incluidos los que nunca iban a entrar.
            if fila.puesto_global <= n:
                desplazadas.append(
                    {
                        "ticker": fila.ticker,
                        "sector": fila.sector,
                        "puesto_global": fila.puesto_global,
                        "bloqueada_por": tuple(ocupadas),
                    }
                )
            continue
        ocupadas.append(fila.ticker)
        elegidas.append(
            {
                "ticker": fila.ticker,
                "sector": fila.sector,
                "compuesto": fila.compuesto,
                "puesto_global": fila.puesto_global,
                "puesto": len(elegidas) + 1,
            }
        )

    columnas_elegidas = ["ticker", "sector", "compuesto", "puesto_global", "puesto"]
    columnas_desplazadas = ["ticker", "sector", "puesto_global", "bloqueada_por"]
    return (
        pd.DataFrame(elegidas, columns=columnas_elegidas),
        pd.DataFrame(desplazadas, columns=columnas_desplazadas),
    )


def desplazamientos_por_ticker(desplazadas: pd.DataFrame) -> dict[str, list[str]]:
    """Map each admitted ticker to the tickers it kept out through the cap."""
    mapa: dict[str, list[str]] = {}
    for fila in desplazadas.itertuples(index=False):
        for bloqueadora in fila.bloqueada_por:
            mapa.setdefault(bloqueadora, []).append(fila.ticker)
    return mapa

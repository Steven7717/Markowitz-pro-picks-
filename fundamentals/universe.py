from research.universe import normalise_ticker, sp500_members

_FUENTES = {"sp500": sp500_members}


def resolve(source: str | list[str]) -> list[str]:
    """Convierte un nombre de universo o una lista suelta en tickers normalizados.

    Accepting an arbitrary list is what lets sub-project B feed candidates that
    are not index members without this module needing to know where they came from.
    """
    if isinstance(source, str):
        if source not in _FUENTES:
            raise ValueError(
                f"Universo desconocido: {source!r}. Disponibles: {sorted(_FUENTES)}"
            )
        tickers = _FUENTES[source]()
    else:
        tickers = list(source)

    if not tickers:
        raise ValueError("El universo está vacío")

    vistos: dict[str, None] = {}
    for t in tickers:
        vistos.setdefault(normalise_ticker(t), None)
    return list(vistos)

"""Reparto de veredictos sobre el S&P 500, con el criterio ya congelado.

Una medida, no un ajuste: si el reparto sale raro, los listones no se mueven
desde aquí, se escribe una enmienda fechada en el spec del sub-proyecto M.

Uso, desde programa/:
    EDGAR_IDENTITY="tu@correo.com" uv run python scripts/medir_valoracion.py

Escribe salidas/medida_valoracion.csv e imprime las tablas que van al anexo.
Tarda: unas cuatro descargas de yfinance por empresa, con caché de un día.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from fundamentals.fetch import set_sec_identity  # noqa: E402
from ranking.run import construir_ranking  # noqa: E402
from valoracion.motor import valorar  # noqa: E402


def main() -> None:
    set_sec_identity()
    resultado = construir_ranking(con_llm=False, con_valoracion=False)
    filas = []
    for ticker, fila in resultado.tabla.iterrows():
        plano = valorar(ticker, fila["valoracion"])
        votos = plano.get("votos", {})
        filas.append(
            {
                "ticker": ticker,
                "sector": fila["sector_gics"],
                "veredicto": plano.get("veredicto", "no_calculada"),
                "motivo": plano.get("motivo"),
                "metodo": plano.get("metodo"),
                **{f"voto_{k}": v["voto"] for k, v in votos.items()},
                **{f"motivo_{k}": v["motivo"] for k, v in votos.items()},
            }
        )
        print(f"{len(filas):>3} {ticker:<6} {filas[-1]['veredicto']}", file=sys.stderr)
    tabla = pd.DataFrame(filas)
    Path("salidas").mkdir(exist_ok=True)
    tabla.to_csv("salidas/medida_valoracion.csv", index=False)

    print("\n## Veredictos\n")
    print(tabla["veredicto"].value_counts().to_markdown())
    print("\n## Veredictos por sector\n")
    print(pd.crosstab(tabla["sector"], tabla["veredicto"]).to_markdown())
    for voto in ("flujos", "sin_crecimiento", "pares"):
        print(f"\n## Voto {voto}\n")
        print(tabla[f"voto_{voto}"].value_counts(dropna=False).to_markdown())
    print("\n## Motivos de no aplica\n")
    print(tabla.filter(like="motivo_").stack().value_counts().to_markdown())
    print("\n## Valoraciones que no se calcularon\n")
    print(tabla["motivo"].value_counts().to_markdown())


if __name__ == "__main__":
    main()

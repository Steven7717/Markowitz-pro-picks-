"""El Analizador sobre tickers reales, sin pantalla: qué es cada uno y cómo sale.

Uso, desde programa/:
    uv run python scripts/sondear_analizador.py MU WALMEX.MX TSM JPM SPY BRK-B RY.TO

Lee las credenciales guardadas en Perfil (EDGAR, Banxico), como la app. Compara
contra `salidas/panel.parquet` si existe; si no, construye el panel en memoria
con la misma corrida que «Generar gratis» (unos dos minutos con la caché
llena) y no escribe nada en `salidas/`: las fichas de los candidatos son del
usuario.

La beta va con su r²: una casi nula con r² ≈ 0 puede ser real (SHEL.L). El
precio y el valor base van en la moneda del precio, que es como se leen en la
pantalla; `valorar` los da en la de la valoración.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import credenciales  # noqa: E402
from analizador.analisis import analizar  # noqa: E402
from analizador.divisas import adr_dudosa  # noqa: E402
from analizador.referencia import cargar_panel  # noqa: E402
from analizador.resolver import separar  # noqa: E402
from fundamentals.sectors import load_sectors  # noqa: E402


def _panel():
    panel, fecha = cargar_panel()
    if panel is not None:
        return panel, f"salidas/panel.parquet del {fecha}"
    from ranking.run import construir_ranking

    resultado = construir_ranking(con_llm=False, con_valoracion=False)
    return resultado.panel, "construido en memoria, sin escribir nada"


def _numero(valor) -> str:
    return "-" if valor is None else f"{valor:.2f}"


def _beta(e) -> str:
    if e is None:
        return "beta=-"
    if e.beta is None:
        return f"beta=- ({e.motivos.get('beta', '-')})"
    return f"beta={e.beta.bruta:.3f} r2={e.beta.r2:.3f}"


def _precio_y_base(e, v) -> str:
    """En la moneda del precio: `valorar` da los dos en la de la valoración."""
    if e is None:
        return "precio=-  base=-"
    tipo = e.divisa.tipo_precio
    base = (v.get("valor") or {}).get("base")
    return (
        f"precio={_numero(e.perfil.precio / tipo)} {e.divisa.moneda_precio}  "
        f"base={_numero(None if base is None else base / tipo)}"
    )


def _adr(e) -> str:
    # Sin cociente no se comprobó nada (una `sec` nunca lo tiene): «ok» mentiría.
    if e is None or e.cociente_adr is None:
        return "adr=-"
    return f"adr={'DUDOSA' if adr_dudosa(e.cociente_adr) else 'ok'}"


def _fila(ticker, a, segundos):
    v = a.valoracion or {}
    e = a.entradas
    ref = a.referencia
    puesto = "-" if ref is None or ref.puesto is None else f"{ref.puesto}/{ref.supervivientes}"
    # Un ETF o un ticker sin clase no tienen referencia ni motivo: no es «ok».
    estado_ref = a.motivo_referencia or (ref.exclusion if ref else None) or ("ok" if ref else "-")
    r_f = v.get("supuestos", {}).get("r_f", {}).get("procedencia", {}).get("fuente", "-")
    return "  ".join(
        [
            f"{ticker:<10}",
            f"clase={a.clase or '-'}",
            f"motivo={a.motivo or '-'}",
            f"sector={a.sector or '-'} ({a.fuente_sector or '-'})",
            f"puesto={puesto}",
            f"ref={estado_ref}",
            f"moneda={e.divisa.moneda_valoracion if e else '-'}",
            f"r_f={r_f}",
            _beta(e),
            f"metodo={v.get('metodo', '-')}",
            _precio_y_base(e, v),
            f"veredicto={v.get('veredicto') or v.get('motivo') or '-'}",
            _adr(e),
            f"{segundos:.1f}s",
        ]
    )


def main(argv: "list[str]") -> None:
    credenciales.aplicar(credenciales.cargar())
    tickers, invalidos = separar(" ".join(argv))
    if invalidos:
        print("Sin forma de ticker:", ", ".join(invalidos))
    print("Tickers:", " ".join(tickers))
    panel, origen = _panel()
    print(f"Panel de referencia: {origen}\n")
    tabla = load_sectors()
    for ticker in tickers:
        inicio = time.perf_counter()
        analisis = analizar(ticker, panel, tabla)
        print(_fila(ticker, analisis, time.perf_counter() - inicio), flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])

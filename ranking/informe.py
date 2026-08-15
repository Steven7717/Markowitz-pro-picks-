from datetime import date

from fundamentals.kpis import TODOS_LOS_KPIS

SIN_VERIFICAR = " **[cita sin verificar]**"
SIN_PROCEDENCIA = "_Procedencia no disponible: la cita no se puede localizar._"


def _pilares(ficha: dict) -> str:
    partes = [
        f"{pilar} {valor:+.2f}" if valor is not None else f"{pilar} n/d"
        for pilar, valor in ficha["pilares"].items()
    ]
    return " · ".join(partes)


def _kpis(items: list[dict]) -> str:
    return ", ".join(f"{item['kpi']} ({item['z']:+.2f})" for item in items) or "—"


def _en_una_linea(texto: str) -> str:
    """Collapse whitespace so a quote stays inside its blockquote.

    The raw Item 1A carries line breaks and tabs, and the citation is stored
    exactly as the model returned it — verificar_cita normalises only for
    comparison. Rendered as-is, everything after the first newline falls out
    of the "> " block and stops reading as a quote at all.
    """
    return " ".join(texto.split())


def _procedencia(narrativa: dict) -> str:
    """Where the quotes came from, or a visible admission that nobody knows.

    redactar() returns only {tesis, riesgos}; whoever orchestrates the run has
    to attach `fuente` from the Riesgos that filings.py downloaded. If that
    does not happen, every quote in this section becomes unlocatable — which
    is the entire promise of this sub-project — so the report says so, in the
    body, for the same reason an unverified quote is marked there rather than
    footnoted. Raising instead would abort a whole run over one ficha.
    """
    fuente = narrativa.get("fuente")
    if not fuente:
        return SIN_PROCEDENCIA
    recorte = " (recortado)" if fuente["recortado"] else ""
    return (
        f"_Fuente: {fuente['formulario']} de {fuente['fecha']}, "
        f"{fuente['seccion']}, accession {fuente['accession']}{recorte}._"
    )


def _narrativa(ficha: dict) -> list[str]:
    narrativa = ficha["narrativa"]
    if narrativa is None:
        return ["", "_Ficha de plantilla: sin narrativa generada._"]

    lineas = ["", narrativa["tesis"], "", "**Riesgos declarados por la empresa**", ""]
    for riesgo in narrativa["riesgos"]:
        marca = "" if riesgo["verificada"] else SIN_VERIFICAR
        lineas.append(f"- {riesgo['afirmacion']}{marca}")
        lineas.append(f'  > "{_en_una_linea(riesgo["cita"])}"')

    return lineas + ["", _procedencia(narrativa)]


def render(fichas: list[dict], exclusiones: dict[str, int]) -> str:
    """Human-readable report.

    Unverified quotes are marked in the body rather than footnoted: a warning
    nobody sees is the same as no warning, and the whole point of verifying was
    that the human gate can trust what it reads.
    """
    lineas = [
        "# Candidatos del sub-proyecto B",
        "",
        f"**Fecha:** {date.today().isoformat()} · **Candidatos:** {len(fichas)}",
        "",
        "> El orden lo decide un score determinista sobre z-scores sectoriales.",
        "> El score **no está validado empíricamente**: es un criterio de",
        "> selección transparente, no una previsión de rentabilidad.",
        "",
    ]

    for ficha in fichas:
        lineas += [
            f"## {ficha['puesto']}. {ficha['ticker']} — {ficha['sector_gics']}",
            "",
            f"Compuesto {ficha['compuesto']:+.2f} · {_pilares(ficha)}",
            "",
            f"- Fuerte en: {_kpis(ficha['destacados'])}",
            f"- Flojo en: {_kpis(ficha['flojos'])}",
            f"- Cobertura: {ficha['cobertura']['kpis_con_dato']} de "
            f"{len(TODOS_LOS_KPIS)} KPIs",
        ]
        if ficha["desplazo_a"]:
            lineas.append(
                f"- Dejó fuera por el tope sectorial: {', '.join(ficha['desplazo_a'])}"
            )
        lineas += _narrativa(ficha)
        lineas.append("")

    lineas += ["---", "", "## Empresas excluidas por las guardas", ""]
    if not exclusiones:
        # Nunca ha pasado y probablemente no pase: las guardas excluyen a
        # alguien en cualquier universo real. Una sección vacía se leería como
        # que no se comprobó, que es lo contrario de lo que ocurrió.
        lineas.append("- Ninguna: todas las empresas del universo pasaron las guardas.")
    for motivo, cuantas in sorted(exclusiones.items(), key=lambda par: -par[1]):
        lineas.append(f"- `{motivo}`: {cuantas}")

    return "\n".join(lineas) + "\n"

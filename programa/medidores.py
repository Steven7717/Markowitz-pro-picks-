"""De un z-score a algo que se lee de un vistazo.

Vive aquí y no dentro de la página por la misma razón que `aprobacion/`: lo que
decide si un pilar sale bueno, regular o malo es una regla, y las reglas se
prueban sin arrancar Streamlit. La página sólo pega el HTML que sale de aquí.

Nada de este módulo toca el ranking. Es presentación de números que ya estaban
calculados: `ranking/criterio.py` sigue siendo el único sitio donde vive el
criterio, y este fichero se limita a leer de allí los signos y los pilares.
"""

import html
from dataclasses import dataclass

import tema
from fundamentals.kpis import TODOS_LOS_KPIS
from ranking.criterio import MIN_KPIS_CON_DATO, PILARES, SIGNOS

# Los mismos cortes que `ranking/fichas.py:descriptor`, que es el vocabulario
# que ya viaja al modelo dentro del prompt. Si los dos juegos divergen, el
# revisor puede leer "por encima de sus pares" en la narrativa junto a una barra
# ámbar en el medidor, sin forma de saber cuál de los dos miente.
# tests/test_medidores.py los contrasta corte a corte.
MUY_ALTO = 1.5
ALTO = 0.5
BAJO = -0.5
MUY_BAJO = -1.5

# La barra se corta en ±3 y el número real se sigue mostrando al lado. Sin tope
# no hay barra que sirva: los z de este motor no están acotados en ninguna parte
# y el |z| máximo de una corrida real es 8,62, así que dibujar hasta el extremo
# dejaría a la inmensa mayoría de los pilares apretados contra el centro e
# indistinguibles entre sí. El desbordamiento se marca, no se esconde.
ESCALA = 3.0

# La paleta la pone tema.py: los medidores, los graficos y el resto de la
# interfaz tienen que usar el mismo verde, o "bueno" significa un color en la
# ficha y otro distinto tres pantallas mas alla.
_VERDE = tema.VERDE
_AMBAR = tema.AMBAR
_ROJO = tema.ROJO
_GRIS = tema.TEXTO_SUAVE
_ACENTO = tema.ACENTO


@dataclass(frozen=True)
class Nivel:
    """Cómo se nombra y cómo se pinta un tramo de la escala."""

    clave: str
    veredicto: str
    detalle: str
    color: str


MUY_BUENO = Nivel("muy_bueno", "Muy bueno", "muy por encima de sus pares", _VERDE)
BUENO = Nivel("bueno", "Bueno", "por encima de sus pares", _VERDE)
REGULAR = Nivel("regular", "Regular", "en línea con sus pares", _AMBAR)
MALO = Nivel("malo", "Malo", "por debajo de sus pares", _ROJO)
MUY_MALO = Nivel("muy_malo", "Muy malo", "muy por debajo de sus pares", _ROJO)
SIN_DATOS = Nivel("sin_datos", "Sin datos", "no se pudo calcular", _GRIS)


def nivel(z: float | None) -> Nivel:
    """Which band a score falls in. SIN_DATOS — never a number — when missing.

    Un pilar sin datos no es un pilar mediocre. Devolver REGULAR aquí, o pintar
    la barra en el centro, convertiría "no se pudo medir" en "salió del montón",
    que es justo la confusión que este módulo existe para no cometer.
    """
    if z is None or z != z:  # NaN no es igual a sí mismo
        return SIN_DATOS
    if z >= MUY_ALTO:
        return MUY_BUENO
    if z >= ALTO:
        return BUENO
    if z > BAJO:
        return REGULAR
    if z > MUY_BAJO:
        return MALO
    return MUY_MALO


def _corte(valor: float) -> str:
    return f"{valor:+.1f}".replace(".", ",")


# La leyenda de la pagina se dibuja desde aqui, no se escribe a mano al lado.
# Una tabla copiada se queda mintiendo en cuanto alguien mueve un corte, y es
# justo la frase que le dice al revisor que significa todo lo que esta viendo:
# equivocada, es peor que no tenerla.
TRAMOS: tuple[tuple[str, Nivel], ...] = (
    (f"z ≥ {_corte(MUY_ALTO)}", MUY_BUENO),
    (f"{_corte(ALTO)} ≤ z < {_corte(MUY_ALTO)}", BUENO),
    (f"{_corte(BAJO)} < z < {_corte(ALTO)}", REGULAR),
    (f"{_corte(MUY_BAJO)} < z ≤ {_corte(BAJO)}", MALO),
    (f"z ≤ {_corte(MUY_BAJO)}", MUY_MALO),
)


def tabla_de_tramos() -> str:
    """The legend, as a Markdown table built from the thresholds themselves."""
    filas = "\n".join(
        f"| {tramo} | **{marca.veredicto}** | {marca.detalle} |"
        for tramo, marca in TRAMOS
    )
    return "| Tramo | Veredicto | Qué significa |\n|---|---|---|\n" + filas


def posicion(z: float) -> float:
    """Where a score sits on a track running from -ESCALA to +ESCALA, in %."""
    acotado = max(-ESCALA, min(ESCALA, z))
    return (acotado + ESCALA) / (2 * ESCALA) * 100


def fuera_de_escala(z: float | None) -> bool:
    """Whether the bar had to be clipped to fit the track."""
    return z is not None and z == z and abs(z) > ESCALA


def orientar(kpi: str, z: float) -> float:
    """Turn a raw z-score into a "how good is this" score.

    El z de `per` llega crudo en la ficha: +2 significa caro, no bueno. Los
    pilares ya vienen con el signo aplicado desde `ranking/score.py`; los KPIs
    sueltos de `destacados` y `flojos`, no. Sin este paso la página pinta de
    verde el múltiplo más caro del panel y lo lista debajo de "Flojo en" — que
    es exactamente lo que hacía mostrando el número a secas.
    """
    return z * SIGNOS[kpi]


def sentido(kpi: str) -> str:
    """The half-sentence that stops a high multiple from reading as good news."""
    return "más es mejor" if SIGNOS[kpi] > 0 else "menos es mejor"


# ── Nombres y unidades ────────────────────────────────────────────────────────

PORCENTAJE = "porcentaje"
MULTIPLO = "multiplo"


@dataclass(frozen=True)
class Presentacion:
    etiqueta: str
    unidad: str


# El identificador interno no es un nombre: "fcf_sobre_beneficio" en pantalla
# obliga al revisor a traducir del código al castellano justo en el momento en
# que está decidiendo. Los diecisiete van declarados uno a uno, y un test
# comprueba que no falta ninguno: un KPI nuevo sin entrada aquí reventaría en
# mitad de la página, con la lista a medio pintar.
KPIS: dict[str, Presentacion] = {
    "margen_bruto": Presentacion("Margen bruto", PORCENTAJE),
    "margen_operativo": Presentacion("Margen operativo", PORCENTAJE),
    "margen_neto": Presentacion("Margen neto", PORCENTAJE),
    "roe": Presentacion("ROE", PORCENTAJE),
    "roic": Presentacion("ROIC", PORCENTAJE),
    "deuda_neta_ebitda": Presentacion("Deuda neta / EBITDA", MULTIPLO),
    "cobertura_intereses": Presentacion("Cobertura de intereses", MULTIPLO),
    "razon_corriente": Presentacion("Razón corriente", MULTIPLO),
    "margen_fcf": Presentacion("Margen de flujo libre", PORCENTAJE),
    "fcf_sobre_beneficio": Presentacion("Flujo libre / beneficio", MULTIPLO),
    "crecimiento_ingresos": Presentacion("Crecimiento de ingresos", PORCENTAJE),
    "crecimiento_bpa": Presentacion("Crecimiento del BPA", PORCENTAJE),
    "crecimiento_fcf": Presentacion("Crecimiento del flujo libre", PORCENTAJE),
    "per": Presentacion("PER", MULTIPLO),
    "ev_ebitda": Presentacion("EV / EBITDA", MULTIPLO),
    "precio_fcf": Presentacion("Precio / flujo libre", MULTIPLO),
    "precio_valor_libro": Presentacion("Precio / valor en libros", MULTIPLO),
}

PILARES_ETIQUETAS: dict[str, str] = {
    "calidad": "Calidad",
    "crecimiento": "Crecimiento",
    "valoracion": "Valoración",
    "solidez": "Solidez",
}


def formatear(kpi: str, valor: float | None) -> str:
    """The raw figure, with its unit. "n/d" when there is none.

    El valor crudo no estaba en la página y el z solo no lo sustituye: un z de
    +2 dice que la empresa destaca entre sus pares, no si su margen es del 4% o
    del 40%. Para decidir hacen falta los dos.
    """
    if valor is None or valor != valor:
        return "n/d"
    if KPIS[kpi].unidad == PORCENTAJE:
        return f"{valor * 100:,.1f}%"
    return f"{valor:,.1f}×"


# ── HTML ──────────────────────────────────────────────────────────────────────

_CORTE_BAJO = posicion(BAJO)
_CORTE_ALTO = posicion(ALTO)

CSS = f"""<style>
.mpp-tarjeta {{
  background:{tema.TARJETA}; border:1px solid {tema.BORDE}; border-left:3px solid {_ACENTO};
  border-radius:10px; padding:.65rem .85rem .55rem; margin-bottom:.35rem;
}}
.mpp-cab {{
  display:flex; align-items:baseline; flex-wrap:wrap; gap:.55rem; margin-bottom:.5rem;
}}
.mpp-puesto {{
  background:{_ACENTO}; color:#0f1117; font-weight:700; font-size:.72rem;
  border-radius:5px; padding:.05rem .38rem;
}}
.mpp-ticker {{ font-size:1.05rem; font-weight:700; color:{tema.TEXTO}; }}
.mpp-chip {{
  border:1px solid {tema.BORDE}; border-radius:999px; padding:.03rem .5rem;
  font-size:.72rem; color:{tema.TEXTO_SUAVE};
}}
.mpp-cab-der {{
  margin-left:auto; font-size:.75rem; color:{tema.TEXTO_SUAVE}; font-variant-numeric:tabular-nums;
}}
.mpp-fila {{
  display:flex; align-items:center; gap:.55rem; margin:.2rem 0;
  font-size:.8rem; line-height:1.35;
}}
.mpp-nombre {{ flex:0 0 12.5rem; color:{tema.TEXTO}; line-height:1.25; }}
.mpp-nota {{ color:{tema.TEXTO_TENUE}; font-size:.7rem; font-weight:400; }}
/* La cobertura no es un quinto pilar: sin este respiro se lee como uno mas. */
.mpp-fila.mpp-aparte {{ margin-top:.55rem; padding-top:.5rem; border-top:1px solid {tema.BORDE_SUAVE}; }}
.mpp-valor {{
  flex:0 0 5rem; text-align:right; color:{tema.TEXTO_SUAVE}; font-variant-numeric:tabular-nums;
}}
.mpp-pista {{
  /* display:block es obligatorio, no cosmetica: dentro de .mpp-fila la pista es
     un item flex y toma altura sola, pero en la tira compacta cuelga de un
     bloque normal, y un <span> inline ignora height -- el carril se derrumba a
     la altura de una linea de texto y no se ve ni la barra ni las zonas. */
  display:block; position:relative; flex:1 1 auto; min-width:5rem; height:.6rem;
  background:{tema.FONDO}; border:1px solid {tema.BORDE}; border-radius:999px; overflow:hidden;
}}
.mpp-zona {{ position:absolute; top:0; bottom:0; }}
.mpp-cero {{ position:absolute; left:50%; top:0; bottom:0; width:1px; background:{tema.TEXTO_TENUE}; }}
.mpp-barra {{ position:absolute; top:1px; bottom:1px; border-radius:999px; }}
.mpp-tope {{ position:absolute; top:0; bottom:0; width:3px; background:{tema.TEXTO}; }}
.mpp-hueco {{
  position:absolute; inset:0;
  background:repeating-linear-gradient(-45deg,{tema.BORDE_SUAVE} 0 4px,{tema.FONDO} 4px 8px);
}}
.mpp-vered {{ flex:0 0 6.2rem; font-size:.76rem; font-weight:600; }}
.mpp-z {{
  flex:0 0 3.6rem; text-align:right; color:{tema.TEXTO_SUAVE}; font-size:.76rem;
  font-variant-numeric:tabular-nums;
}}
.mpp-tira {{ display:flex; gap:.5rem; flex-wrap:wrap; }}
.mpp-celda {{ flex:1 1 8rem; min-width:7.5rem; }}
.mpp-celda .mpp-pista {{ margin:.22rem 0; }}
.mpp-celda-cab {{ display:flex; justify-content:space-between; font-size:.7rem; color:{tema.TEXTO_SUAVE}; }}
.mpp-celda-pie {{ font-size:.74rem; font-weight:600; }}
</style>"""


def _esc(texto: object) -> str:
    return html.escape(str(texto))


def _pista(z: float | None) -> str:
    """The track: qualitative zones, a zero line, and the bar itself.

    Las zonas van de fondo a propósito: con la barra sola, saber si un +0,6 es
    bueno exige recordar dónde caían los cortes. Pintadas, el mapa se lee sin
    memoria. Cuando no hay dato no se pintan — una escala vacía se leería como
    un cero — y en su lugar va un rayado que no se puede confundir con una
    medición.
    """
    marca = nivel(z)
    if marca is SIN_DATOS:
        return '<span class="mpp-pista"><i class="mpp-hueco"></i></span>'

    p = posicion(z)
    izquierda, ancho = min(50.0, p), abs(p - 50.0)
    tope = ""
    if fuera_de_escala(z):
        tope = f'<i class="mpp-tope" style="left:{0.0 if z < 0 else 99.0:.2f}%"></i>'
    return (
        '<span class="mpp-pista">'
        f'<i class="mpp-zona" style="left:0;width:{_CORTE_BAJO:.2f}%;'
        f'background:{tema.rgba(_ROJO, .13)}"></i>'
        f'<i class="mpp-zona" style="left:{_CORTE_BAJO:.2f}%;'
        f'width:{_CORTE_ALTO - _CORTE_BAJO:.2f}%;background:{tema.rgba(_AMBAR, .13)}"></i>'
        f'<i class="mpp-zona" style="left:{_CORTE_ALTO:.2f}%;'
        f'width:{100 - _CORTE_ALTO:.2f}%;background:{tema.rgba(_VERDE, .13)}"></i>'
        '<i class="mpp-cero"></i>'
        f'<i class="mpp-barra" style="left:{izquierda:.2f}%;width:{ancho:.2f}%;'
        f'background:{marca.color}"></i>'
        f"{tope}"
        "</span>"
    )


def medidor(
    nombre: str, z: float | None, *, nota: str = "", valor: str = "", titulo: str = ""
) -> str:
    """One labelled row: name, figure, meter, verdict in words, and the z.

    El veredicto va escrito además de en color. Un medidor que sólo cambia de
    tono no le dice nada a quien no distingue el verde del rojo, ni a quien mira
    la página impresa en blanco y negro.
    """
    marca = nivel(z)
    numero = "—" if marca is SIN_DATOS else f"{z:+.2f}"
    if fuera_de_escala(z):
        # El signo avisa de que la barra está tocando el tope y el número la ha
        # desbordado: sin él, un +6,39 y un +3,00 se dibujan exactamente igual.
        numero = f"›{numero}"
    aclaracion = titulo or f"{nombre}: {marca.detalle}"
    etiqueta = _esc(nombre) + (
        f' <span class="mpp-nota">{_esc(nota)}</span>' if nota else ""
    )
    return (
        f'<div class="mpp-fila" title="{_esc(aclaracion)}">'
        f'<span class="mpp-nombre">{etiqueta}</span>'
        + (f'<span class="mpp-valor">{_esc(valor)}</span>' if valor else "")
        + _pista(z)
        + f'<span class="mpp-vered" style="color:{marca.color}">'
        f"{_esc(marca.veredicto)}</span>"
        f'<span class="mpp-z">{_esc(numero)}</span>'
        "</div>"
    )


def medidor_kpi(item: dict) -> str:
    """A meter for one of the ficha's `destacados` / `flojos` entries.

    La nota del sentido sólo se escribe cuando contradice a la intuición. En un
    margen, valor alto y barra verde apuntan al mismo sitio y anotarlo es ruido
    repetido diecisiete veces; en el `PER` apuntan a lados opuestos, y ahí es
    donde una línea de texto evita que el revisor lea "caro" como "bueno". El
    tooltip sigue diciéndolo en los dos casos.
    """
    kpi = item["kpi"]
    presentacion = KPIS[kpi]
    z = orientar(kpi, item["z"])
    return medidor(
        presentacion.etiqueta,
        z,
        nota="" if SIGNOS[kpi] > 0 else sentido(kpi),
        valor=formatear(kpi, item["valor"]),
        titulo=(
            f"{presentacion.etiqueta}: {formatear(kpi, item['valor'])}, "
            f"{nivel(z).detalle}. Para este KPI, {sentido(kpi)}."
        ),
    )


def _nota_pilar(pilar: str, cobertura: dict) -> str:
    """How many of the pillar's KPIs actually carried data, when B recorded it.

    Un +6,39 en solidez sostenido por 1 de 3 KPIs y otro sostenido por los 3 se
    leen igual en un número y no significan lo mismo. Las fichas anteriores a
    este campo se pintan sin la nota, en vez de inventarse un recuento.
    """
    por_pilar = (cobertura or {}).get("kpis_por_pilar") or {}
    if pilar not in por_pilar:
        return ""
    return f"{por_pilar[pilar]} de {len(PILARES[pilar])} KPIs"


def medidores_pilares(ficha: dict) -> str:
    """The four pillar meters, in the order the criterion declares them."""
    pilares = ficha["pilares"]
    return "".join(
        medidor(
            PILARES_ETIQUETAS[pilar],
            pilares.get(pilar),
            nota=_nota_pilar(pilar, ficha.get("cobertura", {})),
        )
        for pilar in PILARES
    )


def tira_pilares(ficha: dict) -> str:
    """The compact four-up strip that makes the list scannable unopened.

    Con quince candidatos, obligar a abrir quince desplegables para saber cuál
    es fuerte en qué convierte una lista en quince lecturas. Aquí los cuatro
    pilares caben en una línea.
    """
    pilares = ficha["pilares"]
    celdas = []
    for pilar in PILARES:
        z = pilares.get(pilar)
        marca = nivel(z)
        numero = "—" if marca is SIN_DATOS else f"{z:+.2f}"
        celdas.append(
            '<div class="mpp-celda" '
            f'title="{_esc(PILARES_ETIQUETAS[pilar])}: {_esc(marca.detalle)}">'
            '<div class="mpp-celda-cab">'
            f"<span>{_esc(PILARES_ETIQUETAS[pilar])}</span><span>{_esc(numero)}</span>"
            "</div>"
            f"{_pista(z)}"
            f'<div class="mpp-celda-pie" style="color:{marca.color}">'
            f"{_esc(marca.veredicto)}</div>"
            "</div>"
        )
    return '<div class="mpp-tira">' + "".join(celdas) + "</div>"


def tarjeta_candidato(ficha: dict) -> str:
    """The whole collapsed row: who it is, its composite, and the four pillars."""
    cobertura = ficha.get("cobertura", {})
    con_dato = cobertura.get("kpis_con_dato")
    resumen_cobertura = (
        f" · {con_dato} de {len(TODOS_LOS_KPIS)} KPIs con dato"
        if con_dato is not None
        else ""
    )
    return (
        '<div class="mpp-tarjeta">'
        '<div class="mpp-cab">'
        f'<span class="mpp-puesto">#{_esc(ficha["puesto"])}</span>'
        f'<span class="mpp-ticker">{_esc(ficha["ticker"])}</span>'
        f'<span class="mpp-chip">{_esc(ficha["sector_gics"])}</span>'
        f'<span class="mpp-cab-der">Compuesto {ficha["compuesto"]:+.2f} '
        f"(z dentro del sector){_esc(resumen_cobertura)}</span>"
        "</div>"
        f"{tira_pilares(ficha)}"
        "</div>"
    )


def medidor_cobertura(con_dato: int, total: int = len(TODOS_LOS_KPIS)) -> str:
    """Coverage as a bar with the guard's own threshold marked on it.

    Sin la marca, "10 de 17" no dice si eso es mucho o poco. Con ella se ve que
    el mínimo para no quedar excluida son 8, así que 10 es aprobar raspando.
    No lleva veredicto: la cobertura no es buena ni mala, es cuánto se sabe.
    """
    ancho = max(0.0, min(100.0, con_dato / total * 100)) if total else 0.0
    umbral = MIN_KPIS_CON_DATO / total * 100 if total else 0.0
    return (
        '<div class="mpp-fila mpp-aparte" '
        f'title="{con_dato} de {total} KPIs con dato; por debajo de '
        f'{MIN_KPIS_CON_DATO} las guardas la habrían excluido">'
        '<span class="mpp-nombre">Cobertura de datos</span>'
        f'<span class="mpp-valor">{con_dato} / {total}</span>'
        '<span class="mpp-pista">'
        f'<i class="mpp-barra" style="left:0;width:{ancho:.2f}%;background:{_ACENTO}"></i>'
        f'<i class="mpp-tope" style="left:{umbral:.2f}%;background:#9aa2b8"></i>'
        "</span>"
        f'<span class="mpp-vered mpp-nota">mínimo {MIN_KPIS_CON_DATO}</span>'
        '<span class="mpp-z"></span>'
        "</div>"
    )

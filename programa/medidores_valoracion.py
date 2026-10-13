"""Cómo se enseña una valoración: etiquetas y HTML, sin Streamlit.

`fichas.json` guarda claves (`"mixtas"`, `"quema_caja"`), nunca textos de
pantalla: es la regla de «La etiqueta de pantalla que se guardaba en disco».
Las palabras viven aquí y sólo aquí. Va aparte de `medidores.py`, que ya pasa
de las 450 líneas, y lo usarán las dos pantallas: Revisar candidatos y, en N, el
Analizador.

Todo lo que sale de la ficha se escapa antes de pintarlo, aunque lo haya
escrito este mismo programa: la moneda, por ejemplo, viene de Yahoo.
"""

import html

import tema
from valoracion.criterio import INVERSO_LIMITES, INVERSO_ROE_LIMITES

VEREDICTO = {
    "infravalorada": ("Infravalorada", tema.VERDE),
    "sobrevalorada": ("Sobrevalorada", tema.ROJO),
    "mixtas": ("Señales mixtas", tema.AMBAR),
    "en_rango": ("En rango", tema.TEXTO_SUAVE),
    "sin_datos": ("Sin datos suficientes", tema.TEXTO_TENUE),
}

VOTO = {
    "barata": ("Barata", tema.VERDE),
    "neutra": ("Neutra", tema.TEXTO_SUAVE),
    "cara": ("Cara", tema.ROJO),
    "no_aplica": ("No aplica", tema.TEXTO_TENUE),
}

NOMBRE_VOTO = {
    "flujos": "Flujos (DCF e inverso)",
    "sin_crecimiento": "Sin crecimiento (EPV)",
    "pares": "Frente a sus pares",
}
_NOMBRE_VOTO_RESIDUAL = {**NOMBRE_VOTO, "flujos": "Beneficio residual"}

MOTIVO = {
    "quema_caja": "quema caja: valorarla exigiría inventar cuándo deja de hacerlo",
    "ebit_negativo": "beneficio operativo negativo: sin crecer no queda nada que capitalizar",
    "sin_historia": "faltan años de historia para normalizar sus márgenes",
    "wacc_bajo_crecimiento": (
        "el coste de capital no supera al crecimiento perpetuo en al menos un "
        "punto, y el valor terminal explotaría"
    ),
    "sin_pares": "sin pares del sector con los que comparar",
    "sin_precio": "no se pudo descargar el precio",
    "sin_tasa_libre": "no se pudo descargar la tasa libre de riesgo",
    "financiera": "no aplica a bancos ni aseguradoras",
    "patrimonio_negativo": "patrimonio negativo: no hay base sobre la que medir la rentabilidad",
    "sin_beneficio_operativo": (
        "no declara beneficio operativo, así que no hay valor sin crecimiento que calcular"
    ),
    "sin_flujo_libre": "no declara capex o flujo operativo, así que no hay flujo libre que proyectar",
    "sin_red": "Yahoo Finance no devolvió datos: sin conexión, un error suyo o un símbolo que no conoce",
    "sin_estados": "no se pudieron leer sus estados financieros de la SEC",
    "error_interno": "error interno al valorar: merece avisar de ello",
}

NOTA = (
    "Un criterio transparente, no una previsión: no hay forma honesta de probar "
    "hacia atrás si acierta, porque las cifras de yfinance no dicen cuándo se "
    "publicaron y el universo arrastra sesgo de supervivencia."
)

# En la corrida real de la Task 10, SNDK salía «en rango» con un margen de
# seguridad del +129 %. No es un error: el voto no mira la distancia al valor
# base sino el crecimiento que el precio exige frente a su referencia, con una
# banda de ± la mitad de esa referencia. Sin decirlo, la pantalla desconcierta.
LECTURA_MARGEN = (
    "El margen de seguridad mide la distancia al valor base. El voto de flujos "
    "no lo usa: compara el crecimiento que el precio exige con su referencia, "
    "con una banda de ± la mitad de esa referencia. Por eso un margen grande "
    "puede convivir con «en rango» cuando el crecimiento de referencia es alto."
)

CSS = f"""<style>
.mpp-veredicto {{
  border:1px solid currentColor; border-radius:999px; padding:.03rem .55rem;
  font-size:.72rem; font-weight:600;
}}
.mpp-val {{ font-size:.8rem; line-height:1.45; color:{tema.TEXTO}; margin:.2rem 0 .4rem; }}
.mpp-val-cab {{ display:flex; flex-wrap:wrap; gap:.55rem; align-items:baseline; margin-bottom:.35rem; }}
.mpp-val-voto {{ display:flex; gap:.55rem; align-items:baseline; margin:.15rem 0; }}
.mpp-val-nombre {{ flex:0 0 11.5rem; }}
.mpp-val-etiqueta {{ flex:0 0 5.5rem; font-weight:600; }}
.mpp-val-detalle {{ color:{tema.TEXTO_SUAVE}; }}
.mpp-val-sup {{ color:{tema.TEXTO_TENUE}; font-size:.72rem; margin-top:.45rem; }}
</style>"""


def _esc(texto: object) -> str:
    return html.escape(str(texto))


def _pct(valor) -> str:
    return "n/d" if valor is None else f"{valor * 100:.1f}%"


def _dinero(valor, moneda: str) -> str:
    return "n/d" if valor is None else f"{valor:,.2f} {moneda}"


def _motivo(clave) -> str:
    return MOTIVO.get(clave, str(clave))


def distintivo(valoracion: "dict | None") -> str:
    """El veredicto en una píldora de color, o nada si no hay veredicto que enseñar."""
    if not isinstance(valoracion, dict) or valoracion.get("veredicto") not in VEREDICTO:
        return ""
    etiqueta, color = VEREDICTO[valoracion["veredicto"]]
    return f'<span class="mpp-veredicto" style="color:{color}">{_esc(etiqueta)}</span>'


def _detalle_flujos(valoracion: dict) -> str:
    lectura = valoracion.get("implicito") or {}
    roe = lectura.get("magnitud") == "roe"
    bajo, alto = INVERSO_ROE_LIMITES if roe else INVERSO_LIMITES
    if lectura.get("fuera_de_limites") == "arriba":
        return (
            f"el precio exige un ROE de más del {_pct(alto)}" if roe
            else f"el precio exige crecer más de un {_pct(alto)} anual"
        )
    if lectura.get("fuera_de_limites") == "abajo":
        return (
            f"el precio queda por debajo incluso de un ROE del {_pct(bajo)}" if roe
            else f"el precio queda por debajo incluso de decrecer un {_pct(-bajo)} anual"
        )
    exige = (
        f"el precio exige un ROE del {_pct(lectura.get('valor'))}" if roe
        else f"el precio exige crecer un {_pct(lectura.get('valor'))} anual cinco años"
    )
    return (
        f"{exige}; su referencia es {_pct(lectura.get('referencia'))} "
        f"(±{_pct(lectura.get('margen'))})"
    )


def _detalle_epv(valoracion: dict) -> str:
    epv = valoracion.get("epv") or {}
    texto = f"sin crecer valdría {_dinero(epv.get('por_accion'), valoracion.get('moneda', ''))}"
    parte = epv.get("parte_crecimiento")
    if parte is not None and parte > 0:
        texto += f"; el {_pct(parte)} del precio es apuesta por el crecimiento"
    return texto


_DETALLE_PARES = {
    "barata": "múltiplos por debajo de los de su sector",
    "cara": "múltiplos por encima de los de su sector",
    "neutra": "múltiplos en línea con los de su sector",
}


def _detalle(clave: str, voto: dict, valoracion: dict) -> str:
    if voto.get("voto") == "no_aplica":
        return _motivo(voto.get("motivo"))
    if clave == "flujos":
        return _detalle_flujos(valoracion)
    if clave == "sin_crecimiento":
        return _detalle_epv(valoracion)
    return _DETALLE_PARES.get(voto.get("voto"), "")


def _rango(valoracion: dict) -> str:
    moneda = valoracion.get("moneda", "")
    valor = valoracion.get("valor")
    if not valor:
        return "Sin rango de valor."
    return (
        f"Valor por acción: pesimista {_dinero(valor.get('pesimista'), moneda)} · "
        f"base {_dinero(valor.get('base'), moneda)} · "
        f"optimista {_dinero(valor.get('optimista'), moneda)} · "
        f"margen de seguridad {_pct(valoracion.get('margen_seguridad'))}"
    )


_NOMBRE_SUPUESTO = {
    "r_f": "tasa libre",
    "beta": "beta",
    "prima": "prima de riesgo",
    "k_e": "coste del capital propio",
    "k_d": "coste de la deuda",
    "t": "impuestos",
    "wacc": "coste de capital",
    "g_ref": "crecimiento de referencia",
    "g_perpetuo": "crecimiento perpetuo",
    "roe_ref": "ROE de referencia",
    "payout": "reparto",
}


def procedencia(nombre: str, supuesto: dict) -> str:
    """De dónde sale un supuesto, en palabras. Vacío si la fuente no se reconoce."""
    p = (supuesto or {}).get("procedencia") or {}
    fuente = p.get("fuente")
    textos = {
        ("r_f", "tesoro_10"): "Tesoro de EE. UU. a 10 años (^TNX)",
        ("beta", "regresion"): (
            f"regresión semanal de {p.get('semanas')} semanas contra {p.get('indice')} "
            f"(R² {p.get('r2')}), con el ajuste de Blume"
        ),
        ("beta", "por_defecto"): "1,0 por defecto: no hubo regresión posible (historial corto o precios inválidos)",
        ("prima", "damodaran"): f"Damodaran, prima implícita a {p.get('fecha')}",
        ("k_e", "capm"): "tasa libre más beta por prima",
        ("k_d", "gasto_entre_deuda"): "gasto financiero entre deuda, acotado",
        ("k_d", "sin_dato"): "sin deuda o sin gasto financiero declarado: la tasa libre",
        ("k_d", "financiera"): "no aplica: en un banco o una aseguradora los intereses incluyen los depósitos",
        ("t", "efectiva"): "tasa efectiva de yfinance, acotada entre 0% y 35%",
        ("t", "legal"): f"tasa legal ({p.get('pais')})",
        ("wacc", "financiera"): "no aplica: se valora con el coste del capital propio",
        ("wacc", "wacc"): (
            f"deuda {_pct(p.get('peso_deuda'))} del capital"
            + ("" if p.get("deuda_declarada", True) else "; sin deuda declarada")
        ),
        ("g_ref", "historia_y_consenso"): (
            f"media del histórico de ingresos ({_pct(p.get('historico'))}) y del "
            f"consenso del próximo año ({_pct(p.get('consenso'))}), acotada"
        ),
        ("g_ref", "historia"): f"histórico de ingresos ({_pct(p.get('historico'))}), sin consenso, acotado",
        ("g_ref", "consenso"): f"consenso del próximo año ({_pct(p.get('consenso'))}), sin historia, acotado",
        ("g_ref", "sin_dato"): "sin historia ni consenso",
        ("g_perpetuo", "criterio"): f"crecimiento de largo plazo en {p.get('moneda')}",
        ("g_perpetuo", "recortado_a_r_f"): "recortado a la tasa libre de riesgo",
        ("roe_ref", "mediana_historica"): f"mediana de {p.get('anos')} años",
        ("roe_ref", "sin_dato"): "sin años suficientes",
        ("payout", "yfinance"): "reparto de beneficios de yfinance",
        ("payout", "por_defecto"): "sin dato: se supone la mitad",
    }
    return textos.get((nombre, fuente), "")


def _supuestos(valoracion: dict) -> str:
    partes = []
    for nombre, supuesto in (valoracion.get("supuestos") or {}).items():
        valor = (supuesto or {}).get("valor")
        cifra = f"{valor:.2f}" if nombre == "beta" and valor is not None else _pct(valor)
        origen = procedencia(nombre, supuesto)
        etiqueta = _NOMBRE_SUPUESTO.get(nombre, nombre)
        partes.append(f"{etiqueta} {cifra}" + (f" ({origen})" if origen else ""))
    if not partes:
        return ""
    return f'<div class="mpp-val-sup">Supuestos del programa: {_esc("; ".join(partes))}.</div>'


def resumen(valoracion: dict) -> str:
    """Los tres votos en una línea cada uno, el rango y la procedencia de los supuestos."""
    if "veredicto" not in valoracion:
        return (
            f'<div class="mpp-val">No se pudo valorar: '
            f'{_esc(_motivo(valoracion.get("motivo")))}.</div>'
        )
    nombres = _NOMBRE_VOTO_RESIDUAL if valoracion.get("metodo") == "residual" else NOMBRE_VOTO
    filas = []
    for clave in ("flujos", "sin_crecimiento", "pares"):
        voto = (valoracion.get("votos") or {}).get(clave) or {}
        etiqueta, color = VOTO.get(voto.get("voto"), ("n/d", tema.TEXTO_TENUE))
        filas.append(
            '<div class="mpp-val-voto">'
            f'<span class="mpp-val-nombre">{_esc(nombres[clave])}</span>'
            f'<span class="mpp-val-etiqueta" style="color:{color}">{_esc(etiqueta)}</span>'
            f'<span class="mpp-val-detalle">{_esc(_detalle(clave, voto, valoracion))}</span>'
            "</div>"
        )
    cabecera = (
        f'<div class="mpp-val-cab">{distintivo(valoracion)}'
        f'<span class="mpp-val-detalle">{_esc(_rango(valoracion))}</span>'
        f'<span class="mpp-val-detalle">Calculada el {_esc(valoracion.get("fecha"))} '
        f'con el precio de {_esc(_dinero(valoracion.get("precio"), valoracion.get("moneda", "")))} '
        f'y estados hasta {_esc(valoracion.get("estados_hasta", "n/d"))}'
        "</span></div>"
    )
    return f'<div class="mpp-val">{cabecera}{"".join(filas)}{_supuestos(valoracion)}</div>'

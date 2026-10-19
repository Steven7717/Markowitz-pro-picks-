"""Cómo se enseña una valoración: etiquetas y HTML, sin Streamlit.

`fichas.json` guarda claves (`"mixtas"`, `"quema_caja"`), nunca textos de
pantalla: es la regla de «La etiqueta de pantalla que se guardaba en disco».
Las palabras viven aquí y sólo aquí. Va aparte de `medidores.py`, que ya pasa
de las 450 líneas, y lo usarán las dos pantallas: Revisar candidatos y, en N, el
Analizador.

Todo lo que sale de la ficha se escapa antes de pintarlo, aunque lo haya
escrito este mismo programa: la moneda, por ejemplo, viene de Yahoo. Y nada de lo
que sale de la ficha se da por bien formado: `fichas.json` lo puede haber tocado
cualquiera, y una tarjeta corrupta no debe tumbar la lista entera, así que cada
lectura degrada a «n/d» en vez de lanzar.

Los textos de los criterios (los topes, la holgura, el reparto por defecto) se
construyen desde `valoracion.criterio`: si un listón se enmienda, la pantalla
cambia sola y no se queda diciendo el número viejo.
"""

import html
import math
from collections import Counter
from datetime import datetime, timezone

import tema
from valoracion.criterio import (
    ANOS_ALTO_CRECIMIENTO,
    BLUME,
    COSTE_DEUDA_PRIMA_MAXIMA,
    CRECIMIENTO_REF_TOPES,
    DELTA_WACC_ESCENARIOS,
    HOLGURA_GORDON,
    INVERSO_LIMITES,
    INVERSO_ROE_LIMITES,
    MARGEN_MINIMO,
    MARGEN_ROE_MINIMO,
    MIN_VOTOS,
    PAYOUT_SIN_DATO,
    TASA_EFECTIVA_TOPES,
    UMBRAL_PARES,
)

# El gris del tema es el de «sin señal»: «en rango» y «sin datos» van en él, y
# `TEXTO_TENUE` queda fuera porque sobre una tarjeta no llega a 4.5:1.
VEREDICTO = {
    "infravalorada": ("Infravalorada", tema.VERDE),
    "sobrevalorada": ("Sobrevalorada", tema.ROJO),
    "mixtas": ("Señales mixtas", tema.AMBAR),
    "en_rango": ("En rango", tema.TEXTO_SUAVE),
    "sin_datos": ("Sin datos suficientes", tema.TEXTO_SUAVE),
}

VOTO = {
    "barata": ("Barata", tema.VERDE),
    "neutra": ("Neutra", tema.TEXTO_SUAVE),
    "cara": ("Cara", tema.ROJO),
    "no_aplica": ("No aplica", tema.TEXTO_SUAVE),
}

NOMBRE_VOTO = {
    "flujos": "Flujos (DCF e inverso)",
    "sin_crecimiento": "Sin crecimiento (EPV)",
    "pares": "Frente a sus pares",
}
_NOMBRE_VOTO_RESIDUAL = {**NOMBRE_VOTO, "flujos": "Beneficio residual"}

# Ninguna etiqueta empieza por «no aplica» ni por «no se pudo», ni las repite:
# en la fila de un voto ya está el «No aplica» a su izquierda, y delante de una
# valoración fallida va «Sin valoración:». Las que pueden ir detrás de ese
# prefijo (las de una fallida) tampoco llevan dos puntos: saldrían dos seguidos.
#
# `{holgura}` se rellena al pintar, en `etiqueta_motivo`, y no al importar: es la
# holgura del criterio, y un texto fijado al importar se quedaría con el número
# viejo si alguien la enmienda. Úsese `etiqueta_motivo`, no `MOTIVO[...]`.
MOTIVO = {
    "quema_caja": "quema caja: valorarla exigiría inventar cuándo deja de hacerlo",
    "ebit_negativo": "beneficio operativo negativo: sin crecer no queda nada que capitalizar",
    "sin_historia": "faltan años de historia",
    "wacc_bajo_crecimiento": (
        "el coste de capital no supera al crecimiento a perpetuidad en al menos "
        "{holgura}, y el valor terminal explotaría"
    ),
    "sin_pares": "sin pares del sector con los que comparar",
    "sin_precio": "Yahoo Finance no devolvió el precio",
    "sin_tasa_libre": "Yahoo Finance no devolvió la tasa libre de riesgo",
    "financiera": "se valora por beneficio residual (entidades financieras)",
    "patrimonio_negativo": "patrimonio negativo: no hay base sobre la que medir la rentabilidad",
    "sin_beneficio_operativo": (
        "no declara beneficio operativo, así que no hay valor sin crecimiento que calcular"
    ),
    "sin_flujo_libre": "no declara capex o flujo operativo, así que no hay flujo libre que proyectar",
    "sin_red": "Yahoo Finance no devolvió datos (sin conexión, un error suyo o un símbolo que no conoce)",
    "sin_estados": "los estados financieros de la SEC no están disponibles o no son legibles",
    "error_interno": "error interno del programa al valorar",
}

# Los estados de M vienen de la SEC, no de yfinance, y `fundamentals/panel.py`
# se queda con la última cifra que la empresa publicó de cada periodo
# (`keep="last"`): una reexpresión pisa a la original. Probar hacia atrás con
# ellas sería usar cifras que nadie tenía en su momento.
NOTA = (
    "Un criterio transparente, no una previsión: no hay forma honesta de probar "
    "hacia atrás si acierta, porque las cifras guardadas son las últimas que "
    "publicó cada empresa, no las que se conocían en su día, y el universo "
    "arrastra sesgo de supervivencia."
)

# En la corrida real de la Task 10, SNDK salía «en rango» con un margen de
# seguridad del +129 %. No es un error: el voto no mira la distancia al valor
# base sino lo que el precio exige frente a su referencia, con la banda de
# `valoracion.votos.margen_voto`. Sin decirlo, la pantalla desconcierta.
#
# Son funciones y no constantes porque nombran el mínimo de la banda, que es
# del criterio: leído al importar, se quedaría con el número viejo.
def lectura_margen() -> str:
    """Por qué un margen de seguridad grande puede ir con «en rango» (método de flujos)."""
    return (
        "El margen de seguridad mide la distancia al valor base. El voto de flujos "
        "no lo usa: compara el crecimiento que el precio exige con su referencia, "
        "con una banda de ± la mitad de esa referencia y nunca menos de "
        f"{_n_puntos(MARGEN_MINIMO)}. Por eso un margen grande puede convivir con "
        "«en rango» cuando el crecimiento de referencia es alto."
    )


def lectura_margen_roe() -> str:
    """Lo mismo para una entidad financiera, cuyo voto compara ROE y no crecimiento."""
    return (
        "El margen de seguridad mide la distancia al valor base. El voto del "
        "beneficio residual no lo usa: compara el ROE que el precio exige con el "
        "ROE de referencia, con una banda de ± la mitad de esa referencia y nunca "
        f"menos de {_n_puntos(MARGEN_ROE_MINIMO)}. Por eso un margen grande puede "
        "convivir con «en rango» cuando el ROE de referencia es alto."
    )


def glosario() -> str:
    """Los términos técnicos de la pantalla, en markdown, para pintarlos una vez.

    La regla del repo es explicar la identidad de cada término la primera vez que
    sale en una pantalla, no en cada tarjeta: la vista llama a esto UNA vez y
    `resumen` no lo repite en ninguno de los resúmenes. Es una función y no una
    constante porque lleva números del criterio (Blume, los votos mínimos, el
    salto del coste de capital): leídos al importar, se quedarían con el valor
    viejo si el criterio se enmienda.
    """
    blume = (1 - BLUME[0]) * 100
    salto = _n_puntos(DELTA_WACC_ESCENARIOS)
    flujos, epv, pares = (f"«{NOMBRE_VOTO[c]}»" for c in ("flujos", "sin_crecimiento", "pares"))
    residual = f"«{_NOMBRE_VOTO_RESIDUAL['flujos']}»"
    umbral = f"{UMBRAL_PARES:g}"
    return f"""\
- **Las lecturas y los votos**: el DCF y el DCF inverso son la misma ecuación leída en los dos sentidos y, por separado, contarían dos veces, así que dan un solo voto, {flujos}: lo decide el inverso, y el DCF da el rango de valor, que es su contexto. El EPV da el voto {epv}, que nunca vota «cara»: pagar por el crecimiento no es estar cara. El tercer voto es {pares}. En las entidades financieras, el beneficio residual y su inverso (el ROE que el precio exige) ocupan el sitio de los flujos de la misma manera: el voto, {residual}, lo decide el inverso, y el beneficio residual da el rango. No hay voto sin crecimiento: tres lecturas y dos votos.
- **Frente a sus pares**: es el pilar «valoración» del score convertido en voto, es decir, los múltiplos de la empresa frente a los de su sector. Vota «barata» con una puntuación de +{umbral} o más, «cara» con −{umbral} o menos y «neutra» entre medias. La puntuación es la del medidor del pilar: desviaciones típicas frente a la media del sector, con el signo ya aplicado, así que positiva es más barata.
- **DCF** (flujos de caja descontados): el valor actual de los flujos de caja libres futuros de la empresa. Es lo que vale hoy todo el dinero que se espera que genere, descontado al coste de capital.
- **DCF inverso**: la misma ecuación leída al revés. En vez de calcular cuánto vale la empresa, busca el crecimiento que el precio de mercado da por hecho.
- **EPV** (valor sin crecimiento, de Greenwald): lo que valdría la empresa si su beneficio operativo después de impuestos se mantuviera para siempre, sin crecer. Greenwald ajusta además la diferencia entre la amortización y el capex de mantenimiento; aquí no se hace, porque ninguna fuente separa el capex de mantenimiento del de expansión.
- **Beneficio residual**: el método para las entidades financieras (bancos, aseguradoras y mercados de capitales), cuyo flujo de caja no significa nada. Su valor es el patrimonio contable más lo que vale la rentabilidad que supera al coste del capital propio, que se supone que persiste.
- **Capex**: la inversión en activos fijos, como fábricas, máquinas o equipos. El flujo de caja libre es el flujo de caja operativo menos el capex.
- **ROE**: la rentabilidad sobre el patrimonio, el beneficio neto entre el patrimonio neto. Dice cuánto gana la empresa por cada unidad de capital de sus accionistas.
- **Consenso**: la media de las previsiones de los analistas; aquí, la del crecimiento de los ingresos del próximo año.
- **Tasa libre de riesgo y prima de riesgo**: la tasa libre es lo que rinde el bono del Tesoro de EE. UU. a 10 años (^TNX), que se considera sin riesgo. La prima de riesgo, que publica Damodaran, es el extra que los inversores exigen por tener acciones en vez de ese bono.
- **Beta, R² y Blume**: la beta dice cuánto se mueve la acción con el mercado; 1.0 es lo mismo que él. El R² es la parte de los movimientos de la acción que el mercado explica, y un R² bajo significa una beta ruidosa. El ajuste de Blume acerca la beta medida un {blume:.0f}% del camino hacia 1.0, porque con el tiempo las betas tienden a él.
- **Coste de capital (WACC)**: lo que cuesta de media financiarse con deuda y con capital propio, según el peso de cada uno. El **coste del capital propio** es la parte de los accionistas: la tasa libre más la beta por la prima de riesgo.
- **Crecimiento a perpetuidad y valor terminal**: pasados los años proyectados se supone que los flujos crecen para siempre a un ritmo bajo, que nunca supera a la tasa libre. El valor terminal es lo que valen todos esos flujos posteriores, y pesa mucho en el valor total.
- **Escenarios** (pesimista, base y optimista): el base usa la referencia tal cual. El pesimista le resta la banda al crecimiento de referencia (o al ROE) y sube {salto} el coste de capital (en las entidades financieras, el del capital propio); el optimista le suma la banda y lo baja {salto}. Juntar los dos extremos es lo que hace tan ancho el rango.
- **Margen de seguridad**: aquí es (valor base − precio) / precio, es decir, cuánto más vale la empresa que su precio. No es el de Graham, (valor − precio) / valor, que se mide sobre el valor.
- **Veredicto**: hacen falta dos votos en el mismo sentido y ninguno en contra. Una «cara» con dos «neutra» es «en rango»; una «barata» con una «cara», señales mixtas; con menos de {MIN_VOTOS} votos aplicables, sin datos suficientes."""


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
.mpp-val-sup {{ color:{tema.TEXTO_SUAVE}; font-size:.72rem; margin-top:.45rem; }}
.mpp-val-sup-titulo {{ font-weight:600; }}
</style>"""


def _esc(texto: object) -> str:
    return html.escape(str(texto))


def _dic(valor: object) -> dict:
    """Lo que debería ser un diccionario, o uno vacío si la ficha vino rota."""
    return valor if isinstance(valor, dict) else {}


def _entrada(tabla: dict, clave: object, defecto):
    """`tabla[clave]` sin reventar con una clave que no es texto (una lista no es hashable)."""
    return tabla.get(clave, defecto) if isinstance(clave, str) else defecto


def _numero(valor: object) -> "float | None":
    """El valor como número finito, o None. Un booleano no es una cifra."""
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None
    try:
        numero = float(valor)
    except OverflowError:
        return None
    return numero if math.isfinite(numero) else None


def _menos(texto: str) -> str:
    """El signo menos tipográfico: el guion corto se lee como un separador."""
    return texto.replace("-", "−")


def _pct(valor: object) -> str:
    numero = _numero(valor)
    return "n/d" if numero is None else _menos(f"{numero * 100:.1f}%")


def _puntos(valor: object) -> str:
    numero = _numero(valor)
    return "n/d" if numero is None else _menos(f"{numero * 100:.1f} puntos")


def _decimales(valor: object, cifras: int) -> str:
    numero = _numero(valor)
    return "n/d" if numero is None else _menos(f"{numero:.{cifras}f}")


def _moneda(valoracion: dict) -> str:
    """La moneda de la ficha, o nada si falta o no es texto: mejor sin ella que con basura."""
    moneda = valoracion.get("moneda")
    return moneda if isinstance(moneda, str) else ""


def _dinero(valor: object, moneda: str) -> str:
    numero = _numero(valor)
    if numero is None:
        return "n/d"
    cifra = _menos(format(numero, ",.2f"))
    return f"{cifra} {moneda}" if moneda else cifra


def _n_puntos(fraccion: float) -> str:
    """«1 punto», «2 puntos»: una fracción del criterio dicha en puntos porcentuales."""
    puntos = fraccion * 100
    return f"{puntos:g} {'punto' if puntos == 1 else 'puntos'}"


def etiqueta_motivo(clave: object) -> str:
    """La etiqueta de un motivo; una clave que no se conoce se enseña tal cual, que
    es mejor que esconderla, y una que ni es texto, «n/d»."""
    if not isinstance(clave, str):
        return "n/d"
    if clave not in MOTIVO:
        return clave
    return MOTIVO[clave].format(holgura=_n_puntos(HOLGURA_GORDON))


def distintivo(valoracion: "dict | None") -> str:
    """El veredicto en una píldora de color, o nada si no hay veredicto que enseñar."""
    clave = _dic(valoracion).get("veredicto")
    if not isinstance(clave, str) or clave not in VEREDICTO:
        return ""
    etiqueta, color = VEREDICTO[clave]
    return f'<span class="mpp-veredicto" style="color:{color}">{_esc(etiqueta)}</span>'


def _referencia(valor: object, crecimiento: bool) -> str:
    """Una referencia de crecimiento negativa se lee como lo que es: una caída.

    La de un ROE no: un ROE del −4 % es una rentabilidad negativa, no una caída.
    """
    numero = _numero(valor)
    if crecimiento and numero is not None and numero < 0:
        return f"una caída del {_pct(-numero)}"
    return _pct(numero)


def _banda(lectura: dict, crecimiento: bool) -> str:
    return (
        f"su referencia es {_referencia(lectura.get('referencia'), crecimiento)} "
        f"(banda de ±{_puntos(lectura.get('margen'))})"
    )


def _detalle_crecimiento(lectura: dict) -> str:
    bajo, alto = INVERSO_LIMITES
    if lectura.get("fuera_de_limites") == "arriba":
        return f"el precio da por hecho un crecimiento de más del {_pct(alto)} al año"
    if lectura.get("fuera_de_limites") == "abajo":
        return f"el precio es tan bajo que ni una caída del {_pct(-bajo)} al año lo explicaría"
    g = _numero(lectura.get("valor"))
    if g is None:
        return "n/d"
    if g >= 0:
        exige = f"que los ingresos crecerán un {_pct(g)} al año"
    else:
        exige = f"que los ingresos caerán un {_pct(-g)} al año"
    return (
        f"el precio da por hecho {exige} durante {ANOS_ALTO_CRECIMIENTO} años; "
        f"{_banda(lectura, crecimiento=True)}"
    )


def _detalle_roe(lectura: dict) -> str:
    bajo, alto = INVERSO_ROE_LIMITES
    if lectura.get("fuera_de_limites") == "arriba":
        return f"el precio exige un ROE de más del {_pct(alto)}"
    if lectura.get("fuera_de_limites") == "abajo":
        return f"el precio es tan bajo que ni un ROE del {_pct(bajo)} lo explicaría"
    return (
        f"el precio exige un ROE del {_pct(lectura.get('valor'))}; "
        f"{_banda(lectura, crecimiento=False)}"
    )


def _detalle_flujos(valoracion: dict) -> str:
    lectura = _dic(valoracion.get("implicito"))
    if lectura.get("magnitud") == "roe":
        return _detalle_roe(lectura)
    return _detalle_crecimiento(lectura)


def _detalle_epv(valoracion: dict) -> str:
    epv = _dic(valoracion.get("epv"))
    texto = f"sin crecer valdría {_dinero(epv.get('por_accion'), _moneda(valoracion))}"
    parte = _numero(epv.get("parte_crecimiento"))
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
        return etiqueta_motivo(voto.get("motivo"))
    if clave == "flujos":
        return _detalle_flujos(valoracion)
    if clave == "sin_crecimiento":
        return _detalle_epv(valoracion)
    return _entrada(_DETALLE_PARES, voto.get("voto"), "")


def _extremos_que_faltan(valor: dict) -> str:
    """Por qué falta un extremo del rango, o nada si no falta ninguno o no hay base.

    El motor sólo deja un escenario en blanco cuando no cumple la holgura de
    Gordon (`wacc_bajo_crecimiento`): el optimista baja el coste de capital y
    puede quedarse sin ella aunque el base la tenga. Sin base no hay escenario
    de referencia, y lo que falta ya no es un extremo.
    """
    if _numero(valor.get("base")) is None:
        return ""
    faltan = [e for e in ("pesimista", "optimista") if _numero(valor.get(e)) is None]
    if not faltan:
        return ""
    quien = " y el ".join(faltan)
    verbo, donde = ("faltan", "esos escenarios") if len(faltan) > 1 else ("falta", "ese escenario")
    return f" · el {quien} {verbo}: en {donde}, {etiqueta_motivo('wacc_bajo_crecimiento')}"


def _rango(valoracion: dict) -> str:
    moneda = _moneda(valoracion)
    valor = _dic(valoracion.get("valor"))
    if not valor:
        return "Sin rango de valor."
    return (
        f"Valor por acción: pesimista {_dinero(valor.get('pesimista'), moneda)} · "
        f"base {_dinero(valor.get('base'), moneda)} · "
        f"optimista {_dinero(valor.get('optimista'), moneda)} · "
        f"margen de seguridad {_pct(valoracion.get('margen_seguridad'))}"
        f"{_extremos_que_faltan(valor)}"
    )


def _hora_cotizacion(valoracion: dict) -> str:
    """La hora del precio en UTC, o nada si falta o no se puede leer.

    La caché puede servir un precio de hasta siete días, así que la fecha de
    cálculo sola no dice de cuándo es la cifra. Una hora sin zona no se da por
    UTC: sería inventar una zona.
    """
    bruta = valoracion.get("precio_hora")
    if not isinstance(bruta, str):
        return ""
    try:
        momento = datetime.fromisoformat(bruta)
    except ValueError:
        return ""
    if momento.tzinfo is None:
        return ""
    return momento.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _cabecera(valoracion: dict) -> str:
    fecha = valoracion.get("fecha", "n/d")
    estados = valoracion.get("estados_hasta", "n/d")
    precio = _dinero(valoracion.get("precio"), _moneda(valoracion))
    hora = _hora_cotizacion(valoracion)
    cotizacion = f" (cotización del {hora})" if hora else ""
    calculo = f"Calculada el {fecha} con el precio de {precio}{cotizacion} y estados hasta {estados}"
    return (
        f'<div class="mpp-val-cab">{distintivo(valoracion)}'
        f'<span class="mpp-val-detalle">{_esc(_rango(valoracion))}</span>'
        f'<span class="mpp-val-detalle">{_esc(calculo)}</span></div>'
    )


_NOMBRE_SUPUESTO = {
    "r_f": "tasa libre",
    "beta": "beta",
    "prima": "prima de riesgo",
    "k_e": "coste del capital propio",
    "k_d": "coste de la deuda",
    "t": "impuestos",
    "wacc": "coste de capital (deuda y capital propio)",
    "g_ref": "crecimiento de referencia",
    "g_perpetuo": "crecimiento a perpetuidad",
    "roe_ref": "ROE de referencia",
    "payout": "reparto de beneficios",
}

# Cada método enseña sólo los supuestos que usa: a un banco no le sirve un coste
# de la deuda, y a una industrial no le sirve un ROE ni un reparto.
_SUPUESTOS_DE = {
    "flujos": ("r_f", "beta", "prima", "k_e", "k_d", "t", "wacc", "g_ref", "g_perpetuo"),
    "residual": ("r_f", "beta", "prima", "k_e", "roe_ref", "payout", "g_perpetuo"),
}

# El reparto de yfinance se acota en `supuestos.payout`, que no lo lee de un
# criterio: éste es el único sitio de la pantalla que repite ese rango.
_PAYOUT_TOPES = (0.0, 1.0)

# Las claves de `criterio.TASA_LEGAL`, dichas como se leen: «tasa legal (otros)»
# enseñaba una clave interna. Un test vigila que no falte ninguna.
_PAIS_LEGAL = {"US": "de EE. UU.", "MX": "de México", "otros": "genérica para otros países"}

# Por qué faltó un dato de mercado (`supuestos._con_motivo`). Sólo «sin_red»
# cambia el texto: es el único que contradice al de siempre. Una beta sin
# regresión posible, una tasa efectiva o un consenso que Yahoo no tiene ya
# quedan bien dichos con él.
_SIN_RED = "sin_red"


def _tasa_legal(p: dict) -> str:
    pais = p.get("pais")
    nombre = _entrada(_PAIS_LEGAL, pais, None)
    texto = f"tasa legal {nombre}" if nombre else f"tasa legal ({pais})"
    if p.get("motivo") == _SIN_RED:
        texto += ", porque Yahoo Finance no devolvió datos de la tasa efectiva"
    return texto


def procedencia(nombre: str, supuesto: dict) -> str:
    """De dónde sale un supuesto, en palabras. Vacío si la fuente no se reconoce."""
    p = _dic(_dic(supuesto).get("procedencia"))
    fuente = p.get("fuente")
    if not isinstance(fuente, str):
        return ""
    g_bajo, g_alto = (_pct(tope) for tope in CRECIMIENTO_REF_TOPES)
    consenso_sin_red = p.get("motivo_consenso") == _SIN_RED
    sin_consenso = (
        "sin consenso porque Yahoo Finance no devolvió datos" if consenso_sin_red else "sin consenso"
    )
    textos = {
        ("r_f", "tesoro_10"): f"Tesoro de EE. UU. a 10 años ({p.get('serie')})",
        ("r_f", "bono_m_10"): (
            f"Bono M a 10 años de Banxico ({p.get('serie')}), subasta del {p.get('fecha')}; "
            "sin restar el diferencial soberano"
        ),
        ("beta", "regresion"): (
            f"regresión semanal de {p.get('semanas')} semanas contra {p.get('indice')} "
            f"(R² {_decimales(p.get('r2'), 2)}), con el ajuste de Blume"
        ),
        ("beta", "por_defecto"): (
            "1.0 por defecto, porque Yahoo Finance no devolvió datos para la regresión"
            if p.get("motivo") == _SIN_RED
            else "1.0 por defecto: no hubo regresión posible (historial corto o precios inválidos)"
        ),
        ("prima", "damodaran"): f"Damodaran, prima implícita a {p.get('fecha')}",
        ("k_e", "capm"): "tasa libre más beta por prima",
        ("k_d", "gasto_entre_deuda"): (
            "gasto financiero entre deuda, acotado entre la tasa libre y esa tasa "
            f"más {_puntos(COSTE_DEUDA_PRIMA_MAXIMA)}"
        ),
        ("k_d", "sin_dato"): "sin deuda o sin gasto financiero declarado: la tasa libre",
        ("k_d", "financiera"): "en un banco o una aseguradora los intereses incluyen los depósitos: no se calcula",
        ("t", "efectiva"): (
            f"tasa efectiva de yfinance, acotada entre {_pct(TASA_EFECTIVA_TOPES[0])} "
            f"y {_pct(TASA_EFECTIVA_TOPES[1])}"
        ),
        ("t", "legal"): _tasa_legal(p),
        ("wacc", "financiera"): "en un banco o una aseguradora no se calcula: se valora con el coste del capital propio",
        ("wacc", "wacc"): (
            f"deuda {_pct(p.get('peso_deuda'))} del capital"
            + ("" if p.get("deuda_declarada", True) else "; sin deuda declarada")
        ),
        ("g_ref", "historia_y_consenso"): (
            f"media del crecimiento histórico de los ingresos ({_pct(p.get('historico'))}) y del "
            f"consenso del próximo año ({_pct(p.get('consenso'))}), acotada entre {g_bajo} y {g_alto}"
        ),
        ("g_ref", "historia"): (
            f"crecimiento histórico de los ingresos ({_pct(p.get('historico'))}), "
            f"{sin_consenso}, acotado entre {g_bajo} y {g_alto}"
        ),
        ("g_ref", "consenso"): (
            f"consenso del próximo año ({_pct(p.get('consenso'))}), sin historia, "
            f"acotado entre {g_bajo} y {g_alto}"
        ),
        ("g_ref", "sin_dato"): (
            f"sin historia, y {sin_consenso}" if consenso_sin_red else "sin historia ni consenso"
        ),
        ("g_perpetuo", "criterio"): f"criterio fijo del programa para el {p.get('moneda')}",
        ("g_perpetuo", "recortado_a_r_f"): "recortado a la tasa libre de riesgo",
        ("roe_ref", "mediana_historica"): f"mediana de {p.get('anos')} años",
        ("roe_ref", "sin_dato"): "sin años suficientes",
        ("payout", "yfinance"): (
            f"según yfinance, acotado entre {_pct(_PAYOUT_TOPES[0])} "
            f"y {_pct(_PAYOUT_TOPES[1])}"
        ),
        ("payout", "por_defecto"): f"sin dato: se supone el {_pct(PAYOUT_SIN_DATO)}",
    }
    if fuente == "usuario":
        return _movido(nombre, p)
    texto = textos.get((nombre, fuente), "")
    if texto and p.get("recalculado") is True:
        texto += " (recalculado con tus supuestos)"
    return texto


def _movido(nombre: str, p: dict) -> str:
    """Un supuesto que movió el usuario, con lo que decía el programa."""
    programa = p.get("programa")
    if programa is None:
        # El programa no tenía ese supuesto (sin dato, o sin Bono M) y lo puso
        # el usuario.
        return "puesto por ti"
    valor = _decimales(programa, 2) if nombre == "beta" else _pct(programa)
    return f"movido por ti; el programa decía {valor}"


def _metodo_residual(valoracion: dict) -> bool:
    return valoracion.get("metodo") == "residual"


def _supuestos(valoracion: dict) -> str:
    supuestos = _dic(valoracion.get("supuestos"))
    usados = _SUPUESTOS_DE["residual" if _metodo_residual(valoracion) else "flujos"]
    lineas = []
    for nombre in usados:
        if nombre not in supuestos:
            continue
        supuesto = _dic(supuestos[nombre])
        valor = supuesto.get("valor")
        cifra = _decimales(valor, 2) if nombre == "beta" else _pct(valor)
        origen = procedencia(nombre, supuesto)
        lineas.append(f"{_NOMBRE_SUPUESTO[nombre]}: {cifra}" + (f" · {origen}" if origen else ""))
    if not lineas:
        return ""
    cuerpo = "".join(f"<div>{_esc(linea)}</div>" for linea in lineas)
    return (
        '<div class="mpp-val-sup">'
        f'<div class="mpp-val-sup-titulo">Supuestos del programa</div>{cuerpo}</div>'
    )


def resumen(valoracion: dict) -> str:
    """Los tres votos en una línea cada uno, el rango y la procedencia de los supuestos.

    No explica los términos: de eso se encarga `glosario()`, una vez por pantalla.
    """
    if not isinstance(valoracion, dict):
        return ""
    if "veredicto" not in valoracion:
        return (
            f'<div class="mpp-val">Sin valoración: '
            f'{_esc(etiqueta_motivo(valoracion.get("motivo")))}.</div>'
        )
    nombres = _NOMBRE_VOTO_RESIDUAL if _metodo_residual(valoracion) else NOMBRE_VOTO
    votos = _dic(valoracion.get("votos"))
    filas = []
    for clave in ("flujos", "sin_crecimiento", "pares"):
        voto = _dic(votos.get(clave))
        etiqueta, color = _entrada(VOTO, voto.get("voto"), ("n/d", tema.TEXTO_SUAVE))
        filas.append(
            '<div class="mpp-val-voto">'
            f'<span class="mpp-val-nombre">{_esc(nombres[clave])}</span>'
            f'<span class="mpp-val-etiqueta" style="color:{color}">{_esc(etiqueta)}</span>'
            f'<span class="mpp-val-detalle">{_esc(_detalle(clave, voto, valoracion))}</span>'
            "</div>"
        )
    return f'<div class="mpp-val">{_cabecera(valoracion)}{"".join(filas)}{_supuestos(valoracion)}</div>'


# --- Lo que rodea al resumen en la pantalla -------------------------------------
#
# «Valor intrínseco» y no «Valoración»: tres líneas más arriba, en la misma ficha,
# está el pilar «valoración» del score, y el voto «Frente a sus pares» es ese
# mismo pilar. Con el mismo nombre, el bloque y el pilar se leían como una cosa.
# «Sin valoración:» de una fallida se queda: ahí es el sustantivo, no el nombre.

TITULO_GLOSARIO = "💰 Cómo se lee el valor intrínseco"


def _con_veredicto(valoracion: object) -> bool:
    return isinstance(valoracion, dict) and "veredicto" in valoracion


def titulo(valoracion: object) -> str:
    """El encabezado del bloque en la ficha, en markdown.

    Sólo remite al glosario si hay votos y rango que leer. No cuenta lecturas ni
    votos: «cuatro lecturas que dan tres votos» es falso en una financiera, que
    tiene tres y dos.
    """
    if _con_veredicto(valoracion):
        return f"**Valor intrínseco** · los términos, en «{TITULO_GLOSARIO}», arriba"
    return "**Valor intrínseco**"


def pie(valoracion: object) -> "list[str]":
    """Las notas que van debajo del resumen, una por `st.caption`.

    Una fallida no lleva ninguna. La nota sobre el criterio va con cualquier
    veredicto; la lectura del margen, sólo si hay margen: cuando el voto de
    flujos no aplica (sin flujo libre, quema caja…) no hay rango, pero el EPV y
    los pares siguen dando veredicto, y explicar un margen que no se enseña
    confunde. La lectura depende del método, porque el voto de una financiera
    compara ROE y no crecimiento; con un método que no se reconoce, sólo la nota.
    """
    if not _con_veredicto(valoracion):
        return []
    if _numero(valoracion.get("margen_seguridad")) is None:
        return [NOTA]
    metodo = valoracion.get("metodo")
    if metodo == "flujos":
        return [lectura_margen(), NOTA]
    if metodo == "residual":
        return [lectura_margen_roe(), NOTA]
    return [NOTA]


# Los motivos que dispara el corte de `ranking/run.py`, con cuántas fichas
# **seguidas** hacen falta para que el fallo sea de la corrida y no de una
# empresa. Tras el corte la corrida deja de preguntar y todas las fichas que
# quedaban heredan ese motivo: el caso típico es 4 valoradas y 11
# `sin_tasa_libre`, y sin un aviso arriba hay que abrir once desplegables para
# saber que ni siquiera se intentó.
#
# La tasa libre es la misma para todas, así que un fallo ya es el corte. Un
# `sin_red` suelto, en cambio, es para `run.py` un símbolo que Yahoo no conoce:
# corta con `sin_red_seguidos >= 2`, y ese 2 se repite aquí (un test vigila que
# no se separen) porque importar `ranking.run` arrastraría pandas y la IA. Por
# lo mismo se mira la racha y no el total: dos `sin_red` separados por otra
# ficha no cortaron nada.
MOTIVOS_DE_CORRIDA = {"sin_tasa_libre": 1, "sin_red": 2}

# Las narrativas se guardan por contenido (`ranking.llm.redactar_con_cache`):
# regenerar con IA sobre los mismos datos las lee del disco sin pagar, y «Generar
# gratis» las tira. Un aviso que dijera «con IA vuelve a costar» empujaría justo
# a la opción que pierde la narrativa.
_PIE_REGENERAR = (
    "El orden y el resto de cada ficha no dependen del valor intrínseco. Para "
    "recalcularlo, vuelve a generar en el mismo modo: si era con IA, las "
    "narrativas ya redactadas salen de la caché sin volver a pagar mientras los "
    "datos no cambien."
)

# En el arranque normal de Windows (`Iniciar App.vbs`) la consola va oculta y su
# salida no se guarda en ningún sitio: el detalle del fallo que se está leyendo
# ya no se puede ver, sólo reproducir. «Salir del programa» y no «cierra la
# pestaña»: sin pestañas el servidor tarda 90 s en apagarse (`apagado.ESPERA`),
# y abrir el .bat antes manda el nuevo al puerto 8502, con dos servidores vivos.
_PIE_DEFECTO = (
    "Es un defecto del programa, no un problema de los datos. El detalle sale en "
    "la consola del programa, que en Windows va oculta y no se guarda: para "
    "verlo, pulsa «Salir del programa», ábrelo con «Iniciar App.bat», en su "
    "carpeta, y vuelve a generar en el mismo modo."
)


def _motivo_de(valoracion: object) -> "str | None":
    """El motivo de una fallida, o None.

    Sólo cuenta si la entrada es un diccionario y el motivo es texto: una ficha
    anterior a M, una valoración calculada (no lleva motivo) o un `fichas.json`
    tocado a mano con un motivo lista no pueden tumbar la lista entera.
    """
    motivo = valoracion.get("motivo") if isinstance(valoracion, dict) else None
    return motivo if isinstance(motivo, str) else None


def _racha_mas_larga(motivos: list, motivo: str) -> int:
    """Cuántas fichas seguidas llevan `motivo`, en el orden de la lista."""
    mejor = actual = 0
    for m in motivos:
        actual = actual + 1 if m == motivo else 0
        mejor = max(mejor, actual)
    return mejor


def aviso_comun(valoraciones: list) -> "str | None":
    """Un aviso para encima de la lista cuando el fallo es de la corrida y no de una empresa.

    Recibe lo que devuelve `valoracion_de` para cada ficha (diccionarios o
    None), en el orden de la corrida, que es el de `fichas.json`. Si todas
    fallaron por lo mismo, lo dice una vez. Si no, pero el corte de la corrida
    dejó fichas sin valorar, dice cuántas y por qué, de más a menos frecuente:
    hubo corte si la racha más larga de un motivo de `MOTIVOS_DE_CORRIDA` llega
    a su umbral, y entonces se cuentan todas las fichas con ese motivo. Un fallo
    suelto de una empresa, como `sin_estados` o un `sin_red` sin otro detrás, no
    sale aquí: se ve en su propia ficha, y regenerar no lo arregla.
    """
    motivos = [_motivo_de(v) for v in valoraciones]
    if motivos and motivos[0] is not None and motivos.count(motivos[0]) == len(motivos):
        comun = motivos[0]
        pie_aviso = _PIE_DEFECTO if comun == "error_interno" else _PIE_REGENERAR
        return f"No se pudo valorar ningún candidato: {etiqueta_motivo(comun)}. {pie_aviso}"
    cuenta = Counter(m for m in motivos if m in MOTIVOS_DE_CORRIDA)
    frases = [
        f"{cuantas} de {len(motivos)} candidatos sin valorar: {etiqueta_motivo(motivo)}."
        for motivo, cuantas in cuenta.most_common()
        if _racha_mas_larga(motivos, motivo) >= MOTIVOS_DE_CORRIDA[motivo]
    ]
    if not frases:
        return None
    return " ".join([*frases, _PIE_REGENERAR])

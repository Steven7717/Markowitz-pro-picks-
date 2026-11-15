"""La ficha y la valoración, dichas en palabras para el modelo.

**Aquí no sale un dígito.** El modelo tiene prohibido escribir cifras, y una
cifra pegada a esa regla es justo lo que copia: lo que ve de la valoración son
frases de un vocabulario cerrado que el código elige mirando los números. Los
umbrales son juicios, no medidas, y están aquí juntos para que se vean.

Cada lectura viaja con una letra —`A` flujos, `B` valor sin crecimiento, `C`
pares—, como las operaciones de `interprete/ajuste.py`: una observación sobre
una letra que no está en el mapa se cae sola.
"""

from ranking.run import contexto as contexto_de_ficha
from valoracion.criterio import MARGEN_MINIMO

# Por debajo de esto la regresión de la beta explica tan poco que el coste de
# capital que sale de ella pesa más de lo que debería.
R2_POCO_FIABLE = 0.10
# El crecimiento del escenario base frente al histórico, en puntos.
_CERCA = 0.02
_LEJOS = 0.10

LETRAS = (("A", "flujos"), ("B", "sin_crecimiento"), ("C", "pares"))
_NOMBRES = {"flujos": "Flujos descontados", "sin_crecimiento": "Valor sin crecimiento", "pares": "Frente a sus pares"}
_VOTO = {
    "barata": "apunta a que está barata",
    "cara": "apunta a que está cara",
    "neutra": "no se inclina a ningún lado",
    "no_aplica": "no se pudo hacer",
}
_VEREDICTO = {
    "infravalorada": "infravalorada",
    "sobrevalorada": "sobrevalorada",
    "mixtas": "señales mixtas",
    "en_rango": "en rango",
    "sin_datos": "sin datos suficientes",
}
_MULTIPLOS = {
    "barata": "múltiplos por debajo de los de su sector",
    "cara": "múltiplos por encima de los de su sector",
    "neutra": "múltiplos parecidos a los de su sector",
}


def contexto_tesis(analisis) -> str:
    """Lo que ve el modelo de la empresa al redactar la tesis.

    Con ficha, exactamente el de candidatos (`ranking.run.contexto`): el mismo
    texto da la misma clave de caché, y una ficha ya pagada no se paga otra vez.
    """
    if analisis.referencia is not None:
        return contexto_de_ficha(analisis.referencia.ficha)
    return (
        f"Empresa: {analisis.ticker}, sector {analisis.sector or 'sin clasificar'}.\n"
        "No hay comparación con sus pares del sector."
    )


def _grado(diferencia: float, cerca: float, lejos: float) -> str:
    if diferencia > lejos:
        return "muy por encima de"
    if diferencia > cerca:
        return "por encima de"
    if diferencia < -lejos:
        return "muy por debajo de"
    if diferencia < -cerca:
        return "por debajo de"
    return "en línea con"


def _exigencia(implicito: object) -> "str | None":
    """Lo que el precio exige frente a su referencia."""
    if not isinstance(implicito, dict):
        return None
    if implicito.get("fuera_de_limites"):
        return "lo que el precio exige queda fuera de lo que el modelo admite"
    valor, referencia = implicito.get("valor"), implicito.get("referencia")
    if valor is None or referencia is None:
        return None
    margen = implicito.get("margen") or MARGEN_MINIMO
    que = "una rentabilidad sobre el capital" if implicito.get("magnitud") == "roe" else "un crecimiento"
    return f"el precio exige {que} {_grado(valor - referencia, margen, 2 * margen)} su referencia"


def _apuesta(epv: object) -> "str | None":
    """Cuánto del precio depende de crecer."""
    parte = epv.get("parte_crecimiento") if isinstance(epv, dict) else None
    if parte is None:
        return None
    if parte <= 0:
        return "el negocio de hoy, sin crecer, ya vale tanto como el precio"
    if parte >= 0.5:
        return "la mayor parte del precio es apuesta por el crecimiento"
    if parte <= 0.2:
        return "casi todo el precio lo respalda el negocio de hoy, sin crecer"
    return "una parte apreciable del precio depende del crecimiento"


def contexto_valoracion(
    ticker: str, sector: "str | None", valoracion: object, movidos_dichos: str = ""
) -> "tuple[str, dict[str, str]] | None":
    """El bloque que lee el modelo y el mapa letra → lectura, o `None` sin votos.

    `movidos_dichos` es la lista de supuestos que movió el usuario, ya en
    palabras (`medidores_analizador.lista_de_supuestos`).
    """
    votos = valoracion.get("votos") if isinstance(valoracion, dict) else None
    if not votos:
        return None
    nombres = dict(_NOMBRES)
    if valoracion.get("metodo") == "residual":
        nombres["flujos"] = "Beneficio residual"
    voto_de = {nombre: (votos.get(nombre) or {}).get("voto") for _letra, nombre in LETRAS}
    detalle = {
        "flujos": _exigencia(valoracion.get("implicito")),
        "sin_crecimiento": _apuesta(valoracion.get("epv")),
        "pares": _MULTIPLOS.get(voto_de["pares"]),
    }
    lineas = [
        f"Empresa: {ticker}, sector {sector or 'sin clasificar'}.",
        f"Veredicto del programa: {_VEREDICTO.get(valoracion.get('veredicto'), 'sin veredicto')}.",
    ]
    mapa = {}
    for letra, nombre in LETRAS:
        voto = voto_de[nombre]
        if voto is None:
            continue
        partes = [_VOTO.get(voto, _VOTO["no_aplica"])]
        if voto in ("barata", "cara", "neutra") and detalle[nombre]:
            partes.append(detalle[nombre])
        lineas.append(f"[{letra}] {nombres[nombre]}: {'; '.join(partes)}.")
        mapa[letra] = nombre
    procedencia = ((valoracion.get("supuestos") or {}).get("beta") or {}).get("procedencia") or {}
    r2 = procedencia.get("r2")
    if isinstance(r2, (int, float)) and r2 < R2_POCO_FIABLE:
        lineas.append("La beta es poco fiable: el ajuste de la regresión es débil.")
    if movidos_dichos:
        lineas.append(f"El usuario movió estos supuestos del programa: {movidos_dichos}.")
    return "\n".join(lineas), mapa


def supuesto_crecimiento(valoracion: object, movidos_dichos: str = "") -> "str | None":
    """El supuesto central del escenario base, en una frase, para contrastarlo con el MD&A."""
    supuestos = valoracion.get("supuestos") if isinstance(valoracion, dict) else None
    if not supuestos:
        return None
    if valoracion.get("metodo") == "residual":
        frase = (
            "El escenario base supone que la rentabilidad sobre el capital se "
            "mantiene cerca de la que la empresa ha tenido estos años."
        )
    else:
        g_ref = supuestos.get("g_ref") or {}
        valor = g_ref.get("valor")
        if valor is None:
            return None
        historico = (g_ref.get("procedencia") or {}).get("historico")
        if historico is None:
            frase = (
                "El escenario base supone un crecimiento de los ingresos sin "
                "historia propia con la que compararlo."
            )
        else:
            frase = (
                "El escenario base supone que los ingresos crecen "
                f"{_grado(valor - historico, _CERCA, _LEJOS)} su ritmo de los últimos años."
            )
    if movidos_dichos:
        frase += f" El usuario movió estos supuestos del programa: {movidos_dichos}."
    return frase

# macro/lectura.py
"""La lectura con IA del entorno macro. Explica; no toca el Top.

Se guarda por región y mes del dato: con el mismo dato la explicación sería la
misma, así que preguntar dos veces en un mes no paga dos veces. Vive en
`lecturas_macro/`, fuera de git, como `analisis/`: lo pagó el usuario.
"""

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from pydantic import BaseModel

from interprete import cliente as cliente_ia
from macro import textos
from macro.criterio import SECTORES_POR_FASE
from noticias import cache

RAIZ = Path(__file__).resolve().parent.parent / "lecturas_macro"
_PARA_SIEMPRE = timedelta(days=36_500)

SISTEMA = (
    "Eres un analista macroeconómico. Explicas en castellano llano, sin jerga "
    "innecesaria, en qué fase del ciclo está una economía según los datos que se "
    "te dan, y qué indicadores conviene vigilar en los próximos meses. No "
    "recomiendas comprar ni vender nada. No inventas datos que no se te hayan dado."
)


class SalidaLectura(BaseModel):
    explicacion: str
    vigilar: list[str]


@dataclass(frozen=True)
class Lectura:
    explicacion: str = ""
    vigilar: tuple = ()
    coste_usd: float = 0.0
    problema: str = ""


def contexto_prompt(estado, contexto) -> str:
    fase = estado.fase
    listas = SECTORES_POR_FASE[fase.clave]
    nombres = lambda sectores: ", ".join(textos.NOMBRE_SECTOR[s] for s in sectores)
    ultimos = estado.serie.dropna().iloc[-12:]
    lineas = [
        f"Región: {textos.NOMBRE_REGION[estado.region]}.",
        f"Fase según el indicador adelantado de la OCDE: {textos.NOMBRE_FASE[fase.clave]}, "
        f"dato de {textos.mes_legible(fase.mes_dato)}, {fase.meses_en_fase} meses en ella.",
        "Últimos doce meses del indicador (100 es la tendencia): "
        + ", ".join(f"{d:%Y-%m} {v:.2f}" for d, v in ultimos.items()) + ".",
        f"Sectores que la fase favorece: {nombres(listas['favorecidos'])}.",
        f"Sectores que desfavorece: {nombres(listas['desfavorecidos'])}.",
    ]
    if contexto is not None:
        if contexto.curva is not None:
            lineas.append(f"Curva de tipos 10 años menos 3 meses: {contexto.curva:.2f} puntos.")
        if contexto.sahm is not None:
            lineas.append(f"Regla de Sahm: {contexto.sahm:.2f} (se activa en 0,50).")
        if contexto.inflacion is not None:
            lineas.append(f"Inflación interanual: {contexto.inflacion:.1%}.")
    lineas.append(
        "Explica la fase en dos o tres párrafos y da entre tres y cinco cosas que vigilar."
    )
    return "\n".join(lineas)


def leer(estado, contexto, *, raiz: Path = RAIZ, cliente=None) -> Lectura:
    if estado.fase is None or estado.fase.clave is None:
        return Lectura(problema="Sin una fase determinada no hay nada que leer.")

    llave = f"{estado.region}_{estado.fase.mes_dato.isoformat()}"
    guardada = cache.leer(raiz, "macro", llave, _PARA_SIEMPRE)
    if guardada is not None and isinstance(guardada.datos, dict):
        return Lectura(guardada.datos["explicacion"], tuple(guardada.datos["vigilar"]))

    respuesta = cliente_ia.preguntar(
        SISTEMA,
        [{"role": "user", "content": contexto_prompt(estado, contexto)}],
        SalidaLectura,
        cliente=cliente,
    )
    if respuesta.salida is None:
        return Lectura(problema=respuesta.problema)

    salida = respuesta.salida
    try:
        cache.guardar(raiz, "macro", llave, {"explicacion": salida.explicacion, "vigilar": salida.vigilar})
    except OSError:
        pass
    return Lectura(
        salida.explicacion,
        tuple(salida.vigilar),
        cliente_ia.coste(respuesta.entrada_tokens, respuesta.salida_tokens),
    )

"""La tesis y los riesgos de candidatos, para cualquier ticker con informe anual.

Es `ranking.llm.redactar_con_cache`, **sin tocar**: el mismo prompt, la misma
verificación de citas y la misma caché por contenido. Lo que añade este módulo
es el gasto: `ranking.llm` lo anota en un contador de módulo **que es del
proceso entero**, y una corrida de candidatos en otra sesión lo está usando (con
su tope de corrida). Por eso aquí **no se reinicia**: se toma una foto del
acumulado antes y otra después, y el gasto de esta llamada es la diferencia.

La única excepción es el acumulado al borde del tope: si ya no queda sitio
para una ficha, `redactar_con_cache` devolvería `None` sin llamar por un tope
que no es de esta pulsación, y entonces sí se reinicia.

Residuo conocido: con una corrida simultánea en otra sesión, la diferencia puede
incluir llamadas ajenas (y el reinicio del borde les pone a cero su contador).
No se arregla sin tocar `ranking/llm.py`.

`redactar_con_cache` devuelve `None` sin decir por qué —sin clave, la API
caída, una respuesta con cifras que sobrevivió al reintento—: la pantalla dice
que no se pudo y lo que costó, que es todo lo que se sabe.
"""

from dataclasses import dataclass
from pathlib import Path

from aprobacion import generacion
from ranking import llm


@dataclass(frozen=True)
class Redaccion:
    narrativa: "dict | None"
    # Si salió de la caché por contenido, sin llamar: no costó nada.
    de_cache: bool
    gasto: llm.Gasto


def redactar(contexto: str, riesgos: str, cliente=None, cache_dir: "Path | None" = None) -> Redaccion:
    """La narrativa de `ranking.llm` para este contexto y estos riesgos, con su gasto."""
    antes = llm.gasto_acumulado()
    # `generacion.coste_peor_caso` y no `ia_costes.tesis`: `ia_costes` importa
    # este mismo cálculo, y no hace falta un ciclo por una línea.
    if antes.usd + generacion.coste_peor_caso(1) >= llm.TOPE_USD_POR_CORRIDA:
        llm.reiniciar_gasto()
        antes = llm.gasto_acumulado()
    narrativa = llm.redactar_con_cache(contexto, riesgos, cache_dir=cache_dir, cliente=cliente)
    despues = llm.gasto_acumulado()
    gasto = llm.Gasto(
        llamadas=max(0, despues.llamadas - antes.llamadas),
        entrada_tokens=max(0, despues.entrada_tokens - antes.entrada_tokens),
        salida_tokens=max(0, despues.salida_tokens - antes.salida_tokens),
        tope_alcanzado=despues.tope_alcanzado and not antes.tope_alcanzado,
    )
    return Redaccion(narrativa, narrativa is not None and gasto.llamadas == 0, gasto)

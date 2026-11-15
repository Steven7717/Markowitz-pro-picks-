"""La tesis y los riesgos de candidatos, para cualquier ticker con informe anual.

Es `ranking.llm.redactar_con_cache`, **sin tocar**: el mismo prompt, la misma
verificación de citas y la misma caché por contenido. Lo que añade este módulo
es el gasto: `ranking.llm` lo anota en un contador de módulo, que se reinicia
antes de llamar y se lee después.

`redactar_con_cache` devuelve `None` sin decir por qué —sin clave, la API
caída, una respuesta con cifras que sobrevivió al reintento—: la pantalla dice
que no se pudo y lo que costó, que es todo lo que se sabe.
"""

from dataclasses import dataclass
from pathlib import Path

from ranking import llm


@dataclass(frozen=True)
class Redaccion:
    narrativa: "dict | None"
    # Si salió de la caché por contenido, sin llamar: no costó nada.
    de_cache: bool
    gasto: llm.Gasto


def redactar(contexto: str, riesgos: str, cliente=None, cache_dir: "Path | None" = None) -> Redaccion:
    """La narrativa de `ranking.llm` para este contexto y estos riesgos, con su gasto."""
    llm.reiniciar_gasto()
    narrativa = llm.redactar_con_cache(contexto, riesgos, cache_dir=cache_dir, cliente=cliente)
    gasto = llm.gasto_acumulado()
    return Redaccion(narrativa, narrativa is not None and gasto.llamadas == 0, gasto)

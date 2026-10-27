"""Dónde se guarda lo que la IA dice de un ticker del Analizador.

`analisis/<TICKER>.json`, en la raíz del programa, junto a `actas/` y
`libros/`, y fuera de git. N2 guarda ahí sólo las lecturas de los 8-K, con el
formato y las funciones de `interprete/archivo.py` tal cual: append-only, un
archivo ilegible no se trata como vacío ni se pisa, y lo ya leído se pinta sin
pagar. N3 añade aquí lo de los otros tres bloques.

**Aviso para N3.** `interprete.archivo.anotar_hechos` reescribe el fichero
entero con sólo `hechos` y `rebalanceo`: una clave más que N3 guarde en el
mismo fichero se perdería en la siguiente lectura de 8-K si antes no cambia
cómo se escribe.
"""

from pathlib import Path

# Relativa, como `aprobacion.acta.ACTAS` y `seguimiento.libro.DIRECTORIO`: los
# lanzadores arrancan en programa/.
DIRECTORIO = Path("analisis")


def ruta_de(ticker: str) -> Path:
    """`analisis/<TICKER>.json`.

    El ticker llega normalizado (`resolver.normalizar`): letras, dígitos y
    `.-=&^`, que Windows admite en el nombre de un fichero.
    """
    return DIRECTORIO / f"{ticker}.json"

"""El envoltorio con que `AppTest` ejecuta una pantalla de `vistas/`.

Lo mismo que `guion_analizador.py`, para cualquier pantalla: `AppTest.from_file`
sobre `vistas/x.py` pone `vistas/` delante en `sys.path`, y entonces
`from analizador import sesion` encuentra la pantalla del Analizador en vez del
paquete. Este guion deja `programa/` delante y ejecuta la pantalla que diga la
variable de entorno `GUION_VISTA` (p. ej. `entorno_macro.py`) con `runpy`.

No es un test: lo usan los `test_pantalla_*.py`.
"""

import os
import runpy
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
try:
    runpy.run_path(str(RAIZ / "vistas" / os.environ["GUION_VISTA"]), run_name="__main__")
finally:
    sys.path.remove(str(RAIZ))

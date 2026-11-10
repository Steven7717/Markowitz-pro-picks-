"""El envoltorio con que `AppTest` ejecuta la pantalla del Analizador.

`AppTest.from_file("vistas/analizador.py")` pone `vistas/` delante en
`sys.path`, y entonces `import analizador` encuentra la pantalla en vez del
paquete: un import circular que en la app real no existe, porque `app.py`
arranca desde `programa/`. Este guion vive fuera de `vistas/`, deja `programa/`
delante y ejecuta la pantalla con `runpy`, como la ejecutaría la app.

No es un test: lo usa `test_pantalla_analizador.py`.
"""

import runpy
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
try:
    runpy.run_path(str(RAIZ / "vistas" / "analizador.py"), run_name="__main__")
finally:
    sys.path.remove(str(RAIZ))

# macro/informe.py
"""El entorno macro tal y como lo cuenta el informe PDF del optimizador.

Dos piezas, como el resto del paquete:

- `recoger` trae lo que haga falta (OCDE, FRED, la lectura ya pagada) y **no
  revienta nunca**: el PDF es del portafolio, y una OCDE caída no puede
  llevárselo por delante. Tampoco paga: la lectura con IA sólo entra si ya se
  pagó desde la pantalla «Entorno macro» para esta región y este mes del dato.
- `declaraciones` lo convierte en filas (etiqueta, valor) y párrafos, con las
  mismas palabras que la pantalla (`macro/textos.py`), para que el papel y el
  monitor no puedan decir cosas distintas del mismo mes.

**El optimizador no usa la fase.** Los pesos no se inclinan por el ciclo —eso
sólo lo hace la casilla de Revisar candidatos sobre el Top—, y el informe lo
dice en vez de dejar que el lector lo suponga.
"""

from dataclasses import dataclass
from datetime import date

from macro import lectura as lectura_mod
from macro import textos
from macro.contexto import traer_contexto as _traer_contexto
from macro.criterio import SECTORES_POR_FASE
from macro.estado import leer_region

NO_INTERVIENE = (
    "El entorno macro no interviene en los pesos de este portafolio: el "
    "optimizador no se inclina por la fase del ciclo. Se incluye como contexto."
)


@dataclass(frozen=True)
class EntornoPDF:
    region: str
    estado: object = None          # macro.estado.Estado
    contexto: object = None        # macro.contexto.ContextoUSA (sólo EE. UU.)
    series_fred: "dict | None" = None
    lectura: object = None         # macro.lectura.Lectura ya pagada, o None
    problema: "str | None" = None  # si traerlo falló de una forma no prevista


def recoger(
    region: str,
    hoy: date,
    *,
    leer=leer_region,
    traer_contexto=_traer_contexto,
    raiz=lectura_mod.RAIZ,
) -> EntornoPDF:
    try:
        estado = leer(region, hoy)
    except Exception as error:  # noqa: BLE001 — el informe sale igual
        return EntornoPDF(region, problema=f"No se pudo leer el indicador de la OCDE ({error}).")

    contexto = series = None
    if region == "usa":
        try:
            contexto, series = traer_contexto()
        except Exception:  # noqa: BLE001 — el contexto es accesorio
            contexto = series = None

    try:
        guardada = lectura_mod.guardada(estado, raiz=raiz)
    except Exception:  # noqa: BLE001 — una caché ilegible no es motivo de fallo
        guardada = None
    return EntornoPDF(region, estado, contexto, series, guardada)


def _sectores(claves) -> str:
    return ", ".join(textos.NOMBRE_SECTOR.get(s, s) for s in claves)


def _motivo(clave) -> str:
    return textos.MOTIVO.get(clave, f"No se puede leer la fase ({clave}).")


def _coma(texto: str) -> str:
    return texto.replace(".", ",")


def declaraciones(entorno: EntornoPDF) -> tuple[list[tuple[str, str]], list[str]]:
    """Las filas de la tabla y los párrafos que van debajo, en ese orden."""
    region = textos.NOMBRE_REGION.get(entorno.region, entorno.region)
    filas: list[tuple[str, str]] = [("Región", region)]
    parrafos: list[str] = []

    if entorno.problema:
        return filas, [entorno.problema, NO_INTERVIENE]

    estado = entorno.estado
    fase = estado.fase
    if fase is None or fase.nivel is None:
        return filas, [_motivo(estado.motivo_no_inclinar), NO_INTERVIENE]

    if fase.clave is None:
        filas.append(("Fase del ciclo (CLI de la OCDE)", "Indeterminada"))
        parrafos.append(_motivo(fase.motivo))
    else:
        filas.append(("Fase del ciclo (CLI de la OCDE)", textos.NOMBRE_FASE[fase.clave]))
        filas.append(("Meses en esta fase", str(fase.meses_en_fase)))
    nivel = textos.cifra(fase.nivel)
    if fase.cambio is not None:
        nivel += _coma(f" ({fase.cambio:+.2f} en 3 meses)")
    filas.append(("Indicador adelantado (100 = tendencia)", nivel))
    if fase.mes_dato is not None:
        filas.append(("Mes del dato", textos.mes_legible(fase.mes_dato)))

    if estado.vieja:
        parrafos.append("La OCDE no respondió: esto es lo último que se guardó.")
    if estado.motivo_no_inclinar == "dato_rancio":
        parrafos.append(textos.MOTIVO["dato_rancio"])

    if fase.clave is not None:
        listas = SECTORES_POR_FASE[fase.clave]
        filas.append(("Suele favorecer", _sectores(listas["favorecidos"])))
        filas.append(("Suele desfavorecer", _sectores(listas["desfavorecidos"])))
        por_que = textos.POR_QUE.get(fase.clave, {})
        for lado in ("favorecidos", "desfavorecidos"):
            for sector in listas[lado]:
                if sector in por_que:
                    parrafos.append(f"{textos.NOMBRE_SECTOR.get(sector, sector)}: {por_que[sector]}")

    contexto = entorno.contexto
    if contexto is not None:
        filas.append(("Curva 10 años - 3 meses (EE. UU.)",
                      "-" if contexto.curva is None else _coma(f"{contexto.curva:+.2f}")))
        filas.append(("Regla de Sahm (EE. UU.)",
                      "-" if contexto.sahm is None else textos.cifra(contexto.sahm)))
        inflacion = "-" if contexto.inflacion is None else _coma(f"{contexto.inflacion:.1%}")
        if contexto.inflacion is not None and contexto.mes_inflacion is not None:
            inflacion += f" ({textos.mes_legible(contexto.mes_inflacion)})"
        filas.append(("Inflación interanual (EE. UU.)", inflacion))
        if contexto.curva_invertida:
            parrafos.append("La curva está invertida: históricamente ha precedido a las recesiones.")
        if contexto.sahm_activada:
            parrafos.append("La regla de Sahm está activada: el desempleo sube como al empezar una recesión.")
        series = entorno.series_fred or {}
        for nombre, valor in (("curva", contexto.curva), ("desempleo", contexto.sahm),
                              ("ipc", contexto.inflacion)):
            if nombre in series:
                nota = textos.nota_fred(series[nombre], valor is not None)
                if nota:
                    parrafos.append(nota)
        if any(s.vieja and s.datos is not None for s in series.values()):
            parrafos.append(textos.AVISO_FRED_VIEJA)
        parrafos.append("El contexto de EE. UU. no entra en la fase: se enseña al lado.")

    parrafos.append(textos.AVISO_EVIDENCIA)

    if entorno.lectura is not None:
        parrafos.append(f"Lectura con IA (guardada para este mes del dato): {entorno.lectura.explicacion}")
        if entorno.lectura.vigilar:
            parrafos.append("Qué vigilar: " + "; ".join(p.rstrip(". ") for p in entorno.lectura.vigilar) + ".")

    parrafos.append(NO_INTERVIENE)
    return filas, parrafos

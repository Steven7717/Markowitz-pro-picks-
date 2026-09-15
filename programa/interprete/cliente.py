"""La llamada, y su degradacion. Lo unico que toca Anthropic.

Mismo contrato que `ranking/llm.py`: sin clave, o con la API caida, se devuelve
una `Respuesta` con `salida=None` y `problema` puesto, y quien llama sigue su
camino con las manos vacias pero sin romperse.

Vive en su propio modulo porque lo usan las dos mitades --hechos y
rebalanceo--, y una tercera copia de la misma llamada seria una tercera copia
que mantener.
"""

import os
from dataclasses import dataclass

MODELO = "claude-sonnet-5"
MAX_TOKENS = 2000

# Precio de `claude-sonnet-5` por millon de tokens, tarifa de Anthropic al
# 2026-06-24. Vive junto a `MODELO` a proposito: quien cambie el modelo tiene
# que cambiar el precio en la misma pantalla, o la app dira un coste que no es.
PRECIO_ENTRADA = 2.00
PRECIO_SALIDA = 10.00

# El tope duro de una pulsacion, en dolares.
#
# `ranking/llm.py` tiene el suyo --`TOPE_USD_POR_CORRIDA`-- desde que se vio
# que nada impedia que quince fichas se convirtieran en treinta llamadas. Este
# camino no tenia ninguno, y es el que mas se pulsa: Noticias y Rebalanceo van
# a diario, mientras que el ranking se genera de uvas a peras. El disparador es
# el mismo y lo controla el mismo tercero: al documento le basta con inducir un
# digito o una cita que no verifique para que el segundo turno salga siempre.
#
# 0,50 $ es holgado a proposito, igual que el 2,50 de la corrida. El peor caso
# de una pulsacion de seis hechos son 0,27 $ --ver
# `vistas/panel_ia.py:coste_peor_caso`--, asi que esto no puede saltar en una
# pulsacion normal: si salta, algo se salio de lo previsto y lo correcto es
# dejar de gastar y entregar lo que ya se tiene, que es exactamente la
# degradacion que las dos mitades ya saben hacer cuando el reintento se agota.
TOPE_USD_POR_PULSACION = 0.50


@dataclass(frozen=True)
class Respuesta:
    """Lo que volvio, lo que costo, y **por que** no volvio si no volvio.

    Antes esto era `parsed_output` o `None`, y el docstring lo justificaba
    diciendo que quien llama no puede hacer nada distinto con cada fallo. Era
    falso: el usuario que ve «o la llamada fallo, o traia cifras» no sabe si
    reintentar o si el problema es el prompt. `problema` existe para que la
    pantalla pueda decirselo.

    Los tokens vienen de `usage`, que la API devuelve siempre y que antes se
    tiraba entera: la informacion del coste llegaba y se descartaba.
    """

    salida: object = None
    entrada_tokens: int = 0
    salida_tokens: int = 0
    problema: str = ""


def coste(entrada_tokens: int, salida_tokens: int) -> float:
    """Lo que cuesta una llamada, en dolares."""
    return (entrada_tokens * PRECIO_ENTRADA + salida_tokens * PRECIO_SALIDA) / 1_000_000


def dentro_del_tope(entrada_tokens: int, salida_tokens: int) -> bool:
    """Si a lo gastado en esta pulsacion le queda margen para otra llamada.

    Se pregunta **antes** de llamar y no despues, por la misma razon que en
    `ranking/llm.py:redactar`: despues ya se gasto. Quien llama lleva su propia
    cuenta de tokens --las dos mitades la llevan ya, porque la `Lectura` y el
    `Comentario` la ensenan en pantalla-- y aqui solo se decide.

    Es una funcion y no una comparacion escrita en cada mitad porque son dos:
    `noticias.leer` y `ajuste.comentar` tienen el mismo bucle de dos turnos, y
    dos copias de una decision de gasto se separan igual de facil que dos
    copias de cualquier otra.
    """
    return coste(entrada_tokens, salida_tokens) < TOPE_USD_POR_PULSACION


def hay_clave() -> bool:
    """Si se puede llamar.

    La pantalla lo necesita para decir `SIN_CLAVE` **antes** de preparar nada:
    bajar seis documentos de EDGAR para descubrir despues que no hay clave son
    seis descargas tiradas y varios segundos de espera por nada.
    """
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def preguntar(sistema: str, mensajes: list, esquema, cliente=None, modelo: str = MODELO) -> Respuesta:
    """Llamar al modelo. Devuelve una `Respuesta`, nunca `None`.

    Sin clave, con la API caida, con una respuesta que no valida contra
    `esquema`, o con `parsed_output` vacio, se devuelve una `Respuesta` con
    `salida=None` y `problema` puesto a por que: antes esos cuatro casos se
    colapsaban en `None` y quien llama no podia distinguirlos, y esa
    distincion si le sirve a quien recibe el resultado en pantalla.

    Cuando sale bien, `entrada_tokens` y `salida_tokens` salen de
    `respuesta.usage`, que la API devuelve siempre y que antes se tiraba
    entera junto con el resto de la respuesta.

    `cliente` se inyecta para probar sin red y sin clave, y **si viene, manda**:
    construir uno propio pese a haberlo recibido haria que los tests tocaran la
    API de verdad.
    """
    import anthropic
    from pydantic import ValidationError

    if cliente is None:
        if not hay_clave():
            return Respuesta(problema="Falta la clave de Anthropic.")
        cliente = anthropic.Anthropic()

    try:
        respuesta = cliente.messages.parse(
            model=modelo,
            max_tokens=MAX_TOKENS,
            system=sistema,
            messages=mensajes,
            output_format=esquema,
            thinking={"type": "disabled"},
        )
    except anthropic.APIError as error:
        return Respuesta(problema=f"La API no respondio: {error}")
    except ValidationError as error:
        return Respuesta(
            problema=f"La respuesta no encaja con lo que se esperaba: {error}"
        )

    if not respuesta.parsed_output:
        return Respuesta(problema="La respuesta vino vacia.")

    uso = getattr(respuesta, "usage", None)
    return Respuesta(
        salida=respuesta.parsed_output,
        entrada_tokens=getattr(uso, "input_tokens", 0),
        salida_tokens=getattr(uso, "output_tokens", 0),
    )

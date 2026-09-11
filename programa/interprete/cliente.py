"""La llamada, y su degradacion. Lo unico que toca Anthropic.

Mismo contrato que `ranking/llm.py`: sin clave, o con la API caida, se devuelve
`None` y quien llama sigue su camino con las manos vacias pero sin romperse.

Vive en su propio modulo porque lo usan las dos mitades --hechos y
rebalanceo--, y una tercera copia de la misma llamada seria una tercera copia
que mantener.
"""

import os

MODELO = "claude-sonnet-5"
MAX_TOKENS = 2000


def hay_clave() -> bool:
    """Si se puede llamar.

    La pantalla lo necesita para decir `SIN_CLAVE` **antes** de preparar nada:
    bajar seis documentos de EDGAR para descubrir despues que no hay clave son
    seis descargas tiradas y varios segundos de espera por nada.
    """
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def preguntar(sistema: str, mensajes: list, esquema, cliente=None, modelo: str = MODELO):
    """La respuesta ya parseada contra `esquema`, o `None`.

    `None` cubre los cuatro casos en los que no hay nada de que fiarse: no hay
    clave, la API fallo, la respuesta no valida contra el esquema, o
    `parsed_output` vino vacio. Quien llama no los distingue porque no puede
    hacer nada distinto con ninguno.

    `cliente` se inyecta para probar sin red y sin clave, y **si viene, manda**:
    construir uno propio pese a haberlo recibido haria que los tests tocaran la
    API de verdad.
    """
    import anthropic
    from pydantic import ValidationError

    if cliente is None:
        if not hay_clave():
            return None
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
    except (anthropic.APIError, ValidationError):
        return None
    return respuesta.parsed_output

"""La valoración como diccionario, para `fichas.json` y el acta.

Se guardan **claves, nunca textos de pantalla**: las etiquetas viven en
`medidores_valoracion.py`. Todo NaN se escribe como `null`, porque
`fichas.json` se escribe con `allow_nan=False` y ese es su contrato.
"""

import math
from dataclasses import fields
from datetime import date
from typing import TYPE_CHECKING

from valoracion.criterio import VERSION

if TYPE_CHECKING:
    from valoracion.motor import Valoracion


def _limpio(objeto):
    """Recorre lo que se va a escribir y cambia cada NaN o infinito por `None`."""
    if isinstance(objeto, dict):
        return {clave: _limpio(valor) for clave, valor in objeto.items()}
    if isinstance(objeto, (list, tuple)):
        return [_limpio(valor) for valor in objeto]
    if isinstance(objeto, float) and not math.isfinite(objeto):
        return None
    return objeto


def a_dict(v: "Valoracion") -> dict:
    return _limpio(
        {
            "version": VERSION,
            "fecha": v.fecha.isoformat(),
            "estados_hasta": v.estados_hasta.isoformat(),
            "moneda": v.moneda,
            "precio": v.precio,
            "precio_hora": v.precio_hora,
            "metodo": v.metodo,
            "valor": None
            if v.valor is None
            else {
                "pesimista": v.valor.pesimista,
                "base": v.valor.base,
                "optimista": v.valor.optimista,
            },
            "margen_seguridad": v.margen_seguridad,
            "implicito": None
            if v.implicito is None
            else {
                "magnitud": v.implicito.magnitud,
                "valor": v.implicito.valor,
                "referencia": v.implicito.referencia,
                "margen": v.implicito.margen,
                "fuera_de_limites": v.implicito.fuera_de_limites,
            },
            "epv": None
            if v.epv is None
            else {
                "por_accion": v.epv.por_accion,
                "parte_crecimiento": v.epv.parte_crecimiento,
            },
            "votos": {
                nombre: {"voto": voto.voto, "motivo": voto.motivo}
                for nombre, voto in v.votos.items()
            },
            "veredicto": v.veredicto,
            "supuestos": {
                campo.name: {
                    "valor": getattr(v.supuestos, campo.name).valor,
                    "procedencia": getattr(v.supuestos, campo.name).procedencia,
                }
                for campo in fields(v.supuestos)
            },
        }
    )


def fallida(motivo: str, hoy: "date | None" = None) -> dict:
    """Una valoración que no llegó a calcularse: su motivo y nada más."""
    return {"version": VERSION, "fecha": (hoy or date.today()).isoformat(), "motivo": motivo}

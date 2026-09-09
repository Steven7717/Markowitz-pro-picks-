import json

import pytest

from seguimiento import libro


def _libro(**kwargs):
    return libro.Libro(nombre="prueba", creado="2026-01-01", **kwargs)


def test_por_defecto_no_hay_fracciones_ni_plan():
    l = _libro()
    assert l.fracciones is False
    assert l.aportacion_prevista is None


def test_se_guardan_y_se_leen(tmp_path):
    l = _libro(
        fracciones=True,
        aportacion_prevista=libro.AportacionPrevista(500.0, "mensual"),
    )
    vuelto = libro.cargar(libro.guardar(l, tmp_path))
    assert vuelto.fracciones is True
    assert vuelto.aportacion_prevista == libro.AportacionPrevista(500.0, "mensual")


def test_un_libro_viejo_sin_los_campos_se_abre_igual(tmp_path):
    """Los libros que ya existen en el disco del usuario no pueden romperse.

    `cargar` lee campo a campo con `crudo.get(...)` -- asi entraron `moneda` y
    `objetivos` -- y esta prueba fija que sigue siendo asi. Un fichero escrito
    antes de esta tarea no tiene las claves nuevas.
    """
    ruta = tmp_path / "viejo.json"
    ruta.write_text(
        json.dumps({"nombre": "viejo", "creado": "2026-01-01", "asientos": []}),
        encoding="utf-8",
    )
    vuelto = libro.cargar(ruta)
    assert vuelto.fracciones is False
    assert vuelto.aportacion_prevista is None


def test_una_cadencia_inventada_no_se_acepta():
    with pytest.raises(ValueError):
        libro.AportacionPrevista(500.0, "cuando me apetezca")


def test_un_importe_previsto_no_positivo_no_se_acepta():
    """Prever aportar cero o menos no es prever nada; es None."""
    with pytest.raises(ValueError):
        libro.AportacionPrevista(0.0, "mensual")
    with pytest.raises(ValueError):
        libro.AportacionPrevista(-100.0, "mensual")


def test_un_importe_previsto_no_finito_no_se_acepta():
    """Misma guarda que los asientos: NaN atraviesa toda comparacion.

    `nan <= 0` es False y NaN es truthy, asi que ninguna guarda de «mayor que
    cero» lo caza. Y entra desde disco sin que nadie lo teclee, porque
    `json.loads` acepta el literal NaN.
    """
    with pytest.raises(ValueError):
        libro.AportacionPrevista(float("nan"), "mensual")
    with pytest.raises(ValueError):
        libro.AportacionPrevista(float("inf"), "mensual")


def test_una_aportacion_prevista_corrupta_en_disco_se_nombra(tmp_path):
    ruta = tmp_path / "malo.json"
    ruta.write_text(
        json.dumps({
            "nombre": "malo", "creado": "2026-01-01", "asientos": [],
            "aportacion_prevista": {"importe": 500.0, "cadencia": "semanal"},
        }),
        encoding="utf-8",
    )
    with pytest.raises(libro.LibroIlegible):
        libro.cargar(ruta)


def test_prevista_no_es_un_asiento_de_aportacion():
    """El nombre lleva «prevista» para que no se confundan.

    Una es dinero que entro y vive en `asientos`; la otra es un plan y vive en
    el libro. Si alguien fusionara las dos, el capital aportado incluiria
    dinero que nunca llego y el rendimiento saldria hundido sin causa visible.
    """
    l = _libro(aportacion_prevista=libro.AportacionPrevista(500.0, "mensual"))
    assert l.asientos == ()

from itertools import chain

from fundamentals.kpis import TODOS_LOS_KPIS
from ranking import criterio


def test_los_pilares_cubren_los_17_kpis_sin_solaparse():
    asignados = list(chain.from_iterable(criterio.PILARES.values()))
    assert len(asignados) == len(set(asignados)), "algún KPI está en dos pilares"
    assert set(asignados) == set(TODOS_LOS_KPIS)


def test_los_17_kpis_tienen_signo_declarado():
    # Un KPI sin signo produciría un ranking plausible y al revés.
    assert set(criterio.SIGNOS) == set(TODOS_LOS_KPIS)
    assert set(criterio.SIGNOS.values()) <= {1, -1}


def test_los_multiplos_y_la_deuda_van_invertidos():
    # Un PER alto significa caro, no bueno.
    for kpi in criterio.PILARES["valoracion"]:
        assert criterio.SIGNOS[kpi] == -1, kpi
    assert criterio.SIGNOS["deuda_neta_ebitda"] == -1


def test_los_pesos_suman_uno_y_cubren_los_pilares():
    assert sum(criterio.PESOS.values()) == 1.0
    assert set(criterio.PESOS) == set(criterio.PILARES)


def test_los_demas_kpis_van_en_signo_natural():
    # Sin esto, un signo volteado por error de copia en cualquiera de los doce
    # restantes pasaría los cuatro tests anteriores sin dejar rastro.
    invertidos = {"per", "ev_ebitda", "precio_fcf", "precio_valor_libro", "deuda_neta_ebitda"}
    for kpi, signo in criterio.SIGNOS.items():
        if kpi not in invertidos:
            assert signo == 1, kpi


def test_los_pilares_exigidos_coinciden_con_los_ponderados():
    # Si se exigieran menos pilares de los que pesan, una empresa con un pilar
    # sin medir pasaría las guardas y su compuesto saldría NaN por min_count.
    # marcar_sin_pares la etiquetaría entonces como "sin_dispersion_sectorial",
    # que es falso: la causa sería la cobertura, no el sector. Este test existe
    # para que una enmienda del criterio rompa aquí y no en el informe.
    assert criterio.MIN_PILARES_CON_DATO == len(criterio.PESOS)

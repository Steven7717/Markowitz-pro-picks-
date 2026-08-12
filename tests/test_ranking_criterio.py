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

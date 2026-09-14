import pandas as pd
import pytest

from seguimiento import posiciones, precios
from seguimiento.libro import Asiento


def asiento(id_, fecha, tipo, **campos) -> Asiento:
    return Asiento(id=id_, fecha=fecha, tipo=tipo, **campos)


APORTA = asiento("a1", "2026-01-05", "aportacion", importe=10_000.0)
COMPRA = asiento(
    "a2", "2026-01-05", "compra", ticker="AAPL",
    acciones=40.0, precio=200.0, importe=8000.0, comision=1.0,
)


def test_una_compra_deja_acciones_y_baja_el_efectivo():
    estado = posiciones.estado([APORTA, COMPRA])
    assert estado.acciones == {"AAPL": 40.0}
    # 10.000 menos 8.000 de compra menos 1 de comision.
    assert estado.efectivo == pytest.approx(1999.0)


def test_la_comision_sale_del_efectivo_y_no_del_aire():
    # Si la comision no bajara el efectivo, el libro cuadraria con mas dinero
    # del que hay y la primera venta descuadraria sin motivo visible.
    sin = posiciones.estado([APORTA, asiento(
        "a2", "2026-01-05", "compra", ticker="AAPL",
        acciones=40.0, precio=200.0, importe=8000.0,
    )])
    assert sin.efectivo - posiciones.estado([APORTA, COMPRA]).efectivo == pytest.approx(1.0)


def test_una_venta_devuelve_efectivo_menos_comision():
    venta = asiento(
        "a3", "2026-02-05", "venta", ticker="AAPL",
        acciones=10.0, precio=250.0, importe=2500.0, comision=1.0,
    )
    estado = posiciones.estado([APORTA, COMPRA, venta])
    assert estado.acciones == {"AAPL": 30.0}
    assert estado.efectivo == pytest.approx(1999.0 + 2499.0)


def test_un_ticker_que_se_vende_entero_desaparece_de_las_posiciones():
    # Dejar "AAPL: 0.0" haria que la tabla mostrara una fila de una empresa que
    # ya no se tiene, con peso cero y precio de hoy: ruido que parece dato.
    venta = asiento(
        "a3", "2026-02-05", "venta", ticker="AAPL",
        acciones=40.0, precio=250.0, importe=10_000.0,
    )
    assert posiciones.estado([APORTA, COMPRA, venta]).acciones == {}


def test_un_dividendo_entra_en_efectivo():
    dividendo = asiento(
        "a3", "2026-02-10", "dividendo", ticker="AAPL", importe=9.6
    )
    estado = posiciones.estado([APORTA, COMPRA, dividendo])
    assert estado.efectivo == pytest.approx(1999.0 + 9.6)


def test_un_asiento_anulado_deja_de_contar():
    anulacion = asiento("a3", "2026-01-06", "anulacion", anula="a2")
    estado = posiciones.estado([APORTA, COMPRA, anulacion])
    assert estado.acciones == {}
    assert estado.efectivo == pytest.approx(10_000.0)


def test_la_propia_anulacion_tampoco_cuenta_como_asiento():
    anulacion = asiento("a3", "2026-01-06", "anulacion", anula="a2", importe=0.0)
    assert posiciones.vigentes([APORTA, COMPRA, anulacion]) == [APORTA]


def test_el_estado_se_puede_pedir_a_una_fecha_pasada():
    venta = asiento(
        "a3", "2026-02-05", "venta", ticker="AAPL",
        acciones=10.0, precio=250.0, importe=2500.0,
    )
    estado = posiciones.estado([APORTA, COMPRA, venta], hasta="2026-01-31")
    assert estado.acciones == {"AAPL": 40.0}


def test_los_asientos_desordenados_dan_el_mismo_estado():
    # El fichero se escribe en orden de alta, pero nada garantiza que alguien no
    # lo reordene a mano. El estado no puede depender de eso.
    revuelto = posiciones.estado([COMPRA, APORTA])
    derecho = posiciones.estado([APORTA, COMPRA])
    assert revuelto.acciones == derecho.acciones
    assert revuelto.efectivo == pytest.approx(derecho.efectivo)


def historia(cierres: dict, splits: dict | None = None, dividendos: dict | None = None):
    fechas = pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-07"])
    ceros = {t: [0.0] * 3 for t in cierres}
    return precios.Historia(
        cierres=pd.DataFrame(cierres, index=fechas),
        dividendos=pd.DataFrame(dividendos or ceros, index=fechas),
        splits=pd.DataFrame(splits or ceros, index=fechas),
        sin_datos=[],
    )


def test_el_valor_diario_suma_acciones_por_cierre_mas_efectivo():
    h = historia({"AAPL": [200.0, 202.0, 204.0]})
    marcha = posiciones.serie([APORTA, COMPRA], h)
    # Dia 5: 40 acciones a 200 = 8.000, mas 1.999 de efectivo.
    assert marcha.valor.loc["2026-01-05"] == pytest.approx(9999.0)
    assert marcha.valor.loc["2026-01-07"] == pytest.approx(40 * 204.0 + 1999.0)


def test_un_split_multiplica_las_acciones_compradas_antes():
    h = historia(
        {"AAPL": [200.0, 202.0, 51.0]},
        splits={"AAPL": [0.0, 0.0, 4.0]},
    )
    marcha = posiciones.serie([APORTA, COMPRA], h)
    # 40 acciones a 200 pasan a 160 a 51: el valor apenas se mueve, que es lo
    # que de verdad ocurre. Sin aplicar el split, la cartera "perderia" un 75%.
    assert marcha.acciones.loc["2026-01-07", "AAPL"] == pytest.approx(160.0)
    assert marcha.valor.loc["2026-01-07"] == pytest.approx(160 * 51.0 + 1999.0)


def test_los_flujos_externos_son_solo_aportaciones_y_retiros():
    # Un dividendo o una compra no son dinero del usuario entrando: contarlos
    # aqui inflaria el capital aportado con lo que la cartera acaba de ganar.
    dividendo = asiento("a3", "2026-01-06", "dividendo", ticker="AAPL", importe=9.6)
    h = historia({"AAPL": [200.0, 202.0, 204.0]})
    marcha = posiciones.serie([APORTA, COMPRA, dividendo], h)
    assert marcha.flujos.loc["2026-01-05"] == pytest.approx(10_000.0)
    assert marcha.flujos.loc["2026-01-06"] == pytest.approx(0.0)


def test_el_dividendo_calculado_entra_en_efectivo():
    h = historia(
        {"AAPL": [200.0, 202.0, 204.0]},
        dividendos={"AAPL": [0.0, 0.24, 0.0]},
    )
    marcha = posiciones.serie([APORTA, COMPRA], h)
    # 40 acciones por 0,24 = 9,60 que entran el dia 6 y siguen el dia 7.
    assert marcha.efectivo.loc["2026-01-07"] == pytest.approx(1999.0 + 9.6)


def test_un_dividendo_apuntado_a_mano_manda_sobre_el_calculado():
    # El calculado es teorico y bruto; el escrito por el usuario es el neto que
    # le llego de verdad. Sumar los dos contaria el cobro dos veces.
    manual = asiento("a3", "2026-01-06", "dividendo", ticker="AAPL", importe=7.1)
    h = historia(
        {"AAPL": [200.0, 202.0, 204.0]},
        dividendos={"AAPL": [0.0, 0.24, 0.0]},
    )
    marcha = posiciones.serie([APORTA, COMPRA, manual], h)
    assert marcha.efectivo.loc["2026-01-07"] == pytest.approx(1999.0 + 7.1)


def test_una_compra_en_la_fecha_ex_no_cobra_ese_dividendo():
    # Para cobrar hay que tener las acciones ANTES de la fecha ex: quien compra
    # ese mismo dia las compra ya sin el dividendo, y el cobro es del vendedor.
    # Medido sobre la version que aplicaba los asientos antes de pagar: una
    # compra de diez acciones el dia ex se llevaba 2,40 que no le tocaban.
    tardia = asiento(
        "a3", "2026-01-06", "compra", ticker="AAPL",
        acciones=10.0, precio=202.0, importe=2020.0,
    )
    h = historia(
        {"AAPL": [200.0, 202.0, 204.0]},
        dividendos={"AAPL": [0.0, 0.24, 0.0]},
    )
    marcha = posiciones.serie([APORTA, tardia], h)
    assert float(marcha.dividendos.sum().sum()) == pytest.approx(0.0)


def test_una_venta_en_la_fecha_ex_si_cobra_el_dividendo():
    # El reverso, y sale de la misma foto: quien vende en la fecha ex ya tenia
    # las acciones al cierre anterior, asi que el dividendo es suyo.
    venta = asiento(
        "a3", "2026-01-06", "venta", ticker="AAPL",
        acciones=40.0, precio=202.0, importe=8080.0,
    )
    h = historia(
        {"AAPL": [200.0, 202.0, 204.0]},
        dividendos={"AAPL": [0.0, 0.24, 0.0]},
    )
    marcha = posiciones.serie([APORTA, COMPRA, venta], h)
    assert float(marcha.dividendos.sum().sum()) == pytest.approx(9.6)


def test_un_hueco_de_precio_no_hunde_el_valor_a_cero():
    # `(acciones * cierres).sum(axis=1)` trata un NaN como cero por defecto, asi
    # que un dia sin dato dibujaria una caida a plomo que nunca ocurrio.
    h = historia({"AAPL": [200.0, float("nan"), 204.0]})
    marcha = posiciones.serie([APORTA, COMPRA], h)
    assert marcha.valor.loc["2026-01-06"] == pytest.approx(40 * 200.0 + 1999.0)


def test_un_ticker_sin_precios_no_aparece_en_las_acciones_y_el_valor_lo_acusa():
    # Fija un limite conocido de `serie`, no un comportamiento deseable. Si un
    # asiento mueve un ticker que `precios.desde_panel` aparto por no traer
    # ningun dato, el efectivo si baja --el dinero salio de verdad-- pero las
    # acciones no tienen columna donde ir, asi que el valor cae por el importe
    # entero de la compra y no hay nada en la serie que lo explique.
    #
    # No se arregla aqui: el valor de una posicion que no se puede cotizar no
    # existe, e inventarlo seria peor. Lo que hace la vista es NOMBRARLO, con
    # `Historia.sin_datos`. Este test esta para que ese contrato no se rompa en
    # silencio si alguien toca el bucle.
    fechas = pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-07"])
    h = precios.Historia(
        cierres=pd.DataFrame({"AAPL": [200.0, 202.0, 204.0]}, index=fechas),
        dividendos=pd.DataFrame({"AAPL": [0.0] * 3}, index=fechas),
        splits=pd.DataFrame({"AAPL": [0.0] * 3}, index=fechas),
        sin_datos=["ZZZZ"],
    )
    compra_ciega = asiento(
        "a2", "2026-01-05", "compra", ticker="ZZZZ",
        acciones=10.0, precio=100.0, importe=1000.0,
    )
    marcha = posiciones.serie([APORTA, compra_ciega], h)
    assert "ZZZZ" not in marcha.acciones.columns
    assert marcha.valor.iloc[-1] == pytest.approx(9000.0)


def test_un_asiento_posterior_al_ultimo_cierre_se_cuenta_aparte():
    # Pasa cada vez que se registra una compra de hoy antes de que yfinance
    # tenga el cierre de hoy. La tabla por activo si la ve, porque sale de los
    # asientos; la serie no puede valorarla. Sin este contador, el valor de
    # cabecera y la tabla dirian cosas distintas y nada lo explicaria.
    manana = asiento(
        "a3", "2026-01-08", "compra", ticker="AAPL",
        acciones=1.0, precio=204.0, importe=204.0,
    )
    h = historia({"AAPL": [200.0, 202.0, 204.0]})
    marcha = posiciones.serie([APORTA, COMPRA, manana], h)
    assert marcha.posteriores == 1
    assert marcha.acciones.loc["2026-01-07", "AAPL"] == pytest.approx(40.0)


def test_un_dividendo_posterior_a_la_venta_no_se_cobra():
    venta = asiento(
        "a3", "2026-01-05", "venta", ticker="AAPL",
        acciones=40.0, precio=200.0, importe=8000.0,
    )
    h = historia(
        {"AAPL": [200.0, 202.0, 204.0]},
        dividendos={"AAPL": [0.0, 0.24, 0.0]},
    )
    marcha = posiciones.serie([APORTA, COMPRA, venta], h)
    assert marcha.efectivo.loc["2026-01-07"] == pytest.approx(9999.0)


# --- El split registrado a mano ----------------------------------------------
#
# `serie()` aplica los splits que trae `Historia`, pero `estado()` y
# `primer_descubierto()` no ven la historia --y no pueden: validar que una
# venta cabe no puede depender de una descarga de red que falla--. Por eso el
# libro admite un asiento de `split`, y estos tests fijan que los tres caminos
# lo cuentan igual.


def parte(id_, fecha, ticker, factor) -> Asiento:
    return Asiento(id=id_, fecha=fecha, tipo="split", ticker=ticker, factor=factor)


def test_un_split_registrado_multiplica_las_acciones_del_estado():
    estado = posiciones.estado(
        [APORTA, COMPRA, parte("s1", "2026-01-06", "AAPL", 2.0)]
    )
    assert estado.acciones == {"AAPL": 80.0}
    # Y no toca el efectivo: un split no paga ni cobra nada.
    assert estado.efectivo == pytest.approx(1999.0)


def test_un_split_registrado_permite_vender_las_acciones_nuevas():
    # Sin el, `primer_descubierto` ve cuarenta acciones donde hay ochenta y
    # rechaza la venta que el usuario si pudo ejecutar en su broker.
    venta = asiento(
        "v1", "2026-01-07", "venta", ticker="AAPL",
        acciones=80.0, precio=100.0, importe=8000.0,
    )
    asientos = [APORTA, COMPRA, parte("s1", "2026-01-06", "AAPL", 2.0), venta]
    assert posiciones.primer_descubierto(asientos) is None


def test_el_orden_importa_dentro_del_mismo_recorrido():
    # Vender ochenta ANTES del split sigue siendo un descubierto. Comprobar el
    # saldo final lo aceptaria; recorrer el camino, no.
    venta = asiento(
        "v1", "2026-01-05", "venta", ticker="AAPL",
        acciones=80.0, precio=100.0, importe=8000.0,
    )
    asientos = [APORTA, COMPRA, venta, parte("s1", "2026-01-06", "AAPL", 2.0)]
    assert "no tienes suficientes" in (posiciones.primer_descubierto(asientos) or "")


def test_el_split_registrado_manda_sobre_el_de_la_historia():
    # Misma regla que los dividendos: el que el usuario apunto es el que
    # ocurrio de verdad, y sumar los dos partiria la posicion dos veces --el
    # peor error posible aqui, porque duplica acciones en silencio.
    h = historia(
        {"AAPL": [200.0, 202.0, 51.0]},
        splits={"AAPL": [0.0, 0.0, 4.0]},
    )
    marcha = posiciones.serie(
        [APORTA, COMPRA, parte("s1", "2026-01-07", "AAPL", 4.0)], h
    )
    assert marcha.acciones.loc["2026-01-07", "AAPL"] == pytest.approx(160.0)


def test_un_split_registrado_en_otra_fecha_que_el_de_la_historia_no_se_duplica_solo():
    # El reverso del anterior, y el limite conocido: la regla de precedencia es
    # por (ticker, fecha), igual que en los dividendos. Registrar el split un
    # dia distinto del que trae yfinance SI lo cuenta dos veces. Se deja
    # escrito porque es el unico modo de equivocarse aqui, y la pantalla lo
    # avisa al registrar.
    h = historia(
        {"AAPL": [200.0, 202.0, 51.0]},
        splits={"AAPL": [0.0, 0.0, 4.0]},
    )
    marcha = posiciones.serie(
        [APORTA, COMPRA, parte("s1", "2026-01-06", "AAPL", 4.0)], h
    )
    assert marcha.acciones.loc["2026-01-07", "AAPL"] == pytest.approx(640.0)


def test_una_compra_anterior_al_calendario_si_se_parte_con_el_split_del_primer_dia():
    # Los asientos fechados antes del primer cierre disponible se arrastran al
    # primer dia del calendario. Si se aplicaran DESPUES del split de ese dia,
    # una compra de diciembre se quedaria sin partir por un split de enero.
    vieja = asiento(
        "c0", "2025-12-20", "compra", ticker="AAPL",
        acciones=40.0, precio=200.0, importe=8000.0,
    )
    aporta = asiento("a0", "2025-12-19", "aportacion", importe=10_000.0)
    h = historia(
        {"AAPL": [50.0, 51.0, 52.0]},
        splits={"AAPL": [4.0, 0.0, 0.0]},
    )
    marcha = posiciones.serie([aporta, vieja], h)
    assert marcha.acciones.loc["2026-01-05", "AAPL"] == pytest.approx(160.0)


# --- El efectivo con los dividendos automaticos dentro -----------------------


def test_el_efectivo_de_estado_cuenta_los_dividendos_de_la_historia():
    # `serie()` los cobraba y `estado()` no, y la pantalla enseña los dos
    # numeros juntos: el saldo de arriba decia 320,00 y el de abajo 300,00 del
    # mismo libro, sin nada que explicara la diferencia.
    h = historia(
        {"AAPL": [200.0, 202.0, 204.0]},
        dividendos={"AAPL": [0.0, 0.24, 0.0]},
    )
    con_historia = posiciones.estado([APORTA, COMPRA], historia=h)
    assert con_historia.efectivo == pytest.approx(1999.0 + 9.6)
    # Y coincide con el que lleva la serie, que es el punto entero.
    marcha = posiciones.serie([APORTA, COMPRA], h)
    assert con_historia.efectivo == pytest.approx(
        float(marcha.efectivo.iloc[-1])
    )


def test_sin_historia_el_estado_sigue_dando_lo_apuntado_a_mano():
    # `libro.anadir` llama a `estado()` sin historia a proposito: financiar una
    # compra no puede depender de la red. Ahi el efectivo es el de los
    # asientos, que es una cifra menor y por tanto conservadora.
    h = historia(
        {"AAPL": [200.0, 202.0, 204.0]},
        dividendos={"AAPL": [0.0, 0.24, 0.0]},
    )
    assert posiciones.estado([APORTA, COMPRA]).efectivo == pytest.approx(1999.0)
    assert posiciones.estado([APORTA, COMPRA], historia=h).efectivo > 1999.0


def test_el_dividendo_a_mano_sigue_mandando_tambien_en_estado():
    manual = asiento("d1", "2026-01-06", "dividendo", ticker="AAPL", importe=7.1)
    h = historia(
        {"AAPL": [200.0, 202.0, 204.0]},
        dividendos={"AAPL": [0.0, 0.24, 0.0]},
    )
    estado = posiciones.estado([APORTA, COMPRA, manual], historia=h)
    assert estado.efectivo == pytest.approx(1999.0 + 7.1)


def test_el_corte_por_fecha_tambien_corta_los_dividendos_automaticos():
    h = historia(
        {"AAPL": [200.0, 202.0, 204.0]},
        dividendos={"AAPL": [0.0, 0.24, 0.0]},
    )
    estado = posiciones.estado([APORTA, COMPRA], hasta="2026-01-05", historia=h)
    assert estado.efectivo == pytest.approx(1999.0)

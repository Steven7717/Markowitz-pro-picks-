from datetime import date

import pytest

from seguimiento.libro import (
    Asiento,
    AsientoInvalido,
    Libro,
    Objetivo,
    derivar,
    validar,
    veredicto_de,
)

HOY = date(2026, 9, 2)
NAN = float("nan")
INF = float("inf")


def compra(**cambios) -> Asiento:
    campos = {
        "id": "a1",
        "fecha": "2026-09-01",
        "tipo": "compra",
        "ticker": "AAPL",
        "acciones": 10.0,
        "precio": 220.0,
        "importe": 2200.0,
    }
    campos.update(cambios)
    return Asiento(**campos)


# --- Forma del asiento -------------------------------------------------------


def test_una_compra_bien_formada_pasa():
    validar(compra(), hoy=HOY)


def test_una_fecha_futura_no_pasa():
    # Registrar algo que no ha ocurrido dejaria una posicion valorada con
    # precios que todavia no existen.
    with pytest.raises(AsientoInvalido, match="futura"):
        validar(compra(fecha="2026-09-03"), hoy=HOY)


def test_una_fecha_en_formato_basico_no_pasa():
    # date.fromisoformat acepta ISO 8601 entero desde Python 3.11, asi que
    # "20260901" es una fecha valida para el. Pero la reconstruccion ordena por
    # la cadena cruda, y '-' es menor que cualquier digito: "20260215" se va
    # DETRAS de "2026-08-01" al ordenar, y la venta se aplicaria antes que su
    # propia compra.
    with pytest.raises(AsientoInvalido, match="YYYY-MM-DD"):
        validar(compra(fecha="20260901"), hoy=HOY)


def test_una_fecha_de_semana_tampoco_pasa():
    with pytest.raises(AsientoInvalido, match="YYYY-MM-DD"):
        validar(compra(fecha="2026-W36-2"), hoy=HOY)


def test_una_fecha_que_no_es_texto_da_asiento_invalido_y_no_typeerror():
    # Pasar un `date` es el error mas probable del llamante, porque el resto
    # del modulo habla en `date`. El docstring promete AsientoInvalido, y un
    # TypeError crudo llegaria a la pantalla como un traceback de Streamlit en
    # vez de como un mensaje.
    with pytest.raises(AsientoInvalido, match="no es una fecha"):
        validar(compra(fecha=date(2026, 9, 1)), hoy=HOY)


def test_un_precio_de_cero_no_pasa():
    with pytest.raises(AsientoInvalido, match="precio"):
        validar(compra(precio=0.0), hoy=HOY)


def test_un_precio_negativo_no_pasa():
    # Sin este test, la mitad `precio <= 0` de la guarda no se ejecuta en toda
    # la suite: el caso de cero entra por la rama de "esta vacio" y la de
    # negativo no la prueba nadie.
    with pytest.raises(AsientoInvalido, match="precio"):
        validar(compra(precio=-220.0), hoy=HOY)


def test_un_importe_de_cero_no_pasa():
    with pytest.raises(AsientoInvalido, match="importe"):
        validar(compra(importe=0.0), hoy=HOY)


def test_un_importe_negativo_no_pasa():
    with pytest.raises(AsientoInvalido, match="importe"):
        validar(compra(importe=-2200.0), hoy=HOY)


def test_unas_acciones_de_cero_no_pasan():
    with pytest.raises(AsientoInvalido, match="acciones"):
        validar(compra(acciones=0.0), hoy=HOY)


def test_unas_acciones_negativas_no_pasan():
    with pytest.raises(AsientoInvalido, match="acciones"):
        validar(compra(acciones=-10.0), hoy=HOY)


def test_una_compra_sin_ticker_no_pasa():
    with pytest.raises(AsientoInvalido, match="ticker"):
        validar(compra(ticker=None), hoy=HOY)


def test_un_ticker_con_forma_rara_no_pasa():
    with pytest.raises(AsientoInvalido, match="forma de ticker"):
        validar(compra(ticker="AAPL!"), hoy=HOY)


def test_un_ticker_con_salto_de_linea_no_pasa():
    # `$` casa tambien justo antes de un salto final, asi que con `match` esto
    # pasaria por ticker valido. Y como el ticker es la clave del diccionario
    # de posiciones, partiria una posicion en dos: "AAPL" y "AAPL\n". El
    # usuario que cree tener veinte acciones veria diez.
    with pytest.raises(AsientoInvalido, match="forma de ticker"):
        validar(compra(ticker="AAPL\n"), hoy=HOY)


def test_una_aportacion_no_lleva_ticker():
    # Dinero que entra no es dinero puesto en algo: si llevara ticker, seria
    # una compra, y contarlo como flujo externo Y como posicion lo duplicaria.
    with pytest.raises(AsientoInvalido, match="ticker"):
        validar(
            Asiento(id="a2", fecha="2026-09-01", tipo="aportacion",
                    ticker="AAPL", importe=1000.0),
            hoy=HOY,
        )


def test_una_comision_negativa_no_pasa():
    with pytest.raises(AsientoInvalido, match="comisión"):
        validar(compra(comision=-1.0), hoy=HOY)


def test_un_tipo_inventado_no_pasa():
    with pytest.raises(AsientoInvalido, match="tipo"):
        validar(compra(tipo="permuta"), hoy=HOY)


# --- Numeros que no son numeros ---------------------------------------------


@pytest.mark.parametrize("campo", ["importe", "acciones", "precio", "comision"])
@pytest.mark.parametrize("veneno", [NAN, INF, -INF])
def test_ningun_campo_numerico_admite_nan_ni_infinito(campo, veneno):
    # Ninguna comparacion con NaN es cierta --`nan <= 0` es False-- y `not nan`
    # tambien es False, porque NaN es truthy. Asi que las guardas de "mayor que
    # cero" lo dejan pasar entero. Y un solo asiento con NaN hace dos cosas a
    # la vez: envenena el efectivo, y BORRA el activo de la tabla de
    # posiciones, porque el filtro de polvo `abs(n) > _POLVO` tambien es False
    # para NaN. El usuario no ve un error: ve una posicion que desaparecio.
    with pytest.raises(AsientoInvalido, match="finito"):
        validar(compra(**{campo: veneno}), hoy=HOY)


def test_el_nan_que_entra_desde_disco_lo_para_la_validacion():
    # No es un caso de laboratorio: json.loads acepta el literal NaN por
    # defecto, asi que un fichero editado a mano o corrompido lo mete en el
    # libro sin que nadie lo teclee. Este test recorre ese camino entero, y no
    # se limita a comprobar lo que hace la libreria estandar.
    import json

    crudo = json.loads(
        '{"id": "a1", "fecha": "2026-09-01", "tipo": "compra", '
        '"ticker": "AAPL", "acciones": 10.0, "precio": 220.0, "importe": NaN}'
    )
    with pytest.raises(AsientoInvalido, match="finito"):
        validar(Asiento(**crudo), hoy=HOY)


# --- La anulacion ------------------------------------------------------------


def test_una_anulacion_necesita_a_quien_anula():
    with pytest.raises(AsientoInvalido, match="anula"):
        validar(Asiento(id="a3", fecha="2026-09-01", tipo="anulacion"), hoy=HOY)


def test_una_anulacion_bien_formada_pasa():
    validar(
        Asiento(id="a3", fecha="2026-09-01", tipo="anulacion", anula="a1"),
        hoy=HOY,
    )


def test_una_anulacion_no_arrastra_importe_ni_ticker():
    # Una anulacion es una nota que tacha otra linea, no un movimiento.
    # Dejarla llevar ticker o dinero guardaria basura con pinta de dato en un
    # fichero que nadie vuelve a validar al leerlo.
    with pytest.raises(AsientoInvalido, match="no lleva ticker"):
        validar(
            Asiento(id="a3", fecha="2026-09-01", tipo="anulacion",
                    anula="a1", ticker="AAPL"),
            hoy=HOY,
        )
    with pytest.raises(AsientoInvalido, match="no mueve dinero"):
        validar(
            Asiento(id="a3", fecha="2026-09-01", tipo="anulacion",
                    anula="a1", importe=9999.0),
            hoy=HOY,
        )


# --- Derivar el tercer campo -------------------------------------------------


def test_de_importe_y_precio_salen_las_acciones():
    assert derivar(importe=2200.0, acciones=None, precio=220.0) == (2200.0, 10.0, 220.0)


def test_de_acciones_y_precio_sale_el_importe():
    assert derivar(importe=None, acciones=10.0, precio=220.0) == (2200.0, 10.0, 220.0)


def test_con_los_tres_puestos_se_respetan_los_tres():
    # El broker cobra redondeos que ninguna division reproduce: si el usuario
    # escribe los tres, mandan los tres, aunque no cuadren al centimo.
    assert derivar(importe=2200.5, acciones=10.0, precio=220.0) == (2200.5, 10.0, 220.0)


def test_sin_precio_no_se_puede_derivar_nada():
    with pytest.raises(AsientoInvalido, match="hace falta el precio"):
        derivar(importe=2200.0, acciones=None, precio=None)


def test_un_precio_negativo_no_sirve_para_derivar():
    with pytest.raises(AsientoInvalido, match="mayor que cero"):
        derivar(importe=2200.0, acciones=None, precio=-220.0)


def test_sin_importe_ni_acciones_no_hay_nada_que_completar():
    with pytest.raises(AsientoInvalido, match="importe o el número de acciones"):
        derivar(importe=None, acciones=None, precio=220.0)


def test_derivar_no_devuelve_un_infinito():
    # Ni el importe ni el precio son absurdos por separado, pero la division
    # desborda. `validar` no lo salvaria despues: `inf > 0` es True, asi que
    # pasa todas las guardas y la cartera acaba con infinitas acciones.
    with pytest.raises(AsientoInvalido, match="no cuadra"):
        derivar(importe=2200.0, acciones=None, precio=1e-320)


@pytest.mark.parametrize("campo", ["importe", "acciones", "precio"])
def test_derivar_rechaza_un_nan_de_entrada(campo):
    # `derivar` corre ANTES que `validar`: recibe lo que el usuario acaba de
    # teclear y no puede apoyarse en nadie.
    campos = {"importe": 2200.0, "acciones": None, "precio": 220.0}
    campos[campo] = NAN
    with pytest.raises(AsientoInvalido, match="finito"):
        derivar(**campos)


# --- El libro ----------------------------------------------------------------


def test_el_objetivo_vigente_es_el_ultimo_apilado():
    libro = Libro(
        nombre="Prueba", creado="2026-01-01T10:00:00",
        objetivos=(
            Objetivo(fecha="2026-01-01", base="estrategia", portafolio={}),
            Objetivo(fecha="2026-06-01", base="equal_weight", portafolio={}),
        ),
    )
    assert libro.objetivo.fecha == "2026-06-01"


def test_un_libro_sin_objetivos_no_tiene_objetivo_vigente():
    # None y no un objetivo vacio: "no hay contra que medir" es un estado real
    # --una cartera creada a mano-- y la pantalla lo dice en vez de ensenar una
    # deriva de cero que nadie calculo.
    assert Libro(nombre="Prueba", creado="2026-01-01T10:00:00").objetivo is None


def test_los_asientos_de_un_libro_no_se_pueden_editar_en_el_sitio():
    # `frozen=True` impide reasignar el campo, pero no tocar una lista por
    # dentro. Con una lista, `libro.asientos.append(...)` funcionaria y la
    # regla central del modulo --nunca se edita, nunca se borra-- estaria
    # documentada pero no impuesta.
    libro = Libro(nombre="Prueba", creado="2026-01-01T10:00:00",
                  asientos=(compra(),))
    with pytest.raises(AttributeError):
        libro.asientos.append(compra())


# --- anadir(): validar contra el estado del libro ----------------------------

from seguimiento.libro import Libro, anadir

VACIO = Libro(nombre="Prueba", creado="2026-01-01T10:00:00")


def con(*asientos) -> Libro:
    from dataclasses import replace
    return replace(VACIO, asientos=tuple(asientos))


def test_no_se_puede_vender_lo_que_no_se_tiene():
    venta = Asiento(
        id="v1", fecha="2026-09-01", tipo="venta", ticker="AAPL",
        acciones=5.0, precio=220.0, importe=1100.0,
    )
    with pytest.raises(AsientoInvalido, match="no tienes"):
        anadir(VACIO, venta, hoy=HOY)


def test_no_se_pueden_vender_mas_acciones_de_las_que_hay():
    libro = con(
        Asiento(id="ap", fecha="2026-08-01", tipo="aportacion", importe=5000.0),
        compra(id="c1", fecha="2026-08-01", acciones=10.0),
    )
    venta = Asiento(
        id="v1", fecha="2026-09-01", tipo="venta", ticker="AAPL",
        acciones=11.0, precio=220.0, importe=2420.0,
    )
    with pytest.raises(AsientoInvalido, match="10"):
        anadir(libro, venta, hoy=HOY)


def test_no_se_puede_retirar_mas_efectivo_del_que_hay():
    libro = con(Asiento(id="ap", fecha="2026-08-01", tipo="aportacion", importe=100.0))
    retiro = Asiento(id="r1", fecha="2026-09-01", tipo="retiro", importe=200.0)
    with pytest.raises(AsientoInvalido, match="efectivo"):
        anadir(libro, retiro, hoy=HOY)


def test_una_compra_sin_efectivo_suficiente_arrastra_su_aportacion():
    # El usuario piensa "compre 2.200 de Apple", no "aporte 2.205 y luego
    # compre". Escribir la aportacion por el sonaria a magia si no se dijera,
    # asi que anadir() la devuelve para que la pantalla la ensene.
    libro, escritos = anadir(VACIO, compra(comision=5.0), hoy=HOY, financiar=True)
    assert [a.tipo for a in escritos] == ["aportacion", "compra"]
    # La comision va DENTRO de la aportacion. Con comision cero este test
    # pasaria igual sin cubrirla, y el comentario estaria prometiendo una
    # cobertura que no existe -- que es como se cuelan las guardas muertas.
    assert escritos[0].importe == pytest.approx(2205.0)


def test_la_aportacion_que_financia_deja_el_efectivo_a_cero():
    # La comprobacion que de verdad cierra el caso: si la aportacion se
    # quedase corta por el importe de la comision, el efectivo acabaria
    # negativo -- un descuadre pequeno, permanente y sin causa visible.
    from seguimiento import posiciones

    libro, _ = anadir(VACIO, compra(comision=5.0), hoy=HOY, financiar=True)
    assert posiciones.estado(libro.asientos).efectivo == pytest.approx(0.0)


def test_una_compra_con_efectivo_suficiente_no_inventa_aportacion():
    libro = con(Asiento(id="ap", fecha="2026-08-01", tipo="aportacion", importe=5000.0))
    _, escritos = anadir(libro, compra(), hoy=HOY, financiar=True)
    assert [a.tipo for a in escritos] == ["compra"]


def test_no_se_puede_anular_un_asiento_que_no_existe():
    anulacion = Asiento(id="x1", fecha="2026-09-01", tipo="anulacion", anula="fantasma")
    with pytest.raises(AsientoInvalido, match="no existe"):
        anadir(VACIO, anulacion, hoy=HOY)


def test_no_se_puede_anular_dos_veces():
    libro = con(
        Asiento(id="ap", fecha="2026-08-01", tipo="aportacion", importe=5000.0),
        Asiento(id="x1", fecha="2026-08-02", tipo="anulacion", anula="ap"),
    )
    otra = Asiento(id="x2", fecha="2026-09-01", tipo="anulacion", anula="ap")
    with pytest.raises(AsientoInvalido, match="ya está anulado"):
        anadir(libro, otra, hoy=HOY)


def test_el_asiento_aceptado_se_queda_en_el_libro():
    libro, _ = anadir(VACIO, Asiento(
        id="ap", fecha="2026-09-01", tipo="aportacion", importe=1000.0), hoy=HOY)
    assert len(libro.asientos) == 1
    assert libro.asientos[0].tipo == "aportacion"


def test_no_se_puede_vender_en_una_fecha_anterior_a_la_compra():
    # El caso que rompe comprobar solo el saldo final: hoy tengo diez acciones,
    # asi que una venta de diez "cuadra" -- pero fechada en julio deja la
    # cartera con menos diez acciones en julio, y `estado(hasta=...)` lo
    # devolveria tal cual. No es un caso raro: es lo que pasa siempre que
    # alguien registra lo que ya tenia comprado y mete los asientos en el orden
    # del extracto y no en orden cronologico.
    libro = con(
        Asiento(id="ap", fecha="2026-08-01", tipo="aportacion", importe=5000.0),
        compra(id="c1", fecha="2026-08-01", acciones=10.0),
    )
    venta = Asiento(
        id="v1", fecha="2026-07-01", tipo="venta", ticker="AAPL",
        acciones=10.0, precio=250.0, importe=2500.0,
    )
    with pytest.raises(AsientoInvalido, match="2026-07-01"):
        anadir(libro, venta, hoy=HOY)


def test_un_retiro_fechado_antes_de_su_aportacion_no_pasa():
    libro = con(Asiento(id="ap", fecha="2026-08-01", tipo="aportacion",
                        importe=5000.0))
    retiro = Asiento(id="r1", fecha="2026-07-01", tipo="retiro", importe=1000.0)
    with pytest.raises(AsientoInvalido, match="2026-07-01"):
        anadir(libro, retiro, hoy=HOY)


def test_una_compra_del_pasado_se_financia_con_el_saldo_de_entonces():
    # Aportar 5.000 en agosto no paga una compra fechada en julio. La
    # aportacion que se escribe tiene que cubrirla entera, no la diferencia
    # contra un saldo que en esa fecha todavia no existia.
    libro = con(Asiento(id="ap", fecha="2026-08-01", tipo="aportacion",
                        importe=5000.0))
    _, escritos = anadir(libro, compra(id="c1", fecha="2026-07-01"),
                         hoy=HOY, financiar=True)
    assert [a.tipo for a in escritos] == ["aportacion", "compra"]
    assert escritos[0].importe == pytest.approx(2200.0)


def test_vender_la_posicion_entera_sobrevive_al_redondeo():
    # Dos compras de 2.500 a 3, y despues vender todo a 11. La pantalla ensena
    # el total acumulado y `derivar()` lo vuelve a calcular desde importe y
    # precio: los dos numeros NO coinciden, y el recalculado es el mayor por
    # 2,3e-13 acciones. Sin el margen de _POLVO, el libro rechazaria una venta
    # de la posicion entera diciendo que no hay suficientes.
    #
    # Una version anterior de este test compraba una sola vez y vendia la misma
    # variable: no probaba nada, porque `0.0 + x` es exactamente `x` en
    # IEEE-754 y los dos lados eran el mismo float. De ahi el assert de la
    # precondicion, que es lo que impide que vuelva a quedarse vacio en
    # silencio si el redondeo cambia.
    from seguimiento import posiciones
    from seguimiento.libro import derivar

    _, acciones, _ = derivar(importe=2500.0, acciones=None, precio=3.0)
    libro = con(
        Asiento(id="ap", fecha="2026-08-01", tipo="aportacion", importe=5000.0),
        Asiento(id="c1", fecha="2026-08-01", tipo="compra", ticker="AAPL",
                acciones=acciones, precio=3.0, importe=2500.0),
        Asiento(id="c2", fecha="2026-08-02", tipo="compra", ticker="AAPL",
                acciones=acciones, precio=3.0, importe=2500.0),
    )
    tiene = posiciones.estado(libro.asientos).acciones["AAPL"]
    importe_v, vendidas, precio_v = derivar(
        importe=tiene * 11.0, acciones=None, precio=11.0
    )
    assert vendidas > tiene, "sin discrepancia de redondeo el test no prueba nada"

    venta = Asiento(id="v1", fecha="2026-09-01", tipo="venta", ticker="AAPL",
                    acciones=vendidas, precio=precio_v, importe=importe_v)
    libro, _ = anadir(libro, venta, hoy=HOY)
    assert len(libro.asientos) == 4


def test_el_veredicto_se_extrae_de_las_metricas_guardadas():
    metricas = {
        "oos_sharpe": 0.41,
        "oos_equal_weight_sharpe": 0.55,
        "oos_sharpe_stderr": 0.09,
        "beats_equal_weight": False,
        "oos_windows": 12,
    }
    assert veredicto_de(metricas) == metricas


def test_un_portafolio_viejo_sin_error_estandar_no_afirma_un_veredicto():
    # Los ficheros guardados antes de este cambio no llevan sharpe_stderr. Sin
    # el, "gana / pierde / no se distingue" no se puede reconstruir: dos Sharpe
    # sueltos no dicen si la diferencia cabe dentro del ruido. None no es False.
    viejo = {"oos_sharpe": 0.41, "oos_equal_weight_sharpe": 0.55, "oos_windows": 12}
    salida = veredicto_de(viejo)
    assert salida["oos_sharpe_stderr"] is None
    assert salida["beats_equal_weight"] is None


def test_el_veredicto_sobrevive_al_viaje_por_el_objetivo():
    objetivo = Objetivo(
        fecha="2026-09-02", base="equal_weight", portafolio={},
        veredicto=veredicto_de({"oos_sharpe": 0.41, "oos_windows": 12}),
    )
    assert objetivo.veredicto["beats_equal_weight"] is None

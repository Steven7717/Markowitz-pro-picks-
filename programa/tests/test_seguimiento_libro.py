from datetime import date

import pytest

from seguimiento.libro import (
    Asiento,
    anadir,
    AsientoInvalido,
    Libro,
    Objetivo,
    derivar,
    validar,
    CAMPOS_VEREDICTO,
    veredicto_de,
    veredicto_vigente,
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


# --- El split ----------------------------------------------------------------
#
# El split es el septimo tipo, y llego tarde: hasta que existio, quien vivia un
# 2:1 de una compra de diez e intentaba vender veinte recibia «no tienes
# suficientes acciones de ACME: harian falta 20 y hay 10». O mentia en el
# numero, o no podia apuntar la venta.


def split(**cambios) -> Asiento:
    campos = {
        "id": "s1",
        "fecha": "2026-09-01",
        "tipo": "split",
        "ticker": "ACME",
        "factor": 2.0,
    }
    campos.update(cambios)
    return Asiento(**campos)


def test_un_split_bien_formado_pasa():
    validar(split(), hoy=HOY)


def test_un_split_necesita_factor():
    with pytest.raises(AsientoInvalido, match="factor"):
        validar(split(factor=None), hoy=HOY)


def test_un_factor_que_no_multiplica_nada_no_pasa():
    # Cero borraria la posicion y un negativo la dejaria en acciones negativas.
    # Las dos cosas se leen igual de plausibles dentro del fichero.
    with pytest.raises(AsientoInvalido, match="factor"):
        validar(split(factor=0.0), hoy=HOY)
    with pytest.raises(AsientoInvalido, match="factor"):
        validar(split(factor=-2.0), hoy=HOY)


def test_un_split_necesita_ticker():
    with pytest.raises(AsientoInvalido, match="ticker"):
        validar(split(ticker=None), hoy=HOY)


def test_un_split_no_mueve_dinero_ni_lleva_acciones():
    # Un split no es una operacion: no se paga ni se cobra nada, y el numero de
    # acciones no se declara sino que sale de multiplicar lo que ya habia.
    with pytest.raises(AsientoInvalido, match="no mueve dinero"):
        validar(split(importe=100.0), hoy=HOY)
    with pytest.raises(AsientoInvalido, match="no lleva acciones"):
        validar(split(acciones=10.0), hoy=HOY)


def test_solo_un_split_lleva_factor():
    # Un factor en una compra no lo aplica nadie, asi que se quedaria en el
    # fichero con pinta de dato mientras el programa lo ignora en silencio.
    with pytest.raises(AsientoInvalido, match="factor"):
        validar(compra(factor=2.0), hoy=HOY)


def test_un_factor_infinito_no_pasa():
    with pytest.raises(AsientoInvalido, match="finito"):
        validar(split(factor=INF), hoy=HOY)


def test_despues_de_un_split_se_pueden_vender_las_acciones_nuevas():
    # El defecto entero, en un test. Diez acciones, un 2:1, y una venta de
    # veinte que antes se rechazaba.
    libro = con(
        Asiento(id="ap", fecha="2026-08-01", tipo="aportacion", importe=5000.0),
        compra(id="c1", fecha="2026-08-01", ticker="ACME", acciones=10.0,
               precio=100.0, importe=1000.0),
        split(id="s1", fecha="2026-08-15", ticker="ACME", factor=2.0),
    )
    venta = Asiento(
        id="v1", fecha="2026-09-01", tipo="venta", ticker="ACME",
        acciones=20.0, precio=60.0, importe=1200.0,
    )
    crecido, _ = anadir(libro, venta, hoy=HOY)
    assert crecido.asientos[-1].id == "v1"


def test_sin_el_split_esa_misma_venta_se_sigue_rechazando():
    # La otra mitad del contrato: el split tiene que estar REGISTRADO. Sin el,
    # vender veinte de diez sigue siendo un descubierto, y aceptarlo por si
    # acaso convertiria el error de tecleo mas caro --un cero de mas-- en un
    # asiento valido.
    libro = con(
        Asiento(id="ap", fecha="2026-08-01", tipo="aportacion", importe=5000.0),
        compra(id="c1", fecha="2026-08-01", ticker="ACME", acciones=10.0,
               precio=100.0, importe=1000.0),
    )
    venta = Asiento(
        id="v1", fecha="2026-09-01", tipo="venta", ticker="ACME",
        acciones=20.0, precio=60.0, importe=1200.0,
    )
    with pytest.raises(AsientoInvalido, match="no tienes suficientes"):
        anadir(libro, venta, hoy=HOY)


def test_un_split_anulado_deja_de_partir_nada():
    libro = con(
        Asiento(id="ap", fecha="2026-08-01", tipo="aportacion", importe=5000.0),
        compra(id="c1", fecha="2026-08-01", ticker="ACME", acciones=10.0,
               precio=100.0, importe=1000.0),
        split(id="s1", fecha="2026-08-15", ticker="ACME", factor=2.0),
        Asiento(id="x1", fecha="2026-08-16", tipo="anulacion", anula="s1"),
    )
    venta = Asiento(
        id="v1", fecha="2026-09-01", tipo="venta", ticker="ACME",
        acciones=20.0, precio=60.0, importe=1200.0,
    )
    with pytest.raises(AsientoInvalido, match="no tienes suficientes"):
        anadir(libro, venta, hoy=HOY)


def test_un_libro_viejo_sin_splits_se_sigue_leyendo(tmp_path):
    # El libro es append-only y se relee con versiones futuras del programa.
    # Anadir un tipo no puede dejar ilegible un fichero escrito antes de que
    # ese tipo existiera: ahi no hay campo `factor` en ningun asiento.
    ruta = tmp_path / "2026-09-02-100000-viejo.json"
    ruta.write_text(
        '{"nombre": "Prueba", "creado": "2026-09-02T10:00:00", "moneda": "USD",'
        ' "objetivos": [], "asientos": [{"id": "a1", "fecha": "2026-09-01",'
        ' "tipo": "compra", "ticker": "AAPL", "acciones": 10.0,'
        ' "precio": 220.0, "importe": 2200.0}]}',
        encoding="utf-8",
    )
    leido = mod.cargar(ruta)
    assert leido.asientos[0].factor is None


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


def test_el_libro_se_lleva_exactamente_lo_que_el_portafolio_escribe():
    """`CAMPOS_VEREDICTO` y `validation.metricas_de_validacion` declaran lo mismo.

    Aqui habia un test que comparaba `veredicto_de(metricas)` con un
    diccionario escrito a mano con esos mismos campos. Era un espejo del
    codigo: cuando `CAMPOS_VEREDICTO` recortaba el umbral y las sigmas, al
    diccionario del test le faltaban tambien, asi que la igualdad se cumplia y
    el test estuvo en verde todo el tiempo que duro el defecto. Solo podia
    saltar si alguien anadia un campo a los dos sitios menos a el, que es una
    alarma sobre el test y no sobre el programa.

    Lo que si habria saltado en el momento exacto es esto. Quien escribe la
    medicion en el portafolio --`metricas_de_validacion`-- y quien la copia
    dentro del libro --`CAMPOS_VEREDICTO`-- son las dos mitades del mismo
    contrato, y cuando la primera empezo a escribir `oos_umbral_veredicto` y
    `oos_sigmas_veredicto`, la segunda se quedo atras y los tiraba justo cuando
    el portafolio ya los traia. Un campo nuevo que solo se anada a un lado deja
    este test en rojo el mismo dia.
    """
    from validation import metricas_de_validacion

    assert set(CAMPOS_VEREDICTO) == set(metricas_de_validacion(None))

    # Y los valores llegan intactos, que es lo unico que el test anterior
    # comprobaba de verdad.
    metricas = {
        "oos_sharpe": 0.41,
        "oos_equal_weight_sharpe": 0.55,
        "oos_sharpe_stderr": 0.09,
        "oos_gap_stderr": 0.03,
        "beats_equal_weight": False,
        "oos_windows": 12,
        "oos_umbral_veredicto": 0.06,
        "oos_sigmas_veredicto": 2.0,
    }
    assert veredicto_de(metricas) == metricas


def test_un_portafolio_viejo_sin_error_estandar_no_afirma_un_veredicto():
    # Los ficheros guardados antes de este cambio no llevan los errores estandar.
    # Sin ellos, "gana / pierde / no se distingue" no se puede reconstruir: dos
    # Sharpe sueltos no dicen si la diferencia cabe dentro del ruido. None no es
    # False.
    viejo = {"oos_sharpe": 0.41, "oos_equal_weight_sharpe": 0.55, "oos_windows": 12}
    salida = veredicto_de(viejo)
    assert salida["oos_sharpe_stderr"] is None
    assert salida["oos_gap_stderr"] is None
    assert salida["beats_equal_weight"] is None


def test_un_portafolio_con_solo_el_error_del_nivel_no_trae_el_de_la_diferencia():
    """El que justifica el veredicto es el de la diferencia, y puede faltar.

    Los portafolios guardados entre que existio `oos_sharpe_stderr` y que
    existio `oos_gap_stderr` llevan un error estandar que NO es el que decidio
    su veredicto. Rellenar el hueco con el otro afirmaria una precision que
    nadie midio.
    """
    intermedio = {"oos_sharpe": 0.41, "oos_equal_weight_sharpe": 0.55,
                  "oos_sharpe_stderr": 0.38, "oos_windows": 12}
    assert veredicto_de(intermedio)["oos_gap_stderr"] is None


def test_el_veredicto_sobrevive_al_viaje_por_el_objetivo():
    objetivo = Objetivo(
        fecha="2026-09-02", base="equal_weight", portafolio={},
        veredicto=veredicto_de({"oos_sharpe": 0.41, "oos_windows": 12}),
    )
    # El campo viaja con su hueco, y quien lo lea pasa por `veredicto_vigente`.
    # Sin el error de la diferencia no hay veredicto que dictar, y `None` --no
    # `False`-- es lo que sale por los dos lados.
    assert objetivo.veredicto["beats_equal_weight"] is None
    assert veredicto_vigente(objetivo) is None


# --- Guardar y leer el libro en disco -----------------------------------------

import json
from datetime import datetime

from seguimiento import libro as mod

AHORA = datetime(2026, 9, 2, 10, 0, 0)


def test_lo_guardado_vuelve_igual(tmp_path):
    original, _ = anadir(VACIO, Asiento(
        id="ap", fecha="2026-09-01", tipo="aportacion", importe=1000.0), hoy=HOY)
    ruta = mod.guardar(original, tmp_path)
    vuelto = mod.cargar(ruta)
    assert vuelto.nombre == "Prueba"
    assert len(vuelto.asientos) == 1
    assert vuelto.asientos[0].tipo == "aportacion"
    assert vuelto.asientos[0].importe == 1000.0


def test_guardar_dos_veces_no_pisa_el_primero(tmp_path):
    # Un libro solo crece. Sobrescribirlo en silencio nunca es lo correcto.
    uno = mod.guardar(VACIO, tmp_path)
    dos = mod.guardar(VACIO, tmp_path)
    assert uno != dos
    assert uno.exists() and dos.exists()


def test_un_fichero_truncado_se_nombra_y_no_se_borra(tmp_path):
    # A diferencia de las caches de ranking/ y fundamentals/, que se borran y se
    # regeneran. Un libro de posiciones no se regenera.
    roto = tmp_path / "2026-09-02-100000-roto.json"
    roto.write_text('{"nombre": "Prue', encoding="utf-8")
    with pytest.raises(mod.LibroIlegible, match="roto.json"):
        mod.cargar(roto)
    assert roto.exists()


def test_listar_devuelve_los_rotos_con_su_motivo(tmp_path):
    mod.guardar(VACIO, tmp_path)
    (tmp_path / "2026-01-01-000000-roto.json").write_text("{", encoding="utf-8")
    entradas = mod.listar(tmp_path)
    assert len(entradas) == 2
    assert sum(1 for e in entradas if e.libro is None) == 1
    assert all(e.libro is not None or e.error for e in entradas)


def test_un_libro_desde_un_portafolio_copia_los_pesos_dentro(tmp_path):
    import cartera
    portafolio = cartera.desde_corrida(
        nombre="Mi cartera", tickers=["AAPL", "MSFT"], pesos=[0.6, 0.4],
        horizonte="1 Mes", estrategia="max_sharpe", peso_min=0.0, peso_max=1.0,
        permitir_cortos=False, shrinkage=True,
        metricas={"oos_sharpe": 0.41, "oos_sharpe_stderr": 0.09,
                  "beats_equal_weight": False},
        ahora=AHORA,
    )
    nuevo = mod.desde_portafolio("Seguimiento", portafolio, base="estrategia",
                                 ahora=AHORA)
    assert nuevo.objetivo.base == "estrategia"
    assert nuevo.objetivo.portafolio["posiciones"][0]["ticker"] == "AAPL"
    # La medicion viaja dentro; el veredicto NO se lee de ahi. Este portafolio
    # es anterior a `oos_gap_stderr`, asi que no se puede recomprobar, y
    # `veredicto_vigente` lo dice en vez de repetir el False guardado.
    assert nuevo.objetivo.veredicto["beats_equal_weight"] is False
    assert mod.veredicto_vigente(nuevo.objetivo) is None
    # Copiado dentro, no referenciado: el fichero de portafolios/ se puede
    # borrar desde su pantalla, y el libro se quedaria apuntando a nada.
    assert "ruta" not in nuevo.objetivo.portafolio


def test_equal_weight_como_base_reparte_por_igual(tmp_path):
    import cartera
    portafolio = cartera.desde_corrida(
        nombre="Mi cartera", tickers=["AAPL", "MSFT"], pesos=[0.6, 0.4],
        horizonte="1 Mes", estrategia="max_sharpe", peso_min=0.0, peso_max=1.0,
        permitir_cortos=False, shrinkage=True, metricas={}, ahora=AHORA,
    )
    nuevo = mod.desde_portafolio("Seguimiento", portafolio,
                                 base="equal_weight", ahora=AHORA)
    assert mod.pesos_objetivo(nuevo.objetivo) == {"AAPL": 0.5, "MSFT": 0.5}


def test_desde_portafolio_no_elige_la_base_por_ti():
    # `base` no tiene valor por defecto A PROPOSITO. El walk-forward ya dice
    # cuando la optimizacion no le gana a repartir por igual, y elegir por el
    # usuario convertiria esa evidencia en un clic que nadie mira -- el mismo
    # razonamiento que dejo las casillas desmarcadas en el gate de aprobacion.
    #
    # Sin este test la decision no esta protegida: los otros tres que llaman a
    # `desde_portafolio` pasan `base=` explicito, asi que alguien puede
    # devolverle un default y ninguno se entera. Comprobado saboteandolo.
    import cartera
    portafolio = cartera.desde_corrida(
        nombre="X", tickers=["AAPL"], pesos=[1.0], horizonte="1 Mes",
        estrategia="max_sharpe", peso_min=0.0, peso_max=1.0,
        permitir_cortos=False, shrinkage=True, metricas={}, ahora=AHORA,
    )
    with pytest.raises(TypeError, match="base"):
        mod.desde_portafolio("X", portafolio, ahora=AHORA)


def test_una_base_inventada_no_pasa():
    import cartera
    portafolio = cartera.desde_corrida(
        nombre="X", tickers=["AAPL"], pesos=[1.0], horizonte="1 Mes",
        estrategia="max_sharpe", peso_min=0.0, peso_max=1.0,
        permitir_cortos=False, shrinkage=True, metricas={}, ahora=AHORA,
    )
    with pytest.raises(AsientoInvalido, match="base"):
        mod.desde_portafolio("X", portafolio, base="a_ojo", ahora=AHORA)


def test_los_objetivos_se_apilan_y_manda_el_ultimo():
    from dataclasses import replace
    con_dos = replace(VACIO, objetivos=[
        Objetivo(fecha="2026-01-01", base="estrategia", portafolio={}),
        Objetivo(fecha="2026-06-01", base="equal_weight", portafolio={}),
    ])
    assert con_dos.objetivo.fecha == "2026-06-01"


def test_actualizar_hace_crecer_el_libro_sin_bifurcarlo(tmp_path):
    # `guardar` nunca sobrescribe, a proposito. Pero registrar una operacion no
    # crea un libro nuevo: hace crecer el que hay. Sin `actualizar`, cada alta
    # dejaba un fichero mas y la pantalla seguia leyendo el primero -- medido en
    # la app: dos altas, tres ficheros, y el saldo siempre a cero.
    libro, _ = anadir(VACIO, Asiento(id="ap", fecha="2026-09-01",
                                     tipo="aportacion", importe=1000.0), hoy=HOY)
    ruta = mod.guardar(libro, tmp_path)

    crecido, _ = anadir(libro, Asiento(id="ap2", fecha="2026-09-02",
                                       tipo="aportacion", importe=500.0), hoy=HOY)
    misma = mod.actualizar(crecido, ruta)

    assert misma == ruta
    assert [p.name for p in tmp_path.glob("*.json")] == [ruta.name]
    assert len(mod.cargar(ruta).asientos) == 2


def test_un_nan_escrito_a_mano_en_el_fichero_impide_abrirlo(tmp_path):
    # json.loads acepta el literal NaN por defecto, asi que un fichero editado
    # a mano lo mete en el libro sin pasar por ningun formulario. Un NaN
    # envenena el efectivo y borra un activo de la tabla sin decir nada: el
    # libro esta corrupto, y se trata como tal en vez de abrirse a medias.
    ruta = tmp_path / "2026-09-02-100000-envenenado.json"
    ruta.write_text(
        '{"nombre": "Prueba", "creado": "2026-09-02T10:00:00", "moneda": "USD",'
        ' "objetivos": [], "asientos": [{"id": "a1", "fecha": "2026-09-01",'
        ' "tipo": "compra", "ticker": "AAPL", "acciones": 10.0,'
        ' "precio": 220.0, "importe": NaN}]}',
        encoding="utf-8",
    )
    with pytest.raises(mod.LibroIlegible, match="a1"):
        mod.cargar(ruta)
    # Y sigue en disco: una cache se regenera, un libro no.
    assert ruta.exists()


def test_un_fallo_a_media_escritura_no_deja_medio_libro_en_el_destino(tmp_path, monkeypatch):
    # El patron tmp-then-replace existe justo para esto: lo que se escribe a
    # medias es el .tmp, y el destino solo aparece a traves del replace, que es
    # atomico. Sin el, un proceso muerto a mitad deja un .json con medio JSON
    # dentro, y ese historial no se regenera -- nadie recuerda que compro en
    # marzo.
    primero, _ = anadir(VACIO, Asiento(
        id="ap", fecha="2026-09-01", tipo="aportacion", importe=1000.0), hoy=HOY)
    ruta = mod.guardar(primero, tmp_path)
    antes = ruta.read_text(encoding="utf-8")

    def revienta(self, *args, **kwargs):
        raise OSError("disco lleno")

    monkeypatch.setattr("pathlib.Path.replace", revienta)
    with pytest.raises(OSError):
        mod.guardar(primero, tmp_path)

    # Ni un .json nuevo a medias, ni el anterior tocado. El .tmp puede quedar de
    # escombro: es el mismo compromiso, escrito y aceptado, que documenta
    # `aprobacion/acta.py:guardar_acta`.
    assert sorted(p.name for p in tmp_path.glob("*.json")) == [ruta.name]
    assert ruta.read_text(encoding="utf-8") == antes


# --- El libro elegido, compartido entre pantallas -----------------------------
#
# Tres pantallas --Seguimiento, Rebalanceo y Noticias-- pintan el mismo
# desplegable. Sin `key`, ninguna de las tres deja rastro en `session_state`,
# asi que «Anotar lo que ejecute» saltaba de Rebalanceo a Seguimiento y
# aterrizaba en OTRO libro con el formulario de registrar abierto debajo. El
# libro es append-only: un asiento en la cartera equivocada solo se deshace con
# una anulacion que queda en el historial para siempre.


def _entrada(nombre: str, fichero: str) -> mod.Entrada:
    from pathlib import Path
    return mod.Entrada(
        ruta=Path("libros") / fichero,
        libro=Libro(nombre=nombre, creado="2026-01-01T10:00:00"),
        error=None,
    )


def test_las_etiquetas_llevan_el_nombre_y_el_fichero():
    # El nombre solo no basta: dos libros pueden llamarse igual, y entonces el
    # desplegable ensena dos opciones indistinguibles.
    entradas = [_entrada("Nucleo", "a.json"), _entrada("Nucleo", "b.json")]
    assert list(mod.etiquetas_de(entradas)) == ["Nucleo · a.json", "Nucleo · b.json"]


def test_un_libro_ilegible_no_es_una_opcion_del_desplegable():
    # Se nombra aparte, con su motivo, pero no se puede elegir: no hay nada
    # dentro que ensenar.
    from pathlib import Path
    entradas = [
        _entrada("Nucleo", "a.json"),
        mod.Entrada(ruta=Path("libros/roto.json"), libro=None, error="roto"),
    ]
    assert list(mod.etiquetas_de(entradas)) == ["Nucleo · a.json"]


def test_el_libro_recordado_manda_si_sigue_estando():
    etiquetas = mod.etiquetas_de([_entrada("Uno", "a.json"), _entrada("Dos", "b.json")])
    assert mod.eleccion_vigente(etiquetas, "Dos · b.json") == "Dos · b.json"


def test_un_libro_recordado_que_ya_no_esta_no_deja_la_pantalla_colgada():
    # Las tres pantallas no listan siempre lo mismo --una puede filtrar, un
    # fichero puede haberse vuelto ilegible-- asi que la clave compartida puede
    # apuntar a una opcion que aqui no existe. Se cae a la primera en vez de
    # reventar.
    etiquetas = mod.etiquetas_de([_entrada("Uno", "a.json")])
    assert mod.eleccion_vigente(etiquetas, "Dos · b.json") == "Uno · a.json"


def test_sin_ningun_libro_legible_no_hay_nada_que_preseleccionar():
    assert mod.eleccion_vigente({}, "Uno · a.json") is None


# `fijar_eleccion` es la mitad que toca `st.session_state`, y esta aqui y no en
# la vista porque es la que puede tumbar la pantalla: Streamlit revienta la
# pasada entera si encuentra en `session_state` un valor que no esta en
# `options`, y quien lo puso pudo ser OTRA pantalla. Recibe el estado como un
# diccionario cualquiera --`st.session_state` lo es a estos efectos-- para que
# se pueda probar sin levantar Streamlit, que es la misma razon por la que la
# aritmetica vive en `seguimiento/panel.py`.


def test_el_libro_recordado_se_queda_puesto_si_sigue_estando():
    etiquetas = mod.etiquetas_de([_entrada("Uno", "a.json"), _entrada("Dos", "b.json")])
    estado = {mod.CLAVE_SELECCION: "Dos · b.json"}
    assert mod.fijar_eleccion(etiquetas, estado) == "Dos · b.json"
    assert estado[mod.CLAVE_SELECCION] == "Dos · b.json"


def test_un_recuerdo_que_ya_no_existe_se_corrige_antes_de_pintar_el_widget():
    # Lo que importa es que quede CORREGIDO en el estado, no solo devuelto: el
    # desplegable lee `session_state` por su `key`, asi que una etiqueta muerta
    # ahi dentro tumba la pantalla antes de dibujar nada.
    etiquetas = mod.etiquetas_de([_entrada("Uno", "a.json")])
    estado = {mod.CLAVE_SELECCION: "Borrado · z.json"}
    assert mod.fijar_eleccion(etiquetas, estado) == "Uno · a.json"
    assert estado[mod.CLAVE_SELECCION] == "Uno · a.json"


def test_sin_nada_que_elegir_el_recuerdo_no_se_borra():
    # Una pantalla sin libros legibles corta antes del desplegable. Borrar aqui
    # el recuerdo castigaria a las otras dos: el usuario volveria a la suya y se
    # encontraria otro libro elegido sin haber tocado nada.
    estado = {mod.CLAVE_SELECCION: "Uno · a.json"}
    assert mod.fijar_eleccion({}, estado) is None
    assert estado[mod.CLAVE_SELECCION] == "Uno · a.json"


def test_la_primera_vez_no_hay_nada_recordado_y_manda_la_primera():
    estado: dict = {}
    etiquetas = mod.etiquetas_de([_entrada("Uno", "a.json"), _entrada("Dos", "b.json")])
    assert mod.fijar_eleccion(etiquetas, estado) == "Uno · a.json"


# --- El temporal de la escritura atomica --------------------------------------


def test_dos_escrituras_no_comparten_el_nombre_del_temporal(tmp_path, monkeypatch):
    # Con `ruta.with_suffix(".tmp")` las dos pasadas escribian en el MISMO
    # fichero. Si un `replace` cae mientras la otra esta a mitad de su
    # escritura, lo que queda en el destino es JSON truncado y el libro pasa a
    # ilegible -- y eso no se regenera.
    from pathlib import Path

    libro, _ = anadir(VACIO, Asiento(id="ap", fecha="2026-09-01",
                                     tipo="aportacion", importe=1000.0), hoy=HOY)
    ruta = mod.guardar(libro, tmp_path)

    usados = []
    original = Path.replace

    def anotando(self, destino):
        usados.append(Path(self))
        return original(self, destino)

    monkeypatch.setattr(Path, "replace", anotando)
    mod.actualizar(libro, ruta)
    mod.actualizar(libro, ruta)

    assert len(usados) == 2
    assert usados[0] != usados[1]
    # Y en el mismo directorio que el destino: un `replace` entre volumenes
    # deja de ser atomico, que es lo unico que este patron compra.
    assert {p.parent for p in usados} == {ruta.parent}


# --- El efectivo que ve quien escribe es el que ve la pantalla ---------------


def _con_dividendo_automatico():
    """Aporta 1.000, compra 10 a 100 (efectivo 0) y cobra 2,00 por accion."""
    import pandas as pd

    from seguimiento import precios

    fechas = pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08"])
    hist = precios.Historia(
        cierres=pd.DataFrame({"ACME": [100.0] * 4}, index=fechas),
        dividendos=pd.DataFrame({"ACME": [0.0, 0.0, 0.0, 2.0]}, index=fechas),
        splits=pd.DataFrame({"ACME": [0.0] * 4}, index=fechas),
        sin_datos=[],
    )
    asientos = [
        Asiento(id="ap", fecha="2026-01-05", tipo="aportacion", importe=1000.0),
        Asiento(id="c1", fecha="2026-01-05", tipo="compra", ticker="ACME",
                acciones=10.0, precio=100.0, importe=1000.0),
    ]
    return Libro(nombre="con dividendo", creado="2026-01-05T09:00:00",
                 asientos=asientos), hist


def test_retirar_el_dividendo_que_la_pantalla_ensena_no_se_rechaza():
    """La cabecera decia 20,00 de efectivo y el validador decia 0,00.

    `estado()` pasó a cobrar los dividendos automáticos y `anadir` se quedó sin
    verlos, así que la pantalla y quien escribe dejaron de contar lo mismo. El
    usuario leía que tenía el dividendo en caja y el programa le rechazaba
    sacarlo.
    """
    libro, hist = _con_dividendo_automatico()
    retiro = Asiento(id="r1", fecha="2026-01-08", tipo="retiro", importe=20.0)

    actualizado, escritos = anadir(libro, retiro, hoy=date(2026, 1, 9), historia=hist)

    assert [a.id for a in escritos] == ["r1"]
    assert actualizado.asientos[-1].tipo == "retiro"


def test_comprar_con_el_dividendo_no_inventa_una_aportacion():
    """Y este es el daño de verdad: el libro es append-only.

    Sin ver el dividendo, `financiar=True` escribía una aportación de 20,00 que
    el usuario nunca hizo. Queda para siempre inflando el «aportado neto»,
    envenenando la TIR con un flujo externo inexistente, y dejando en caja un
    dinero que en el broker no está.
    """
    libro, hist = _con_dividendo_automatico()
    compra_pequena = Asiento(id="c2", fecha="2026-01-08", tipo="compra",
                             ticker="ACME", acciones=0.2, precio=100.0, importe=20.0)

    _, escritos = anadir(libro, compra_pequena, hoy=date(2026, 1, 9),
                         financiar=True, historia=hist)

    assert [a.tipo for a in escritos] == ["compra"], (
        "se ha escrito una aportación que el usuario no hizo"
    )


def test_sin_historia_el_guardarrail_sigue_siendo_el_conservador():
    """Si la descarga de precios falla, no se puede saber del dividendo.

    Ahí lo correcto es seguir siendo estricto: rechazar de más es recuperable
    --el usuario registra el dividendo a mano y vuelve a intentarlo-- y aceptar
    de más escribe un descubierto que no se puede deshacer.
    """
    libro, _ = _con_dividendo_automatico()
    retiro = Asiento(id="r1", fecha="2026-01-08", tipo="retiro", importe=20.0)

    with pytest.raises(AsientoInvalido):
        anadir(libro, retiro, hoy=date(2026, 1, 9))


def test_el_veredicto_del_libro_conserva_el_liston_contra_el_que_se_dicto():
    """`CAMPOS_VEREDICTO` recortaba los dos campos nuevos justo cuando el
    portafolio ya los traia.

    Guardar `beats_equal_weight` sin el umbral contra el que se dicto es
    guardar una conclusion sin su premisa: el liston paso de uno a dos errores
    estandar, asi que un booleano suelto no se puede volver a leer. Es el mismo
    defecto que se acaba de cerrar en la pantalla de portafolios, una capa mas
    abajo.
    """
    metricas = {
        "oos_sharpe": 2.24, "oos_equal_weight_sharpe": 2.07,
        "oos_sharpe_stderr": 2.10, "oos_gap_stderr": 0.20,
        "beats_equal_weight": True, "oos_windows": 4,
        "oos_umbral_veredicto": 0.40, "oos_sigmas_veredicto": 2.0,
        "sharpe": 1.13,  # no es del veredicto: no debe colarse
    }

    guardado = veredicto_de(metricas)

    assert guardado["oos_umbral_veredicto"] == 0.40
    assert guardado["oos_sigmas_veredicto"] == 2.0
    assert "sharpe" not in guardado


def test_un_portafolio_sin_el_liston_sigue_dando_un_veredicto_leible():
    """Los guardados antes de que el umbral viajara no traen los campos."""
    guardado = veredicto_de({"oos_sharpe": 2.24, "beats_equal_weight": None})

    assert guardado["oos_umbral_veredicto"] is None
    assert guardado["oos_sigmas_veredicto"] is None


# --- Leer el veredicto que el libro se llevo dentro ---------------------------
#
# `veredicto_de` es la mitad de ida del contrato: copia la MEDICION dentro del
# objetivo. Estos prueban la mitad de vuelta -- que al leerla se vuelve a
# dictar, y no se lee el `beats_equal_weight` congelado.


def _objetivo_con(**metricas) -> Objetivo:
    """Un objetivo cualquiera cuyo interes esta entero en sus metricas."""
    return Objetivo(
        fecha="2026-09-02", base="estrategia",
        portafolio={"posiciones": [{"ticker": "AAPL", "peso": 1.0}]},
        veredicto=veredicto_de(metricas),
    )


def test_el_libro_re_dicta_el_veredicto_en_vez_de_leer_el_booleano_guardado():
    """Un True dictado a un error estandar no puede seguir siendo True hoy.

    Es el mismo defecto que se acaba de cerrar en las tres pantallas, una capa
    mas abajo: el objetivo del libro guarda `beats_equal_weight` y quien lo lea
    a pelo se lleva la conclusion de entonces contra el liston de entonces. El
    hueco de +0,35 con error de +-0,20 pasaba de uno y no pasa de dos, asi que
    hoy la respuesta es «no se distingue», y hay que DECIR que el fichero
    guarda otra cosa en vez de cambiarla en silencio.
    """
    objetivo = _objetivo_con(
        oos_sharpe=2.42, oos_equal_weight_sharpe=2.07,
        oos_gap_stderr=0.20, oos_windows=4,
        beats_equal_weight=True,
        oos_umbral_veredicto=0.20, oos_sigmas_veredicto=1.0,
    )

    dictamen = mod.veredicto_vigente(objetivo)

    assert objetivo.veredicto["beats_equal_weight"] is True
    assert dictamen["estado"] is None
    assert dictamen["discrepa"] is True
    assert dictamen["umbral"] == pytest.approx(0.40)


def test_un_objetivo_sin_el_error_de_la_diferencia_no_afirma_ningun_veredicto():
    """Los libros anteriores a `oos_gap_stderr` no se pueden recomprobar.

    Devolver el booleano guardado seria afirmar un resultado que nadie puede
    volver a obtener; inventarle un False afirmaria uno que nadie obtuvo. None
    es la unica respuesta cierta, y es la que `veredicto_guardado` ya da.
    """
    viejo = _objetivo_con(
        oos_sharpe=2.42, oos_equal_weight_sharpe=2.07,
        oos_windows=4, beats_equal_weight=True,
    )

    assert mod.veredicto_vigente(viejo) is None


def test_un_libro_sin_objetivo_no_tiene_veredicto_que_dictar():
    # Misma forma que `pesos_objetivo` e `importe_previsto`: recibe el campo
    # opcional y devuelve el valor neutro, para que quien pinte no tenga que
    # preguntar dos veces.
    assert VACIO.objetivo is None
    assert mod.veredicto_vigente(None) is None
    assert mod.veredicto_vigente(Objetivo(
        fecha="2026-09-02", base="equal_weight", portafolio={},
    )) is None


def test_el_veredicto_se_vuelve_a_dictar_despues_de_pasar_por_el_disco(tmp_path):
    """El JSON tiene que llevar la medicion, no solo la conclusion.

    Si `CAMPOS_VEREDICTO` recortase el umbral o las sigmas, esto seguiria
    pasando; lo que no sobrevive al viaje es el hueco y su error, y sin ellos
    `veredicto_vigente` devolveria None aqui. Por eso se comprueba contra el
    fichero y no contra el objeto en memoria.
    """
    import cartera
    portafolio = cartera.desde_corrida(
        nombre="Mi cartera", tickers=["AAPL", "MSFT"], pesos=[0.6, 0.4],
        horizonte="1 Mes", estrategia="max_sharpe", peso_min=0.0, peso_max=1.0,
        permitir_cortos=False, shrinkage=True,
        metricas={
            "oos_sharpe": 2.42, "oos_equal_weight_sharpe": 2.07,
            "oos_gap_stderr": 0.20, "oos_windows": 4,
            "beats_equal_weight": True,
            "oos_umbral_veredicto": 0.20, "oos_sigmas_veredicto": 1.0,
        },
        ahora=AHORA,
    )
    nuevo = mod.desde_portafolio("Seguimiento", portafolio, base="estrategia",
                                 ahora=AHORA)

    vuelto = mod.cargar(mod.guardar(nuevo, tmp_path))

    dictamen = mod.veredicto_vigente(vuelto.objetivo)
    assert dictamen["estado"] is None
    assert dictamen["discrepa"] is True
    assert dictamen["titular"] == "Indistinguible de repartir por igual"

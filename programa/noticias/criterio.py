"""Que tipos de 8-K salen destacados, y por que esos.

**Este fichero esta congelado.** Vive aparte del codigo que lo usa por la misma
razon que `rebalanceo/criterio.py` y `ranking/criterio.py`: la fecha del commit
que lo introduce es la prueba de que la lista no se armo a la vista de los
expedientes de ninguna cartera real.

La regla que genera la lista, y que hay que poder defender sin ver datos: **son
materiales los tipos que invalidan o alteran los numeros sobre los que se
construyo la tesis.** La cartera sale de un analisis fundamental (sub-proyectos
A y B), asi que lo grave es lo que mueve esos fundamentales o dice que estaban
mal. Nada de esto es una apuesta sobre el precio: es una apuesta sobre si las
cifras que se analizaron siguen siendo las cifras.

**Destacar no es excluir.** Lo que no esta aqui se pliega, no se descarta. Si
se descartara, el sub-proyecto I nunca lo veria.
"""

DESCRIPCIONES = {
    "4.02": "Cuentas anteriores no fiables",
    "4.01": "Cambio de auditor",
    "1.03": "Concurso o quiebra",
    "3.01": "Aviso de exclusión de cotización",
    "2.06": "Deterioros materiales",
    "2.02": "Resultados",
    "2.01": "Adquisición o venta de activos",
    "5.01": "Cambio de control",
    "5.02": "Salidas o nombramientos en la directiva",
    "1.01": "Acuerdo material",
    "1.05": "Incidente material de ciberseguridad",
    # Los de rutina tambien llevan texto: se pliegan, pero se muestran, y un
    # codigo desnudo no le dice nada a nadie.
    "7.01": "Divulgación Regulation FD",
    "8.01": "Otros eventos",
    "9.01": "Estados financieros y anexos",
    "5.07": "Votación de accionistas",
    "5.03": "Cambio de estatutos",
    "2.03": "Nueva obligación financiera",
    "3.02": "Venta de acciones no registrada",
}

MATERIALES = frozenset({
    "4.02", "4.01", "1.03", "3.01", "2.06",
    "2.02", "2.01", "5.01", "5.02", "1.01", "1.05",
})


def material(tipos: "tuple[str, ...]") -> bool:
    """Whether any of the filing's items is one that matters.

    **Basta uno.** Un expediente comunica varias cosas a la vez y el indice de
    la SEC las devuelve juntas: un anuncio de resultados es "2.02,9.01", donde
    el 9.01 son los anexos. Exigir que todos fueran materiales, o comparar la
    cadena entera contra la lista, dejaria plegado el caso mas frecuente que
    existe.
    """
    return any(tipo in MATERIALES for tipo in tipos)

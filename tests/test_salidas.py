"""Los codigos de salida del constructor, y que el workflow los lea igual.

El 21 y el 22 de noviembre de 2026 el servidor de rasteres de FAO devolvio 502.
La construccion murio en su primera llamada de red, sin descargar ni escribir
nada, y aun asi la actualizacion automatica abrio un issue anunciando que FAO
habia republicado dekads y recomendando relanzar con `--aceptar-republicacion`.

El diagnostico era falso y la recomendacion apuntaba a la unica accion
destructiva que el constructor sabe hacer: sobrescribir cifras que alguien ya
pudo citar. Nadie la siguio, pero podria haberla seguido.

La causa no fue un error de logica sino una colision de significados. La
republicacion salia con codigo 1, que es tambien con lo que Python sale ante
cualquier excepcion sin atrapar, asi que el workflow -que solo ve el numero- no
podia distinguir un diagnostico del constructor de un choque cualquiera.

De ahi estas pruebas, y son dos cosas distintas. Que el numero del diagnostico
sea uno que un choque no pueda producir, y que el workflow este leyendo ese
mismo numero: el codigo y el workflow son dos archivos que tienen que decir lo
mismo, y separarse en silencio es exactamente lo que paso.
"""
import re
from pathlib import Path

import pytest

from asis import build

WORKFLOW = (Path(__file__).resolve().parent.parent
            / ".github" / "workflows" / "actualizar-panel.yml")

# Los codigos que el constructor usa para decir algo, no para morirse.
DIAGNOSTICOS = {"EXIT_ARGS": build.EXIT_ARGS,
                "EXIT_REPUBLICACION": build.EXIT_REPUBLICACION}


def test_ningun_diagnostico_usa_el_uno():
    """Es la prueba del defecto. Python sale con 1 ante cualquier excepcion sin
    atrapar, asi que un 1 no puede significar nada nuestro: si lo significara,
    una caida de red podria hacerse pasar por el diagnostico."""
    for nombre, codigo in DIAGNOSTICOS.items():
        assert codigo != 1, (
            f"{nombre} vale 1, que es con lo que Python sale al chocar: un "
            "fallo cualquiera podria hacerse pasar por este diagnostico")


def test_los_codigos_son_distintos_entre_si():
    """Dos diagnosticos con el mismo numero serian indistinguibles para quien
    los lee, que es el workflow."""
    codigos = list(DIAGNOSTICOS.values()) + [build.EXIT_OK]
    assert len(set(codigos)) == len(codigos)


def test_el_exito_es_cero():
    assert build.EXIT_OK == 0


def test_una_serie_inexistente_sale_por_argumentos(capsys):
    """Un camino real de main(), no una constante: pedir una serie que no
    existe sale con EXIT_ARGS y no toca la red."""
    assert build.main(["--series", "no-existe"]) == build.EXIT_ARGS
    assert "serie desconocida" in capsys.readouterr().out


# --- El workflow lee los mismos numeros --------------------------------------

@pytest.fixture(scope="module")
def workflow() -> str:
    if not WORKFLOW.exists():
        pytest.skip(f"no esta {WORKFLOW}")
    return WORKFLOW.read_text(encoding="utf-8")


def test_el_aviso_de_republicacion_espera_el_codigo_de_republicacion(workflow):
    """El paso que abre el issue tiene que dispararse con el numero que el
    constructor devuelve de verdad, no con uno escrito a mano que quedo viejo.
    """
    esperado = f"salida == '{build.EXIT_REPUBLICACION}'"
    assert esperado in workflow, (
        f"el workflow no condiciona ningun paso a {esperado}; si cambio "
        "EXIT_REPUBLICACION hay que cambiarlo ahi tambien")


def test_el_workflow_ya_no_trata_el_uno_como_republicacion(workflow):
    """La condicion vieja. Mientras exista, una caida de FAO vuelve a abrir un
    issue que recomienda sobrescribir datos."""
    assert "salida == '1'" not in workflow


def test_el_paso_de_fallo_no_se_traga_la_republicacion(workflow):
    """Los dos caminos tienen que ser excluyentes: una republicacion abre su
    issue y no se reporta como caida, y una caida no se reporta como
    republicacion."""
    fallo = re.search(r"salida != '0' && steps\.construir\.outputs\.salida "
                      r"!= '(\d+)'", workflow)
    assert fallo, ("el paso que explica un fallo deberia excluir el codigo de "
                   "republicacion")
    assert int(fallo.group(1)) == build.EXIT_REPUBLICACION

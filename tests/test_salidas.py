"""Los codigos de salida del constructor, y que el workflow los lea igual.

El 21 y el 22 de noviembre de 2026 el servidor de rasteres de FAO devolvio 502.
La construccion murio en su primera llamada de red, sin descargar ni escribir
nada, y aun asi la actualizacion automatica abrio un issue anunciando que FAO
habia republicado dekads y recomendando relanzar con `--aceptar-republicacion`.

El diagnostico era falso y la recomendacion apuntaba a la unica accion
destructiva que el constructor sabe hacer: sobrescribir cifras que alguien ya
pudo citar.

La causa no fue un error de logica sino una colision de significados. La
republicacion salia con codigo 1, que es tambien con lo que Python sale ante
cualquier excepcion sin atrapar, asi que el workflow -que solo ve el numero- no
podia distinguir un diagnostico del constructor de un choque cualquiera.

Estas pruebas cubren tres cosas distintas, y las tres fallaron alguna vez.

Que cada camino salga con su numero, ejercitando el camino y no la constante:
una prueba que solo compare constantes pasaria igual si manana alguien vuelve a
escribir `return 1` en el camino de republicacion.

Que la clasificacion la haga la excepcion que mato la corrida y no el texto del
registro. El registro guarda errores ya recuperados, y la URL viaja dentro de
los mensajes de error, asi que diagnosticar leyendo texto confunde un 400
rechazado con un servicio caido.

Y que el workflow este leyendo los mismos numeros: el codigo y el workflow son
dos archivos que tienen que decir lo mismo, y separarse en silencio es
exactamente lo que paso.
"""
import re
from pathlib import Path

import pandas as pd
import pytest
import requests

from asis import build, panel

WORKFLOW = (Path(__file__).resolve().parent.parent
            / ".github" / "workflows" / "actualizar-panel.yml")

# Los codigos que el constructor usa para decir algo, no para morirse.
DIAGNOSTICOS = {"EXIT_ARGS": build.EXIT_ARGS,
                "EXIT_REPUBLICACION": build.EXIT_REPUBLICACION,
                "EXIT_FUENTE": build.EXIT_FUENTE}


# --- Los numeros --------------------------------------------------------------

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


# --- Los caminos, ejercitados -------------------------------------------------

def test_una_serie_inexistente_sale_por_argumentos(capsys):
    assert build.main(["--series", "no-existe"]) == build.EXIT_ARGS
    assert "serie desconocida" in capsys.readouterr().out


def _red_que_falla(monkeypatch, err):
    """Hace que la primera llamada de red del constructor lance `err`."""
    def caido(*a, **k):
        raise err
    monkeypatch.setattr(build.client, "last_dekad", caido)


@pytest.mark.parametrize("err", [
    requests.exceptions.RetryError("too many 502 error responses"),
    requests.ConnectionError("connection refused"),
    requests.Timeout("read timed out"),
])
def test_la_fuente_caida_sale_por_su_propio_codigo(monkeypatch, capsys, err):
    """El caso del 21 y 22 de noviembre. Lo que llega cuando el servicio no
    esta: reintentos agotados, conexion rechazada o tiempo agotado."""
    _red_que_falla(monkeypatch, err)
    assert build.main([]) == build.EXIT_FUENTE
    salida = capsys.readouterr().out
    assert "LA FUENTE NO RESPONDIO" in salida
    assert "REPUBLICACION" not in salida


def test_una_peticion_rechazada_no_es_una_caida_de_la_fuente(monkeypatch):
    """Un 400 lleva la URL de FAO dentro del mensaje, asi que diagnosticar por
    texto lo confundia con un servicio caido y avisaba que no habia nada que
    arreglar. Un HTTPError si pide mirar el codigo: se deja pasar, con su traza
    y la salida 1 de Python."""
    _red_que_falla(monkeypatch, requests.HTTPError(
        "400 Client Error for url: https://asis-esri.fao.org/image/rest/"))
    with pytest.raises(requests.HTTPError):
        build.main([])


def test_un_fallo_que_no_entendemos_no_se_disfraza(monkeypatch):
    """Cualquier otra excepcion sale a la superficie en vez de convertirse en
    un diagnostico. Es la diferencia entre decir que no sabemos y decir algo
    falso con confianza."""
    _red_que_falla(monkeypatch, ValueError("algo nuestro se rompio"))
    with pytest.raises(ValueError):
        build.main([])


def test_la_republicacion_sin_aceptar_sale_por_su_propio_codigo(
        monkeypatch, capsys):
    """El camino completo hasta el return, no la constante. Si alguien vuelve a
    escribir `return 1` ahi, esta prueba falla."""
    republicado = {"serie": "asi_gs1", "dekad_id": "2026-10-D3",
                   "dif_max": 4.2, "tolerancia": 0.5,
                   "municipios_afectados": 17,
                   "aparecen": 0, "desaparecen": 0}
    monkeypatch.setattr(build, "stored_dekads", lambda sid: set())
    monkeypatch.setattr(build.client, "last_dekad",
                        lambda *a, **k: "2026-11-D2")
    monkeypatch.setattr(build, "build_series", lambda *a, **k: {
        "nuevos": 0, "preliminares": [], "dekads": [],
        "preliminares_fao": None, "republicados": [republicado]})
    monkeypatch.setattr(build, "build_official", lambda *a, **k: {})
    monkeypatch.setattr(build, "write_manifest", lambda *a, **k: None)
    monkeypatch.setattr(panel, "load", lambda *a, **k: pd.DataFrame())

    assert build.main(["--sin-geometria"]) == build.EXIT_REPUBLICACION
    assert "REPUBLICACION DETECTADA" in capsys.readouterr().out


# --- El workflow lee los mismos numeros ---------------------------------------

@pytest.fixture(scope="module")
def workflow() -> str:
    if not WORKFLOW.exists():
        pytest.skip(f"no esta {WORKFLOW}")
    return WORKFLOW.read_text(encoding="utf-8")


def test_el_aviso_de_republicacion_espera_su_codigo(workflow):
    esperado = f"salida == '{build.EXIT_REPUBLICACION}'"
    assert esperado in workflow, (
        f"el workflow no condiciona ningun paso a {esperado}; si cambio "
        "EXIT_REPUBLICACION hay que cambiarlo ahi tambien")


def test_el_aviso_de_fuente_caida_espera_su_codigo(workflow):
    esperado = f"salida == '{build.EXIT_FUENTE}'"
    assert esperado in workflow, (
        f"el workflow no condiciona ningun paso a {esperado}; una caida de la "
        "fuente quedaria reportada como fallo propio")


def test_el_workflow_ya_no_trata_el_uno_como_republicacion(workflow):
    """La condicion vieja. Mientras exista, una caida de FAO vuelve a abrir un
    issue que recomienda sobrescribir datos."""
    assert "salida == '1'" not in workflow


def test_el_workflow_no_diagnostica_leyendo_el_registro(workflow):
    """La primera version de este arreglo clasificaba con grep sobre
    construccion.log. El registro guarda errores ya recuperados y los mensajes
    traen la URL dentro, asi que el texto no sirve como evidencia."""
    assert "asis-esri" not in workflow
    assert not re.search(r"grep[^\n]*construccion\.log", workflow)


def test_el_paso_de_fallo_propio_excluye_los_dos_diagnosticos(workflow):
    """Los caminos tienen que ser excluyentes: ni una republicacion ni una
    caida de la fuente pueden caer tambien en el paso que dice que la
    construccion se rompio por causa propia."""
    fallo = re.search(
        r"salida != '0'((?: && steps\.construir\.outputs\.salida != '\d+')+)",
        workflow)
    assert fallo, "no encontre la condicion del paso de fallo propio"
    excluidos = {int(n) for n in re.findall(r"'(\d+)'", fallo.group(1))}
    assert {build.EXIT_REPUBLICACION, build.EXIT_FUENTE} <= excluidos

"""Curación de la biblioteca: retirar y fusionar lecciones sin perder su historia."""
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "harness" / "hooks"))
from lib import biblioteca  # noqa: E402

REF_A = "ISR-1/fase_1/h1"
REF_B = "ISR-1/fase_1/h2"
REF_C = "ISR-1/fase_1/h3"
FECHA = "03-11-2026"


def _aprobado(id, **extra):
    base = {"id": id, "origen": "reflector", "estado": "aprobado",
            "senal": f"señal {id}", "leccion": f"lección {id}", "evidencia": "e",
            "confianza": "media", "dimension": "proceso", "componente": "check"}
    base.update(extra)
    return base


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name)
        for id in ("h1", "h2", "h3"):
            biblioteca.escribir_entrada(self.raiz, "ISR-1", "fase_1", _aprobado(id),
                                        fecha="01-11-2026")

    def texto(self, ruta: Path) -> str:
        return ruta.read_text(encoding="utf-8")

    def retirada(self, ref: str) -> Path:
        return biblioteca.entrada_path(self.raiz, ref, subdir="retiradas")


class TestRetirar(Base):
    def test_retirar_mueve_la_entrada_y_anota_el_motivo(self):
        destino = biblioteca.retirar(self.raiz, REF_A, "contradice agent-x §2", FECHA)
        self.assertFalse(biblioteca.entrada_path(self.raiz, REF_A).exists())
        self.assertEqual(destino, self.retirada(REF_A))
        self.assertTrue(self.texto(destino).rstrip("\n").endswith(
            "- **retirada**: 03-11-2026 · contradice agent-x §2"))

    def test_retirar_conserva_fallas_e_implementada(self):
        biblioteca.registrar_falla(self.raiz, REF_A, "ISR-2/fase_1/h1", "volvió", "02-11-2026")
        biblioteca.marcar_implementada(self.raiz, REF_A, "check x", "02-11-2026")
        texto = self.texto(biblioteca.retirar(self.raiz, REF_A, "obsoleta", FECHA))
        self.assertIn("- **falló**: 02-11-2026 · ISR-2/fase_1/h1 · sin pieza — volvió", texto)
        self.assertIn("- **implementada**: 02-11-2026 · check x", texto)

    def test_retirar_una_ref_que_no_esta_es_error(self):
        with self.assertRaises(ValueError):
            biblioteca.retirar(self.raiz, "ISR-9/fase_1/h1", "x", FECHA)
        self.assertFalse((biblioteca.biblioteca_dir(self.raiz) / "retiradas").exists())

    def test_el_indice_lista_las_retiradas_aparte(self):
        biblioteca.retirar(self.raiz, REF_A, "contradice agent-x §2", FECHA)
        indice = self.texto(biblioteca.biblioteca_dir(self.raiz) / "INDEX.md")
        aprobadas, resto = indice.split("## Retiradas — no aplicar", 1)
        retiradas, rechazadas = resto.split("## Rechazadas", 1)
        self.assertNotIn("ISR-1-fase_1-h1.md", aprobadas)
        self.assertIn("señal h1 — retiradas/ISR-1-fase_1-h1.md — motivo: contradice "
                      "agent-x §2", retiradas)
        self.assertIn("entradas/ISR-1-fase_1-h2.md", aprobadas)

    def test_sin_retiradas_la_seccion_dice_vacia(self):
        indice = self.texto(biblioteca.reconstruir_indice(self.raiz))
        retiradas = indice.split("## Retiradas — no aplicar", 1)[1].split("## Rechazadas")[0]
        self.assertIn("_(vacía)_", retiradas)

    def test_ubicacion_dice_donde_esta(self):
        self.assertEqual(biblioteca.ubicacion(self.raiz, REF_A), ("entradas", ""))
        biblioteca.retirar(self.raiz, REF_A, "contradice agent-x §2", FECHA)
        self.assertEqual(biblioteca.ubicacion(self.raiz, REF_A),
                         ("retiradas", "contradice agent-x §2"))
        self.assertEqual(biblioteca.ubicacion(self.raiz, "ISR-9/fase_1/h1"), ("ninguna", ""))


class TestFusionar(Base):
    def fusionar(self, absorbidas=(REF_B,), leccion="lección fusionada", senal=None):
        return biblioteca.fusionar(self.raiz, REF_A, list(absorbidas), leccion, senal, FECHA)

    def test_fusionar_reemplaza_la_leccion_y_guarda_la_original(self):
        texto = self.texto(self.fusionar())
        self.assertIn("- **lección**: lección fusionada", texto)
        self.assertIn("- **lección original**: lección h1", texto)
        self.assertEqual(texto.count("- **lección**: "), 1)
        self.assertIn(f"- **fusionada**: {FECHA} · {REF_B}", texto)

    def test_una_leccion_original_previa_no_se_pisa(self):
        ruta = biblioteca.entrada_path(self.raiz, REF_A)
        ruta.write_text(self.texto(ruta).replace(
            "- **lección**: lección h1", "- **lección**: lección h1\n"
            "- **lección original**: la del reflector"), encoding="utf-8")
        texto = self.texto(self.fusionar())
        self.assertIn("- **lección original**: la del reflector", texto)
        self.assertEqual(texto.count("lección original"), 1)

    def test_fusionar_copia_las_fallas_de_las_absorbidas(self):
        biblioteca.registrar_falla(self.raiz, REF_B, "ISR-2/fase_1/h1", "volvió", "02-11-2026")
        self.fusionar()
        self.assertIn("- **falló**: 02-11-2026 · ISR-2/fase_1/h1 · sin pieza — volvió",
                      self.texto(biblioteca.entrada_path(self.raiz, REF_A)))
        self.assertEqual(len(biblioteca.leer_entrada(self.raiz, REF_A)["fallas"]), 1)

    def test_las_absorbidas_quedan_retiradas_como_fusionadas(self):
        self.fusionar(absorbidas=(REF_B, REF_C))
        for ref in (REF_B, REF_C):
            self.assertEqual(biblioteca.ubicacion(self.raiz, ref),
                             ("retiradas", f"fusionada en {REF_A}"))

    def test_fusionar_con_senal_la_reemplaza_y_sin_senal_la_conserva(self):
        self.assertIn("- **señal**: señal h1", self.texto(self.fusionar()))
        biblioteca.escribir_entrada(self.raiz, "ISR-1", "fase_1", _aprobado("h2"))
        texto = self.texto(self.fusionar(senal="señal nueva"))
        self.assertIn("- **señal**: señal nueva", texto)
        self.assertEqual(texto.count("- **señal**: "), 1)

    def test_fusionar_agrega_senal_a_una_entrada_que_no_la_tenia(self):
        humano = {"id": "h1", "origen": "humano", "estado": "aprobado", "leccion": "mía"}
        biblioteca.escribir_entrada(self.raiz, "ISR-1", "fase_1", humano)
        texto = self.texto(self.fusionar(senal="señal nueva"))
        self.assertIn("- **señal**: señal nueva", texto)
        self.assertIn("- **lección**: lección fusionada", texto)

    def test_fusionar_mezcla_de_implementadas_es_error_y_no_escribe(self):
        biblioteca.marcar_implementada(self.raiz, REF_B, "check y", "02-11-2026")
        antes = [self.texto(biblioteca.entrada_path(self.raiz, r)) for r in (REF_A, REF_B)]
        with self.assertRaises(ValueError):
            self.fusionar()
        despues = [self.texto(biblioteca.entrada_path(self.raiz, r)) for r in (REF_A, REF_B)]
        self.assertEqual(antes, despues)

    def test_fusionar_una_ref_que_no_esta_o_el_destino_absorbido_es_error(self):
        with self.assertRaises(ValueError):
            self.fusionar(absorbidas=("ISR-9/fase_1/h1",))
        with self.assertRaises(ValueError):
            self.fusionar(absorbidas=(REF_A,))
        self.assertTrue(biblioteca.entrada_path(self.raiz, REF_B).is_file())

    def test_fusionar_todas_implementadas_conserva_la_marca_y_anota_las_otras(self):
        biblioteca.marcar_implementada(self.raiz, REF_A, "check x", "02-11-2026")
        biblioteca.marcar_implementada(self.raiz, REF_B, "check y", "02-11-2026")
        texto = self.texto(self.fusionar())
        self.assertIn("- **implementada**: 02-11-2026 · check x", texto)
        self.assertIn(f"- **fusionada**: {FECHA} · {REF_B} · implementada 02-11-2026 · "
                      f"check y", texto)

    def test_fusionar_una_entrada_con_crlf(self):
        ruta = biblioteca.entrada_path(self.raiz, REF_A)
        ruta.write_bytes(self.texto(ruta).replace("\n", "\r\n").encode("utf-8"))
        texto = self.fusionar().read_bytes().decode("utf-8")
        self.assertIn("- **lección**: lección fusionada", texto)
        self.assertEqual(texto.count("- **lección**: "), 1)
        self.assertIn("- **lección original**: lección h1", texto)


if __name__ == "__main__":
    unittest.main()

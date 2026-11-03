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


if __name__ == "__main__":
    unittest.main()

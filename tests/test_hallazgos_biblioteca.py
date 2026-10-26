import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "harness" / "hooks"))
from lib import biblioteca, hallazgos  # noqa: E402


def _h(id="h1", estado="propuesto", **extra):
    base = {"id": id, "origen": "reflector", "estado": estado,
            "senal": "Al editar un formulario", "leccion": "Agregar un check",
            "evidencia": "fase_1 falló dos veces", "confianza": "media",
            "dimension": "proceso", "componente": "check"}
    base.update(extra)
    return base


def _datos(*hs):
    return {"ticket_id": "ISR-110722", "fase_id": "fase_1", "hallazgos": list(hs)}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)


class TestHallazgos(Base):
    def test_render_lista_ids_y_comandos(self):
        txt = hallazgos.render(_datos(_h()))
        for esperado in ("h1", "/hallazgo-ok h1", "/hallazgo-no h1", "No bloquean"):
            self.assertIn(esperado, txt)

    def test_render_vacio_dice_que_no_hubo_lecciones(self):
        self.assertIn("no encontró lecciones", hallazgos.render(_datos()))

    def test_guardar_invalido_lanza_value_error(self):
        malo = _h()
        del malo["id"]
        with self.assertRaises(ValueError):
            hallazgos.guardar(self.root, _datos(malo))

    def test_guardar_escribe_json_y_md(self):
        datos = _datos(_h())
        md = hallazgos.guardar(self.root, datos)
        self.assertTrue(md.exists())
        self.assertTrue(hallazgos.ruta(self.root, "ISR-110722", "fase_1").exists())
        self.assertEqual(hallazgos.leer(self.root, "ISR-110722", "fase_1"), datos)
        self.assertIsNone(hallazgos.leer(self.root, "ISR-110722", "fase_9"))


class TestBiblioteca(Base):
    def test_aprobado_va_a_entradas_y_al_indice(self):
        p = biblioteca.escribir_entrada(self.root, "ISR-110722", "fase_1", _h(estado="aprobado"))
        self.assertEqual(p.parent.name, "entradas")
        indice = (biblioteca.biblioteca_dir(self.root) / "INDEX.md").read_text(encoding="utf-8")
        self.assertIn("[proceso · check]", indice)
        self.assertIn("Al editar un formulario", indice)

    def test_rechazado_va_a_rechazados_con_motivo(self):
        p = biblioteca.escribir_entrada(self.root, "ISR-110722", "fase_1",
                                        _h(estado="rechazado", motivo="es falsa"))
        self.assertEqual(p.parent.name, "rechazados")
        indice = (biblioteca.biblioteca_dir(self.root) / "INDEX.md").read_text(encoding="utf-8")
        self.assertIn("no volver a proponer", indice)
        self.assertIn("es falsa", indice)

    def test_propuesto_no_se_escribe(self):
        with self.assertRaises(ValueError):
            biblioteca.escribir_entrada(self.root, "ISR-110722", "fase_1", _h())

    def test_indice_se_reconstruye_desde_disco(self):
        p = biblioteca.escribir_entrada(self.root, "ISR-110722", "fase_1", _h(estado="aprobado"))
        p.unlink()
        biblioteca.reconstruir_indice(self.root)
        indice = (biblioteca.biblioteca_dir(self.root) / "INDEX.md").read_text(encoding="utf-8")
        self.assertNotIn("Al editar un formulario", indice)
        self.assertIn("_(vacía)_", indice)

    def test_ningun_perfil_trae_biblioteca(self):
        for perfil in (RAIZ / "profiles").iterdir():
            if perfil.is_dir():
                self.assertFalse((perfil / "biblioteca").exists(),
                                 f"{perfil.name} trae biblioteca/: deploy la pisaría (DA6)")

    def test_acentos_sobreviven_ida_y_vuelta(self):
        senal = "Señal: acción en la sección año"
        h = _h(estado="aprobado", senal=senal, leccion="Lección: reparación del módulo")
        md = hallazgos.guardar(self.root, _datos(h))
        p = biblioteca.escribir_entrada(self.root, "ISR-110722", "fase_1", h)
        indice = biblioteca.biblioteca_dir(self.root) / "INDEX.md"
        for archivo in (md, p, indice):
            self.assertIn(senal, archivo.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

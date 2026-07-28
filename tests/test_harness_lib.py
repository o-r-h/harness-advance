import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "harness" / "hooks"))
from lib import harness  # noqa: E402


class TestFindProjectRoot(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_encuentra_la_raiz_desde_un_subdirectorio_profundo(self):
        (self.root / ".claude").mkdir()
        (self.root / ".claude" / "rules.json").write_text("{}", encoding="utf-8")
        profundo = self.root / "Scripts" / "sub" / "otro"
        profundo.mkdir(parents=True)
        self.assertEqual(harness.find_project_root(profundo), self.root.resolve())

    def test_devuelve_none_sin_perfil(self):
        profundo = self.root / "a" / "b"
        profundo.mkdir(parents=True)
        self.assertIsNone(harness.find_project_root(profundo))


class TestJsonAtomico(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_write_json_crea_los_directorios_padre(self):
        destino = self.root / "a" / "b" / "estado.json"
        harness.write_json(destino, {"acentúa": "sí"})
        self.assertEqual(json.loads(destino.read_text(encoding="utf-8"))["acentúa"], "sí")

    def test_write_json_no_deja_archivos_temporales(self):
        destino = self.root / "estado.json"
        harness.write_json(destino, {"a": 1})
        self.assertEqual([p.name for p in self.root.iterdir()], ["estado.json"])


class TestPunteroActual(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_read_current_devuelve_none_si_no_existe(self):
        self.assertIsNone(harness.read_current(self.root))

    def test_write_y_read_current_hacen_ida_y_vuelta(self):
        harness.write_current(self.root, "ISR-110722", "fase_1")
        actual = harness.read_current(self.root)
        self.assertEqual(actual["ticket_id"], "ISR-110722")
        self.assertEqual(actual["fase_id"], "fase_1")


class TestAutoexclusion(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_reconoce_el_repo_fuente_del_harness(self):
        (self.root / "harness" / "hooks").mkdir(parents=True)
        (self.root / "profiles").mkdir()
        self.assertTrue(harness.is_harness_source(self.root))

    def test_un_proyecto_normal_no_es_el_repo_fuente(self):
        (self.root / "Scripts").mkdir()
        self.assertFalse(harness.is_harness_source(self.root))


if __name__ == "__main__":
    unittest.main()

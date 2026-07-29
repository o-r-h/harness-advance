import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
HOOK = RAIZ / "harness" / "hooks" / "gate_phase.py"
sys.path.insert(0, str(RAIZ / "harness" / "hooks"))
from lib import harness  # noqa: E402


def lanzar(payload: dict) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload),
                          capture_output=True, text=True, encoding="utf-8")


class TestHookStop(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / ".claude").mkdir()
        harness.write_json(self.root / ".claude" / "rules.json", {"perfil": "p"})
        harness.write_current(self.root, "ISR-110722", "fase_1")

    def tearDown(self):
        self.tmp.cleanup()

    def con_estado(self, estado: str, intento: int = 1, maximo: int = 3) -> None:
        harness.write_json(
            harness.fase_dir(self.root, "ISR-110722", "fase_1") / "fase_state.json",
            {"fase_id": "fase_1", "estado": estado, "intento_actual": intento,
             "max_reintentos": maximo, "historial_fallos": []})

    def payload(self, reentrada: bool = False) -> dict:
        return {"hook_event_name": "Stop", "cwd": str(self.root),
                "stop_hook_active": reentrada}

    def test_bloquea_si_la_fase_esta_en_ejecucion(self):
        self.con_estado("en_ejecucion")
        resultado = lanzar(self.payload())
        self.assertEqual(resultado.returncode, 2)
        self.assertIn("en_ejecucion", resultado.stderr)

    def test_bloquea_si_la_fase_esta_en_correccion(self):
        self.con_estado("en_correccion", intento=2)
        self.assertEqual(lanzar(self.payload()).returncode, 2)

    def test_bloquea_si_la_fase_esta_en_verificacion(self):
        self.con_estado("en_verificacion")
        self.assertEqual(lanzar(self.payload()).returncode, 2)

    def test_NO_bloquea_esperando_humano(self):
        self.con_estado("esperando_humano")
        resultado = lanzar(self.payload())
        self.assertEqual(resultado.returncode, 0, resultado.stderr)

    def test_NO_bloquea_una_fase_escalada(self):
        self.con_estado("escalado", intento=3)
        self.assertEqual(lanzar(self.payload()).returncode, 0)

    def test_NO_bloquea_una_fase_aprobada(self):
        self.con_estado("aprobada")
        self.assertEqual(lanzar(self.payload()).returncode, 0)

    def test_NO_bloquea_en_la_reentrada_del_propio_hook(self):
        self.con_estado("en_ejecucion")
        self.assertEqual(lanzar(self.payload(reentrada=True)).returncode, 0)

    def test_es_inerte_sin_perfil(self):
        with tempfile.TemporaryDirectory() as sin_perfil:
            resultado = lanzar({"hook_event_name": "Stop", "cwd": sin_perfil,
                                "stop_hook_active": False})
            self.assertEqual(resultado.returncode, 0)
            self.assertEqual(resultado.stderr.strip(), "")

    def test_es_inerte_sin_fase_activa(self):
        harness.write_json(harness.current_pointer_path(self.root),
                           {"ticket_id": "ISR-110722", "fase_id": None})
        self.assertEqual(lanzar(self.payload()).returncode, 0)

    def test_un_payload_ilegible_no_rompe_nada(self):
        resultado = subprocess.run([sys.executable, str(HOOK)], input="no json",
                                   capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(resultado.returncode, 0)


if __name__ == "__main__":
    unittest.main()

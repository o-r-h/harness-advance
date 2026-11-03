import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
HOOK = RAIZ / "harness" / "hooks" / "gate_phase.py"
sys.path.insert(0, str(RAIZ / "harness" / "hooks"))
from lib import harness  # noqa: E402


def lanzar(payload: dict, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload),
                          capture_output=True, text=True, encoding="utf-8",
                          env={**os.environ, **(env or {})})


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
        datos = {"fase_id": "fase_1", "estado": estado, "intento_actual": intento,
                 "max_reintentos": maximo, "historial_fallos": []}
        if estado == "pausada":
            datos["pausas"] = [{"desde": "en_ejecucion", "fecha": "02-11-2026",
                                "motivo": "almuerzo"}]
        harness.write_json(
            harness.fase_dir(self.root, "ISR-110722", "fase_1") / "fase_state.json",
            datos)

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

    def test_NO_bloquea_una_fase_pausada(self):
        self.con_estado("pausada")
        resultado = lanzar(self.payload())
        self.assertEqual(resultado.returncode, 0, resultado.stderr)

    def test_HARNESS_STOP_off_apaga_el_hook(self):
        self.con_estado("en_ejecucion")
        for valor in ("off", "OFF", " off "):
            with self.subTest(valor=valor):
                resultado = lanzar(self.payload(), env={"HARNESS_STOP": valor})
                self.assertEqual(resultado.returncode, 0, resultado.stderr)

    def test_HARNESS_STOP_con_otro_valor_no_apaga(self):
        self.con_estado("en_ejecucion")
        for valor in ("0", "", "no"):
            with self.subTest(valor=valor):
                resultado = lanzar(self.payload(), env={"HARNESS_STOP": valor})
                self.assertEqual(resultado.returncode, 2)

    def test_el_bloqueo_ofrece_la_pausa(self):
        self.con_estado("en_ejecucion")
        self.assertIn("/fase-pausa", lanzar(self.payload()).stderr)

    def test_no_bloquea_con_hallazgos_pendientes(self):
        self.con_estado("aprobada")
        harness.write_json(
            harness.fase_dir(self.root, "ISR-110722", "fase_1") / "hallazgos.json",
            {"ticket_id": "ISR-110722", "fase_id": "fase_1",
             "hallazgos": [{"id": "h1", "origen": "reflector", "estado": "propuesto",
                            "senal": "s", "leccion": "l", "evidencia": "e",
                            "confianza": "alta", "dimension": "proceso",
                            "componente": "skill"}]})
        resultado = lanzar(self.payload())
        self.assertEqual(resultado.returncode, 0, resultado.stderr)

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

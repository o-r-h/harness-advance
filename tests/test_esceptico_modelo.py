"""El escéptico juzga con un modelo de Claude distinto al que ejecutó la fase.

Omar (03-11-2026): solo hay Claude; Sonnet por defecto. Si el ejecutor ya es Sonnet,
el escéptico pasa a Opus para que nunca sea el mismo modelo. El perfil puede fijarlo.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "harness" / "hooks"))
sys.path.insert(0, str(RAIZ / "tests"))
from lib import contracts, harness  # noqa: E402
import report  # noqa: E402
from test_cli_veredicto import REGLAS, _plan, correr  # noqa: E402


def _veredicto(aprobado: bool, resultado: str = "pendiente", intento: int = 1) -> dict:
    return {"fase_id": "fase_1", "intento": intento, "aprobado": False,
            "juicio_esceptico": {"aprobado": aprobado,
                                 "razones_rechazo": [] if aprobado else ["falta x"],
                                 "claims_sin_evidencia": [], "anclajes_sin_resolver": []},
            "prueba_manual": {"requerida": True, "ejecutada": resultado != "pendiente",
                              "resultado": resultado}}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / ".claude").mkdir()
        self.reglas(REGLAS)

    def reglas(self, reglas: dict) -> None:
        harness.write_json(self.root / ".claude" / "rules.json", reglas)

    def modelo(self, *args: str):
        return correr("modelo-esceptico", "--project", str(self.root), *args)


class TestModeloEsceptico(Base):
    def test_por_defecto_es_sonnet(self):
        for ejecutor in ("opus", "claude-opus-5-5", "desconocido", "fable"):
            with self.subTest(ejecutor=ejecutor):
                salida = self.modelo("--ejecutor", ejecutor)
                self.assertEqual(salida.returncode, 0, salida.stderr)
                self.assertEqual(salida.stdout.strip(), "sonnet")

    def test_si_el_ejecutor_es_sonnet_el_esceptico_es_opus(self):
        for ejecutor in ("sonnet", "Claude-Sonnet-5-5", "claude-sonnet-5-5[1m]"):
            with self.subTest(ejecutor=ejecutor):
                self.assertEqual(self.modelo("--ejecutor", ejecutor).stdout.strip(), "opus")

    def test_el_perfil_puede_fijarlo(self):
        self.reglas(dict(REGLAS, esceptico={"modelo": "opus"}))
        self.assertEqual(self.modelo("--ejecutor", "opus").stdout.strip(), "opus")

    def test_esceptico_que_no_es_objeto_es_error_claro(self):
        # Revisión del paso 6, #5: antes salía un traceback.
        self.reglas(dict(REGLAS, esceptico="opus"))
        salida = self.modelo("--ejecutor", "opus")
        self.assertEqual(salida.returncode, 1)
        self.assertIn("esceptico", salida.stderr)
        self.assertNotIn("Traceback", salida.stderr)

    def test_un_modelo_del_perfil_que_no_existe_es_error(self):
        self.reglas(dict(REGLAS, esceptico={"modelo": "gpt-5"}))
        salida = self.modelo("--ejecutor", "opus")
        self.assertEqual(salida.returncode, 1)
        self.assertIn("esceptico.modelo", salida.stderr)


class TestRecordVeredictoConModelo(Base):
    def setUp(self):
        super().setUp()
        harness.write_json(harness.ticket_dir(self.root, "ISR-110722") / "plan.json",
                           _plan(True))
        correr("open-ticket", "--project", str(self.root), "--ticket-id", "ISR-110722",
               "--nroticket", "110722", "--desarrollador", "OMAR RODRIGUEZ",
               "--fecha", "28-07-2026", "--perfil", "p")
        correr("open-fase", "--project", str(self.root), "--fase", "fase_1")
        self.ruta = self.root / "v.json"
        self.ruta.write_text(json.dumps(_veredicto(True)), encoding="utf-8")

    def guardado(self) -> dict:
        return harness.read_json(harness.intento_dir(self.root, "ISR-110722", "fase_1", 1)
                                 / "veredicto.json")

    def test_registra_el_modelo_que_juzgo(self):
        salida = correr("record-veredicto", "--project", str(self.root), "--archivo",
                        str(self.ruta), "--modelo-esceptico", "sonnet")
        self.assertEqual(salida.returncode, 0, salida.stderr)
        self.assertEqual(self.guardado()["juicio_esceptico"]["modelo"], "sonnet")

    def test_un_modelo_en_blanco_no_deja_un_veredicto_invalido(self):
        # Revisión del paso 6, #4: después record-manual fallaba y la fase quedaba trabada.
        salida = correr("record-veredicto", "--project", str(self.root), "--archivo",
                        str(self.ruta), "--modelo-esceptico", "   ")
        self.assertEqual(salida.returncode, 0, salida.stderr)
        self.assertEqual(contracts.validate_veredicto(self.guardado()), [])
        manual = correr("record-manual", "--project", str(self.root), "--resultado", "ok")
        self.assertEqual(manual.returncode, 0, manual.stderr)

    def test_sin_modelo_sigue_funcionando(self):
        salida = correr("record-veredicto", "--project", str(self.root), "--archivo",
                        str(self.ruta))
        self.assertEqual(salida.returncode, 0, salida.stderr)
        self.assertNotIn("modelo", self.guardado()["juicio_esceptico"])

    def test_el_contrato_acepta_el_modelo_y_rechaza_uno_vacio(self):
        v = _veredicto(True)
        v["juicio_esceptico"]["modelo"] = "sonnet"
        self.assertEqual(contracts.validate_veredicto(v), [])
        v["juicio_esceptico"]["modelo"] = " "
        self.assertTrue(contracts.validate_veredicto(v))


class TestReporteDelEsceptico(Base):
    def intento(self, fase: str, n: int, aprobado: bool, resultado: str, modelo=None):
        v = _veredicto(aprobado, resultado, intento=n)
        v["fase_id"] = fase
        if modelo:
            v["juicio_esceptico"]["modelo"] = modelo
        harness.write_json(harness.intento_dir(self.root, "ISR-1", fase, n) / "veredicto.json", v)

    def test_cuenta_por_modelo_y_los_fallos_que_se_le_escaparon(self):
        self.intento("fase_1", 1, False, "pendiente", "sonnet")
        self.intento("fase_1", 2, True, "fallo", "sonnet")   # aprobó y la prueba falló
        self.intento("fase_1", 3, True, "ok", "sonnet")
        self.intento("fase_2", 1, True, "ok", "opus")
        self.intento("fase_3", 1, True, "fallo")             # veredicto viejo, sin modelo
        datos = report.agregar(self.root)["esceptico"]
        self.assertEqual(datos, {
            "desconocido": {"juicios": 1, "aprobados": 1, "rechazados": 0,
                            "aprobados_que_fallaron_en_prueba": 1},
            "opus": {"juicios": 1, "aprobados": 1, "rechazados": 0,
                     "aprobados_que_fallaron_en_prueba": 0},
            "sonnet": {"juicios": 3, "aprobados": 2, "rechazados": 1,
                       "aprobados_que_fallaron_en_prueba": 1}})
        texto = report.render(report.agregar(self.root))
        self.assertIn("\nEscéptico por modelo\n", texto)
        self.assertIn("sonnet: 3 juicios — aprobó 2, rechazó 1; se le escaparon 1 "
                      "(aprobó y la prueba manual falló)", texto)

    def test_sin_veredictos_no_hay_datos(self):
        self.assertEqual(report.agregar(self.root)["esceptico"], {})
        seccion = report.render(report.agregar(self.root)).split("\nEscéptico por modelo\n")[1]
        self.assertTrue(seccion.startswith("  Sin datos todavía."))


if __name__ == "__main__":
    unittest.main()

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CLI = RAIZ / "harness" / "hooks" / "cli.py"
sys.path.insert(0, str(RAIZ / "harness" / "hooks"))
from lib import harness, prueba_manual, state  # noqa: E402

FASE = {"id": "fase_1", "titulo": "Agregar campo de comentario",
        "criterio_exito": "El comentario se guarda y se relee",
        "prueba_manual": {"requerida": True, "url": "frmReviewReport.aspx",
                          "datos": "review 4471, idioma EN"},
        "max_reintentos": 3}
PASOS = [{"paso": "Abrir la review 4471 y entrar a Other Q", "esperado": "El campo aparece vacío"},
         {"paso": "Escribir 'prueba harness' y guardar", "esperado": "Mensaje de guardado"},
         {"paso": "Salir y reabrir la review", "esperado": "El campo conserva el texto"}]


def correr(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(CLI), *args],
                          capture_output=True, text=True, encoding="utf-8")


class TestRender(unittest.TestCase):
    def test_incluye_url_datos_y_los_pasos_numerados(self):
        texto = prueba_manual.render(FASE, 2, PASOS)
        self.assertIn("frmReviewReport.aspx", texto)
        self.assertIn("review 4471", texto)
        self.assertIn("intento_2", texto)
        for numero in ("| 1 |", "| 2 |", "| 3 |"):
            self.assertIn(numero, texto)

    def test_recuerda_como_responder(self):
        texto = prueba_manual.render(FASE, 1, PASOS)
        self.assertIn("/fase-ok", texto)
        self.assertIn("/fase-fallo", texto)

    def test_incluye_el_criterio_de_exito_de_la_fase(self):
        self.assertIn("se relee", prueba_manual.render(FASE, 1, PASOS))


class TestRecordManual(unittest.TestCase):
    def preparar(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / ".claude").mkdir()
        harness.write_json(self.root / ".claude" / "rules.json",
                           {"perfil": "p", "audit_comments": {"requerido": True,
                                                              "severidad": "error"}})
        plan = {"ticket_id": "ISR-110722", "perfil": "p",
                "fases": [dict(FASE, pasos=["uno"], anclajes=[],
                               checks_deterministas=["audit_comments"],
                               herramientas_permitidas=["edit"], depende_de=[])]}
        harness.write_json(harness.ticket_dir(self.root, "ISR-110722") / "plan.json", plan)
        correr("open-ticket", "--project", str(self.root), "--ticket-id", "ISR-110722",
               "--nroticket", "110722", "--desarrollador", "OMAR RODRIGUEZ",
               "--fecha", "28-07-2026", "--perfil", "p")
        correr("open-fase", "--project", str(self.root), "--fase", "fase_1")
        state.set_estado(self.root, "ISR-110722", "fase_1", "esperando_humano")
        veredicto = {"fase_id": "fase_1", "intento": 1, "aprobado": False,
                     "juicio_esceptico": {"aprobado": True, "razones_rechazo": [],
                                          "claims_sin_evidencia": [],
                                          "anclajes_sin_resolver": []},
                     "prueba_manual": {"requerida": True, "ejecutada": False,
                                       "resultado": "pendiente"}}
        harness.write_json(
            harness.intento_dir(self.root, "ISR-110722", "fase_1", 1) / "veredicto.json",
            veredicto)

    def test_ok_aprueba_la_fase_y_completa_el_veredicto(self):
        self.preparar()
        resultado = correr("record-manual", "--project", str(self.root), "--resultado", "ok")
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertEqual(state.leer_fase(self.root, "ISR-110722", "fase_1")["estado"], "aprobada")
        veredicto = harness.read_json(
            harness.intento_dir(self.root, "ISR-110722", "fase_1", 1) / "veredicto.json")
        self.assertTrue(veredicto["aprobado"])
        self.assertEqual(veredicto["prueba_manual"]["resultado"], "ok")
        self.assertTrue(veredicto["prueba_manual"]["ejecutada"])

    def test_fallo_registra_el_origen_humano_con_paso_y_observacion(self):
        self.preparar()
        resultado = correr("record-manual", "--project", str(self.root), "--resultado", "fallo",
                           "--paso", "3", "--observacion", "el campo volvió vacío")
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        estado = state.leer_fase(self.root, "ISR-110722", "fase_1")
        self.assertEqual(estado["intento_actual"], 2)
        fallo = estado["historial_fallos"][0]
        self.assertEqual(fallo["origen"], "humano")
        self.assertIn("paso 3", fallo["razon"])
        self.assertIn("volvió vacío", fallo["razon"])

    def test_fallo_exige_paso_y_observacion(self):
        self.preparar()
        resultado = correr("record-manual", "--project", str(self.root), "--resultado", "fallo")
        self.assertEqual(resultado.returncode, 1)
        self.assertIn("--paso", resultado.stderr)

    def test_rechaza_registrar_si_la_fase_no_espera_al_humano(self):
        self.preparar()
        state.set_estado(self.root, "ISR-110722", "fase_1", "en_ejecucion")
        resultado = correr("record-manual", "--project", str(self.root), "--resultado", "ok")
        self.assertEqual(resultado.returncode, 1)
        self.assertIn("esperando_humano", resultado.stderr)

    def test_generar_prueba_escribe_el_archivo_en_el_intento(self):
        self.preparar()
        entrada = self.root / "pasos.json"
        entrada.write_text(json.dumps(PASOS), encoding="utf-8")
        resultado = correr("generar-prueba", "--project", str(self.root),
                           "--pasos-json", str(entrada))
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        destino = (harness.intento_dir(self.root, "ISR-110722", "fase_1", 1)
                   / "prueba_manual.md")
        self.assertIn("review 4471", destino.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

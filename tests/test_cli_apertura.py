import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CLI = RAIZ / "harness" / "hooks" / "cli.py"
sys.path.insert(0, str(RAIZ / "harness" / "hooks"))
from lib import harness  # noqa: E402

PLAN = {
    "ticket_id": "ISR-110722", "perfil": "reviewsystemgfs",
    "generado_por": "task-planner-v3",
    "fases": [{
        "id": "fase_1", "titulo": "Agregar campo", "pasos": ["uno"],
        "anclajes": [{"ref": "frm.aspx.vb:412", "confianza": "verificado"}],
        "criterio_exito": "se guarda y se relee",
        "checks_deterministas": ["audit_comments"],
        "prueba_manual": {"requerida": True, "url": "frm.aspx", "datos": "review 4471"},
        "herramientas_permitidas": ["read", "edit"], "max_reintentos": 3, "depende_de": []}]}


def correr(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(CLI), *args],
                          capture_output=True, text=True, encoding="utf-8")


class TestAperturaDeTicketYFase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / ".claude").mkdir()
        (self.root / ".claude" / "rules.json").write_text(
            json.dumps({"perfil": "reviewsystemgfs",
                        "audit_comments": {"requerido": True, "severidad": "error"}}),
            encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def abrir_ticket(self):
        return correr("open-ticket", "--project", str(self.root),
                      "--ticket-id", "ISR-110722", "--nroticket", "110722",
                      "--desarrollador", "OMAR RODRIGUEZ", "--fecha", "28-07-2026",
                      "--perfil", "reviewsystemgfs")

    def test_open_ticket_crea_contexto_y_puntero(self):
        resultado = self.abrir_ticket()
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        ctx = harness.read_json(
            harness.ticket_dir(self.root, "ISR-110722") / "ticket_context.json")
        self.assertEqual(ctx["nroticket"], "110722")
        self.assertEqual(harness.read_current(self.root)["ticket_id"], "ISR-110722")

    def test_open_ticket_rechaza_una_fecha_en_formato_iso(self):
        resultado = correr("open-ticket", "--project", str(self.root),
                           "--ticket-id", "ISR-1", "--nroticket", "1",
                           "--desarrollador", "OMAR RODRIGUEZ", "--fecha", "2026-07-28",
                           "--perfil", "reviewsystemgfs")
        self.assertEqual(resultado.returncode, 1)
        self.assertIn("DD-MM-YYYY", resultado.stderr)

    def test_open_fase_exige_un_plan_valido(self):
        self.abrir_ticket()
        resultado = correr("open-fase", "--project", str(self.root), "--fase", "fase_1")
        self.assertEqual(resultado.returncode, 1)
        self.assertIn("plan.json", resultado.stderr)

    def test_open_fase_crea_el_estado_y_actualiza_el_puntero(self):
        self.abrir_ticket()
        harness.write_json(
            harness.ticket_dir(self.root, "ISR-110722") / "plan.json", PLAN)
        resultado = correr("open-fase", "--project", str(self.root), "--fase", "fase_1")
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        estado = harness.read_json(
            harness.fase_dir(self.root, "ISR-110722", "fase_1") / "fase_state.json")
        self.assertEqual(estado["intento_actual"], 1)
        self.assertEqual(harness.read_current(self.root)["fase_id"], "fase_1")

    def test_open_fase_rechaza_una_fase_inexistente_en_el_plan(self):
        self.abrir_ticket()
        harness.write_json(
            harness.ticket_dir(self.root, "ISR-110722") / "plan.json", PLAN)
        resultado = correr("open-fase", "--project", str(self.root), "--fase", "fase_7")
        self.assertEqual(resultado.returncode, 1)
        self.assertIn("fase_7", resultado.stderr)

    def test_open_fase_bloquea_si_una_dependencia_no_esta_aprobada(self):
        self.abrir_ticket()
        plan = json.loads(json.dumps(PLAN))
        plan["fases"].append({
            "id": "fase_2", "titulo": "Depende de la 1", "pasos": ["uno"], "anclajes": [],
            "criterio_exito": "x", "checks_deterministas": ["audit_comments"],
            "prueba_manual": {"requerida": False},
            "herramientas_permitidas": ["read"], "max_reintentos": 3,
            "depende_de": ["fase_1"]})
        harness.write_json(harness.ticket_dir(self.root, "ISR-110722") / "plan.json", plan)
        resultado = correr("open-fase", "--project", str(self.root), "--fase", "fase_2")
        self.assertEqual(resultado.returncode, 1)
        self.assertIn("fase_1", resultado.stderr)

    def test_validate_reporta_los_errores_del_contrato(self):
        malo = self.root / "plan_malo.json"
        malo.write_text(json.dumps({"ticket_id": "ISR-1", "perfil": "x", "fases": []}),
                        encoding="utf-8")
        resultado = correr("validate", "--project", str(self.root),
                           "--contrato", "plan", "--archivo", str(malo))
        self.assertEqual(resultado.returncode, 1)
        self.assertIn("fases", resultado.stderr)


if __name__ == "__main__":
    unittest.main()

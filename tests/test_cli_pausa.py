import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CLI = RAIZ / "harness" / "hooks" / "cli.py"
sys.path.insert(0, str(RAIZ / "harness" / "hooks"))
from lib import harness, state  # noqa: E402

REGLAS = {"perfil": "p", "audit_comments": {"requerido": True, "severidad": "error"}}
TICKET = "ISR-110722"


def _fase(id_: str, depende_de: list[str]) -> dict:
    return {"id": id_, "titulo": "t", "pasos": ["p"], "anclajes": [],
            "criterio_exito": "c", "checks_deterministas": ["audit_comments"],
            "prueba_manual": {"requerida": True},
            "herramientas_permitidas": ["edit"], "max_reintentos": 3,
            "depende_de": depende_de}


PLAN = {"ticket_id": TICKET, "perfil": "p",
        "fases": [_fase("fase_1", []), _fase("fase_2", []), _fase("fase_3", ["fase_1"])]}


def correr(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(CLI), *args],
                          capture_output=True, text=True, encoding="utf-8")


class TestPausa(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / ".claude").mkdir()
        harness.write_json(self.root / ".claude" / "rules.json", REGLAS)
        harness.write_json(harness.ticket_dir(self.root, TICKET) / "plan.json", PLAN)
        self.abrir_ticket(TICKET)

    def abrir_ticket(self, ticket_id: str):
        return correr("open-ticket", "--project", str(self.root), "--ticket-id", ticket_id,
                      "--nroticket", "110722", "--desarrollador", "OMAR RODRIGUEZ",
                      "--fecha", "28-07-2026", "--perfil", "p")

    def cli(self, *args: str):
        return correr(*args, "--project", str(self.root))

    def abrir(self, fase="fase_1"):
        return self.cli("open-fase", "--fase", fase)

    def estado(self, fase="fase_1") -> dict:
        return state.leer_fase(self.root, TICKET, fase)

    def actual(self) -> dict:
        return harness.read_current(self.root)

    def test_pausar_deja_la_fase_pausada_con_motivo(self):
        self.abrir()
        r = self.cli("pausar-fase", "--motivo", "almuerzo")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("/fase fase_1", r.stdout)
        e = self.estado()
        self.assertEqual(e["estado"], "pausada")
        self.assertEqual(e["pausas"][-1]["motivo"], "almuerzo")

    def test_pausar_sin_motivo_guarda_sin_motivo(self):
        self.abrir()
        r = self.cli("pausar-fase")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.estado()["pausas"][-1]["motivo"], "sin motivo")

    def test_pausar_sin_fase_activa_falla(self):
        r = self.cli("pausar-fase")
        self.assertEqual(r.returncode, 1)

    def test_pausar_esperando_humano_explica_que_no_bloquea(self):
        self.abrir()
        state.set_estado(self.root, TICKET, "fase_1", "esperando_humano")
        r = self.cli("pausar-fase")
        self.assertEqual(r.returncode, 1)
        self.assertIn("ya no bloquea", r.stderr)

    def test_open_fase_reanuda_una_fase_pausada(self):
        self.abrir()
        self.cli("pausar-fase", "--motivo", "x")
        r = self.abrir()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("reanudada", r.stdout)
        e = self.estado()
        self.assertEqual(e["estado"], "en_ejecucion")
        self.assertEqual(e["intento_actual"], 1)

    def test_open_fase_sobre_fase_no_pausada_sigue_idempotente(self):
        self.abrir()
        antes = self.estado()
        r = self.abrir()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.estado(), antes)

    def test_veredicto_y_prueba_se_rechazan_en_pausada(self):
        self.abrir()
        self.cli("pausar-fase")
        veredicto = self.root / "v.json"
        veredicto.write_text(json.dumps({
            "fase_id": "fase_1", "intento": 1, "aprobado": False,
            "juicio_esceptico": {"aprobado": True, "razones_rechazo": [],
                                 "claims_sin_evidencia": [], "anclajes_sin_resolver": []},
            "prueba_manual": {"requerida": True, "ejecutada": False,
                              "resultado": "pendiente"}}), encoding="utf-8")
        pasos = self.root / "pasos.json"
        pasos.write_text(json.dumps([{"paso": "abre", "esperado": "ok"}]), encoding="utf-8")
        r1 = self.cli("record-veredicto", "--archivo", str(veredicto))
        r2 = self.cli("generar-prueba", "--pasos-json", str(pasos))
        for r in (r1, r2):
            self.assertEqual(r.returncode, 1)
            self.assertIn("/fase fase_1", r.stderr)
        intento = harness.intento_dir(self.root, TICKET, "fase_1", 1)
        self.assertFalse((intento / "veredicto.json").exists())
        self.assertFalse((intento / "prueba_manual.md").exists())

    def test_no_se_abre_otra_fase_con_la_activa_corriendo(self):
        self.abrir()
        r = self.abrir("fase_2")
        self.assertEqual(r.returncode, 1)
        self.assertIn("fase_1", r.stderr)
        self.assertIn("/fase-pausa", r.stderr)
        self.assertEqual(self.actual()["fase_id"], "fase_1")

    def test_con_la_activa_pausada_se_abre_otra_y_la_pausada_sigue_pausada(self):
        self.abrir()
        self.cli("pausar-fase")
        r = self.abrir("fase_2")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.estado()["estado"], "pausada")
        self.assertEqual(self.actual()["fase_id"], "fase_2")

    def test_open_ticket_se_rechaza_con_la_fase_corriendo(self):
        self.abrir()
        for ticket_id in ("ISR-999999", TICKET):
            r = self.abrir_ticket(ticket_id)
            self.assertEqual(r.returncode, 1, ticket_id)
            self.assertIn("/fase-pausa", r.stderr)
        self.cli("pausar-fase")
        self.assertEqual(self.abrir_ticket("ISR-999999").returncode, 0)

    def test_fase_dependiente_de_una_pausada_no_se_abre(self):
        self.abrir()
        self.cli("pausar-fase")
        r = self.abrir("fase_3")
        self.assertEqual(r.returncode, 1)
        self.assertIn("pausada", r.stderr)


if __name__ == "__main__":
    unittest.main()

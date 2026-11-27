"""El requerimiento viaja por referencia: las citas del plan son copia textual de ticket.md."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CLI = RAIZ / "harness" / "hooks" / "cli.py"
sys.path.insert(0, str(RAIZ / "harness" / "hooks"))
from lib import contracts, harness  # noqa: E402

TICKET = ("# Pedido\n\nAl guardar sin comentario mostrar el mensaje\n"
          "\"El comentario es obligatorio\" y no cerrar la ventana.\n")


def plan(citas=None) -> dict:
    fase = {"id": "fase_1", "titulo": "t", "pasos": ["p"], "anclajes": [],
            "criterio_exito": "c", "checks_deterministas": [],
            "prueba_manual": {"requerida": False}, "herramientas_permitidas": ["edit"],
            "max_reintentos": 3, "depende_de": []}
    if citas is not None:
        fase["citas"] = citas
    return {"ticket_id": "T-1", "perfil": "p", "fases": [fase]}


class TestContrato(unittest.TestCase):
    def test_las_citas_son_opcionales(self):
        self.assertEqual(contracts.validate_plan(plan(), requerimiento=TICKET), [])

    def test_una_cita_textual_pasa_aunque_cambien_los_saltos_de_linea(self):
        cita = 'mostrar el mensaje "El comentario es obligatorio" y no cerrar la ventana'
        self.assertEqual(contracts.validate_plan(plan([cita]), requerimiento=TICKET), [])

    def test_una_parafrasis_se_rechaza(self):
        errores = contracts.validate_plan(
            plan(["mostrar un aviso de que falta el comentario"]), requerimiento=TICKET)
        self.assertEqual(len(errores), 1)
        self.assertIn("citas[0]", errores[0])
        self.assertIn("no se parafrasea", errores[0])

    def test_sin_ticket_md_solo_se_revisa_la_forma(self):
        self.assertEqual(contracts.validate_plan(plan(["lo que sea"])), [])
        for mala in ("texto", [""], [3]):
            with self.subTest(citas=mala):
                self.assertIn("citas", contracts.validate_plan(plan(mala))[0])


def correr(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(CLI), *args],
                          capture_output=True, text=True, encoding="utf-8")


class TestEnElCli(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        (self.root / ".claude").mkdir()
        harness.write_json(self.root / ".claude" / "rules.json", {"perfil": "p"})
        self.carpeta = harness.ticket_dir(self.root, "T-1")
        self.carpeta.mkdir(parents=True)
        (self.carpeta / "ticket.md").write_text(TICKET, encoding="utf-8")
        correr("open-ticket", "--project", str(self.root), "--ticket-id", "T-1",
               "--nroticket", "1", "--desarrollador", "DEV", "--fecha", "01-01-2026",
               "--perfil", "p")

    def validar(self, citas) -> subprocess.CompletedProcess:
        harness.write_json(self.carpeta / "plan.json", plan(citas))
        return correr("validate", "--project", str(self.root), "--contrato", "plan",
                      "--archivo", str(self.carpeta / "plan.json"))

    def test_validate_lee_el_ticket_md_hermano_del_plan(self):
        self.assertEqual(self.validar(["no cerrar la ventana"]).returncode, 0)
        resultado = self.validar(["dejar la ventana abierta"])
        self.assertEqual(resultado.returncode, 1)
        self.assertIn("ticket.md", resultado.stderr)

    def test_open_fase_no_abre_con_una_cita_inventada_y_si_con_una_textual(self):
        self.validar(["dejar la ventana abierta"])
        rechazo = correr("open-fase", "--project", str(self.root), "--fase", "fase_1")
        self.assertEqual(rechazo.returncode, 1)
        self.validar(["no cerrar la ventana"])
        abierta = correr("open-fase", "--project", str(self.root), "--fase", "fase_1")
        self.assertEqual(abierta.returncode, 0, abierta.stderr)
        self.assertIn("ticket.md", abierta.stdout)


if __name__ == "__main__":
    unittest.main()

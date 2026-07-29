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

REGLAS = {
    "perfil": "reviewsystemgfs",
    "audit_comments": {"requerido": True, "severidad": "error",
                       "aplica_a": [".vb", ".js"]},
    "prohibido": [{"id": "no_fetch", "archivos": [".js"], "severidad": "error",
                   "patron": r"\bfetch\s*\(", "mensaje": "IE11 no soporta fetch"},
                  {"id": "no_es6", "archivos": [".js"], "severidad": "warning",
                   "patron": r"=>", "mensaje": "preferir function"}],
    "checks_estructurales": [],
    "grupos": {"ie11_syntax": ["no_fetch", "no_es6"]},
}

PLAN = {
    "ticket_id": "ISR-110722", "perfil": "reviewsystemgfs",
    "fases": [{"id": "fase_1", "titulo": "t", "pasos": ["p"], "anclajes": [],
               "criterio_exito": "c", "checks_deterministas": ["audit_comments", "ie11_syntax"],
               "prueba_manual": {"requerida": True}, "herramientas_permitidas": ["edit"],
               "max_reintentos": 3, "depende_de": []}]}


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


def correr(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(CLI), *args],
                          capture_output=True, text=True, encoding="utf-8")


class TestRunChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / ".claude").mkdir()
        harness.write_json(self.root / ".claude" / "rules.json", REGLAS)
        _git(self.root, "init")
        _git(self.root, "config", "user.email", "t@t.t")
        _git(self.root, "config", "user.name", "t")
        (self.root / "frm.js").write_text("var a = 1;\n", encoding="utf-8")
        _git(self.root, "add", ".")
        _git(self.root, "commit", "-m", "base")
        harness.write_json(harness.ticket_dir(self.root, "ISR-110722") / "plan.json", PLAN)
        correr("open-ticket", "--project", str(self.root), "--ticket-id", "ISR-110722",
               "--nroticket", "110722", "--desarrollador", "OMAR RODRIGUEZ",
               "--fecha", "28-07-2026", "--perfil", "reviewsystemgfs")
        correr("open-fase", "--project", str(self.root), "--fase", "fase_1")

    def tearDown(self):
        self.tmp.cleanup()

    def leer_checks(self) -> dict:
        return harness.read_json(
            harness.intento_dir(self.root, "ISR-110722", "fase_1", 1) / "checks.json")

    def test_un_error_deja_el_agregado_en_fallo_y_exit_1(self):
        (self.root / "frm.js").write_text("var a = 1;\nvar b = 2;\n", encoding="utf-8")
        resultado = correr("run-checks", "--project", str(self.root))
        self.assertEqual(resultado.returncode, 1)
        datos = self.leer_checks()
        self.assertEqual(datos["resultado"], "fallo")
        self.assertTrue(any(c["id"] == "audit_comments" for c in datos["checks"]))

    def test_solo_warnings_deja_el_agregado_en_ok_y_exit_0(self):
        (self.root / "frm.js").write_text(
            "var a = 1;\n"
            "//--[B] ISR 110722 OMAR RODRIGUEZ 28-07-2026\n"
            "var g = (x) => x;\n"
            "//--[E] ISR 110722 OMAR RODRIGUEZ 28-07-2026\n", encoding="utf-8")
        resultado = correr("run-checks", "--project", str(self.root))
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        datos = self.leer_checks()
        self.assertEqual(datos["resultado"], "ok")
        self.assertTrue(any(c["id"] == "no_es6" and c["severidad"] == "warning"
                            for c in datos["checks"]))

    def test_sin_cambios_el_agregado_es_ok(self):
        resultado = correr("run-checks", "--project", str(self.root))
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertEqual(self.leer_checks()["resultado"], "ok")

    def test_el_checks_json_cumple_su_contrato(self):
        (self.root / "frm.js").write_text("var a = 1;\nvar b = 2;\n", encoding="utf-8")
        correr("run-checks", "--project", str(self.root))
        ruta = harness.intento_dir(self.root, "ISR-110722", "fase_1", 1) / "checks.json"
        resultado = correr("validate", "--project", str(self.root),
                           "--contrato", "checks", "--archivo", str(ruta))
        self.assertEqual(resultado.returncode, 0, resultado.stderr)

    def test_un_check_estructural_que_crashea_produce_error_check_sin_bloquear(self):
        destino = self.root / ".claude" / "checks"
        destino.mkdir()
        (destino / "roto.py").write_text(
            "def run(project_root, archivos, ctx):\n"
            "    raise RuntimeError('bug del harness')\n", encoding="utf-8")
        reglas = dict(REGLAS, checks_estructurales=["roto"])
        harness.write_json(self.root / ".claude" / "rules.json", reglas)
        plan = json.loads(json.dumps(PLAN))
        plan["fases"][0]["checks_deterministas"] = ["roto"]
        harness.write_json(harness.ticket_dir(self.root, "ISR-110722") / "plan.json", plan)
        (self.root / "frm.js").write_text("var a = 1;\nvar b = 2;\n", encoding="utf-8")
        resultado = correr("run-checks", "--project", str(self.root))
        datos = self.leer_checks()
        self.assertTrue(any(c["resultado"] == "error_check" for c in datos["checks"]))
        self.assertEqual(datos["resultado"], "ok")
        self.assertEqual(resultado.returncode, 0, resultado.stderr)

    def test_un_check_estructural_valido_se_ejecuta(self):
        destino = self.root / ".claude" / "checks"
        destino.mkdir()
        (destino / "siempre_falla.py").write_text(
            "def run(project_root, archivos, ctx):\n"
            "    return [{'id': 'siempre_falla', 'resultado': 'fallo',\n"
            "             'severidad': 'error', 'detalle': 'falla a propósito'}]\n",
            encoding="utf-8")
        reglas = dict(REGLAS, checks_estructurales=["siempre_falla"])
        harness.write_json(self.root / ".claude" / "rules.json", reglas)
        plan = json.loads(json.dumps(PLAN))
        plan["fases"][0]["checks_deterministas"] = ["siempre_falla"]
        harness.write_json(harness.ticket_dir(self.root, "ISR-110722") / "plan.json", plan)
        (self.root / "frm.js").write_text("var a = 1;\nvar b = 2;\n", encoding="utf-8")
        resultado = correr("run-checks", "--project", str(self.root))
        self.assertEqual(resultado.returncode, 1)
        self.assertTrue(any(c["id"] == "siempre_falla" for c in self.leer_checks()["checks"]))


if __name__ == "__main__":
    unittest.main()

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
HOOK = RAIZ / "harness" / "hooks" / "check_rules.py"
sys.path.insert(0, str(RAIZ / "harness" / "hooks"))
from lib import harness  # noqa: E402

REGLAS = {
    "perfil": "perfil-demo",
    "audit_comments": {"requerido": True, "severidad": "error",
                       "aplica_a": [".vb", ".js", ".sql", ".aspx"]},
    "prohibido": [{"id": "no_fetch", "archivos": [".js"], "severidad": "error",
                   "patron": r"\bfetch\s*\(", "mensaje": "IE11 no soporta fetch"},
                  {"id": "no_es6", "archivos": [".js"], "severidad": "warning",
                   "patron": r"=>", "mensaje": "preferir function"}],
}


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


def lanzar(payload: dict) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload),
                          capture_output=True, text=True, encoding="utf-8")


class TestHookCheckRules(unittest.TestCase):
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
        harness.write_current(self.root, "ISR-110722", "fase_1")
        harness.write_json(
            harness.ticket_dir(self.root, "ISR-110722") / "ticket_context.json",
            {"ticket_id": "ISR-110722", "nroticket": "110722",
             "desarrollador": "OMAR RODRIGUEZ", "fecha": "28-07-2026",
             "perfil": "perfil-demo"})

    def tearDown(self):
        self.tmp.cleanup()

    def payload(self, archivo: Path) -> dict:
        return {"hook_event_name": "PostToolUse", "tool_name": "Edit",
                "cwd": str(self.root), "tool_input": {"file_path": str(archivo)}}

    def test_bloquea_una_linea_sin_bloque_de_auditoria(self):
        (self.root / "frm.js").write_text("var a = 1;\nvar b = 2;\n", encoding="utf-8")
        resultado = lanzar(self.payload(self.root / "frm.js"))
        self.assertEqual(resultado.returncode, 2)
        self.assertIn("audit_comments", resultado.stderr)

    def test_no_bloquea_un_cambio_correctamente_comentado(self):
        (self.root / "frm.js").write_text(
            "var a = 1;\n"
            "//--[B] ISR 110722 OMAR RODRIGUEZ 28-07-2026\n"
            "var b = 2;\n"
            "//--[E] ISR 110722 OMAR RODRIGUEZ 28-07-2026\n", encoding="utf-8")
        resultado = lanzar(self.payload(self.root / "frm.js"))
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertEqual(resultado.stderr.strip(), "")

    def test_bloquea_fetch_aunque_este_bien_comentado(self):
        (self.root / "frm.js").write_text(
            "var a = 1;\n"
            "//--[B] ISR 110722 OMAR RODRIGUEZ 28-07-2026\n"
            "fetch('/api/x');\n"
            "//--[E] ISR 110722 OMAR RODRIGUEZ 28-07-2026\n", encoding="utf-8")
        resultado = lanzar(self.payload(self.root / "frm.js"))
        self.assertEqual(resultado.returncode, 2)
        self.assertIn("no_fetch", resultado.stderr)

    def test_un_warning_no_bloquea_y_no_ensucia_la_salida(self):
        (self.root / "frm.js").write_text(
            "var a = 1;\n"
            "//--[B] ISR 110722 OMAR RODRIGUEZ 28-07-2026\n"
            "var f = function(x) { return x; }; // sin arrow\n"
            "var g = (x) => x;\n"
            "//--[E] ISR 110722 OMAR RODRIGUEZ 28-07-2026\n", encoding="utf-8")
        resultado = lanzar(self.payload(self.root / "frm.js"))
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertEqual(resultado.stderr.strip(), "")

    def test_es_inerte_en_un_proyecto_sin_perfil(self):
        with tempfile.TemporaryDirectory() as sin_perfil:
            otro = Path(sin_perfil)
            archivo = otro / "cualquiera.js"
            archivo.write_text("fetch('/x');\n", encoding="utf-8")
            resultado = lanzar({"hook_event_name": "PostToolUse", "tool_name": "Edit",
                                "cwd": str(otro),
                                "tool_input": {"file_path": str(archivo)}})
            self.assertEqual(resultado.returncode, 0)
            self.assertEqual(resultado.stdout.strip(), "")
            self.assertEqual(resultado.stderr.strip(), "")

    def test_sin_ticket_activo_no_juzga_los_comentarios_de_auditoria(self):
        harness.write_json(harness.current_pointer_path(self.root),
                           {"ticket_id": None, "fase_id": None})
        (self.root / "frm.js").write_text("var a = 1;\nvar b = 2;\n", encoding="utf-8")
        resultado = lanzar(self.payload(self.root / "frm.js"))
        self.assertEqual(resultado.returncode, 0, resultado.stderr)

    def test_un_payload_ilegible_no_rompe_nada(self):
        resultado = subprocess.run([sys.executable, str(HOOK)], input="esto no es json",
                                   capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(resultado.returncode, 0)

    def test_ignora_una_herramienta_sin_archivo(self):
        resultado = lanzar({"hook_event_name": "PostToolUse", "tool_name": "Bash",
                            "cwd": str(self.root), "tool_input": {"command": "ls"}})
        self.assertEqual(resultado.returncode, 0)


if __name__ == "__main__":
    unittest.main()

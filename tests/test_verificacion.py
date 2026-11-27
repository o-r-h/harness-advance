"""Aviso cuando una fase toca lo que la verifica (rules.json, checks, tests del perfil)."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CLI = RAIZ / "harness" / "hooks" / "cli.py"
sys.path.insert(0, str(RAIZ / "harness" / "hooks"))
from lib import harness, verificacion  # noqa: E402

FASE = {"id": "fase_1", "titulo": "Agregar campo", "criterio_exito": "se guarda",
        "pasos": ["Editar src/orden.cs"], "anclajes": []}


class TestHallazgos(unittest.TestCase):
    def setUp(self):
        self.raiz = Path("proyecto").resolve()

    def correr(self, rutas, fase=FASE, reglas=None):
        return verificacion.hallazgos(self.raiz, [self.raiz / r for r in rutas], fase,
                                      reglas or {})

    def test_el_codigo_normal_no_avisa(self):
        self.assertEqual(self.correr(["src/orden.cs"]), [])

    def test_tocar_las_reglas_o_un_check_del_perfil_avisa(self):
        encontrados = self.correr([".claude/rules.json", ".claude/checks/build.py"])
        self.assertEqual([h["archivo"] for h in encontrados],
                         [".claude/rules.json", ".claude/checks/build.py"])
        for hallazgo in encontrados:
            self.assertEqual((hallazgo["id"], hallazgo["resultado"], hallazgo["severidad"]),
                             ("verificacion_tocada", "fallo", "warning"))

    def test_los_tests_cuentan_solo_si_el_perfil_los_declara(self):
        self.assertEqual(self.correr(["tests/test_orden.py"]), [])
        encontrados = self.correr(["tests/test_orden.py", "tests/sub/test_x.py"],
                                  reglas={"rutas_de_verificacion": ["tests/*"]})
        self.assertEqual(len(encontrados), 2)

    def test_si_el_plan_nombra_el_archivo_no_avisa(self):
        reglas = {"rutas_de_verificacion": ["tests/*"]}
        por_ruta = dict(FASE, pasos=["Agregar un caso en tests/test_orden.py"])
        por_nombre = dict(FASE, anclajes=[{"ref": "test_orden.py:12",
                                           "confianza": "verificado"}])
        for fase in (por_ruta, por_nombre):
            with self.subTest(fase=fase):
                self.assertEqual(self.correr(["tests/test_orden.py"], fase, reglas), [])

    def test_una_declaracion_mal_formada_no_rompe(self):
        for mala in ("tests/*", [3, ""], None):
            with self.subTest(declaracion=mala):
                self.assertEqual(
                    self.correr(["src/a.cs"], reglas={"rutas_de_verificacion": mala}), [])


def git(raiz: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
                   cwd=str(raiz), check=True, capture_output=True)


def correr(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(CLI), *args],
                          capture_output=True, text=True, encoding="utf-8")


class TestEnRunChecks(unittest.TestCase):
    def test_debilitar_una_regla_queda_como_warning_y_no_bloquea(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            (raiz / ".claude").mkdir()
            reglas = {"perfil": "p", "audit_comments": {"requerido": True,
                                                        "severidad": "error"}}
            harness.write_json(raiz / ".claude" / "rules.json", reglas)
            (raiz / ".gitignore").write_text(".harness/\n", encoding="utf-8")
            git(raiz, "init", "-q")
            git(raiz, "add", "-A")
            git(raiz, "commit", "-q", "-m", "base")
            plan = {"ticket_id": "T-1", "perfil": "p", "fases": [dict(
                FASE, checks_deterministas=[], prueba_manual={"requerida": False},
                herramientas_permitidas=["edit"], max_reintentos=3, depende_de=[])]}
            harness.write_json(harness.ticket_dir(raiz, "T-1") / "plan.json", plan)
            correr("open-ticket", "--project", tmp, "--ticket-id", "T-1", "--nroticket", "1",
                   "--desarrollador", "DEV", "--fecha", "01-01-2026", "--perfil", "p")
            correr("open-fase", "--project", tmp, "--fase", "fase_1")
            reglas["audit_comments"] = {"requerido": False, "severidad": "warning"}
            harness.write_json(raiz / ".claude" / "rules.json", reglas)

            resultado = correr("run-checks", "--project", tmp)

            self.assertEqual(resultado.returncode, 0, resultado.stdout + resultado.stderr)
            checks = harness.read_json(
                harness.intento_dir(raiz, "T-1", "fase_1", 1) / "checks.json")
            self.assertEqual(checks["resultado"], "ok")
            avisos = [c for c in checks["checks"] if c["id"] == "verificacion_tocada"]
            self.assertEqual([a["archivo"] for a in avisos], [".claude/rules.json"])


if __name__ == "__main__":
    unittest.main()

"""doctor: diagnóstico de solo lectura de la instalación y del proyecto."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CLI = RAIZ / "harness" / "hooks" / "cli.py"
sys.path.insert(0, str(RAIZ / "harness" / "hooks"))
from lib import doctor, harness  # noqa: E402


def correr(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(CLI), *args],
                          capture_output=True, text=True, encoding="utf-8")


def git(raiz: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
                   cwd=str(raiz), check=True, capture_output=True)


def foto(raiz: Path) -> dict[str, bytes]:
    return {p.relative_to(raiz).as_posix(): p.read_bytes()
            for p in sorted(raiz.rglob("*")) if p.is_file() and ".git/" not in p.as_posix()}


class ConProyecto(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "proyecto"
        (self.root / ".claude").mkdir(parents=True)
        harness.write_json(self.root / ".claude" / "rules.json", {"perfil": "p"})
        (self.root / ".gitignore").write_text(".harness/\n", encoding="utf-8")
        git(self.root, "init", "-q")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "base")
        self.settings = Path(self._tmp.name) / "settings.json"
        hooks = RAIZ / "harness" / "hooks"
        self.settings.write_text(json.dumps({"hooks": {
            "PostToolUse": [{"matcher": "Edit|Write|MultiEdit", "hooks": [
                {"type": "command", "command": f'python "{hooks / "check_rules.py"}"'}]}],
            "Stop": [{"matcher": "", "hooks": [
                {"type": "command", "command": f'python "{hooks / "gate_phase.py"}"'}]}],
        }}), encoding="utf-8")

    def doctor(self, *extra: str) -> subprocess.CompletedProcess:
        return correr("doctor", "--project", str(self.root),
                      "--settings", str(self.settings), *extra)

    def niveles(self, texto: str) -> dict[str, str]:
        """{fragmento de cada línea: nivel}, para buscar por contenido."""
        return {linea[8:]: linea[1:6].strip() for linea in texto.splitlines()
                if linea.startswith("[")}

    def nivel_de(self, salida: str, fragmento: str) -> str:
        return next(nivel for linea, nivel in self.niveles(salida).items()
                    if fragmento in linea)


class TestInstalacionSana(ConProyecto):
    def test_todo_bien_sale_con_cero_y_sin_fallas(self):
        resultado = self.doctor()
        self.assertEqual(resultado.returncode, 0, resultado.stdout + resultado.stderr)
        self.assertIn("0 falla(s)", resultado.stdout)
        self.assertEqual(self.nivel_de(resultado.stdout, "hook Stop"), "ok")
        self.assertEqual(self.nivel_de(resultado.stdout, "repositorio git"), "ok")

    def test_no_escribe_nada_en_el_proyecto(self):
        antes = foto(self.root)
        self.doctor("--fuente", str(RAIZ))
        self.assertEqual(foto(self.root), antes)
        self.assertFalse((self.root / ".harness").exists())

    def test_contra_su_propia_fuente_no_hay_copia_que_comparar(self):
        resultado = self.doctor("--fuente", str(RAIZ))
        self.assertEqual(self.nivel_de(resultado.stdout, "desde la fuente"), "ok")


class TestProblemas(ConProyecto):
    def test_un_hook_sin_registrar_es_falla_con_remedio(self):
        self.settings.write_text(json.dumps({"hooks": {}}), encoding="utf-8")
        resultado = self.doctor()
        self.assertEqual(resultado.returncode, 1)
        self.assertEqual(self.nivel_de(resultado.stdout, "hook PostToolUse"), "falla")
        self.assertIn("→ vuelve a correr deploy.ps1", resultado.stdout)

    def test_un_hook_que_apunta_a_un_archivo_que_no_existe_es_falla(self):
        texto = self.settings.read_text(encoding="utf-8").replace("gate_phase.py", "x")
        self.settings.write_text(texto.replace('hooks\\\\x', 'hooks\\\\gate_phase.py')
                                 .replace("harness", "no-existe"), encoding="utf-8")
        resultado = self.doctor()
        self.assertEqual(resultado.returncode, 1)
        self.assertIn("que no existe", resultado.stdout)

    def test_settings_roto_es_falla(self):
        self.settings.write_text("{ roto", encoding="utf-8")
        resultado = self.doctor()
        self.assertEqual(resultado.returncode, 1)
        self.assertIn("no es JSON válido", resultado.stdout)

    def test_un_check_estructural_declarado_sin_archivo_es_falla(self):
        harness.write_json(self.root / ".claude" / "rules.json",
                           {"perfil": "p", "checks_estructurales": ["build"]})
        resultado = self.doctor()
        self.assertEqual(resultado.returncode, 1)
        self.assertEqual(self.nivel_de(resultado.stdout, "sin archivo: build"), "falla")

    def test_rules_json_roto_es_falla(self):
        (self.root / ".claude" / "rules.json").write_text("{ roto", encoding="utf-8")
        resultado = self.doctor()
        self.assertEqual(resultado.returncode, 1)
        self.assertEqual(self.nivel_de(resultado.stdout, "rules.json no se puede leer"),
                         "falla")

    def test_harness_fuera_del_gitignore_es_aviso_y_no_falla(self):
        (self.root / ".gitignore").write_text("bin/\n", encoding="utf-8")
        resultado = self.doctor()
        self.assertEqual(resultado.returncode, 0, resultado.stdout)
        self.assertEqual(self.nivel_de(resultado.stdout, "no está en .gitignore"), "aviso")

    def test_fuera_de_un_proyecto_avisa(self):
        with tempfile.TemporaryDirectory() as vacio:
            resultado = correr("doctor", "--project", vacio, "--settings", str(self.settings))
        self.assertEqual(resultado.returncode, 0, resultado.stdout)
        self.assertEqual(self.nivel_de(resultado.stdout, "no está dentro de un proyecto"),
                         "aviso")

    def test_prohibidas_sin_probador_del_proyecto_es_falla(self):
        harness.write_json(self.root / ".claude" / "prueba_asistida.json", {
            "navegador": None, "base": {"servidor": "b", "prohibidas": ["srv__x"]}})
        resultado = self.doctor()
        self.assertEqual(resultado.returncode, 1)
        self.assertIn("el bloqueo no es técnico", resultado.stdout)

    def test_tras_el_setup_el_probador_bloquea_las_prohibidas(self):
        correr("setup-prueba", "--project", str(self.root), "--sin-navegador",
               "--base", "b", "--prohibida", "srv__x")
        resultado = self.doctor()
        self.assertEqual(resultado.returncode, 0, resultado.stdout)
        self.assertEqual(self.nivel_de(resultado.stdout, "bloquea las prohibidas"), "ok")

    def test_muestra_la_fase_activa(self):
        plan = {"ticket_id": "T-1", "perfil": "p", "fases": [{
            "id": "fase_1", "titulo": "t", "pasos": ["p"], "anclajes": [],
            "criterio_exito": "c", "checks_deterministas": [],
            "prueba_manual": {"requerida": False}, "herramientas_permitidas": ["edit"],
            "max_reintentos": 3, "depende_de": []}]}
        harness.write_json(harness.ticket_dir(self.root, "T-1") / "plan.json", plan)
        correr("open-ticket", "--project", str(self.root), "--ticket-id", "T-1",
               "--nroticket", "1", "--desarrollador", "DEV", "--fecha", "01-01-2026",
               "--perfil", "p")
        correr("open-fase", "--project", str(self.root), "--fase", "fase_1")
        self.assertIn("T-1/fase_1: en_ejecucion, intento 1/3", self.doctor().stdout)


class TestContraLaFuente(unittest.TestCase):
    def test_nombra_lo_que_falta_y_lo_que_difiere(self):
        with tempfile.TemporaryDirectory() as tmp:
            fuente, instalado = Path(tmp) / "fuente", Path(tmp) / "instalado"
            for base in (fuente / "harness", instalado):
                (base / "hooks").mkdir(parents=True)
                (base / "agents").mkdir()
                (base / "hooks" / "cli.py").write_text("igual\n", encoding="utf-8")
            (fuente / "harness" / "hooks" / "probe_hook.py").write_text("x", encoding="utf-8")
            (fuente / "harness" / "agents" / "a.md").write_text("nuevo\n", encoding="utf-8")
            (instalado / "agents" / "a.md").write_text("viejo\n", encoding="utf-8")
            (fuente / "harness" / "agents" / "b.md").write_text("b\n", encoding="utf-8")
            (nivel, texto, _), = doctor._contra_la_fuente(instalado, fuente)
        self.assertEqual(nivel, doctor.AVISO)
        self.assertIn("agents/a.md (distinto)", texto)
        self.assertIn("agents/b.md (falta)", texto)
        self.assertNotIn("probe_hook", texto)
        self.assertNotIn("cli.py", texto)

    def test_los_finales_de_linea_no_cuentan_como_diferencia(self):
        with tempfile.TemporaryDirectory() as tmp:
            fuente, instalado = Path(tmp) / "fuente", Path(tmp) / "instalado"
            (fuente / "harness" / "hooks").mkdir(parents=True)
            (instalado / "hooks").mkdir(parents=True)
            (fuente / "harness" / "hooks" / "cli.py").write_bytes(b"a\nb\n")
            (instalado / "hooks" / "cli.py").write_bytes(b"a\r\nb\r\n")
            (nivel, _, _), = doctor._contra_la_fuente(instalado, fuente)
        self.assertEqual(nivel, doctor.OK)


if __name__ == "__main__":
    unittest.main()

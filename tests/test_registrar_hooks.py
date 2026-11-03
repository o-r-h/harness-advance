import contextlib
import copy
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
import registrar_hooks  # noqa: E402

HOOKS = "C:/harness/hooks"
CMD_CHECK = f'python "{Path(HOOKS) / "check_rules.py"}"'
CMD_GATE = f'python "{Path(HOOKS) / "gate_phase.py"}"'
MATCHER_CHECK = "Edit|Write|MultiEdit"


def _ajeno(matcher: str) -> dict:
    return {"matcher": matcher, "hooks": [{
        "type": "command",
        "command": "C:/Users/Omarj/AppData/Local/Programs/codebase-memory-mcp/codebase-memory-mcp.exe",
        "args": ["hook-augment"], "timeout": 5}]}


REAL = {
    "autoUpdatesChannel": "latest",
    "effortLevel": "high",
    "enabledPlugins": {"superpowers@x": True},
    "env": {"NOTA": "configuración"},
    "extraKnownMarketplaces": {},
    "hooks": {
        "PostToolUse": [_ajeno("Read")],
        "PreToolUse": [_ajeno("Grep|Glob|Bash")],
        "SessionStart": [_ajeno(m) for m in ("startup", "resume", "clear", "compact")],
        "SubagentStart": [_ajeno("*")],
    },
    "model": "opus",
    "modelSettings": {},
    "theme": "dark",
}


def _propio(matcher: str, comando: str) -> dict:
    return {"matcher": matcher, "hooks": [{"type": "command", "command": comando}]}


class TestRegistrar(unittest.TestCase):
    def test_registra_desde_cero_y_conserva_lo_ajeno(self):
        nuevo, lineas = registrar_hooks.registrar(REAL, HOOKS)
        self.assertEqual(nuevo["hooks"]["PostToolUse"][-1],
                         _propio(MATCHER_CHECK, CMD_CHECK))
        self.assertEqual(nuevo["hooks"]["Stop"], [_propio("", CMD_GATE)])
        sin = copy.deepcopy(nuevo)
        sin["hooks"]["PostToolUse"].pop()
        del sin["hooks"]["Stop"]
        self.assertEqual(sin, REAL)
        self.assertEqual(list(sin), list(REAL))
        self.assertEqual(list(sin["hooks"]), list(REAL["hooks"]))
        self.assertEqual(len(lineas), 2)
        self.assertTrue(all("registrado" in linea for linea in lineas))

    def test_no_muta_la_entrada(self):
        copia = copy.deepcopy(REAL)
        registrar_hooks.registrar(copia, HOOKS)
        self.assertEqual(copia, REAL)

    def test_segunda_vez_ya_estaba(self):
        primero, _ = registrar_hooks.registrar(REAL, HOOKS)
        segundo, lineas = registrar_hooks.registrar(primero, HOOKS)
        self.assertEqual(segundo, primero)
        self.assertEqual(len(lineas), 2)
        self.assertTrue(all("ya estaba" in linea for linea in lineas))

    def test_ruta_vieja_se_actualiza(self):
        datos = copy.deepcopy(REAL)
        datos["hooks"]["PostToolUse"].append(
            _propio(MATCHER_CHECK, 'python "C:/viejo/hooks/check_rules.py"'))
        nuevo, lineas = registrar_hooks.registrar(datos, HOOKS)
        self.assertEqual(nuevo["hooks"]["PostToolUse"][-1]["hooks"][0]["command"],
                         CMD_CHECK)
        self.assertEqual(len(nuevo["hooks"]["PostToolUse"]), 2)
        self.assertTrue(any("check_rules.py" in linea and "ruta actualizada" in linea
                            for linea in lineas))

    def test_matcher_distinto_se_corrige(self):
        datos = copy.deepcopy(REAL)
        datos["hooks"]["PostToolUse"].append(_propio("Write", CMD_CHECK))
        nuevo, _ = registrar_hooks.registrar(datos, HOOKS)
        self.assertEqual(nuevo["hooks"]["PostToolUse"][-1]["matcher"], MATCHER_CHECK)

    def test_entrada_mixta_no_toca_el_matcher(self):
        ajeno = _ajeno("x")["hooks"][0]
        mixta = {"matcher": "Write", "hooks": [
            copy.deepcopy(ajeno),
            {"type": "command", "command": 'python "C:/viejo/hooks/check_rules.py"'}]}
        datos = copy.deepcopy(REAL)
        datos["hooks"]["PostToolUse"].append(mixta)
        nuevo, lineas = registrar_hooks.registrar(datos, HOOKS)
        entrada = nuevo["hooks"]["PostToolUse"][-1]
        self.assertEqual(entrada["matcher"], "Write")
        self.assertEqual(entrada["hooks"][0], ajeno)
        self.assertEqual(entrada["hooks"][1]["command"], CMD_CHECK)
        self.assertTrue(any("matcher sin tocar" in linea for linea in lineas))

    def test_duplicados_se_corrigen_y_se_avisa(self):
        datos = copy.deepcopy(REAL)
        datos["hooks"]["Stop"] = [_propio("", 'python "C:/a/hooks/gate_phase.py"'),
                                  _propio("", 'python "C:/b/hooks/gate_phase.py"')]
        nuevo, lineas = registrar_hooks.registrar(datos, HOOKS)
        self.assertEqual(nuevo["hooks"]["Stop"], [_propio("", CMD_GATE)] * 2)
        self.assertTrue(any("2 entradas del harness" in linea for linea in lineas))

    def test_hook_ajeno_con_el_mismo_nombre_no_se_toca(self):
        ajena = {"matcher": "", "hooks": [{
            "type": "command",
            "command": "node C:/otra/herramienta/gate_phase.py --x"}]}
        datos = copy.deepcopy(REAL)
        datos["hooks"]["Stop"] = [copy.deepcopy(ajena)]
        nuevo, lineas = registrar_hooks.registrar(datos, HOOKS)
        self.assertEqual(nuevo["hooks"]["Stop"], [ajena, _propio("", CMD_GATE)])
        self.assertTrue(any("Stop" in linea and "registrado" in linea
                            for linea in lineas))

    def test_nombre_parecido_no_es_nuestro(self):
        ajena = _propio("", 'python "C:/x/hooks/pre_check_rules.py"')
        datos = copy.deepcopy(REAL)
        datos["hooks"]["PostToolUse"].append(copy.deepcopy(ajena))
        nuevo, _ = registrar_hooks.registrar(datos, HOOKS)
        self.assertEqual(nuevo["hooks"]["PostToolUse"][-2], ajena)
        self.assertEqual(nuevo["hooks"]["PostToolUse"][-1],
                         _propio(MATCHER_CHECK, CMD_CHECK))

    def test_comando_no_cadena_es_ajeno(self):
        self.assertFalse(registrar_hooks._es_nuestro(
            {"command": ["hooks/check_rules.py"]}, "check_rules.py"))

    def test_rutas_del_harness_se_reconocen(self):
        for comando in (r'python "C:\Users\x\.claude\hooks\check_rules.py"',
                        'python "C:/viejo/hooks/check_rules.py"',
                        'python "$HOME/.claude/hooks/check_rules.py"'):
            self.assertTrue(registrar_hooks._es_nuestro(
                {"command": comando}, "check_rules.py"), comando)

    def test_sin_clave_hooks(self):
        nuevo, _ = registrar_hooks.registrar({"model": "x"}, HOOKS)
        self.assertEqual(nuevo["model"], "x")
        self.assertEqual(set(nuevo["hooks"]), {"PostToolUse", "Stop"})


class TestMain(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.settings = self.dir / "settings.json"

    def _correr(self):
        salida, error = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(salida), contextlib.redirect_stderr(error):
            codigo = registrar_hooks.main(
                ["--settings", str(self.settings), "--hooks-dir", HOOKS])
        return codigo, salida.getvalue() + error.getvalue()

    def _respaldos(self):
        return sorted(self.dir.glob("settings.json.bak-*"))

    def _escribir_real(self):
        self.settings.write_bytes(
            (json.dumps(REAL, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))

    def test_main_crea_el_archivo_si_no_existe(self):
        codigo, _ = self._correr()
        self.assertEqual(codigo, 0)
        self.assertTrue(self.settings.exists())
        self.assertEqual(self._respaldos(), [])

    def test_main_segunda_corrida_no_escribe_ni_respalda(self):
        self._correr()
        mtime = self.settings.stat().st_mtime_ns
        contenido = self.settings.read_bytes()
        codigo, salida = self._correr()
        self.assertEqual(codigo, 0)
        self.assertEqual(self.settings.stat().st_mtime_ns, mtime)
        self.assertEqual(self.settings.read_bytes(), contenido)
        self.assertEqual(self._respaldos(), [])
        self.assertIn("ya estaba", salida)

    def test_main_respalda_solo_cuando_escribe(self):
        self._escribir_real()
        original = self.settings.read_bytes()
        codigo, _ = self._correr()
        self.assertEqual(codigo, 0)
        respaldos = self._respaldos()
        self.assertEqual(len(respaldos), 1)
        self.assertRegex(respaldos[0].name,
                         r"^settings\.json\.bak-\d{2}-\d{2}-\d{4}-\d{6}$")
        self.assertEqual(respaldos[0].read_bytes(), original)

    def test_main_escribe_utf8_sin_bom_indent_2_y_lf(self):
        self._escribir_real()
        self._correr()
        crudo = self.settings.read_bytes()
        self.assertFalse(crudo.startswith(b"\xef\xbb\xbf"))
        self.assertNotIn(b"\r", crudo)
        texto = crudo.decode("utf-8")
        self.assertIn("configuración", texto)
        datos = json.loads(texto)
        self.assertEqual(texto, json.dumps(datos, indent=2, ensure_ascii=False) + "\n")

    def test_main_lee_con_bom(self):
        self.settings.write_bytes(b"\xef\xbb\xbf" + b'{"model": "x"}\n')
        codigo, _ = self._correr()
        self.assertEqual(codigo, 0)
        self.assertFalse(self.settings.read_bytes().startswith(b"\xef\xbb\xbf"))
        self.assertEqual(json.loads(self.settings.read_text("utf-8"))["model"], "x")

    def test_main_json_roto_no_toca_nada(self):
        self.settings.write_bytes(b'{"hooks": [')
        codigo, salida = self._correr()
        self.assertEqual(codigo, 1)
        self.assertEqual(self.settings.read_bytes(), b'{"hooks": [')
        self.assertEqual(self._respaldos(), [])
        self.assertIn("línea", salida)
        self.assertIn("columna", salida)

    def test_main_json_que_no_es_objeto(self):
        self.settings.write_bytes(b"[]")
        codigo, _ = self._correr()
        self.assertEqual(codigo, 1)
        self.assertEqual(self.settings.read_bytes(), b"[]")
        self.assertEqual(self._respaldos(), [])


if __name__ == "__main__":
    unittest.main()

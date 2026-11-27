"""Setup de la prueba asistida: qué navegador y qué base usa el probador en este proyecto."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CLI = RAIZ / "harness" / "hooks" / "cli.py"
sys.path.insert(0, str(RAIZ / "harness" / "hooks"))
from lib import contracts, harness, prueba_asistida, state  # noqa: E402

COMPLETA = {"navegador": "navegador-x",
            "base": {"servidor": "base-y", "ambiente": "dev",
                     "prohibidas": ["base-y.cambiar_ambiente"]}}


def correr(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(CLI), *args],
                          capture_output=True, text=True, encoding="utf-8")


class TestContrato(unittest.TestCase):
    def test_acepta_la_configuracion_completa(self):
        self.assertEqual(contracts.validate_prueba_asistida(COMPLETA), [])

    def test_acepta_sin_navegador_ni_base(self):
        self.assertEqual(contracts.validate_prueba_asistida(
            {"navegador": None, "base": None}), [])

    def test_las_dos_decisiones_son_obligatorias(self):
        errores = contracts.validate_prueba_asistida({})
        self.assertTrue(any("navegador" in e for e in errores))
        self.assertTrue(any("base" in e for e in errores))

    def test_navegador_vacio_no_es_sin_navegador(self):
        errores = contracts.validate_prueba_asistida({"navegador": " ", "base": None})
        self.assertIn("navegador", errores[0])

    def test_la_base_exige_servidor_y_lista_de_prohibidas(self):
        errores = contracts.validate_prueba_asistida(
            {"navegador": None, "base": {"prohibidas": "x"}})
        self.assertTrue(any("base.servidor" in e for e in errores))
        self.assertTrue(any("base.prohibidas" in e for e in errores))

    def test_una_prohibida_vacia_es_error(self):
        errores = contracts.validate_prueba_asistida(
            {"navegador": None, "base": {"servidor": "b", "prohibidas": [""]}})
        self.assertTrue(any("prohibidas" in e for e in errores))


class ConProyecto(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / ".claude").mkdir()
        harness.write_json(self.root / ".claude" / "rules.json",
                           {"perfil": "p", "audit_comments": {"requerido": True,
                                                              "severidad": "error"}})

    def tearDown(self):
        self._tmp.cleanup()

    def config(self) -> dict:
        return harness.read_json(self.root / ".claude" / "prueba_asistida.json")


class TestSetupPrueba(ConProyecto):
    def test_sin_configurar_lo_dice_y_no_escribe(self):
        resultado = correr("setup-prueba", "--project", str(self.root))
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertIn("sin configurar", resultado.stdout)
        self.assertIsNone(prueba_asistida.leer(self.root))

    def test_guarda_navegador_base_ambiente_y_prohibidas(self):
        resultado = correr("setup-prueba", "--project", str(self.root),
                           "--navegador", "navegador-x", "--base", "base-y",
                           "--ambiente", "dev", "--prohibida", "base-y.cambiar_ambiente")
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertEqual(self.config(), COMPLETA)

    def test_sin_navegador_y_sin_base_es_una_respuesta_valida(self):
        resultado = correr("setup-prueba", "--project", str(self.root),
                           "--sin-navegador", "--sin-base")
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertEqual(self.config(), {"navegador": None, "base": None})
        self.assertIn("humano", resultado.stdout)

    def test_sin_navegador_con_base_no_dice_que_todo_es_del_humano(self):
        resultado = correr("setup-prueba", "--project", str(self.root),
                           "--sin-navegador", "--base", "base-y")
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertIn("consulta o de API", resultado.stdout)
        self.assertNotIn("todos los pasos son del humano", resultado.stdout)

    def test_exige_decidir_navegador_y_base_a_la_vez(self):
        resultado = correr("setup-prueba", "--project", str(self.root),
                           "--navegador", "navegador-x")
        self.assertEqual(resultado.returncode, 1)
        self.assertIn("--base", resultado.stderr)
        self.assertIsNone(prueba_asistida.leer(self.root))

    def test_ambiente_y_prohibidas_solo_con_base(self):
        resultado = correr("setup-prueba", "--project", str(self.root),
                           "--sin-navegador", "--sin-base", "--prohibida", "x")
        self.assertEqual(resultado.returncode, 1)
        self.assertIn("--base", resultado.stderr)

    def test_muestra_la_configuracion_guardada(self):
        harness.write_json(self.root / ".claude" / "prueba_asistida.json", COMPLETA)
        resultado = correr("setup-prueba", "--project", str(self.root))
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertIn("navegador-x", resultado.stdout)
        self.assertIn("base-y.cambiar_ambiente", resultado.stdout)

    def test_rechaza_un_proyecto_sin_perfil(self):
        with tempfile.TemporaryDirectory() as vacio:
            resultado = correr("setup-prueba", "--project", vacio,
                               "--sin-navegador", "--sin-base")
        self.assertEqual(resultado.returncode, 1)
        self.assertIn("rules.json", resultado.stderr)

    def test_validate_conoce_el_contrato(self):
        harness.write_json(self.root / ".claude" / "prueba_asistida.json", {"navegador": 3})
        resultado = correr("validate", "--project", str(self.root),
                           "--contrato", "prueba_asistida",
                           "--archivo", str(self.root / ".claude" / "prueba_asistida.json"))
        self.assertEqual(resultado.returncode, 1)


class TestAvisos(ConProyecto):
    def abrir_ticket(self) -> subprocess.CompletedProcess:
        return correr("open-ticket", "--project", str(self.root), "--ticket-id", "T-1",
                      "--nroticket", "1", "--desarrollador", "DEV", "--fecha", "01-01-2026",
                      "--perfil", "p")

    def test_open_ticket_avisa_si_falta_el_setup_sin_bloquear(self):
        resultado = self.abrir_ticket()
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertIn("/harness-setup", resultado.stdout)

    def test_open_ticket_no_avisa_con_el_setup_hecho(self):
        harness.write_json(self.root / ".claude" / "prueba_asistida.json",
                           {"navegador": None, "base": None})
        resultado = self.abrir_ticket()
        self.assertNotIn("/harness-setup", resultado.stdout)

    def test_open_ticket_avisa_si_el_setup_es_invalido(self):
        harness.write_json(self.root / ".claude" / "prueba_asistida.json", {"navegador": 3})
        resultado = self.abrir_ticket()
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertIn("/harness-setup", resultado.stdout)

    def preparar_fase(self):
        plan = {"ticket_id": "T-1", "perfil": "p",
                "fases": [{"id": "fase_1", "titulo": "t", "criterio_exito": "c",
                           "prueba_manual": {"requerida": True}, "max_reintentos": 3,
                           "pasos": ["uno"], "anclajes": [],
                           "checks_deterministas": ["audit_comments"],
                           "herramientas_permitidas": ["edit"], "depende_de": []}]}
        self.abrir_ticket()
        harness.write_json(harness.ticket_dir(self.root, "T-1") / "plan.json", plan)
        correr("open-fase", "--project", str(self.root), "--fase", "fase_1")
        state.set_estado(self.root, "T-1", "fase_1", "esperando_humano")

    def generar(self, pasos) -> subprocess.CompletedProcess:
        entrada = self.root / "pasos.json"
        entrada.write_text(json.dumps(pasos), encoding="utf-8")
        return correr("generar-prueba", "--project", str(self.root),
                      "--pasos-json", str(entrada))

    def test_sin_navegador_acepta_pasos_del_agente_y_avisa(self):
        # Un repo sin pantalla (una API) igual tiene pasos de consulta o de API que
        # el probador corre sin navegador; los que lo necesiten los marca él.
        self.preparar_fase()
        harness.write_json(self.root / ".claude" / "prueba_asistida.json",
                           {"navegador": None, "base": {"servidor": "b", "prohibidas": []}})
        resultado = self.generar([{"paso": "x", "esperado": "y", "quien": "agente"}])
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertIn("sin navegador", resultado.stdout)
        self.assertIn("probador", resultado.stdout)

    def test_con_navegador_apunta_al_probador_y_a_la_configuracion(self):
        self.preparar_fase()
        harness.write_json(self.root / ".claude" / "prueba_asistida.json", COMPLETA)
        resultado = self.generar([{"paso": "x", "esperado": "y", "quien": "agente"}])
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertIn("probador", resultado.stdout)
        self.assertIn("prueba_asistida.json", resultado.stdout)

    def test_sin_setup_acepta_pasos_del_agente_pero_avisa(self):
        self.preparar_fase()
        resultado = self.generar([{"paso": "x", "esperado": "y", "quien": "agente"}])
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertIn("/harness-setup", resultado.stdout)


class TestNingunPerfilTraeElSetup(unittest.TestCase):
    """deploy.ps1 copia el perfil con -Force: si un perfil trajera el archivo, pisaría el setup."""

    def test_ningun_perfil_trae_prueba_asistida_json(self):
        for perfil in (RAIZ / "profiles").iterdir():
            with self.subTest(perfil=perfil.name):
                self.assertFalse((perfil / prueba_asistida.ARCHIVO).exists())


if __name__ == "__main__":
    unittest.main()

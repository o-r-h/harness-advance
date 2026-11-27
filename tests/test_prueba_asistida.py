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


class ConFase(ConProyecto):
    def abrir_ticket(self) -> subprocess.CompletedProcess:
        return correr("open-ticket", "--project", str(self.root), "--ticket-id", "T-1",
                      "--nroticket", "1", "--desarrollador", "DEV", "--fecha", "01-01-2026",
                      "--perfil", "p")

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


class TestAvisos(ConFase):

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


    def test_setup_invalido_no_se_reporta_como_sin_configurar(self):
        self.preparar_fase()
        harness.write_json(self.root / ".claude" / "prueba_asistida.json", {"navegador": 3})
        resultado = self.generar([{"paso": "x", "esperado": "y", "quien": "agente"}])
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertIn("inválido", resultado.stdout)
        self.assertNotIn("no está configurada", resultado.stdout)

    def test_un_paso_del_agente_sin_esperado_se_rechaza(self):
        self.preparar_fase()
        resultado = self.generar([{"paso": "x", "quien": "agente"}])
        self.assertEqual(resultado.returncode, 1)
        self.assertIn("esperado", resultado.stderr)


class TestBloqueoTecnico(ConProyecto):
    """Las prohibidas pasan a disallowedTools de un probador del proyecto."""

    def agente(self) -> Path:
        return prueba_asistida.ruta_agente(self.root)

    def setup(self, *prohibidas: str) -> subprocess.CompletedProcess:
        args = ["setup-prueba", "--project", str(self.root), "--sin-navegador",
                "--base", "base-y"]
        for herramienta in prohibidas:
            args += ["--prohibida", herramienta]
        return correr(*args)

    def herramientas(self) -> list[str]:
        linea = next(l for l in self.agente().read_text(encoding="utf-8").splitlines()
                     if l.startswith("disallowedTools:"))
        return [h.strip() for h in linea.split(":", 1)[1].split(",")]

    def test_el_setup_genera_el_probador_del_proyecto(self):
        resultado = self.setup("srv__cambiar_ambiente", "srv__escribir")
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertIn("Bloqueo técnico", resultado.stdout)
        self.assertEqual(self.herramientas(), ["Edit", "NotebookEdit", "Agent",
                                               "srv__cambiar_ambiente", "srv__escribir"])
        texto = self.agente().read_text(encoding="utf-8")
        self.assertIn(prueba_asistida.MARCA, texto)
        self.assertIn("name: probador", texto)
        self.assertIn("Eres el probador del harness", texto)

    def test_el_frontmatter_generado_sigue_cerrado_y_la_marca_va_despues(self):
        self.setup("srv__x")
        lineas = self.agente().read_text(encoding="utf-8").splitlines()
        cierre = lineas.index("---", 1)
        self.assertGreater(lineas.index(prueba_asistida.MARCA), cierre)
        self.assertTrue(all(":" in l or l.startswith(" ") for l in lineas[1:cierre]))

    def test_sin_prohibidas_no_genera_nada(self):
        resultado = self.setup()
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertFalse(self.agente().exists())

    def test_quitar_las_prohibidas_quita_el_probador_generado(self):
        self.setup("srv__x")
        resultado = self.setup()
        self.assertFalse(self.agente().exists())
        self.assertIn("probador global", resultado.stdout)

    def test_un_probador_propio_del_proyecto_no_se_toca(self):
        self.agente().parent.mkdir(parents=True)
        self.agente().write_text("---\nname: probador\n---\nmío\n", encoding="utf-8")
        resultado = self.setup("srv__x")
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertIn("no se toca", resultado.stdout)
        self.assertIn("mío", self.agente().read_text(encoding="utf-8"))

    def test_repetir_el_setup_no_duplica_herramientas(self):
        self.setup("srv__x", "srv__x", "Edit")
        self.assertEqual(self.herramientas(), ["Edit", "NotebookEdit", "Agent", "srv__x"])

    def test_open_ticket_repone_el_probador_si_falta_o_quedo_viejo(self):
        self.setup("srv__x")
        self.agente().write_text(prueba_asistida.MARCA + "\nviejo\n", encoding="utf-8")
        resultado = correr("open-ticket", "--project", str(self.root), "--ticket-id", "T-1",
                           "--nroticket", "1", "--desarrollador", "DEV",
                           "--fecha", "01-01-2026", "--perfil", "p")
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertIn("Bloqueo técnico", resultado.stdout)
        self.assertEqual(self.herramientas()[-1], "srv__x")

    def test_una_prohibida_con_coma_o_espacio_se_rechaza(self):
        for mala in ("a, b", "a b"):
            with self.subTest(prohibida=mala):
                resultado = self.setup(mala)
                self.assertEqual(resultado.returncode, 1)
                self.assertIn("sin comas ni espacios", resultado.stderr)
        self.assertFalse(self.agente().exists())

    def test_sin_disallowedtools_en_el_generico_se_agrega_el_campo(self):
        texto = prueba_asistida.agente_con_prohibidas(
            "---\nname: probador\n---\n\ncuerpo\n", ["srv__x"])
        self.assertEqual(texto, "---\nname: probador\ndisallowedTools: srv__x\n---\n\n"
                                + prueba_asistida.MARCA + "\n\ncuerpo\n")


class TestAvisoDelProbadorAlDarOk(ConFase):
    def registrar_ok(self, reporte: str | None) -> subprocess.CompletedProcess:
        self.preparar_fase()
        self.generar([{"paso": "x", "esperado": "y", "quien": "agente"}])
        carpeta = harness.intento_dir(self.root, "T-1", "fase_1", 1)
        harness.write_json(carpeta / "veredicto.json", {
            "fase_id": "fase_1", "intento": 1, "aprobado": False,
            "juicio_esceptico": {"aprobado": True, "criterio_cumplido": True,
                                 "claims_sin_evidencia": [], "anclajes_sin_resolver": [],
                                 "razones_rechazo": []},
            "prueba_manual": {"requerida": True, "ejecutada": False, "resultado": None}})
        if reporte is not None:
            (carpeta / "prueba_asistida.md").write_text(reporte, encoding="utf-8")
        return correr("record-manual", "--project", str(self.root), "--resultado", "ok")

    def test_avisa_si_el_probador_marco_una_falla(self):
        resultado = self.registrar_ok("| 1 | agente | **falla** | otra cosa | 01.png |\n")
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertIn("'falla'", resultado.stdout)
        self.assertIn("aprobada", resultado.stdout)

    def test_avisa_si_el_probador_no_dejo_reporte(self):
        resultado = self.registrar_ok(None)
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertIn("no hay prueba_asistida.md", resultado.stdout)

    def test_no_avisa_si_todo_paso(self):
        resultado = self.registrar_ok("Resumen: 1 pasa, ninguna falla.\n\n"
                                      "| 1 | agente | pasa | lo esperado | 01.png |\n")
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertNotIn("Aviso", resultado.stdout)


class TestNingunPerfilTraeElSetup(unittest.TestCase):
    """deploy.ps1 copia el perfil con -Force: si un perfil trajera el archivo, pisaría el setup."""

    def test_ningun_perfil_trae_prueba_asistida_json(self):
        for perfil in (RAIZ / "profiles").iterdir():
            with self.subTest(perfil=perfil.name):
                self.assertFalse((perfil / prueba_asistida.ARCHIVO).exists())

    def test_ningun_perfil_trae_un_probador(self):
        for perfil in (RAIZ / "profiles").iterdir():
            with self.subTest(perfil=perfil.name):
                self.assertFalse((perfil / "agents" / prueba_asistida.AGENTE).exists())


if __name__ == "__main__":
    unittest.main()

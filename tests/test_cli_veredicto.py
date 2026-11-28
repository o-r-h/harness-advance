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


def _plan(prueba_requerida: bool) -> dict:
    return {"ticket_id": "ISR-110722", "perfil": "p",
            "fases": [{"id": "fase_1", "titulo": "t", "pasos": ["p"], "anclajes": [],
                       "criterio_exito": "c", "checks_deterministas": ["audit_comments"],
                       "prueba_manual": {"requerida": prueba_requerida},
                       "herramientas_permitidas": ["edit"], "max_reintentos": 3,
                       "depende_de": []}]}


def correr(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(CLI), *args],
                          capture_output=True, text=True, encoding="utf-8")


class TestRecordVeredicto(unittest.TestCase):
    def preparar(self, prueba_requerida=True):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / ".claude").mkdir()
        harness.write_json(self.root / ".claude" / "rules.json", REGLAS)
        harness.write_json(harness.ticket_dir(self.root, "ISR-110722") / "plan.json",
                           _plan(prueba_requerida))
        correr("open-ticket", "--project", str(self.root), "--ticket-id", "ISR-110722",
               "--nroticket", "110722", "--desarrollador", "OMAR RODRIGUEZ",
               "--fecha", "28-07-2026", "--perfil", "p")
        correr("open-fase", "--project", str(self.root), "--fase", "fase_1")
        self.checks()

    def checks(self) -> subprocess.CompletedProcess:
        return correr("run-checks", "--project", str(self.root))

    def escribir(self, veredicto: dict) -> Path:
        ruta = self.root / "veredicto_entrada.json"
        ruta.write_text(json.dumps(veredicto), encoding="utf-8")
        return ruta

    @staticmethod
    def _veredicto(aprobado_esceptico: bool, razones=None, prueba=None) -> dict:
        return {"fase_id": "fase_1", "intento": 1, "aprobado": False,
                "juicio_esceptico": {"aprobado": aprobado_esceptico,
                                     "razones_rechazo": razones or [],
                                     "claims_sin_evidencia": [],
                                     "anclajes_sin_resolver": []},
                "prueba_manual": prueba or {"requerida": True, "ejecutada": False,
                                            "resultado": "pendiente"}}

    def test_rechazo_incrementa_el_intento_y_deja_en_correccion(self):
        self.preparar()
        ruta = self.escribir(self._veredicto(False, ["falta validar el campo"]))
        resultado = correr("record-veredicto", "--project", str(self.root), "--archivo", str(ruta))
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        estado = state.leer_fase(self.root, "ISR-110722", "fase_1")
        self.assertEqual(estado["intento_actual"], 2)
        self.assertEqual(estado["estado"], "en_correccion")
        self.assertEqual(estado["historial_fallos"][0]["origen"], "esceptico")

    def test_aprobacion_con_prueba_requerida_deja_esperando_humano(self):
        self.preparar(prueba_requerida=True)
        ruta = self.escribir(self._veredicto(True))
        correr("record-veredicto", "--project", str(self.root), "--archivo", str(ruta))
        estado = state.leer_fase(self.root, "ISR-110722", "fase_1")
        self.assertEqual(estado["estado"], "esperando_humano")

    def test_aprobacion_sin_prueba_requerida_cierra_la_fase(self):
        self.preparar(prueba_requerida=False)
        ruta = self.escribir(self._veredicto(
            True, prueba={"requerida": False, "ejecutada": False, "resultado": "na"}))
        correr("record-veredicto", "--project", str(self.root), "--archivo", str(ruta))
        estado = state.leer_fase(self.root, "ISR-110722", "fase_1")
        self.assertEqual(estado["estado"], "aprobada")

    def test_rechaza_un_veredicto_que_viola_su_contrato(self):
        self.preparar()
        ruta = self.escribir(self._veredicto(False, []))  # rechazo sin razones
        resultado = correr("record-veredicto", "--project", str(self.root), "--archivo", str(ruta))
        self.assertEqual(resultado.returncode, 1)
        self.assertIn("razones_rechazo", resultado.stderr)

    def test_el_veredicto_queda_guardado_en_la_carpeta_del_intento(self):
        self.preparar()
        ruta = self.escribir(self._veredicto(True))
        correr("record-veredicto", "--project", str(self.root), "--archivo", str(ruta))
        destino = harness.intento_dir(self.root, "ISR-110722", "fase_1", 1) / "veredicto.json"
        self.assertTrue(destino.is_file())

    def test_al_tercer_rechazo_la_fase_escala(self):
        self.preparar()
        for _ in range(3):
            ruta = self.escribir(self._veredicto(False, ["sigue mal"]))
            correr("record-veredicto", "--project", str(self.root), "--archivo", str(ruta))
            self.checks()
        estado = state.leer_fase(self.root, "ISR-110722", "fase_1")
        self.assertEqual(estado["estado"], "escalado")

    def test_sin_run_checks_en_este_intento_se_rechaza(self):
        self.preparar()
        ruta = self.escribir(self._veredicto(False, ["mal"]))
        correr("record-veredicto", "--project", str(self.root), "--archivo", str(ruta))
        # El rechazo abrió el intento 2, que todavía no pasó por run-checks.
        resultado = correr("record-veredicto", "--project", str(self.root),
                           "--archivo", str(self.escribir(self._veredicto(True))))
        self.assertEqual(resultado.returncode, 1)
        self.assertIn("run-checks", resultado.stderr)
        estado = state.leer_fase(self.root, "ISR-110722", "fase_1")
        self.assertEqual(estado["intento_actual"], 2)


def git(raiz: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
                   cwd=str(raiz), check=True, capture_output=True)


class TestEvidenciaAtadaAlCambio(TestRecordVeredicto):
    """Con git, checks.json guarda la huella del cambio y el veredicto se ata a ella."""

    def preparar(self, prueba_requerida=True):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / ".claude").mkdir()
        harness.write_json(self.root / ".claude" / "rules.json",
                           {"perfil": "p", "audit_comments": {"requerido": False,
                                                              "severidad": "warning"}})
        (self.root / ".gitignore").write_text(".harness/\n", encoding="utf-8")
        (self.root / "codigo.txt").write_text("uno\n", encoding="utf-8")
        git(self.root, "init", "-q")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "base")
        harness.write_json(harness.ticket_dir(self.root, "ISR-110722") / "plan.json",
                           _plan(prueba_requerida))
        correr("open-ticket", "--project", str(self.root), "--ticket-id", "ISR-110722",
               "--nroticket", "110722", "--desarrollador", "OMAR RODRIGUEZ",
               "--fecha", "28-07-2026", "--perfil", "p")
        correr("open-fase", "--project", str(self.root), "--fase", "fase_1")
        (self.root / "codigo.txt").write_text("uno\ndos\n", encoding="utf-8")
        resultado = self.checks()
        assert resultado.returncode == 0, resultado.stdout + resultado.stderr

    def intento(self) -> Path:
        return harness.intento_dir(self.root, "ISR-110722", "fase_1", 1)

    def escribir(self, veredicto: dict) -> Path:
        # Dentro de .harness/: un temporal en la raíz del proyecto movería la huella.
        ruta = self.root / ".harness" / "veredicto_entrada.json"
        ruta.write_text(json.dumps(veredicto), encoding="utf-8")
        return ruta

    def aprobar(self) -> subprocess.CompletedProcess:
        return correr("record-veredicto", "--project", str(self.root),
                      "--archivo", str(self.escribir(self._veredicto(True))))

    def manual(self, *extra: str) -> subprocess.CompletedProcess:
        return correr("record-manual", "--project", str(self.root), *extra)

    def test_checks_json_guarda_la_huella(self):
        self.preparar()
        huella = harness.read_json(self.intento() / "checks.json")["huella_cambio"]
        self.assertEqual(list(huella), ["codigo.txt"])
        self.assertRegex(huella["codigo.txt"], r"^[0-9a-f]{64}$")

    def test_veredicto_se_rechaza_si_el_codigo_cambio_tras_los_checks(self):
        self.preparar()
        (self.root / "codigo.txt").write_text("uno\ndos\ntres\n", encoding="utf-8")
        resultado = self.aprobar()
        self.assertEqual(resultado.returncode, 1)
        self.assertIn("cambió después de 'run-checks'", resultado.stderr)
        self.assertIn("codigo.txt (modificado)", resultado.stderr)
        estado = state.leer_fase(self.root, "ISR-110722", "fase_1")
        self.assertEqual((estado["estado"], estado["intento_actual"]), ("en_verificacion", 1))
        self.assertFalse((self.intento() / "veredicto.json").exists())

    def test_tras_volver_a_correr_los_checks_el_veredicto_entra(self):
        self.preparar()
        (self.root / "codigo.txt").write_text("uno\ndos\ntres\n", encoding="utf-8")
        self.checks()
        self.assertEqual(self.aprobar().returncode, 0)

    def test_un_archivo_nuevo_sin_rastrear_tambien_cuenta(self):
        self.preparar()
        (self.root / "nuevo.txt").write_text("x\n", encoding="utf-8")
        resultado = self.aprobar()
        self.assertEqual(resultado.returncode, 1)
        self.assertIn("nuevo.txt (nuevo en el cambio)", resultado.stderr)

    def test_lo_que_escribe_el_harness_no_mueve_la_huella(self):
        self.preparar()
        entradas = self.root / ".claude" / "biblioteca" / "entradas"
        entradas.mkdir(parents=True)
        (entradas / "x.md").write_text("lección\n", encoding="utf-8")
        (self.root / ".claude" / "prueba_asistida.json").write_text("{}", encoding="utf-8")
        self.assertEqual(self.aprobar().returncode, 0, self.aprobar().stderr)

    def test_fase_ok_se_rechaza_si_el_codigo_cambio_tras_el_veredicto(self):
        self.preparar()
        self.aprobar()
        (self.root / "codigo.txt").write_text("otra cosa\n", encoding="utf-8")
        resultado = self.manual("--resultado", "ok")
        self.assertEqual(resultado.returncode, 1)
        self.assertIn("--aceptar-cambio", resultado.stderr)
        estado = state.leer_fase(self.root, "ISR-110722", "fase_1")
        self.assertEqual(estado["estado"], "esperando_humano")

    def test_el_humano_puede_aceptar_el_cambio_y_queda_registrado(self):
        self.preparar()
        self.aprobar()
        (self.root / "codigo.txt").write_text("otra cosa\n", encoding="utf-8")
        resultado = self.manual("--resultado", "ok", "--aceptar-cambio", "solo un comentario")
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        veredicto = harness.read_json(self.intento() / "veredicto.json")
        self.assertEqual(veredicto["prueba_manual"]["cambio_posterior"],
                         {"archivos": "codigo.txt (modificado)",
                          "motivo": "solo un comentario"})
        self.assertEqual(state.leer_fase(self.root, "ISR-110722", "fase_1")["estado"],
                         "aprobada")

    def test_fase_fallo_entra_aunque_el_codigo_haya_cambiado(self):
        self.preparar()
        self.aprobar()
        (self.root / "codigo.txt").write_text("otra cosa\n", encoding="utf-8")
        resultado = self.manual("--resultado", "fallo", "--paso", "1", "--observacion", "x")
        self.assertEqual(resultado.returncode, 0, resultado.stderr)

    def test_sin_cambios_fase_ok_no_pide_nada(self):
        self.preparar()
        self.aprobar()
        resultado = self.manual("--resultado", "ok")
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        veredicto = harness.read_json(self.intento() / "veredicto.json")
        self.assertNotIn("cambio_posterior", veredicto["prueba_manual"])


class TestBaseDeLaFase(TestEvidenciaAtadaAlCambio):
    """El cambio de la fase se mide contra el commit en que se abrió, no contra HEAD."""

    def commitear(self, mensaje="a mitad de fase") -> None:
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", mensaje)

    def base(self) -> dict:
        return harness.read_json(
            harness.fase_dir(self.root, "ISR-110722", "fase_1") / "base.json")

    def huella(self) -> dict:
        return harness.read_json(self.intento() / "checks.json")["huella_cambio"]

    def test_open_fase_anota_el_commit_de_apertura(self):
        self.preparar()
        self.assertRegex(self.base()["commit"], r"^[0-9a-f]{40}$")
        self.assertEqual(self.base()["sucios"], {})
        checks = harness.read_json(self.intento() / "checks.json")
        self.assertEqual(checks["base_commit"], self.base()["commit"])

    def test_un_commit_a_mitad_de_fase_no_mueve_la_huella(self):
        self.preparar()
        antes = self.huella()
        self.commitear()
        self.assertEqual(self.aprobar().returncode, 0, self.aprobar().stderr)
        resultado = self.manual("--resultado", "ok")
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.checks_no_se_movieron(antes)

    def checks_no_se_movieron(self, antes: dict) -> None:
        self.assertEqual(self.huella(), antes)

    def test_tras_el_commit_los_checks_siguen_viendo_el_cambio(self):
        self.preparar()
        self.commitear()
        self.assertEqual(self.checks().returncode, 0)
        self.assertEqual(list(self.huella()), ["codigo.txt"])

    def test_tras_el_commit_las_reglas_siguen_revisando_lo_agregado(self):
        self.preparar()
        reglas = {"perfil": "p", "prohibido": [
            {"id": "sin_dos", "archivos": [".txt"], "severidad": "error",
             "patron": "^dos$", "mensaje": "no se escribe dos"}]}
        harness.write_json(self.root / ".claude" / "rules.json", reglas)
        plan = _plan(True)
        plan["fases"][0]["checks_deterministas"] = ["sin_dos"]
        harness.write_json(harness.ticket_dir(self.root, "ISR-110722") / "plan.json", plan)
        self.commitear()
        resultado = self.checks()
        self.assertEqual(resultado.returncode, 1, resultado.stdout + resultado.stderr)
        detalle = json.dumps(harness.read_json(self.intento() / "checks.json"),
                             ensure_ascii=False)
        self.assertIn("codigo.txt:2 no se escribe dos", detalle)

    def test_un_cambio_despues_del_commit_se_sigue_rechazando(self):
        self.preparar()
        self.commitear()
        (self.root / "codigo.txt").write_text("uno\ndos\ntres\n", encoding="utf-8")
        resultado = self.aprobar()
        self.assertEqual(resultado.returncode, 1)
        self.assertIn("codigo.txt (modificado)", resultado.stderr)

    def diff(self) -> str:
        return (self.intento() / "cambio.diff").read_text(encoding="utf-8")

    def test_run_checks_escribe_el_diff_de_la_fase(self):
        self.preparar()
        self.assertIn("+++ b/codigo.txt", self.diff())
        self.assertIn("\n+dos", self.diff())
        self.assertNotIn("\n+uno", self.diff())

    def test_el_diff_conserva_lo_commiteado_a_mitad_de_fase(self):
        self.preparar()
        antes = self.diff()
        self.commitear()
        self.assertEqual(self.checks().returncode, 0)
        self.assertEqual(self.diff(), antes)

    def test_un_archivo_nuevo_sale_completo_en_el_diff(self):
        self.preparar()
        (self.root / "nuevo.txt").write_text("a\nb\n", encoding="utf-8")
        self.checks()
        self.assertIn("--- /dev/null\n+++ b/nuevo.txt", self.diff())
        self.assertIn("\n+a\n+b", self.diff())

    def test_un_archivo_borrado_sale_en_el_diff(self):
        self.preparar()
        (self.root / "codigo.txt").unlink()
        self.checks()
        self.assertIn("--- a/codigo.txt\n+++ /dev/null", self.diff())
        self.assertIn("\n-uno", self.diff())

    def test_reabrir_la_fase_no_mueve_la_base(self):
        self.preparar()
        original = self.base()
        self.commitear()
        correr("open-fase", "--project", str(self.root), "--fase", "fase_1")
        self.assertEqual(self.base(), original)

    def test_una_base_cuyo_commit_ya_no_existe_se_avisa_y_no_se_calla(self):
        self.preparar()
        ruta = harness.fase_dir(self.root, "ISR-110722", "fase_1") / "base.json"
        harness.write_json(ruta, {"commit": "0" * 40, "sucios": {}})
        self.assertEqual(self.checks().returncode, 0)
        checks = harness.read_json(self.intento() / "checks.json")
        aviso = [c for c in checks["checks"] if c["id"] == "base_de_fase"]
        self.assertEqual([c["resultado"] for c in aviso], ["error_check"])
        self.assertEqual(list(checks["huella_cambio"]), ["codigo.txt"])

    def test_una_fase_sin_base_se_mide_contra_HEAD_como_antes(self):
        self.preparar()
        (harness.fase_dir(self.root, "ISR-110722", "fase_1") / "base.json").unlink()
        self.assertEqual(self.checks().returncode, 0)
        self.assertEqual(list(self.huella()), ["codigo.txt"])
        self.assertIsNone(harness.read_json(self.intento() / "checks.json")["base_commit"])


class TestLoQueYaEstabaSinCommitear(unittest.TestCase):
    """Lo que dejó sin commitear una fase anterior no se le cuenta a la siguiente."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / ".claude").mkdir()
        harness.write_json(self.root / ".claude" / "rules.json",
                           {"perfil": "p", "audit_comments": {"requerido": False,
                                                              "severidad": "warning"}})
        (self.root / ".gitignore").write_text(".harness/\n", encoding="utf-8")
        (self.root / "codigo.txt").write_text("uno\n", encoding="utf-8")
        git(self.root, "init", "-q")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "base")
        # Restos de una fase anterior: un archivo modificado y uno nuevo, sin commit.
        (self.root / "codigo.txt").write_text("uno\nfase anterior\n", encoding="utf-8")
        (self.root / "anterior.txt").write_text("fase anterior\n", encoding="utf-8")
        harness.write_json(harness.ticket_dir(self.root, "ISR-110722") / "plan.json",
                           _plan(True))
        correr("open-ticket", "--project", str(self.root), "--ticket-id", "ISR-110722",
               "--nroticket", "110722", "--desarrollador", "OMAR RODRIGUEZ",
               "--fecha", "28-07-2026", "--perfil", "p")
        self.apertura = correr("open-fase", "--project", str(self.root), "--fase", "fase_1")

    def huella(self) -> list[str]:
        resultado = correr("run-checks", "--project", str(self.root))
        assert resultado.returncode == 0, resultado.stdout + resultado.stderr
        intento = harness.intento_dir(self.root, "ISR-110722", "fase_1", 1)
        return list(harness.read_json(intento / "checks.json")["huella_cambio"])

    def test_open_fase_avisa_de_lo_que_ya_estaba_sin_commitear(self):
        self.assertIn("2 archivo(s) sin commitear", self.apertura.stdout)

    def test_lo_que_ya_estaba_no_entra_en_la_huella(self):
        (self.root / "nuevo.txt").write_text("de esta fase\n", encoding="utf-8")
        self.assertEqual(self.huella(), ["nuevo.txt"])

    def test_si_la_fase_lo_vuelve_a_tocar_si_entra(self):
        (self.root / "anterior.txt").write_text("fase anterior\ny esta\n", encoding="utf-8")
        self.assertEqual(self.huella(), ["anterior.txt"])

    def diff(self) -> str:
        intento = harness.intento_dir(self.root, "ISR-110722", "fase_1", 1)
        return (intento / "cambio.diff").read_text(encoding="utf-8")

    def test_el_diff_de_un_archivo_que_ya_estaba_sucio_trae_solo_lo_de_la_fase(self):
        (self.root / "codigo.txt").write_text("uno\nfase anterior\nesta fase\n",
                                              encoding="utf-8")
        self.assertEqual(self.huella(), ["codigo.txt"])
        self.assertIn("\n+esta fase", self.diff())
        self.assertNotIn("+fase anterior", self.diff())

    def test_un_sucio_sin_tocar_no_aparece_en_el_diff(self):
        (self.root / "nuevo.txt").write_text("de esta fase\n", encoding="utf-8")
        self.huella()
        self.assertIn("nuevo.txt", self.diff())
        self.assertNotIn("anterior.txt", self.diff())
        self.assertNotIn("codigo.txt", self.diff())

    def test_las_reglas_no_vuelven_a_juzgar_las_lineas_de_la_fase_anterior(self):
        reglas = {"perfil": "p", "prohibido": [
            {"id": "sin_anterior", "archivos": [".txt"], "severidad": "error",
             "patron": "fase anterior", "mensaje": "línea de otra fase"}]}
        harness.write_json(self.root / ".claude" / "rules.json", reglas)
        plan = _plan(True)
        plan["fases"][0]["checks_deterministas"] = ["sin_anterior"]
        harness.write_json(harness.ticket_dir(self.root, "ISR-110722") / "plan.json", plan)
        (self.root / "codigo.txt").write_text("uno\nfase anterior\nesta fase\n",
                                              encoding="utf-8")
        # huella() exige que run-checks salga con 0: la línea vieja no disparó la regla.
        self.assertIn("codigo.txt", self.huella())

    def test_commitear_los_restos_a_mitad_de_fase_tampoco_los_mete(self):
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "lo de la fase anterior")
        (self.root / "nuevo.txt").write_text("de esta fase\n", encoding="utf-8")
        self.assertEqual(self.huella(), ["nuevo.txt"])


class TestAgenteEsceptico(unittest.TestCase):
    def test_no_menciona_reglas_de_otro_proyecto(self):
        texto = (RAIZ / "harness" / "agents" / "skeptic.md").read_text(encoding="utf-8")
        for prohibido in ("Kilo Code", ".kilocode", "actor system", "TypeScript"):
            self.assertNotIn(prohibido, texto)

    def test_no_menciona_ningun_stack_concreto(self):
        texto = (RAIZ / "harness" / "agents" / "skeptic.md").read_text(encoding="utf-8")
        for prohibido in ("VB.NET", "Web Forms", "jQuery", "EjecutarSp"):
            self.assertNotIn(prohibido, texto)


if __name__ == "__main__":
    unittest.main()

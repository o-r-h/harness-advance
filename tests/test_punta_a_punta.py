"""Ciclo completo del harness con un modelo falso.

Cada actor que en la vida real es un modelo (planner, ejecutor, escéptico,
reflector) aquí es una respuesta fija; el humano son los comandos que escribiría.
Todo lo demás es lo real: el CLI, los hooks PostToolUse y Stop, git y el reporte,
cada uno como subproceso. Las pruebas de cada pieza viven en sus propios archivos;
esta atrapa lo que se rompe entre piezas.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
HOOKS = RAIZ / "harness" / "hooks"
sys.path.insert(0, str(HOOKS))
from lib import biblioteca, harness, state  # noqa: E402

PERFIL = "demo"
REGLAS = {"perfil": PERFIL,
          "prohibido": [{"id": "no_todo", "archivos": [".txt"], "severidad": "error",
                         "patron": r"\bTODO\b",
                         "mensaje": "no se entrega con un TODO pendiente"}]}
LECCION = "Antes de entregar, buscar y resolver los TODO del cambio"


def _python(script: Path, *args: str, entrada: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(script), *args], input=entrada,
                          capture_output=True, text=True, encoding="utf-8")


class CicloCompleto(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / ".claude").mkdir()
        harness.write_json(self.root / ".claude" / "rules.json", REGLAS)
        self.git("init")
        self.git("config", "user.email", "t@t.t")
        self.git("config", "user.name", "t")
        (self.root / "base.txt").write_text("base\n", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-m", "base")

    # --- infraestructura real --------------------------------------------------

    def git(self, *args: str) -> None:
        subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True)

    def cli(self, *args: str, codigo: int = 0) -> subprocess.CompletedProcess:
        resultado = _python(HOOKS / "cli.py", *args, "--project", str(self.root))
        self.assertEqual(resultado.returncode, codigo,
                         f"cli {args[0]}: {resultado.stdout}{resultado.stderr}")
        return resultado

    def hook_stop(self) -> subprocess.CompletedProcess:
        return _python(HOOKS / "gate_phase.py", entrada=json.dumps(
            {"hook_event_name": "Stop", "cwd": str(self.root), "stop_hook_active": False}))

    def fase(self, ticket: str) -> dict:
        return state.leer_fase(self.root, ticket, "fase_1")

    def intento(self, ticket: str, n: int) -> Path:
        return harness.intento_dir(self.root, ticket, "fase_1", n)

    def escribir_json(self, nombre: str, datos) -> str:
        ruta = self.root / ".harness" / "entrada" / nombre
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
        return str(ruta)

    # --- los actores falsos ----------------------------------------------------

    def planner(self, ticket: str, max_reintentos: int) -> None:
        plan = {"ticket_id": ticket, "perfil": PERFIL,
                "fases": [{"id": "fase_1", "titulo": "Agregar el módulo",
                           "pasos": ["crear modulo.txt"], "anclajes": [],
                           "criterio_exito": "modulo.txt existe y valida la entrada vacía",
                           "checks_deterministas": ["no_todo"],
                           "prueba_manual": {"requerida": True},
                           "herramientas_permitidas": ["edit"],
                           "max_reintentos": max_reintentos, "depende_de": []}]}
        ruta = harness.ticket_dir(self.root, ticket) / "plan.json"
        harness.write_json(ruta, plan)
        self.cli("validate", "--contrato", "plan", "--archivo", str(ruta))

    def ejecutor(self, archivo: str, contenido: str) -> subprocess.CompletedProcess:
        """Escribe el archivo y dispara el PostToolUse como lo haría Claude Code."""
        ruta = self.root / archivo
        ruta.write_text(contenido, encoding="utf-8")
        return _python(HOOKS / "check_rules.py", entrada=json.dumps(
            {"hook_event_name": "PostToolUse", "tool_name": "Write",
             "tool_input": {"file_path": str(ruta)}, "cwd": str(self.root)}))

    def esceptico(self, intento: int, aprobado: bool, razones: list[str] | None = None) -> str:
        return self.escribir_json(f"veredicto_{intento}.json", {
            "fase_id": "fase_1", "intento": intento, "aprobado": False,
            "juicio_esceptico": {"aprobado": aprobado, "razones_rechazo": razones or [],
                                 "claims_sin_evidencia": [], "anclajes_sin_resolver": []},
            "prueba_manual": {"requerida": True, "ejecutada": False,
                              "resultado": "pendiente"}})

    def reflector(self, ticket: str, reincide: str | None = None) -> str:
        hallazgo = {"senal": "el cambio llegó a verificación con un TODO pendiente",
                    "leccion": LECCION, "evidencia": "intento_1/checks.json: no_todo",
                    "confianza": "alta", "dimension": "proceso", "componente": "check"}
        if reincide:
            hallazgo["reincide"] = reincide
        return self.escribir_json(f"propuesta_{ticket}.json",
                                  {"fase_id": "fase_1", "hallazgos": [hallazgo]})

    # --- los dos tickets -------------------------------------------------------

    def ticket_que_escala(self) -> str:
        """ISR-1: falla checks, falla el escéptico, falla la prueba manual y escala."""
        t = "ISR-1"
        self.cli("open-ticket", "--ticket-id", t, "--nroticket", "1",
                 "--desarrollador", "OMAR RODRIGUEZ", "--fecha", "02-11-2026",
                 "--perfil", PERFIL)
        self.planner(t, max_reintentos=3)
        self.assertIn("intento 1/3", self.cli("open-fase", "--fase", "fase_1").stdout)
        self.assertEqual(self.hook_stop().returncode, 2, "el turno no cierra a mitad de fase")

        # Intento 1: el hook avisa del TODO, pero el ejecutor no corrige.
        aviso = self.ejecutor("modulo.txt", "leer entrada\nTODO: validar vacía\n")
        self.assertEqual(aviso.returncode, 2)
        self.assertIn("no_todo", aviso.stderr)
        self.assertEqual(self.fase(t)["intento_actual"], 1, "la autocorrección no es intento")
        self.cli("run-checks", codigo=1)
        self.assertEqual((self.fase(t)["estado"], self.fase(t)["intento_actual"]),
                         ("en_correccion", 2))
        self.assertIn("en_correccion", self.hook_stop().stderr)

        # Intento 2: checks limpios; el escéptico rechaza.
        self.assertEqual(self.ejecutor("modulo.txt", "leer entrada\n").returncode, 0)
        self.cli("run-checks")
        self.assertEqual(self.fase(t)["estado"], "en_verificacion")
        self.cli("open-ticket", "--ticket-id", "ISR-9", "--nroticket", "9",
                 "--desarrollador", "OMAR RODRIGUEZ", "--fecha", "02-11-2026",
                 "--perfil", PERFIL, codigo=1)
        self.cli("pausar-fase", "--motivo", "almuerzo")
        self.assertEqual(self.hook_stop().returncode, 0)
        self.cli("open-fase", "--fase", "fase_1")
        self.assertEqual((self.fase(t)["estado"], self.fase(t)["intento_actual"]),
                         ("en_verificacion", 2))
        self.assertEqual(self.hook_stop().returncode, 2)
        self.cli("record-veredicto", "--archivo",
                 self.esceptico(2, False, ["no valida la entrada vacía"]))
        self.assertEqual(self.fase(t)["intento_actual"], 3)

        # Intento 3: el escéptico aprueba; el humano prueba y falla: se agotó.
        self.ejecutor("modulo.txt", "leer entrada\nsi está vacía, avisar\n")
        self.cli("run-checks")
        self.cli("record-veredicto", "--archivo", self.esceptico(3, True))
        self.assertEqual(self.fase(t)["estado"], "esperando_humano")
        self.assertEqual(self.hook_stop().returncode, 0, "esperar al humano no bloquea")
        self.cli("generar-prueba", "--pasos-json", self.escribir_json("pasos.json", [
            {"paso": "dejar la entrada vacía", "esperado": "nada"},
            {"paso": "aceptar", "esperado": "aparece el aviso"}]))
        self.cli("record-manual", "--resultado", "fallo", "--paso", "2",
                 "--observacion", "no aparece el aviso")

        estado = self.fase(t)
        self.assertEqual((estado["estado"], estado["intento_actual"]), ("escalado", 3))
        self.assertEqual([f["origen"] for f in estado["historial_fallos"]],
                         ["check", "esceptico", "humano"])
        self.assertEqual(self.hook_stop().returncode, 0, "una fase escalada no bloquea")
        self.cli("run-checks", codigo=1)
        for n in (1, 2, 3):
            self.assertTrue((self.intento(t, n) / "checks.json").is_file(), f"intento {n}")
        for n in (2, 3):
            self.assertTrue((self.intento(t, n) / "veredicto.json").is_file(), f"intento {n}")
        self.assertTrue((self.intento(t, 3) / "prueba_manual.md").is_file())

        # Al cerrar: el reflector propone, el humano aprueba y luego hace la pieza.
        self.cli("record-hallazgos", "--archivo", self.reflector(t))
        ref = f"{t}/fase_1/h1"
        self.assertIn(ref, self.cli("hallazgos-pendientes").stdout)
        self.cli("resolver-hallazgo", "--id", ref, "--decision", "ok")
        self.assertEqual(biblioteca.leer_entrada(self.root, ref)["leccion"], LECCION)
        self.assertIn("entradas/ISR-1-fase_1-h1.md",
                      (self.root / ".claude" / "biblioteca" / "INDEX.md")
                      .read_text(encoding="utf-8"))
        self.cli("hallazgo-hecho", "--id", ref, "--nota", "regla no_todo en rules.json")
        self.assertTrue(biblioteca.leer_entrada(self.root, ref)["implementada"])
        return ref

    def test_un_ticket_que_escala_deja_una_leccion_implementada(self):
        ref = self.ticket_que_escala()
        self.assertEqual(self.cli("hallazgos-pendientes").stdout.count("/fase_1/h"), 0)
        self.assertEqual(biblioteca.leer_entrada(self.root, ref)["fallas"], [])

    def test_la_leccion_que_vuelve_a_fallar_llega_al_reporte(self):
        ref = self.ticket_que_escala()
        self.git("add", ".")
        self.git("commit", "-m", "ISR-1")

        # ISR-2: un solo intento, y el mismo error vuelve.
        t = "ISR-2"
        self.cli("open-ticket", "--ticket-id", t, "--nroticket", "2",
                 "--desarrollador", "OMAR RODRIGUEZ", "--fecha", "02-11-2026",
                 "--perfil", PERFIL)
        self.planner(t, max_reintentos=1)
        self.cli("open-fase", "--fase", "fase_1")
        self.ejecutor("otro.txt", "TODO: terminar\n")
        self.assertIn("escalado", self.cli("run-checks", codigo=1).stdout)
        self.assertEqual(self.fase(t)["estado"], "escalado")

        self.cli("record-hallazgos", "--archivo", self.reflector(t, reincide=ref))
        self.cli("resolver-hallazgo", "--id", f"{t}/fase_1/h1", "--decision", "ok")
        fallas = biblioteca.leer_entrada(self.root, ref)["fallas"]
        self.assertEqual([(f["ref"], f["tipo"]) for f in fallas],
                         [(f"{t}/fase_1/h1", "implementada")])
        self.assertIn("falló 1×", (self.root / ".claude" / "biblioteca" / "INDEX.md")
                      .read_text(encoding="utf-8"))

        datos = json.loads(self.cli("report", "--json").stdout)
        self.assertEqual(datos["ilegibles"], [])
        self.assertEqual(
            {k: datos["resumen"][k] for k in ("tickets", "fases", "fases_escaladas",
                                              "lecciones_aprobadas", "implementadas",
                                              "fallaron_implementadas")},
            {"tickets": 2, "fases": 2, "fases_escaladas": 2, "lecciones_aprobadas": 1,
             "implementadas": 1, "fallaron_implementadas": 1})
        self.assertEqual([e["ref"] for e in datos["fallaron_implementadas"]], [ref])
        self.assertEqual(datos["deuda"], {}, "la única lección ya está implementada")
        self.assertEqual(datos["fases"]["origen_de_fallos"],
                         {"check": 2, "esceptico": 1, "humano": 1})
        self.assertEqual(datos["fases"]["reglas_mas_violadas"], {"no_todo": 2})
        self.assertEqual((datos["hallazgos"]["aprobados_tal_cual"],
                          datos["hallazgos"]["reincidencias"]), (1, 1))
        self.assertIn(ref, self.cli("report").stdout)


if __name__ == "__main__":
    unittest.main()

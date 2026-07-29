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
        estado = state.leer_fase(self.root, "ISR-110722", "fase_1")
        self.assertEqual(estado["estado"], "escalado")


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

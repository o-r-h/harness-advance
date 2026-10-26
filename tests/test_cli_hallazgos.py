import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CLI = RAIZ / "harness" / "hooks" / "cli.py"
sys.path.insert(0, str(RAIZ / "harness" / "hooks"))
from lib import biblioteca, hallazgos, harness, state  # noqa: E402

REGLAS = {"perfil": "p", "audit_comments": {"requerido": True, "severidad": "error"}}
TICKET = "ISR-110722"


def _fase(identificador: str, depende: list[str]) -> dict:
    return {"id": identificador, "titulo": "t", "pasos": ["p"], "anclajes": [],
            "criterio_exito": "c", "checks_deterministas": ["audit_comments"],
            "prueba_manual": {"requerida": True},
            "herramientas_permitidas": ["edit"], "max_reintentos": 3,
            "depende_de": depende}


PLAN = {"ticket_id": TICKET, "perfil": "p",
        "fases": [_fase("fase_1", []), _fase("fase_2", ["fase_1"])]}


def _hallazgo(n: int, leccion: str = "Declarar la dependencia en el plan") -> dict:
    return {"senal": f"señal {n}", "leccion": leccion, "evidencia": "intento 2",
            "confianza": "alta", "dimension": "proceso", "componente": "skill"}


def correr(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(CLI), *args],
                          capture_output=True, text=True, encoding="utf-8")


class Base(unittest.TestCase):
    def preparar(self, cerrar: bool = True):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / ".claude").mkdir()
        harness.write_json(self.root / ".claude" / "rules.json", REGLAS)
        harness.write_json(harness.ticket_dir(self.root, TICKET) / "plan.json", PLAN)
        self.p = ["--project", str(self.root)]
        correr("open-ticket", *self.p, "--ticket-id", TICKET, "--nroticket", "110722",
               "--desarrollador", "OMAR RODRIGUEZ", "--fecha", "28-07-2026", "--perfil", "p")
        correr("open-fase", *self.p, "--fase", "fase_1")
        if cerrar:
            state.aprobar_fase(self.root, TICKET, "fase_1")

    def proponer(self, cantidad: int = 2, fase: str = "fase_1") -> subprocess.CompletedProcess:
        ruta = self.root / "propuesta.json"
        ruta.write_text(json.dumps({"fase_id": fase,
                                    "hallazgos": [_hallazgo(i + 1) for i in range(cantidad)]}),
                        encoding="utf-8")
        return correr("record-hallazgos", *self.p, "--archivo", str(ruta))

    def resolver(self, *args: str) -> subprocess.CompletedProcess:
        return correr("resolver-hallazgo", *self.p, *args)

    def guardados(self, fase: str = "fase_1") -> dict:
        return hallazgos.leer(self.root, TICKET, fase)


class TestRecordHallazgos(Base):
    def test_record_rechaza_fase_sin_cerrar(self):
        self.preparar(cerrar=False)
        resultado = self.proponer()
        self.assertEqual(resultado.returncode, 1)
        self.assertIn("aprobada", resultado.stderr)

    def test_record_asigna_ids_y_escribe_md(self):
        self.preparar()
        resultado = self.proponer(2)
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        items = self.guardados()["hallazgos"]
        self.assertEqual([h["id"] for h in items], ["h1", "h2"])
        self.assertTrue(all(h["estado"] == "propuesto" and h["origen"] == "reflector"
                            for h in items))
        self.assertTrue(hallazgos.ruta(self.root, TICKET, "fase_1")
                        .with_suffix(".md").is_file())

    def test_record_acepta_propuesta_vacia(self):
        self.preparar()
        resultado = self.proponer(0)
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertIn("Sin hallazgos", resultado.stdout)

    def test_record_acepta_fase_escalada(self):
        self.preparar(cerrar=False)
        state.set_estado(self.root, TICKET, "fase_1", "escalado")
        self.assertEqual(self.proponer().returncode, 0)

    def test_no_reescribe_hallazgos_ya_resueltos(self):
        self.preparar()
        self.proponer(2)
        self.resolver("--id", "h1", "--decision", "ok")
        resultado = self.proponer(3)
        self.assertEqual(resultado.returncode, 1)
        items = self.guardados()["hallazgos"]
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["estado"], "aprobado")


class TestRecordHallazgosRondaDeCorreccion(Base):
    def test_la_propuesta_no_puede_autoaprobarse(self):
        self.preparar()
        item = _hallazgo(1)
        item.update({"estado": "aprobado", "origen": "humano", "id": "h7"})
        ruta = self.root / "propuesta.json"
        ruta.write_text(json.dumps({"fase_id": "fase_1", "hallazgos": [item]}),
                        encoding="utf-8")
        resultado = correr("record-hallazgos", *self.p, "--archivo", str(ruta))
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        h = self.guardados()["hallazgos"][0]
        self.assertEqual((h["id"], h["origen"], h["estado"]), ("h1", "reflector", "propuesto"))
        pendientes = correr("hallazgos-pendientes", *self.p)
        self.assertIn("ISR-110722/fase_1/h1", pendientes.stdout)

    def test_hallazgo_humano_previo_no_bloquea_la_reflexion(self):
        self.preparar(cerrar=False)
        correr("hallazgo", *self.p, "--texto", "Lección del humano")
        state.aprobar_fase(self.root, TICKET, "fase_1")
        resultado = self.proponer(2)
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        items = self.guardados()["hallazgos"]
        self.assertEqual([(h["id"], h["estado"]) for h in items],
                         [("h1", "aprobado"), ("h2", "propuesto"), ("h3", "propuesto")])
        self.assertEqual(items[0]["origen"], "humano")

    def test_pendientes_salta_archivo_corrupto(self):
        self.preparar()
        self.proponer(1)
        corrupto = harness.fase_dir(self.root, TICKET, "fase_2") / "hallazgos.json"
        corrupto.parent.mkdir(parents=True, exist_ok=True)
        corrupto.write_text("{no es json", encoding="utf-8")
        resultado = correr("hallazgos-pendientes", *self.p)
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertIn("ISR-110722/fase_1/h1", resultado.stdout)
        self.assertIn("fase_2", resultado.stderr)


class TestResolverHallazgo(Base):
    def test_ok_aprueba_y_escribe_entrada(self):
        self.preparar()
        self.proponer()
        resultado = self.resolver("--id", "h1", "--decision", "ok")
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertEqual(self.guardados()["hallazgos"][0]["estado"], "aprobado")
        self.assertTrue((biblioteca.biblioteca_dir(self.root) / "entradas"
                         / "ISR-110722-fase_1-h1.md").is_file())

    def test_no_exige_motivo(self):
        self.preparar()
        self.proponer()
        sin = self.resolver("--id", "h1", "--decision", "no")
        self.assertEqual(sin.returncode, 1)
        con = self.resolver("--id", "h1", "--decision", "no", "--motivo", "ya lo cubre una regla")
        self.assertEqual(con.returncode, 0, con.stderr)
        self.assertTrue((biblioteca.biblioteca_dir(self.root) / "rechazados"
                         / "ISR-110722-fase_1-h1.md").is_file())

    def test_editar_conserva_leccion_original(self):
        self.preparar()
        self.proponer()
        resultado = self.resolver("--id", "h1", "--decision", "editar",
                                  "--texto", "Lección corregida por el humano")
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        h = self.guardados()["hallazgos"][0]
        self.assertEqual(h["leccion"], "Lección corregida por el humano")
        self.assertEqual(h["leccion_original"], "Declarar la dependencia en el plan")
        self.assertEqual(h["estado"], "aprobado")

    def test_resolver_dos_veces_falla(self):
        self.preparar()
        self.proponer()
        self.resolver("--id", "h1", "--decision", "ok")
        resultado = self.resolver("--id", "h1", "--decision", "no", "--motivo", "x")
        self.assertEqual(resultado.returncode, 1)
        self.assertIn("ya está 'aprobado'", resultado.stderr)

    def test_id_inexistente_lista_validos(self):
        self.preparar()
        self.proponer(1)
        resultado = self.resolver("--id", "h9", "--decision", "ok")
        self.assertEqual(resultado.returncode, 1)
        self.assertIn("h1", resultado.stderr)

    def test_resuelve_fase_anterior_con_flag_fase(self):
        self.preparar()
        self.proponer()
        correr("open-fase", *self.p, "--fase", "fase_2")
        resultado = self.resolver("--fase", "fase_1", "--id", "h1", "--decision", "ok")
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertEqual(self.guardados()["hallazgos"][0]["estado"], "aprobado")


class TestHallazgoHumano(Base):
    def test_hallazgo_humano_entra_aprobado(self):
        self.preparar(cerrar=False)
        resultado = correr("hallazgo", *self.p, "--texto", "Revisar el contrato antes de editar",
                           "--dimension", "dominio", "--componente", "agente")
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        h = self.guardados()["hallazgos"][0]
        self.assertEqual((h["origen"], h["estado"]), ("humano", "aprobado"))
        self.assertTrue((biblioteca.biblioteca_dir(self.root) / "entradas"
                         / "ISR-110722-fase_1-h1.md").is_file())

    def test_hallazgo_humano_sin_fase_activa_falla(self):
        self.preparar(cerrar=False)
        harness.write_current(self.root, TICKET, None)
        resultado = correr("hallazgo", *self.p, "--texto", "algo")
        self.assertEqual(resultado.returncode, 1)


class TestPendientesYBiblioteca(Base):
    def test_pendientes_lista_y_luego_vacio(self):
        self.preparar()
        self.proponer(1)
        antes = correr("hallazgos-pendientes", *self.p)
        self.assertEqual(antes.returncode, 0)
        self.assertIn("ISR-110722/fase_1/h1", antes.stdout)
        self.resolver("--id", "h1", "--decision", "ok")
        despues = correr("hallazgos-pendientes", *self.p)
        self.assertEqual(despues.returncode, 0)
        self.assertIn("Sin hallazgos pendientes.", despues.stdout)

    def test_reconstruir_biblioteca_regenera_el_indice(self):
        self.preparar()
        self.proponer(1)
        self.resolver("--id", "h1", "--decision", "ok")
        indice = biblioteca.biblioteca_dir(self.root) / "INDEX.md"
        indice.write_text("<<<<<<< basura\n", encoding="utf-8")
        resultado = correr("reconstruir-biblioteca", *self.p)
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        texto = indice.read_text(encoding="utf-8")
        self.assertNotIn("basura", texto)
        self.assertIn("entradas/ISR-110722-fase_1-h1.md", texto)

    def test_validate_conoce_el_contrato_hallazgos(self):
        self.preparar()
        self.proponer()
        resultado = correr("validate", *self.p, "--contrato", "hallazgos", "--archivo",
                           str(hallazgos.ruta(self.root, TICKET, "fase_1")))
        self.assertEqual(resultado.returncode, 0, resultado.stderr)


if __name__ == "__main__":
    unittest.main()

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parents[1]
CLI = RAIZ / "harness" / "hooks" / "cli.py"
sys.path.insert(0, str(RAIZ / "harness" / "hooks"))
import cli  # noqa: E402
from lib import biblioteca, contracts, hallazgos, harness, state  # noqa: E402

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

    def test_renumera_despues_del_id_mas_alto_aunque_se_reemplace(self):
        self.preparar()
        self.proponer(3)
        resultado = self.proponer(1)
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertEqual([h["id"] for h in self.guardados()["hallazgos"]], ["h4"])

    def test_el_mensaje_cuenta_solo_los_propuestos_nuevos(self):
        self.preparar(cerrar=False)
        correr("hallazgo", *self.p, "--texto", "Lección del humano")
        state.aprobar_fase(self.root, TICKET, "fase_1")
        resultado = self.proponer(2)
        self.assertIn("2 hallazgo(s) propuesto(s)", resultado.stdout)
        vacia = self.proponer(0)
        self.assertIn("Sin hallazgos", vacia.stdout)
        self.assertNotIn("1 hallazgo", vacia.stdout)

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


class TestRecordHallazgosDeFaseAnterior(Base):
    def proponer_en(self, ticket: str, fase: str, cantidad: int = 1,
                    fase_propuesta: str | None = None) -> subprocess.CompletedProcess:
        ruta = self.root / "propuesta.json"
        ruta.write_text(json.dumps({"fase_id": fase_propuesta or fase,
                                    "hallazgos": [_hallazgo(i + 1) for i in range(cantidad)]}),
                        encoding="utf-8")
        return correr("record-hallazgos", *self.p, "--archivo", str(ruta),
                      "--ticket", ticket, "--fase", fase)

    def test_registra_en_la_fase_indicada_aunque_no_sea_la_activa(self):
        self.preparar()
        correr("open-fase", *self.p, "--fase", "fase_2")
        resultado = self.proponer_en(TICKET, "fase_1", 2)
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertEqual([h["id"] for h in self.guardados()["hallazgos"]], ["h1", "h2"])
        self.assertIsNone(self.guardados("fase_2"))

    def test_la_fase_indicada_debe_estar_cerrada(self):
        self.preparar()
        correr("open-fase", *self.p, "--fase", "fase_2")
        resultado = self.proponer_en(TICKET, "fase_2")
        self.assertEqual(resultado.returncode, 1)
        self.assertIn("aprobada", resultado.stderr)

    def test_la_propuesta_debe_ser_de_la_fase_indicada(self):
        self.preparar()
        correr("open-fase", *self.p, "--fase", "fase_2")
        resultado = self.proponer_en(TICKET, "fase_1", fase_propuesta="fase_2")
        self.assertEqual(resultado.returncode, 1)
        self.assertIsNone(self.guardados())

    def test_ticket_y_fase_van_juntos(self):
        self.preparar()
        ruta = self.root / "propuesta.json"
        ruta.write_text(json.dumps({"fase_id": "fase_1", "hallazgos": []}), encoding="utf-8")
        for extra in (["--ticket", TICKET], ["--fase", "fase_1"]):
            with self.subTest(extra=extra):
                resultado = correr("record-hallazgos", *self.p, "--archivo", str(ruta), *extra)
                self.assertEqual(resultado.returncode, 1)
        self.assertIsNone(self.guardados())

    def test_fase_inexistente_falla(self):
        self.preparar()
        resultado = self.proponer_en(TICKET, "fase_9")
        self.assertEqual(resultado.returncode, 1)
        self.assertIn("HARNESS · ", resultado.stderr)


class TestHallazgosJsonMalFormado(Base):
    def romper(self):
        destino = hallazgos.ruta(self.root, TICKET, "fase_1")
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(json.dumps({"ticket_id": TICKET, "fase_id": "fase_1"}),
                           encoding="utf-8")

    def verificar_error_limpio(self, resultado: subprocess.CompletedProcess):
        self.assertEqual(resultado.returncode, 1)
        self.assertIn("HARNESS · ", resultado.stderr)
        self.assertNotIn("Traceback", resultado.stderr)

    def test_resolver_hallazgo(self):
        self.preparar()
        self.romper()
        self.verificar_error_limpio(self.resolver("--id", "h1", "--decision", "ok"))

    def test_hallazgo_humano(self):
        self.preparar(cerrar=False)
        self.romper()
        self.verificar_error_limpio(correr("hallazgo", *self.p, "--texto", "algo"))

    def test_record_hallazgos(self):
        self.preparar()
        self.romper()
        self.verificar_error_limpio(self.proponer(1))


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

    def test_resuelve_fase_anterior_con_ticket_y_fase(self):
        self.preparar()
        self.proponer()
        correr("open-fase", *self.p, "--fase", "fase_2")
        resultado = self.resolver("--ticket", TICKET, "--fase", "fase_1", "--id", "h1",
                                  "--decision", "ok")
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertEqual(self.guardados()["hallazgos"][0]["estado"], "aprobado")

    def test_resuelve_fase_anterior_con_referencia_completa(self):
        self.preparar()
        self.proponer()
        correr("open-fase", *self.p, "--fase", "fase_2")
        resultado = self.resolver("--id", f"{TICKET}/fase_1/h1", "--decision", "ok")
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertEqual(self.guardados()["hallazgos"][0]["estado"], "aprobado")


class TestResolverHallazgoEntreTickets(Base):
    OTRO = "ISR-2"

    def abrir_otro_ticket(self, cerrar: bool = True):
        plan = dict(PLAN, ticket_id=self.OTRO)
        harness.write_json(harness.ticket_dir(self.root, self.OTRO) / "plan.json", plan)
        correr("open-ticket", *self.p, "--ticket-id", self.OTRO, "--nroticket", "2",
               "--desarrollador", "OMAR RODRIGUEZ", "--fecha", "28-07-2026", "--perfil", "p")
        correr("open-fase", *self.p, "--fase", "fase_1")
        if cerrar:
            state.aprobar_fase(self.root, self.OTRO, "fase_1")

    def estado_h1(self, ticket: str) -> str:
        return hallazgos.leer(self.root, ticket, "fase_1")["hallazgos"][0]["estado"]

    def test_referencia_completa_aprueba_el_del_ticket_indicado(self):
        self.preparar()
        self.proponer(1)
        self.abrir_otro_ticket()
        self.assertEqual(self.proponer(1).returncode, 0)
        resultado = self.resolver("--id", f"{TICKET}/fase_1/h1", "--decision", "ok")
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertEqual(self.estado_h1(TICKET), "aprobado")
        self.assertEqual(self.estado_h1(self.OTRO), "propuesto")

    def test_la_referencia_completa_manda_sobre_ticket_y_fase(self):
        self.preparar()
        self.proponer(1)
        self.abrir_otro_ticket()
        self.proponer(1)
        resultado = self.resolver("--id", f"{TICKET}/fase_1/h1", "--ticket", self.OTRO,
                                  "--fase", "fase_1", "--decision", "ok")
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertEqual(self.estado_h1(TICKET), "aprobado")
        self.assertEqual(self.estado_h1(self.OTRO), "propuesto")

    def test_fase_sin_ticket_con_otro_ticket_abierto_falla(self):
        self.preparar()
        self.proponer(1)
        correr("open-ticket", *self.p, "--ticket-id", self.OTRO, "--nroticket", "2",
               "--desarrollador", "OMAR RODRIGUEZ", "--fecha", "28-07-2026", "--perfil", "p")
        resultado = self.resolver("--fase", "fase_1", "--id", "h1", "--decision", "ok")
        self.assertEqual(resultado.returncode, 1)
        self.assertIn("HARNESS · ", resultado.stderr)
        self.assertEqual(self.estado_h1(TICKET), "propuesto")

    def test_fase_sin_ticket_que_no_es_la_activa_falla(self):
        self.preparar()
        self.proponer(1)
        correr("open-fase", *self.p, "--fase", "fase_2")
        resultado = self.resolver("--fase", "fase_1", "--id", "h1", "--decision", "ok")
        self.assertEqual(resultado.returncode, 1)
        self.assertIn(f"{TICKET}/fase_1/h1", resultado.stderr)
        self.assertEqual(self.estado_h1(TICKET), "propuesto")

    def test_ticket_sin_fase_falla(self):
        self.preparar()
        self.proponer(1)
        resultado = self.resolver("--ticket", TICKET, "--id", "h1", "--decision", "ok")
        self.assertEqual(resultado.returncode, 1)
        self.assertEqual(self.estado_h1(TICKET), "propuesto")

    def test_fase_con_formato_invalido_falla(self):
        self.preparar()
        self.proponer(1)
        resultado = self.resolver("--ticket", TICKET, "--fase", "../fase_1", "--id", "h1",
                                  "--decision", "ok")
        self.assertEqual(resultado.returncode, 1)
        self.assertIn("fase_N", resultado.stderr)

    def test_referencia_mal_formada_falla(self):
        self.preparar()
        self.proponer(1)
        resultado = self.resolver("--id", f"{TICKET}/fase_1", "--decision", "ok")
        self.assertEqual(resultado.returncode, 1)
        self.assertIn("HARNESS · ", resultado.stderr)
        self.assertEqual(self.estado_h1(TICKET), "propuesto")

    def test_hallazgos_md_ofrece_la_referencia_completa(self):
        self.preparar()
        self.proponer(1)
        md = hallazgos.ruta(self.root, TICKET, "fase_1").with_suffix(".md")
        self.assertIn(f"/hallazgo-ok {TICKET}/fase_1/h1", md.read_text(encoding="utf-8"))


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


class TestReincidencia(Base):
    ORIGINAL = f"{TICKET}/fase_1/h1"
    NUEVA = f"{TICKET}/fase_2/h1"

    def setUp(self):
        self.preparar()
        self.proponer(1)
        self.resolver("--id", "h1", "--decision", "ok")
        correr("open-fase", *self.p, "--fase", "fase_2")
        state.aprobar_fase(self.root, TICKET, "fase_2")

    def proponer_reincide(self, ref: str | None, fase: str = "fase_2"):
        item = _hallazgo(1)
        if ref is not None:
            item["reincide"] = ref
        ruta = self.root / "propuesta2.json"
        ruta.write_text(json.dumps({"fase_id": fase, "hallazgos": [item]}), encoding="utf-8")
        return correr("record-hallazgos", *self.p, "--archivo", str(ruta))

    def entradas(self) -> int:
        return len(list((biblioteca.biblioteca_dir(self.root) / "entradas").glob("*.md")))

    def test_registra_el_campo_reincide(self):
        resultado = self.proponer_reincide(self.ORIGINAL)
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertEqual(self.guardados("fase_2")["hallazgos"][0]["reincide"], self.ORIGINAL)
        md = hallazgos.ruta(self.root, TICKET, "fase_2").with_suffix(".md")
        self.assertIn(f"reincide en {self.ORIGINAL}", md.read_text(encoding="utf-8"))

    def test_reincide_en_una_fusionada_dice_cual_usar(self):
        otra = f"{TICKET}/fase_1/h8"
        biblioteca.escribir_entrada(self.root, TICKET, "fase_1", {
            "id": "h8", "estado": "aprobado", "leccion": "la que queda"})
        biblioteca.fusionar(self.root, otra, [self.ORIGINAL], "fusionada", None, "03-11-2026")
        resultado = self.proponer_reincide(self.ORIGINAL)
        self.assertEqual(resultado.returncode, 1)
        self.assertIn(f"se retiró de la biblioteca (fusionada en {otra}): usa {otra}",
                      resultado.stderr)
        self.assertIsNone(self.guardados("fase_2"))

    def test_reincide_hacia_rechazada_o_inexistente(self):
        rechazada = f"{TICKET}/fase_1/h9"
        biblioteca.escribir_entrada(self.root, TICKET, "fase_1",
                                    {"id": "h9", "estado": "rechazado", "leccion": "x"})
        for ref in (rechazada, "ISR-9/fase_1/h1"):
            with self.subTest(ref=ref):
                resultado = self.proponer_reincide(ref)
                self.assertEqual(resultado.returncode, 1)
                self.assertIn("no es una lección aprobada", resultado.stderr)
                self.assertIsNone(self.guardados("fase_2"))

    def test_aprobar_reincidencia_no_crea_entrada(self):
        self.proponer_reincide(self.ORIGINAL)
        antes = self.entradas()
        resultado = self.resolver("--decision", "ok", "--id", self.NUEVA)
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertEqual(self.entradas(), antes)
        self.assertEqual(biblioteca.leer_entrada(self.root, self.ORIGINAL)["fallas"][0]["ref"],
                         self.NUEVA)
        self.assertIn(f"aprobado como reincidencia de {self.ORIGINAL}", resultado.stdout)

    def test_editar_reincidencia_guarda_la_leccion_corregida(self):
        self.proponer_reincide(self.ORIGINAL)
        resultado = self.resolver("--decision", "editar", "--id", self.NUEVA,
                                  "--texto", "Usar curl.exe")
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        falla = biblioteca.leer_entrada(self.root, self.ORIGINAL)["fallas"][0]
        self.assertEqual(falla["leccion"], "Usar curl.exe")

    def test_nueva_ignora_reincide(self):
        self.proponer_reincide(self.ORIGINAL)
        resultado = self.resolver("--decision", "ok", "--id", self.NUEVA, "--nueva")
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertTrue((biblioteca.biblioteca_dir(self.root) / "entradas"
                         / f"{TICKET}-fase_2-h1.md").is_file())
        self.assertNotIn("reincide", self.guardados("fase_2")["hallazgos"][0])
        self.assertEqual(biblioteca.leer_entrada(self.root, self.ORIGINAL)["fallas"], [])

    def test_reincide_manual_sin_marca_del_reflector(self):
        self.proponer_reincide(None)
        antes = self.entradas()
        resultado = self.resolver("--decision", "ok", "--id", self.NUEVA,
                                  "--reincide", self.ORIGINAL)
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertEqual(self.entradas(), antes)
        self.assertEqual(len(biblioteca.leer_entrada(self.root, self.ORIGINAL)["fallas"]), 1)

    def test_reincide_manual_hacia_inexistente_no_escribe(self):
        self.proponer_reincide(None)
        resultado = self.resolver("--decision", "ok", "--id", self.NUEVA,
                                  "--reincide", "ISR-9/fase_1/h1")
        self.assertEqual(resultado.returncode, 1)
        self.assertIn("no es una lección aprobada", resultado.stderr)
        self.assertIn("usa --nueva", resultado.stderr)
        self.assertEqual(self.guardados("fase_2")["hallazgos"][0]["estado"], "propuesto")

    def test_opciones_incompatibles(self):
        self.proponer_reincide(None)
        casos = (("--decision", "ok", "--nueva", "--reincide", self.ORIGINAL),
                 ("--decision", "no", "--motivo", "m", "--nueva"),
                 ("--decision", "no", "--motivo", "m", "--reincide", self.ORIGINAL))
        for caso in casos:
            with self.subTest(caso=caso):
                resultado = self.resolver("--id", self.NUEVA, *caso)
                self.assertEqual(resultado.returncode, 1)
                self.assertEqual(self.guardados("fase_2")["hallazgos"][0]["estado"],
                                 "propuesto")

    def test_toda_aprobacion_lleva_fecha(self):
        self.proponer_reincide(None)
        self.resolver("--decision", "ok", "--id", self.NUEVA)
        entrada = biblioteca.leer_entrada(self.root, self.NUEVA)
        self.assertRegex(entrada["aprobada"], contracts.RE_FECHA)
        correr("hallazgo", *self.p, "--texto", "t")
        humano = biblioteca.leer_entrada(self.root, f"{TICKET}/fase_2/h2")
        self.assertRegex(humano["aprobada"], contracts.RE_FECHA)


class TestHallazgoHecho(Base):
    REF = f"{TICKET}/fase_1/h1"

    def setUp(self):
        self.preparar()
        self.proponer(1)
        self.resolver("--id", "h1", "--decision", "ok")

    def hecho(self, *args: str) -> subprocess.CompletedProcess:
        return correr("hallazgo-hecho", *self.p, *args)

    def test_marca_la_leccion(self):
        resultado = self.hecho("--id", self.REF, "--nota", "commit abc123")
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertIn(f"Lección {self.REF} implementada: ", resultado.stdout)
        self.assertTrue(biblioteca.leer_entrada(self.root, self.REF)["implementada"]
                        .endswith("· commit abc123"))
        indice = (biblioteca.biblioteca_dir(self.root) / "INDEX.md").read_text(encoding="utf-8")
        self.assertIn("(implementada ", indice)

    def test_hallazgo_hecho_sobre_una_retirada_dice_por_que(self):
        biblioteca.retirar(self.root, self.REF, "obsoleta desde ISR-9", "03-11-2026")
        resultado = self.hecho("--id", self.REF, "--nota", "commit abc123")
        self.assertEqual(resultado.returncode, 1)
        self.assertIn("se retiró de la biblioteca (obsoleta desde ISR-9)", resultado.stderr)

    def test_reemplaza_y_avisa(self):
        self.hecho("--id", self.REF, "--nota", "commit abc123")
        resultado = self.hecho("--id", self.REF, "--nota", "commit def456")
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertIn("Reemplaza la marca anterior:", resultado.stdout)

    def test_exige_nota_no_vacia(self):
        resultado = self.hecho("--id", self.REF, "--nota", "  ")
        self.assertEqual(resultado.returncode, 1)
        self.assertEqual(biblioteca.leer_entrada(self.root, self.REF)["implementada"], "")

    def test_rechaza_ref_suelta_o_no_aprobada(self):
        biblioteca.escribir_entrada(self.root, TICKET, "fase_1",
                                    {"id": "h9", "estado": "rechazado", "leccion": "x"})
        ruta = biblioteca.entrada_path(self.root, self.REF)
        antes = ruta.read_bytes()
        for ref in ("h1", f"{TICKET}/fase_1/h9", r"..\..\x/fase_1/h1"):
            with self.subTest(ref=ref):
                resultado = self.hecho("--id", ref, "--nota", "commit abc123")
                self.assertEqual(resultado.returncode, 1)
        self.assertEqual(ruta.read_bytes(), antes)


class TestOrdenYErroresDeEscritura(Base):
    REF = f"{TICKET}/fase_1/h1"

    def en_proceso(self, *args: str) -> tuple[int, str]:
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            codigo = cli.main([*args, *self.p])
        return codigo, err.getvalue()

    def reincidencia_pendiente(self):
        self.preparar()
        self.proponer(1)
        self.resolver("--id", "h1", "--decision", "ok")
        correr("open-fase", *self.p, "--fase", "fase_2")
        state.aprobar_fase(self.root, TICKET, "fase_2")
        ruta = self.root / "propuesta2.json"
        item = _hallazgo(1)
        item["reincide"] = self.REF
        ruta.write_text(json.dumps({"fase_id": "fase_2", "hallazgos": [item]}),
                        encoding="utf-8")
        correr("record-hallazgos", *self.p, "--archivo", str(ruta))

    def test_falla_la_biblioteca_y_el_hallazgo_sigue_propuesto(self):
        self.reincidencia_pendiente()
        with mock.patch.object(biblioteca, "registrar_falla", side_effect=OSError("disco")):
            codigo, err = self.en_proceso("resolver-hallazgo", "--id", f"{TICKET}/fase_2/h1",
                                          "--decision", "ok")
        self.assertEqual(codigo, 1)
        self.assertIn("HARNESS · OSError", err)
        self.assertEqual(self.guardados("fase_2")["hallazgos"][0]["estado"], "propuesto")

    def test_falla_la_entrada_nueva_y_el_hallazgo_sigue_propuesto(self):
        self.preparar()
        self.proponer(1)
        with mock.patch.object(biblioteca, "escribir_entrada", side_effect=OSError("disco")):
            codigo, _ = self.en_proceso("resolver-hallazgo", "--id", "h1", "--decision", "ok")
        self.assertEqual(codigo, 1)
        self.assertEqual(self.guardados()["hallazgos"][0]["estado"], "propuesto")

    def test_entrada_en_cp1252_da_error_del_harness(self):
        self.reincidencia_pendiente()
        biblioteca.entrada_path(self.root, self.REF).write_bytes(b"# x\n- **se\xf1al**: x\n")
        propuesta = self.root / "propuesta3.json"
        propuesta.write_text(json.dumps({"fase_id": "fase_2", "hallazgos": []}),
                             encoding="utf-8")
        casos = (("hallazgo-hecho", "--id", self.REF, "--nota", "n"),
                 ("resolver-hallazgo", "--id", f"{TICKET}/fase_2/h1", "--decision", "ok"),
                 ("record-hallazgos", "--archivo", str(propuesta)))
        # record-hallazgos solo lee la biblioteca si la propuesta trae reincidencias.
        datos = json.loads(propuesta.read_text(encoding="utf-8"))
        datos["hallazgos"] = [dict(_hallazgo(1), reincide=self.REF)]
        propuesta.write_text(json.dumps(datos), encoding="utf-8")
        for caso in casos:
            with self.subTest(caso=caso):
                codigo, err = self.en_proceso(*caso)
                self.assertEqual(codigo, 1)
                self.assertIn("HARNESS · UnicodeDecodeError", err)

    def test_editar_con_texto_vacio_es_error(self):
        self.preparar()
        self.proponer(1)
        for texto in ("", "   "):
            with self.subTest(texto=texto):
                codigo, err = self.en_proceso("resolver-hallazgo", "--id", "h1",
                                              "--decision", "editar", "--texto", texto)
                self.assertEqual(codigo, 1)
                self.assertIn("exige --texto", err)
                self.assertEqual(self.guardados()["hallazgos"][0]["estado"], "propuesto")


if __name__ == "__main__":
    unittest.main()

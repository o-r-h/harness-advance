import json
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "harness" / "hooks"))
from lib import biblioteca, harness  # noqa: E402
import report  # noqa: E402

REF_A = "ISR-1/fase_1/h1"
REF_B = "ISR-1/fase_1/h2"
REF_C = "ISR-1/fase_1/h3"
REF_H0 = "ISR-1/fase_1/h0"


def _aprobado(id, **extra):
    base = {"id": id, "origen": "reflector", "estado": "aprobado",
            "senal": f"señal {id}", "leccion": f"lección {id}", "evidencia": "e",
            "confianza": "media", "dimension": "proceso", "componente": "check"}
    base.update(extra)
    return base


def _fase_state(fase_id, estado, intento, maximo, fallos):
    return {"fase_id": fase_id, "estado": estado, "intento_actual": intento,
            "max_reintentos": maximo,
            "historial_fallos": [{"intento": i + 1, "origen": o, "razon": r,
                                  "correccion_aplicada": ""}
                                 for i, (o, r) in enumerate(fallos)]}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def _sembrar(self):
        r = self.root
        f1 = harness.fase_dir(r, "ISR-1", "fase_1")
        harness.write_json(f1 / "fase_state.json", _fase_state(
            "fase_1", "aprobada", 2, 3, [("check", "designer_x violada")]))
        harness.write_json(harness.intento_dir(r, "ISR-1", "fase_1", 1) / "checks.json", {
            "fase_id": "fase_1", "intento": 1, "resultado": "fallo",
            "checks": [{"id": "designer_x", "resultado": "fallo", "severidad": "error",
                        "detalle": "d"},
                       {"id": "otro", "resultado": "ok"}]})
        harness.write_json(harness.fase_dir(r, "ISR-1", "fase_2") / "fase_state.json",
                           _fase_state("fase_2", "aprobada", 2, 3,
                                       [("esceptico", "un solo rechazo")]))
        f2 = harness.fase_dir(r, "ISR-2", "fase_1")
        harness.write_json(f2 / "fase_state.json", _fase_state(
            "fase_1", "escalado", 3, 3,
            [("esceptico", "falta evidencia"), ("esceptico", "anclaje roto"),
             ("humano", "no abre")]))

        harness.write_json(f1 / "hallazgos.json", {
            "ticket_id": "ISR-1", "fase_id": "fase_1", "hallazgos": [
                _aprobado("h1", estado="propuesto"),
                _aprobado("h2"),
                _aprobado("h3", leccion_original="original"),
                _aprobado("h4", reincide="ISR-0/fase_1/h1"),
                _aprobado("h5", estado="rechazado", motivo="ya existe"),
                _aprobado("h7", leccion_original="orig", reincide="ISR-0/fase_1/h1"),
                {"id": "h6", "origen": "humano", "estado": "aprobado", "leccion": "mía"},
            ]})

        biblioteca.escribir_entrada(r, "ISR-1", "fase_1", _aprobado("h0"), "01-11-2026")
        biblioteca.escribir_entrada(r, "ISR-1", "fase_1", _aprobado("h1"), "01-11-2026")
        biblioteca.escribir_entrada(r, "ISR-1", "fase_1", _aprobado("h2"), "01-11-2026")
        biblioteca.escribir_entrada(
            r, "ISR-1", "fase_1",
            {"id": "h3", "origen": "humano", "estado": "aprobado", "leccion": "regla mía"},
            "01-11-2026")
        biblioteca.marcar_implementada(r, REF_A, "check designer_x", "02-11-2026")
        biblioteca.registrar_falla(r, REF_A, "ISR-2/fase_1/h1", "volvió", "03-11-2026")
        biblioteca.registrar_falla(r, REF_B, "ISR-2/fase_1/h2", "otra vez", "03-11-2026")
        biblioteca.registrar_falla(r, REF_B, "ISR-3/fase_1/h1", "y otra", "04-11-2026")


class TestAgregar(Base):
    def setUp(self):
        super().setUp()
        self._sembrar()
        self.datos = report.agregar(self.root)

    def test_resumen(self):
        self.assertEqual(self.datos["resumen"], {
            "tickets": 2, "fases": 3, "fases_escaladas": 1, "lecciones_aprobadas": 4,
            "implementadas": 1, "fallaron_implementadas": 1, "volvieron_sin_pieza": 1})

    def test_fallaron_implementadas(self):
        lista = self.datos["fallaron_implementadas"]
        self.assertEqual([e["ref"] for e in lista], [REF_A])
        self.assertEqual(len(lista[0]["fallas"]), 1)
        self.assertEqual(lista[0]["componente"], "check")

    def test_deuda_agrupa_y_ordena(self):
        deuda = self.datos["deuda"]
        self.assertEqual(deuda["check"][0]["ref"], REF_B)
        self.assertEqual(len(deuda["check"][0]["fallas"]), 2)
        # Más fallas primero; sin fallas, por ref (h0 sortea antes que h2).
        self.assertEqual([e["ref"] for e in deuda["check"]], [REF_B, REF_H0])
        self.assertEqual([e["ref"] for e in deuda["sin pieza"]], [REF_C])
        self.assertEqual(deuda["sin pieza"][0]["senal"], "regla mía")
        self.assertNotIn(REF_A, [e["ref"] for g in deuda.values() for e in g])

    def test_salud_de_hallazgos(self):
        h = self.datos["hallazgos"]
        self.assertEqual((h["aprobados_tal_cual"], h["aprobados_editados"],
                          h["reincidencias"], h["del_humano"]), (1, 1, 2, 1))
        self.assertEqual(h["rechazados"], [{"ref": "ISR-1/fase_1/h5", "motivo": "ya existe"}])
        self.assertEqual(len(h["propuestos"]), 1)

    def test_fases(self):
        f = self.datos["fases"]
        self.assertEqual(f["escaladas"], ["ISR-2/fase_1"])
        self.assertEqual(f["origen_de_fallos"], {"check": 1, "esceptico": 3, "humano": 1})
        self.assertEqual(f["reglas_mas_violadas"], {"designer_x": 1})
        self.assertEqual(f["intentos_por_fase"]["ISR-1/fase_1"],
                         {"intentos": 2, "max": 3, "estado": "aprobada"})
        rep = f["rechazos_repetidos_del_esceptico"]
        self.assertEqual(len(rep), 1)  # ISR-1/fase_2 con un solo rechazo no entra
        self.assertEqual((rep[0]["fase"], rep[0]["veces"]), ("ISR-2/fase_1", 2))
        self.assertEqual(rep[0]["razones"], ["falta evidencia", "anclaje roto"])

    def test_serializable_y_sin_ilegibles(self):
        json.dumps(self.datos)
        self.assertEqual(self.datos["ilegibles"], [])

    def test_no_escribe_nada(self):
        def foto():
            return {str(p): (p.stat().st_size, p.stat().st_mtime_ns)
                    for p in self.root.rglob("*") if p.is_file()}
        antes = foto()
        report.agregar(self.root)
        self.assertEqual(foto(), antes)


class TestCasosLimite(Base):
    def test_proyecto_vacio(self):
        datos = report.agregar(self.root)
        self.assertEqual(datos["resumen"], {k: 0 for k in datos["resumen"]})
        self.assertEqual(datos["fallaron_implementadas"], [])
        self.assertEqual(datos["deuda"], {})
        self.assertEqual(datos["hallazgos"], {
            "propuestos": [], "aprobados_tal_cual": 0, "aprobados_editados": 0,
            "reincidencias": 0, "del_humano": 0, "rechazados": []})
        self.assertEqual(datos["fases"]["escaladas"], [])
        self.assertEqual(datos["fases"]["intentos_por_fase"], {})
        self.assertEqual(datos["ilegibles"], [])

    def test_datos_rotos_no_detienen(self):
        self._sembrar()
        r = self.root
        t3 = harness.ticket_dir(r, "ISR-3")
        for f in ("fase_1", "fase_2", "fase_3"):
            (t3 / f).mkdir(parents=True)
        (t3 / "fase_1" / "fase_state.json").write_text("{no es json", encoding="utf-8")
        (t3 / "fase_2" / "fase_state.json").write_bytes(b"\xe9")
        (t3 / "fase_3" / "fase_state.json").write_text("{}", encoding="utf-8")
        harness.write_json(t3 / "fase_1" / "hallazgos.json", {"hallazgos": "no"})
        harness.write_json(t3 / "fase_1" / "intento_1" / "checks.json", [])
        datos = report.agregar(r)
        base = ".harness/tickets/ISR-3"
        self.assertEqual(datos["ilegibles"], sorted([
            f"{base}/fase_1/fase_state.json", f"{base}/fase_2/fase_state.json",
            f"{base}/fase_3/fase_state.json", f"{base}/fase_1/hallazgos.json",
            f"{base}/fase_1/intento_1/checks.json"]))
        self.assertEqual(datos["resumen"]["fases"], 3)
        self.assertEqual(datos["resumen"]["tickets"], 3)
        self.assertEqual(datos["resumen"]["lecciones_aprobadas"], 4)

    def test_copia_de_entrada_no_cuenta_dos_veces(self):
        self._sembrar()
        origen = biblioteca.entrada_path(self.root, REF_A)
        copia = origen.parent / "copia.md"
        copia.write_bytes(origen.read_bytes())
        datos = report.agregar(self.root)
        self.assertEqual(datos["ilegibles"], [".claude/biblioteca/entradas/copia.md"])
        self.assertEqual(datos["resumen"]["lecciones_aprobadas"], 4)

    def test_carpeta_que_no_se_puede_recorrer(self):
        self._sembrar()
        tickets = harness.tickets_dir(self.root)
        original = Path.glob

        def glob(self_, patron):
            if self_ == tickets:
                raise PermissionError("denegado")
            return original(self_, patron)

        with mock.patch.object(Path, "glob", glob):
            datos = report.agregar(self.root)
        self.assertEqual(datos["ilegibles"], [".harness/tickets"])
        self.assertEqual(datos["resumen"]["lecciones_aprobadas"], 4)

    def test_entrada_ilegible_se_nombra(self):
        self._sembrar()
        mala = biblioteca.entrada_path(self.root, "ISR-9/fase_1/h1")
        mala.write_bytes(b"# ISR-9/fase_1/h1\n- **se\xf1al**: x\n")
        sin_ref = biblioteca.biblioteca_dir(self.root) / "entradas" / "suelta.md"
        sin_ref.write_text("sin encabezado\n", encoding="utf-8")
        datos = report.agregar(self.root)
        self.assertEqual(datos["ilegibles"], [
            ".claude/biblioteca/entradas/ISR-9-fase_1-h1.md",
            ".claude/biblioteca/entradas/suelta.md"])
        self.assertEqual(datos["resumen"]["lecciones_aprobadas"], 4)


class TestRender(Base):
    def test_secciones_en_orden(self):
        self._sembrar()
        texto = report.render(report.agregar(self.root))
        encabezados = ["HARNESS · reporte", "Resumen", "Fallaron estando implementadas",
                       "Deuda", "Hallazgos", "Fases"]
        lineas = texto.splitlines()
        indices = [lineas.index(e) for e in encabezados]
        self.assertEqual(indices, sorted(indices))

    def test_deuda_dice_cuanto_costo(self):
        self._sembrar()
        texto = report.render(report.agregar(self.root))
        linea = next(l for l in texto.splitlines() if REF_B in l)
        self.assertIn("costó otra vez 2×", linea)

    def test_falla_muestra_lo_que_debio_hacer(self):
        self._sembrar()
        self.assertIn("volvió", report.render(report.agregar(self.root)))

    def test_secciones_vacias(self):
        texto = report.render(report.agregar(self.root))
        self.assertGreaterEqual(texto.count("Sin datos todavía."), 4)
        self.assertNotIn("Archivos que no se pudieron leer", texto)

    def test_ilegibles_aparecen(self):
        self._sembrar()
        (biblioteca.biblioteca_dir(self.root) / "entradas" / "suelta.md").write_text(
            "sin encabezado\n", encoding="utf-8")
        texto = report.render(report.agregar(self.root))
        self.assertIn("Archivos que no se pudieron leer", texto)
        self.assertIn("suelta.md", texto)


class TestCli(Base):
    def _correr(self, *extra):
        return subprocess.run(
            [sys.executable, str(RAIZ / "harness" / "hooks" / "cli.py"), "report",
             "--project", str(self.root), *extra],
            capture_output=True, encoding="utf-8")

    def test_cli_report_texto_y_json(self):
        self._sembrar()
        r = self._correr()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Resumen", r.stdout)
        self.assertIn("costó otra vez 2×", r.stdout)
        r = self._correr("--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["resumen"]["tickets"], 2)

    def test_cli_report_proyecto_vacio(self):
        r = self._correr()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Sin datos todavía.", r.stdout)


if __name__ == "__main__":
    unittest.main()

import json
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "harness" / "hooks"))
from lib import biblioteca, harness  # noqa: E402
import report  # noqa: E402

REF_A = "ISR-1/fase_1/h1"
REF_B = "ISR-1/fase_1/h2"
REF_C = "ISR-1/fase_1/h3"


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
                {"id": "h6", "origen": "humano", "estado": "aprobado", "leccion": "mía"},
            ]})

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
            "tickets": 2, "fases": 2, "fases_escaladas": 1, "lecciones_aprobadas": 3,
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
        self.assertEqual([e["ref"] for e in deuda["sin pieza"]], [REF_C])
        self.assertEqual(deuda["sin pieza"][0]["senal"], "regla mía")
        self.assertNotIn(REF_A, [e["ref"] for g in deuda.values() for e in g])

    def test_salud_de_hallazgos(self):
        h = self.datos["hallazgos"]
        self.assertEqual((h["aprobados_tal_cual"], h["aprobados_editados"],
                          h["reincidencias"], h["del_humano"]), (1, 1, 1, 1))
        self.assertEqual(h["rechazados"], [{"ref": "ISR-1/fase_1/h5", "motivo": "ya existe"}])
        self.assertEqual(len(h["propuestos"]), 1)

    def test_fases(self):
        f = self.datos["fases"]
        self.assertEqual(f["escaladas"], ["ISR-2/fase_1"])
        self.assertEqual(f["origen_de_fallos"], {"check": 1, "esceptico": 2, "humano": 1})
        self.assertEqual(f["reglas_mas_violadas"], {"designer_x": 1})
        self.assertEqual(f["intentos_por_fase"]["ISR-1/fase_1"],
                         {"intentos": 2, "max": 3, "estado": "aprobada"})
        rep = f["rechazos_repetidos_del_esceptico"]
        self.assertEqual(len(rep), 1)
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
        self.assertEqual(datos["resumen"]["fases"], 2)
        self.assertEqual(datos["resumen"]["tickets"], 3)
        self.assertEqual(datos["resumen"]["lecciones_aprobadas"], 3)

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
        self.assertEqual(datos["resumen"]["lecciones_aprobadas"], 3)


if __name__ == "__main__":
    unittest.main()

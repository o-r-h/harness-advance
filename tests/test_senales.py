"""Señales deterministas de la biblioteca: usos, último uso y rutas ausentes."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CLI = RAIZ / "harness" / "hooks" / "cli.py"
sys.path.insert(0, str(RAIZ / "harness" / "hooks"))
from lib import biblioteca, harness, senales  # noqa: E402

REF_A = "ISR-1/fase_1/h1"
REF_B = "ISR-1/fase_1/h2"


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


def _entrada(raiz: Path, id: str, leccion: str = "", senal: str = "", evidencia: str = "e"):
    biblioteca.escribir_entrada(raiz, "ISR-1", "fase_1", {
        "id": id, "origen": "reflector", "estado": "aprobado",
        "senal": senal or f"señal {id}", "leccion": leccion or f"lección {id}",
        "evidencia": evidencia, "confianza": "media", "dimension": "proceso",
        "componente": "check"}, fecha="01-11-2026")


def _plan(raiz: Path, ticket: str, fecha: str | None, refs_por_fase: list[list[str]]):
    destino = harness.ticket_dir(raiz, ticket)
    fases = [{"id": f"fase_{i}", "anclajes": [
        {"ref": f".claude/biblioteca/entradas/{r.replace('/', '-')}.md",
         "confianza": "por_confirmar"} for r in refs]}
        for i, refs in enumerate(refs_por_fase, start=1)]
    harness.write_json(destino / "plan.json", {"ticket_id": ticket, "fases": fases})
    if fecha:
        harness.write_json(destino / "ticket_context.json", {"ticket_id": ticket, "fecha": fecha})


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name)
        _git(self.raiz, "init")
        _git(self.raiz, "config", "user.email", "t@t.t")
        _git(self.raiz, "config", "user.name", "t")
        for ruta in ("AzzuleSite/Assets/components/global/x.vue",
                     "AzzuleSite/Assets/src/scss/base.scss", "archivo.vue"):
            (self.raiz / ruta).parent.mkdir(parents=True, exist_ok=True)
            (self.raiz / ruta).write_text("x\n", encoding="utf-8")
        _git(self.raiz, "add", ".")
        _git(self.raiz, "commit", "-m", "base")

    def leccion(self, ref: str) -> dict:
        return next(l for l in senales.senales(self.raiz)["lecciones"] if l["ref"] == ref)

    def ausentes(self, leccion: str, **extra) -> list[str] | None:
        _entrada(self.raiz, "h1", leccion=leccion, **extra)
        return self.leccion(REF_A)["rutas_ausentes"]


class TestUsos(Base):
    def test_cuenta_los_planes_que_la_anclan(self):
        _entrada(self.raiz, "h1")
        _entrada(self.raiz, "h2")
        _plan(self.raiz, "ISR-10", "01-10-2026", [[REF_A], [REF_A]])
        _plan(self.raiz, "ISR-11", "02-10-2026", [[REF_A, REF_B]])
        self.assertEqual(self.leccion(REF_A)["usos"], 2)
        self.assertEqual(self.leccion(REF_B)["usos"], 1)

    def test_ultimo_uso_es_el_ticket_mas_reciente_por_fecha(self):
        _entrada(self.raiz, "h1")
        _plan(self.raiz, "ISR-99", "01-01-2026", [[REF_A]])
        _plan(self.raiz, "ISR-10", "15-10-2026", [[REF_A]])
        self.assertEqual(self.leccion(REF_A)["ultimo_uso"], "ISR-10")

    def test_sin_fecha_el_ultimo_uso_es_el_mayor_por_nombre(self):
        _entrada(self.raiz, "h1")
        _plan(self.raiz, "ISR-10", None, [[REF_A]])
        _plan(self.raiz, "ISR-11", None, [[REF_A]])
        self.assertEqual(self.leccion(REF_A)["ultimo_uso"], "ISR-11")

    def test_un_ancla_a_una_absorbida_cuenta_para_el_destino(self):
        _entrada(self.raiz, "h1")
        _entrada(self.raiz, "h2")
        _plan(self.raiz, "ISR-10", "01-10-2026", [[REF_B]])
        biblioteca.fusionar(self.raiz, REF_A, [REF_B], "fusionada", None, "03-11-2026")
        self.assertEqual(self.leccion(REF_A)["usos"], 1)
        self.assertEqual(self.leccion(REF_A)["ultimo_uso"], "ISR-10")

    def test_trae_fallas_implementada_y_senal(self):
        _entrada(self.raiz, "h1")
        biblioteca.registrar_falla(self.raiz, REF_A, "ISR-2/fase_1/h1", "x", "02-11-2026")
        leccion = self.leccion(REF_A)
        self.assertEqual((leccion["fallas"], leccion["implementada"], leccion["senal"]),
                         (1, False, "señal h1"))
        self.assertEqual(leccion["archivo"], "entradas/ISR-1-fase_1-h1.md")


class TestRutasAusentes(Base):
    def test_ruta_que_coincide_por_sufijo_no_es_ausente(self):
        self.assertEqual(self.ausentes("usa `components/global/x.vue` así"), [])

    def test_mayusculas_no_importan(self):
        self.assertEqual(self.ausentes("usa Components/Global/X.vue"), [])

    def test_carpeta_rastreada_cuenta(self):
        self.assertEqual(self.ausentes("el CSS de src/scss manda"), [])

    def test_ruta_inexistente_es_ausente(self):
        self.assertEqual(self.ausentes("usa `components/global/borrado.vue`"),
                         ["components/global/borrado.vue"])

    def test_en_la_senal_tambien_cuenta(self):
        self.assertEqual(self.ausentes("nada", senal="toca src/viejo/a.js"), ["src/viejo/a.js"])

    def test_no_toma_como_ruta_lo_que_no_lo_es(self):
        texto = ("global.api, §4.1, un par [B]/[E], y/o, ok/no, https://x.y/zzz/aaa.js, "
                 "('archivo.vue:31-47') y lo de TICKET/fase_N/hN")
        self.assertEqual(self.ausentes(texto), [])

    def test_una_ruta_relativa_con_puntos_se_compara_sin_ellos(self):
        # Caso real de NAS: "import ... from '../../global/modal.vue'".
        self.assertEqual(self.ausentes("importa '../../global/x.vue' y ./src/scss"), [])

    def test_el_numero_de_linea_no_es_parte_de_la_ruta(self):
        self.assertEqual(self.ausentes("como components/global/x.vue:31-47 dice"), [])

    def test_la_evidencia_no_cuenta(self):
        self.assertEqual(self.ausentes("nada", evidencia="ver intento_1/veredicto.json"), [])

    def test_sin_git_rutas_desconocidas_y_sin_harness_cero_usos(self):
        sin_git = tempfile.TemporaryDirectory()
        self.addCleanup(sin_git.cleanup)
        raiz = Path(sin_git.name)
        _entrada(raiz, "h1", leccion="usa `src/a/b.js`")
        leccion = senales.senales(raiz)["lecciones"][0]
        self.assertIsNone(leccion["rutas_ausentes"])
        self.assertEqual((leccion["usos"], leccion["ultimo_uso"]), (0, None))


class TestUltimaCuracionYCli(Base):
    def test_ultima_curacion_sale_de_curacion_json(self):
        _entrada(self.raiz, "h1")
        self.assertIsNone(senales.senales(self.raiz)["ultima_curacion"])
        harness.write_json(harness.harness_dir(self.raiz) / "curacion.json", {"acciones": [
            {"id": "c1", "estado": "aprobado", "fecha_resuelta": "02-11-2026"},
            {"id": "c2", "estado": "rechazado", "fecha_resuelta": "10-10-2026"},
            {"id": "c3", "estado": "propuesto"}]})
        self.assertEqual(senales.senales(self.raiz)["ultima_curacion"], "02-11-2026")

    def test_curacion_json_ilegible_no_revienta(self):
        _entrada(self.raiz, "h1")
        (harness.harness_dir(self.raiz)).mkdir(exist_ok=True)
        (harness.harness_dir(self.raiz) / "curacion.json").write_text("{", encoding="utf-8")
        self.assertIsNone(senales.senales(self.raiz)["ultima_curacion"])

    def test_cli_senales_json_y_texto(self):
        _entrada(self.raiz, "h1", leccion="usa src/viejo/a.js")
        _plan(self.raiz, "ISR-10", "01-10-2026", [[REF_A]])
        (self.raiz / ".claude" / "rules.json").write_text("{}", encoding="utf-8")
        salida = subprocess.run([sys.executable, str(CLI), "senales-biblioteca", "--project",
                                 str(self.raiz), "--json"], capture_output=True, text=True,
                                encoding="utf-8")
        self.assertEqual(salida.returncode, 0, salida.stderr)
        self.assertEqual(json.loads(salida.stdout)["lecciones"][0]["usos"], 1)
        texto = subprocess.run([sys.executable, str(CLI), "senales-biblioteca", "--project",
                                str(self.raiz)], capture_output=True, text=True,
                               encoding="utf-8").stdout
        self.assertIn(f"{REF_A} — usos 1 (último ISR-10) — rutas ausentes: src/viejo/a.js",
                      texto)


if __name__ == "__main__":
    unittest.main()

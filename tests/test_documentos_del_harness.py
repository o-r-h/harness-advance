import re
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def leer(*partes: str) -> str:
    return (RAIZ.joinpath(*partes)).read_text(encoding="utf-8")


def frontmatter(texto: str) -> dict:
    bloque = re.match(r"^---\n(.*?)\n---\n", texto, re.DOTALL)
    if not bloque:
        return {}
    campos = {}
    for linea in bloque.group(1).splitlines():
        if re.match(r"^\w+:", linea):
            clave, _, valor = linea.partition(":")
            campos[clave.strip()] = valor.strip()
    return campos


class TestSkillOrquestadora(unittest.TestCase):
    def setUp(self):
        self.texto = leer("harness", "skills", "ticket-loop", "SKILL.md")

    def test_tiene_frontmatter_con_nombre_y_descripcion(self):
        campos = frontmatter(self.texto)
        self.assertEqual(campos.get("name"), "ticket-loop")
        self.assertIn("description", campos)

    def test_menciona_todos_los_subcomandos_del_ciclo(self):
        for comando in ("open-ticket", "open-fase", "run-checks", "record-veredicto",
                        "generar-prueba", "validate"):
            with self.subTest(comando=comando):
                self.assertIn(comando, self.texto)

    def test_deja_claro_que_el_esceptico_va_aislado(self):
        self.assertIn("contexto aislado", self.texto)

    def test_deja_claro_que_el_ciclo_se_detiene_en_el_gate_humano(self):
        self.assertIn("/fase-ok", self.texto)
        self.assertIn("/fase-fallo", self.texto)


class TestAgenteDelPerfil(unittest.TestCase):
    def setUp(self):
        self.texto = leer("profiles", "reviewsystemgfs", "agents", "agent-rsgfs.md")

    def test_tiene_frontmatter_con_el_nombre_esperado(self):
        self.assertEqual(frontmatter(self.texto).get("name"), "agent-rsgfs")

    def test_conserva_la_regla_de_comentarios_de_auditoria(self):
        self.assertIn("[B]", self.texto)
        self.assertIn("[E]", self.texto)

    def test_conserva_los_patrones_del_stack(self):
        for patron in ("EjecutarSp", "InstanciarConsulta", "__doPostBack"):
            with self.subTest(patron=patron):
                self.assertIn(patron, self.texto)

    def test_documenta_la_operacion_bajo_el_harness(self):
        for concepto in ("ticket_context.json", "historial_fallos",
                         "herramientas_permitidas"):
            with self.subTest(concepto=concepto):
                self.assertIn(concepto, self.texto)


class TestSeparacionDePlanos(unittest.TestCase):
    def test_el_harness_generico_no_conoce_el_stack_legacy(self):
        prohibidos = ("VB.NET", "Web Forms", "aspx", "EjecutarSp", "jQuery",
                      "SepararCadena", "designer.vb")
        for ruta in (RAIZ / "harness").rglob("*"):
            if ruta.suffix not in {".py", ".md"} or not ruta.is_file():
                continue
            if ruta.name == "probe_hook.py":
                continue
            texto = ruta.read_text(encoding="utf-8")
            for termino in prohibidos:
                with self.subTest(archivo=ruta.name, termino=termino):
                    self.assertNotIn(termino, texto,
                                     f"{ruta.name} menciona '{termino}': eso pertenece "
                                     f"a profiles/, no al harness genérico")


if __name__ == "__main__":
    unittest.main()

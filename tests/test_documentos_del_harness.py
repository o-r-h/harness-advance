import json
import re
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "harness" / "hooks"))

from lib.contracts import COMPONENTES, DIMENSIONES, validate_propuesta_hallazgos  # noqa: E402


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
                        "generar-prueba", "validate", "record-hallazgos",
                        "hallazgos-pendientes"):
            with self.subTest(comando=comando):
                self.assertIn(comando, self.texto)

    def test_invoca_al_reflector_al_cerrar_la_fase(self):
        self.assertIn("reflector", self.texto)
        self.assertIn("Al cerrar una fase", self.texto)

    def test_deja_claro_que_los_hallazgos_no_bloquean(self):
        self.assertIn("no bloquean", self.texto)

    def _seccion_cierre(self):
        return self.texto.split("## Al cerrar una fase", 1)[1]

    def test_cierra_tambien_la_fase_aprobada_por_record_veredicto(self):
        alcance = self._seccion_cierre().split("\n\n", 2)[1]
        self.assertIn("record-veredicto", alcance)
        self.assertIn("escalad", alcance)

    def test_cierra_la_fase_antes_de_abrir_la_siguiente(self):
        seccion = self._seccion_cierre()
        self.assertIn("antes de", seccion)
        self.assertIn("open-fase", seccion)

    def test_explica_como_elegir_el_agente_ejecutor_de_cada_fase(self):
        self.assertIn("agente_ejecutor", self.texto)

    def test_deja_claro_que_el_esceptico_va_aislado(self):
        self.assertIn("contexto aislado", self.texto)

    def test_deja_claro_que_el_ciclo_se_detiene_en_el_gate_humano(self):
        self.assertIn("/fase-ok", self.texto)
        self.assertIn("/fase-fallo", self.texto)


class TestComandosDeHallazgos(unittest.TestCase):
    COMANDOS = {
        "hallazgo-ok": "resolver-hallazgo --decision ok",
        "hallazgo-no": "resolver-hallazgo --decision no",
        "hallazgo-editar": "resolver-hallazgo --decision editar",
        "hallazgo": 'hallazgo --texto',
    }

    def test_cada_comando_tiene_descripcion_y_subcomando(self):
        for nombre, subcomando in self.COMANDOS.items():
            with self.subTest(comando=nombre):
                texto = leer("harness", "commands", f"{nombre}.md")
                self.assertIn("description", frontmatter(texto))
                self.assertIn(subcomando, texto)


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


class TestAgenteReflector(unittest.TestCase):
    def setUp(self):
        self.texto = leer("harness", "agents", "reflector.md")

    def test_frontmatter(self):
        campos = frontmatter(self.texto)
        self.assertEqual(campos.get("name"), "reflector")
        self.assertIn("description", campos)

    def test_nombra_cada_componente_y_dimension(self):
        for valor in sorted(COMPONENTES | DIMENSIONES):
            with self.subTest(valor=valor):
                self.assertIn(f"`{valor}`", self.texto)

    def test_permite_no_proponer_nada(self):
        self.assertIn('"hallazgos": []', self.texto)

    def test_lee_los_rechazados(self):
        self.assertIn("rechazad", self.texto)

    def test_evidencia_es_dato(self):
        self.assertIn("no instrucciones", self.texto)

    def test_trata_la_biblioteca_como_hipotesis(self):
        self.assertIn("hipótesis", self.texto)

    def test_el_ejemplo_de_salida_cumple_el_contrato(self):
        bloques = re.findall(r"```json\n(.*?)\n```", self.texto, re.DOTALL)
        self.assertTrue(bloques, "reflector.md no trae un ejemplo JSON")
        for bloque in bloques:
            with self.subTest(bloque=bloque[:40]):
                self.assertEqual(validate_propuesta_hallazgos(json.loads(bloque)), [])


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

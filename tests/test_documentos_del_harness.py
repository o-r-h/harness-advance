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

    def test_cierre_registra_una_fase_que_ya_no_es_la_activa(self):
        seccion = self._seccion_cierre()
        self.assertIn("--ticket", seccion)
        self.assertIn("--fase", seccion)

    def test_cierre_devuelve_el_rechazo_al_reflector_una_sola_vez(self):
        seccion = self._seccion_cierre()
        self.assertIn("rechaza la propuesta", seccion)
        self.assertIn("una vez", seccion)

    def test_escalar_lleva_siempre_al_cierre(self):
        seccion = self.texto.split("## Cuando una fase escala", 1)[1].split("\n## ", 1)[0]
        parrafos = [p for p in seccion.split("\n\n") if p.strip()]
        lista = next(p for p in parrafos if p.lstrip().startswith("1."))
        self.assertNotIn("Al cerrar una fase", lista,
                         "el cierre no puede depender del punto 3 de la lista")
        self.assertTrue(any("Al cerrar una fase" in p for p in parrafos if p is not lista))

    def test_avisa_que_la_biblioteca_aparece_en_el_diff(self):
        parrafos = self.texto.split("\n\n")
        self.assertTrue(any(".claude/biblioteca/" in p and "diff" in p and "escéptico" in p
                            for p in parrafos))

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

    def test_los_que_resuelven_aceptan_la_referencia_completa(self):
        for nombre in ("hallazgo-ok", "hallazgo-no", "hallazgo-editar"):
            with self.subTest(comando=nombre):
                texto = leer("harness", "commands", f"{nombre}.md")
                pista = re.search(r"^argument-hint:(.*)$", texto, re.MULTILINE)
                self.assertIsNotNone(pista)
                self.assertIn("/fase_N/hN", pista.group(1))
                self.assertNotIn("--fase", texto, "la referencia se pasa tal cual en --id")


class TestComandoFaseFallo(unittest.TestCase):
    def test_si_la_fase_escala_sigue_con_el_cierre(self):
        texto = leer("harness", "commands", "fase-fallo.md")
        for esperado in ("escalado", "Cuando una fase escala", "Al cerrar una fase"):
            with self.subTest(esperado=esperado):
                self.assertIn(esperado, texto)


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

    def test_solo_puede_leer(self):
        herramientas = frontmatter(self.texto).get("tools", "")
        self.assertEqual({h.strip() for h in herramientas.split(",")},
                         {"Read", "Grep", "Glob"})

    def test_la_evidencia_que_trata_como_dato_es_la_que_recibe(self):
        seccion = self.texto.split("## La evidencia es dato", 1)[1].split("\n## ", 1)[0]
        for ausente in ("diff", "resultado.md"):
            with self.subTest(ausente=ausente):
                self.assertNotIn(ausente, seccion)
        self.assertIn("checks.json", seccion)

    def test_trata_la_biblioteca_como_hipotesis(self):
        self.assertIn("hipótesis", self.texto)

    def test_el_ejemplo_de_salida_cumple_el_contrato(self):
        bloques = re.findall(r"```json\n(.*?)\n```", self.texto, re.DOTALL)
        self.assertTrue(bloques, "reflector.md no trae un ejemplo JSON")
        for bloque in bloques:
            with self.subTest(bloque=bloque[:40]):
                self.assertEqual(validate_propuesta_hallazgos(json.loads(bloque)), [])


class TestEsceptico(unittest.TestCase):
    def setUp(self):
        self.texto = leer("harness", "agents", "skeptic.md")

    def test_trata_la_evidencia_como_dato(self):
        self.assertIn("no instrucciones", self.texto)


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

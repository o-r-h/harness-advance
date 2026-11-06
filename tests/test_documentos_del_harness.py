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
        "hallazgo-hecho": "hallazgo-hecho --id",
    }

    def test_cada_comando_tiene_descripcion_y_subcomando(self):
        for nombre, subcomando in self.COMANDOS.items():
            with self.subTest(comando=nombre):
                texto = leer("harness", "commands", f"{nombre}.md")
                self.assertIn("description", frontmatter(texto))
                self.assertIn(subcomando, texto)

    def test_los_que_resuelven_aceptan_la_referencia_completa(self):
        for nombre in ("hallazgo-ok", "hallazgo-no", "hallazgo-editar", "hallazgo-hecho"):
            with self.subTest(comando=nombre):
                texto = leer("harness", "commands", f"{nombre}.md")
                pista = re.search(r"^argument-hint:(.*)$", texto, re.MULTILINE)
                self.assertIsNotNone(pista)
                self.assertIn("/fase_N/hN", pista.group(1))
                self.assertNotIn("--fase", texto, "la referencia se pasa tal cual en --id")

    def test_ok_y_editar_documentan_nueva_y_reincide(self):
        for nombre in ("hallazgo-ok", "hallazgo-editar"):
            with self.subTest(comando=nombre):
                texto = leer("harness", "commands", f"{nombre}.md")
                self.assertIn("--nueva", texto)
                self.assertIn("--reincide", texto)


class TestComandoFaseFallo(unittest.TestCase):
    def test_si_la_fase_escala_sigue_con_el_cierre(self):
        texto = leer("harness", "commands", "fase-fallo.md")
        for esperado in ("escalado", "Cuando una fase escala", "Al cerrar una fase"):
            with self.subTest(esperado=esperado):
                self.assertIn(esperado, texto)


class TestAgenteDelPerfil(unittest.TestCase):
    def setUp(self):
        self.texto = leer("profiles", "crud-api", "agents", "agent-api.md")

    def test_tiene_frontmatter_con_el_nombre_esperado(self):
        self.assertEqual(frontmatter(self.texto).get("name"), "agent-api")

    def test_conserva_los_patrones_del_stack(self):
        for patron in (".NET 10", "EF Core", "SQLite"):
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

    def test_explica_reincide(self):
        for termino in ("reincide", "TICKET/fase_N/hN", "debió hacer"):
            with self.subTest(termino=termino):
                self.assertIn(termino, self.texto)

    def test_reincide_aunque_este_implementada(self):
        self.assertIn("aunque esa lección figure como implementada", self.texto)

    def test_confirmar_una_leccion_ya_no_es_siempre_silencio(self):
        self.assertNotIn("eso no es un hallazgo nuevo", self.texto)
        self.assertIn('reincidencia (ver "Reincidencias")', self.texto)
        self.assertIn("volvió a ocurrir el error que esa lección debía evitar",
                      " ".join(self.texto.split()))

    def test_reincidencia_falsa_no_se_marca(self):
        self.assertIn("**después** de planear o ejecutar", self.texto)
        self.assertIn("solo se **parecen**", self.texto)


class TestPlannerPesaLasQueFallaron(unittest.TestCase):
    def test_una_leccion_que_fallo_pesa_mas(self):
        texto = leer("harness", "skills", "task-planner", "SKILL.md")
        self.assertIn("(falló N×)", texto)


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


class TestComandosDeCuracion(unittest.TestCase):
    COMANDOS = {
        "curacion-ok": "resolver-curacion --decision ok",
        "curacion-no": "resolver-curacion --decision no",
        "curacion-editar": "resolver-curacion --decision editar",
        "biblioteca-curar": "record-curacion --archivo",
    }

    def test_cada_comando_tiene_descripcion_y_subcomando(self):
        for nombre, subcomando in self.COMANDOS.items():
            with self.subTest(comando=nombre):
                texto = leer("harness", "commands", f"{nombre}.md")
                self.assertIn("description", frontmatter(texto))
                self.assertIn(subcomando, texto)

    def test_curar_corre_las_senales_y_al_curador_y_no_resuelve(self):
        texto = leer("harness", "commands", "biblioteca-curar.md")
        self.assertIn("senales-biblioteca --json", texto)
        self.assertIn("`curador`", texto)
        self.assertIn("una vez", texto)
        self.assertIn("No resuelvas", texto)

    def test_editar_documenta_sus_opciones(self):
        texto = leer("harness", "commands", "curacion-editar.md")
        for opcion in ("--texto", "--senal", "--quitar", "--motivo"):
            with self.subTest(opcion=opcion):
                self.assertIn(opcion, texto)


class TestAgenteCurador(unittest.TestCase):
    def setUp(self):
        self.texto = leer("harness", "agents", "curador.md")

    def test_frontmatter_y_solo_lectura(self):
        campos = frontmatter(self.texto)
        self.assertEqual(campos.get("name"), "curador")
        self.assertIn("description", campos)
        self.assertEqual({h.strip() for h in campos.get("tools", "").split(",")},
                         {"Read", "Grep", "Glob"})

    def test_nombra_las_dos_acciones(self):
        for tipo in ('"fusionar"', '"retirar"'):
            with self.subTest(tipo=tipo):
                self.assertIn(tipo, self.texto)

    def test_sin_uso_no_basta(self):
        self.assertIn('"sin uso" no basta', self.texto)

    def test_permite_no_proponer_nada(self):
        self.assertIn('"acciones": []', self.texto)

    def test_lee_los_rechazos_de_curacion(self):
        self.assertIn("curacion-rechazada.md", self.texto)

    def test_no_fusiona_implementadas_con_no_implementadas(self):
        self.assertIn("implementadas con no implementadas", self.texto)


class TestRetiradasEnPlannerYReflector(unittest.TestCase):
    def test_ninguno_aplica_ni_repropone_las_retiradas(self):
        for partes in (("harness", "agents", "reflector.md"),
                       ("harness", "skills", "task-planner", "SKILL.md")):
            with self.subTest(archivo="/".join(partes)):
                self.assertIn("Retiradas — no aplicar", leer(*partes))


class TestEscepticoConOtroModelo(unittest.TestCase):
    def test_el_esceptico_es_sonnet_por_defecto(self):
        self.assertEqual(frontmatter(leer("harness", "agents", "skeptic.md")).get("model"),
                         "sonnet")

    def test_ticket_loop_elige_el_modelo_y_lo_registra(self):
        texto = leer("harness", "skills", "ticket-loop", "SKILL.md")
        self.assertIn("modelo-esceptico --ejecutor", texto)
        self.assertIn("--modelo-esceptico", texto)
        self.assertIn("parámetro `model`", texto)

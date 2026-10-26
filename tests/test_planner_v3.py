import json
import re
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "harness" / "hooks"))
from lib import contracts  # noqa: E402

SKILL = RAIZ / "harness" / "skills" / "task-planner" / "SKILL.md"


class TestPlannerV3(unittest.TestCase):
    def setUp(self):
        self.texto = SKILL.read_text(encoding="utf-8")

    def test_conserva_la_fase_0_de_anclaje(self):
        self.assertIn("Fase 0", self.texto)
        self.assertIn("archivo:línea", self.texto)

    def test_exige_emitir_plan_json_ademas_del_md(self):
        self.assertIn("plan.json", self.texto)
        self.assertIn("plan.md", self.texto)

    def test_documenta_los_campos_nuevos_por_fase(self):
        for campo in ("checks_deterministas", "prueba_manual", "herramientas_permitidas",
                      "max_reintentos", "anclajes", "depende_de", "criterio_exito",
                      "agente_ejecutor"):
            with self.subTest(campo=campo):
                self.assertIn(campo, self.texto)

    def test_manda_validar_el_plan_antes_de_entregarlo(self):
        self.assertIn("validate --contrato plan", self.texto)

    def test_el_ejemplo_de_plan_json_es_valido_contra_el_contrato(self):
        bloques = re.findall(r"```json\n(.*?)```", self.texto, re.DOTALL)
        planes = []
        for bloque in bloques:
            try:
                datos = json.loads(bloque)
            except json.JSONDecodeError:
                continue
            if isinstance(datos, dict) and "fases" in datos:
                planes.append(datos)
        self.assertTrue(planes, "la skill debe incluir un ejemplo completo de plan.json")
        for plan in planes:
            errores = contracts.validate_plan(plan)
            self.assertEqual(errores, [], msg="; ".join(errores))

    def test_conoce_la_biblioteca_como_entrada_opcional(self):
        for esperado in ("biblioteca", ".claude/biblioteca/INDEX.md", "entradas/",
                         "rechazad", '"confianza": "por_confirmar"'):
            with self.subTest(esperado=esperado):
                self.assertIn(esperado, self.texto)
        entradas = self.texto.split("## Entradas", 1)[1].split("\n---", 1)[0]
        self.assertIn("INDEX.md", entradas)
        checklist = self.texto.split("## Checklist antes de entregar el plan", 1)[1]
        self.assertIn("biblioteca", checklist)

    def test_aclara_que_cambia_en_la_v3(self):
        self.assertIn("Skill: task-planner-v3", self.texto)
        self.assertNotIn("de la v2, sin cambios", self.texto)
        self.assertIn("La v3", self.texto)


if __name__ == "__main__":
    unittest.main()

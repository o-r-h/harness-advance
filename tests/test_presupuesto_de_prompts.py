"""Presupuesto de tamaño de lo que el modelo carga entero.

Una skill o un agente se carga completo cada vez que se usa. Lo que solo hace falta
en una situación (plantillas, ejemplos, pasos de cierre) va en `references/` de la
skill y se lee cuando toca. Si un test de aquí falla, no subas el límite: mueve a
`references/` lo que no se necesita siempre.
"""
import re
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SKILLS = RAIZ / "harness" / "skills"
AGENTES = RAIZ / "harness" / "agents"

MAX_LINEAS_SKILL = 200
# Un agente no tiene references/: su .md es todo lo que ve. El tope evita que crezca.
MAX_LINEAS_AGENTE = 230
MAX_LINEAS_COMANDO = 40
RE_REFERENCIA = re.compile(r"`(references/[\w./-]+\.md)`")


def lineas(archivo: Path) -> int:
    return len(archivo.read_text(encoding="utf-8").splitlines())


class TestPresupuesto(unittest.TestCase):
    def test_ninguna_skill_pasa_el_limite(self):
        for skill in sorted(SKILLS.glob("*/SKILL.md")):
            with self.subTest(skill=skill.parent.name):
                self.assertLessEqual(lineas(skill), MAX_LINEAS_SKILL)

    def test_ningun_agente_pasa_el_limite(self):
        for agente in sorted(AGENTES.glob("*.md")):
            with self.subTest(agente=agente.name):
                self.assertLessEqual(lineas(agente), MAX_LINEAS_AGENTE)

    def test_ningun_comando_pasa_el_limite(self):
        for comando in sorted((RAIZ / "harness" / "commands").glob("*.md")):
            with self.subTest(comando=comando.name):
                self.assertLessEqual(lineas(comando), MAX_LINEAS_COMANDO)


class TestReferencias(unittest.TestCase):
    def test_toda_referencia_nombrada_existe(self):
        for skill in sorted(SKILLS.glob("*/SKILL.md")):
            carpeta = skill.parent
            textos = [skill, *sorted((carpeta / "references").glob("*.md"))]
            for archivo in textos:
                for referencia in RE_REFERENCIA.findall(archivo.read_text(encoding="utf-8")):
                    with self.subTest(skill=carpeta.name, referencia=referencia):
                        self.assertTrue((carpeta / referencia).is_file())

    def test_toda_referencia_esta_nombrada_en_su_skill(self):
        # Un archivo que SKILL.md no nombra nunca se lee.
        for skill in sorted(SKILLS.glob("*/SKILL.md")):
            texto = skill.read_text(encoding="utf-8")
            for archivo in sorted((skill.parent / "references").glob("*.md")):
                with self.subTest(skill=skill.parent.name, archivo=archivo.name):
                    self.assertIn(f"references/{archivo.name}", texto)

    def test_ticket_loop_manda_a_leer_antes_de_actuar(self):
        texto = (SKILLS / "ticket-loop" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Léelo\nentero antes de actuar", texto)
        for situacion in ("Al cerrar una fase", "Cuando una fase escala", "Pausar una fase"):
            with self.subTest(situacion=situacion):
                self.assertIn(situacion, texto)


if __name__ == "__main__":
    unittest.main()

import re
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

SKILL = re.compile(r"skill\s+`([a-z0-9-]+)`")
SUBAGENTE = re.compile(r"subagente\s+`([a-z0-9-]+)`")
SUBCOMANDO = (re.compile(r"`CLI\s+([a-z][a-z-]+)"),
              re.compile(r'cli\.py"\s+([a-z][a-z-]+)'))
COMANDO = re.compile(r"`/([a-z][a-z0-9-]+)")


def _md_del_harness() -> list[Path]:
    return sorted((RAIZ / "harness").rglob("*.md"))


def _skills() -> set[str]:
    return {c.name for c in (RAIZ / "harness" / "skills").iterdir()
            if c.is_dir() and (c / "SKILL.md").is_file()}


def _agentes() -> set[str]:
    rutas = list((RAIZ / "harness" / "agents").glob("*.md"))
    rutas += list((RAIZ / "profiles").glob("*/agents/*.md"))
    return {r.stem for r in rutas}


def _comandos() -> set[str]:
    return {r.stem for r in (RAIZ / "harness" / "commands").glob("*.md")}


def _subcomandos_cli() -> set[str]:
    texto = (RAIZ / "harness" / "hooks" / "cli.py").read_text(encoding="utf-8")
    return set(re.findall(r'add_parser\(\s*"([a-z-]+)"', texto))


def _referencias(patrones) -> list[tuple[str, str]]:
    if not isinstance(patrones, tuple):
        patrones = (patrones,)
    hallazgos = []
    for ruta in _md_del_harness():
        texto = ruta.read_text(encoding="utf-8")
        archivo = ruta.relative_to(RAIZ).as_posix()
        for patron in patrones:
            for ref in patron.findall(texto):
                hallazgos.append((archivo, ref))
    return hallazgos


class TestReferenciasDelHarness(unittest.TestCase):
    def _verificar(self, patrones, existentes: set[str]):
        for archivo, ref in _referencias(patrones):
            with self.subTest(archivo=archivo, referencia=ref):
                self.assertIn(ref, existentes,
                              f"{archivo} nombra '{ref}', que no existe")

    def test_toda_skill_invocada_existe(self):
        self._verificar(SKILL, _skills())

    def test_todo_subagente_nombrado_existe(self):
        self._verificar(SUBAGENTE, _agentes())

    def test_todo_subcomando_del_cli_existe(self):
        self._verificar(SUBCOMANDO, _subcomandos_cli())

    def test_todo_comando_con_barra_existe(self):
        self._verificar(COMANDO, _comandos())

    def test_los_patrones_encuentran_referencias_reales(self):
        texto = leer_ticket_loop()
        self.assertIn("open-fase", SUBCOMANDO[0].findall(texto))
        self.assertIn("fase-ok", COMANDO.findall(texto))
        self.assertIn("task-planner", SKILL.findall(texto))
        self.assertIn("reflector", SUBAGENTE.findall(texto))
        self.assertIn("skeptic", SUBAGENTE.findall(texto))


def leer_ticket_loop() -> str:
    return (RAIZ / "harness" / "skills" / "ticket-loop" / "SKILL.md").read_text(
        encoding="utf-8")


if __name__ == "__main__":
    unittest.main()

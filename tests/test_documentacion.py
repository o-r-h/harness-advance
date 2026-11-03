"""La documentación sigue al código: enlaces, comandos, subcomandos y reparto sin duplicar."""
import re
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
README = RAIZ / "README.md"
TECNICO = RAIZ / "docs" / "tecnico.md"


def _leer(ruta: Path) -> str:
    return ruta.read_text(encoding="utf-8")


def _encabezados(ruta: Path) -> set[str]:
    return {m.group(1).strip() for m in re.finditer(r"^## (.+)$", _leer(ruta), re.MULTILINE)}


class TestDocumentacion(unittest.TestCase):
    def test_readme_enlaza_al_tecnico(self):
        self.assertIn("docs/tecnico.md", _leer(README))

    def test_readme_documenta_cada_comando(self):
        texto = _leer(README)
        comandos = sorted((RAIZ / "harness" / "commands").glob("*.md"))
        self.assertTrue(comandos)
        for comando in comandos:
            with self.subTest(comando=comando.stem):
                self.assertIn(f"`/{comando.stem}", texto)

    def test_tecnico_documenta_cada_subcomando(self):
        self.assertTrue(TECNICO.is_file(), "falta docs/tecnico.md")
        texto = _leer(TECNICO)
        fuente = _leer(RAIZ / "harness" / "hooks" / "cli.py")
        subcomandos = re.findall(r'add_parser\("([^"]+)"', fuente)
        self.assertTrue(subcomandos)
        for nombre in subcomandos:
            with self.subTest(subcomando=nombre):
                self.assertIn(nombre, texto)

    def test_sin_secciones_duplicadas(self):
        self.assertTrue(TECNICO.is_file(), "falta docs/tecnico.md")
        repetidos = _encabezados(README) & _encabezados(TECNICO)
        self.assertEqual(repetidos, set())


if __name__ == "__main__":
    unittest.main()

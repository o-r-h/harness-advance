import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "harness" / "hooks"))
from lib import gitdiff  # noqa: E402


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True,
                   capture_output=True, text=True)


class TestAddedLines(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        _git(self.root, "init")
        _git(self.root, "config", "user.email", "t@t.t")
        _git(self.root, "config", "user.name", "t")
        self.archivo = self.root / "frmReviewReport.aspx.vb"
        self.archivo.write_text("Linea1\nLinea2\nLinea3\n", encoding="utf-8")
        _git(self.root, "add", ".")
        _git(self.root, "commit", "-m", "base")

    def tearDown(self):
        self.tmp.cleanup()

    def test_sin_cambios_devuelve_lista_vacia(self):
        self.assertEqual(gitdiff.added_lines(self.root, self.archivo), [])

    def test_detecta_una_linea_insertada_con_su_numero_nuevo(self):
        self.archivo.write_text("Linea1\nNUEVA\nLinea2\nLinea3\n", encoding="utf-8")
        self.assertEqual(gitdiff.added_lines(self.root, self.archivo), [(2, "NUEVA")])

    def test_detecta_cambios_ya_agregados_al_index(self):
        self.archivo.write_text("Linea1\nNUEVA\nLinea2\nLinea3\n", encoding="utf-8")
        _git(self.root, "add", ".")
        self.assertEqual(gitdiff.added_lines(self.root, self.archivo), [(2, "NUEVA")])

    def test_un_archivo_nuevo_sin_rastrear_cuenta_completo(self):
        nuevo = self.root / "frmNuevo.js"
        nuevo.write_text("var a = 1;\nvar b = 2;\n", encoding="utf-8")
        self.assertEqual(gitdiff.added_lines(self.root, nuevo),
                         [(1, "var a = 1;"), (2, "var b = 2;")])

    def test_devuelve_none_si_no_es_un_repo_git(self):
        with tempfile.TemporaryDirectory() as sin_git:
            raiz = Path(sin_git)
            suelto = raiz / "x.vb"
            suelto.write_text("algo\n", encoding="utf-8")
            self.assertIsNone(gitdiff.added_lines(raiz, suelto))


class TestDecodificacionConRespaldoCp1252(unittest.TestCase):
    """Cobertura del hallazgo 1: archivos legacy en cp1252 no deben corromperse."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        _git(self.root, "init")
        _git(self.root, "config", "user.email", "t@t.t")
        _git(self.root, "config", "user.name", "t")

    def tearDown(self):
        self.tmp.cleanup()

    def test_archivo_sin_rastrear_en_cp1252_conserva_acentos(self):
        archivo = self.root / "frmLegacyCp1252.aspx.vb"
        archivo.write_bytes("línea con ñ y á y é".encode("cp1252"))
        resultado = gitdiff.added_lines(self.root, archivo)
        self.assertIsNotNone(resultado)
        _, texto = resultado[0]
        self.assertEqual(texto, "línea con ñ y á y é")
        self.assertNotIn("�", texto)

    def test_diff_de_archivo_modificado_en_cp1252_conserva_acentos(self):
        archivo = self.root / "frmLegacyCp1252Mod.aspx.vb"
        archivo.write_bytes("Linea1\nLinea2\n".encode("cp1252"))
        _git(self.root, "add", ".")
        _git(self.root, "commit", "-m", "base")
        archivo.write_bytes("Linea1\nlínea con ñ y á y é\nLinea2\n".encode("cp1252"))
        resultado = gitdiff.added_lines(self.root, archivo)
        self.assertIsNotNone(resultado)
        textos = [texto for _, texto in resultado]
        self.assertIn("línea con ñ y á y é", textos)
        self.assertFalse(any("�" in texto for texto in textos))


class TestArchivosModificados(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        _git(self.root, "init")
        _git(self.root, "config", "user.email", "t@t.t")
        _git(self.root, "config", "user.name", "t")
        (self.root / "a.vb").write_text("uno\n", encoding="utf-8")
        _git(self.root, "add", ".")
        _git(self.root, "commit", "-m", "base")

    def tearDown(self):
        self.tmp.cleanup()

    def test_lista_modificados_y_sin_rastrear(self):
        (self.root / "a.vb").write_text("uno\ndos\n", encoding="utf-8")
        (self.root / "b.js").write_text("var x;\n", encoding="utf-8")
        nombres = sorted(p.name for p in gitdiff.archivos_modificados(self.root))
        self.assertEqual(nombres, ["a.vb", "b.js"])

    def test_sin_cambios_devuelve_lista_vacia(self):
        self.assertEqual(gitdiff.archivos_modificados(self.root), [])


class TestCompresionDeNumeros(unittest.TestCase):
    def test_agrupa_rangos_contiguos(self):
        self.assertEqual(gitdiff.compress_line_numbers([3, 4, 5, 9]), "3-5, 9")

    def test_numero_suelto(self):
        self.assertEqual(gitdiff.compress_line_numbers([7]), "7")

    def test_lista_vacia(self):
        self.assertEqual(gitdiff.compress_line_numbers([]), "")


if __name__ == "__main__":
    unittest.main()

"""Perfil reviewsystemgfs: check estructural xhtml_selfclose.

Del repo real (03-11-2026): conviven páginas XHTML 1.0 Transitional y páginas
HTML5 (frmReviewReport.aspx, GenericAIReport.aspx), y hay páginas de contenido
que heredan el DOCTYPE de su master. La regla solo aplica a las XHTML.
"""
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
MODULO = RAIZ / "profiles" / "reviewsystemgfs" / "checks" / "xhtml_selfclose.py"
sys.path.insert(0, str(RAIZ / "harness" / "hooks"))

XHTML = ('<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" '
         '"http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">\n')
BASE = XHTML + "<div>viejo sin cerrar <br> aqui</div>\n"


def cargar():
    especificacion = importlib.util.spec_from_file_location("xhtml_selfclose", MODULO)
    modulo = importlib.util.module_from_spec(especificacion)
    especificacion.loader.exec_module(modulo)
    return modulo


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


class TestXhtmlSelfClose(unittest.TestCase):
    def setUp(self):
        self.modulo = cargar()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        _git(self.root, "init")
        _git(self.root, "config", "user.email", "t@t.t")
        _git(self.root, "config", "user.name", "t")
        self.aspx = self.root / "frm.aspx"
        self.aspx.write_text(BASE, encoding="utf-8")
        _git(self.root, "add", ".")
        _git(self.root, "commit", "-m", "base")

    def correr(self, *archivos: Path):
        return self.modulo.run(self.root, list(archivos or [self.aspx]), None)

    def agregar(self, markup: str, base: str = BASE) -> None:
        self.aspx.write_text(base + markup + "\n", encoding="utf-8")

    def test_un_br_agregado_sin_cerrar_es_warning(self):
        self.agregar("<p>nuevo<br></p>")
        hallazgos = self.correr()
        self.assertEqual(len(hallazgos), 1, hallazgos)
        self.assertEqual((hallazgos[0]["severidad"], hallazgos[0]["resultado"]),
                         ("warning", "fallo"))
        self.assertIn("frm.aspx:3", hallazgos[0]["detalle"])
        self.assertIn("<br>", hallazgos[0]["detalle"])

    def test_no_marca_el_markup_viejo_que_no_se_toco(self):
        self.agregar("<p>nuevo</p>")
        self.assertEqual(self.correr(), [])

    def test_un_tag_autocerrado_no_produce_hallazgos(self):
        self.agregar("<img src='x.png' alt='x' /><br/><hr />")
        self.assertEqual(self.correr(), [])

    def test_detecta_img_e_input_sin_cerrar_y_en_mayusculas(self):
        self.agregar("<img src='x.png'>\n<INPUT type='text'>")
        detalles = " ".join(h["detalle"] for h in self.correr())
        self.assertIn("img", detalles)
        self.assertIn("INPUT", detalles)

    def test_no_confunde_tags_con_el_mismo_prefijo(self):
        self.agregar("<br-custom></br-custom><input-group></input-group><colgroup></colgroup>")
        self.assertEqual(self.correr(), [])

    def test_una_pagina_html5_no_aplica(self):
        html5 = "<!DOCTYPE html>\n<div>viejo</div>\n"
        self.aspx.write_text(html5, encoding="utf-8")
        _git(self.root, "commit", "-am", "html5")
        self.agregar("<p>nuevo<br></p>", base=html5)
        self.assertEqual(self.correr(), [])

    def test_una_pagina_sin_doctype_ni_master_no_aplica(self):
        sin = "<div>viejo</div>\n"
        self.aspx.write_text(sin, encoding="utf-8")
        _git(self.root, "commit", "-am", "sin doctype")
        self.agregar("<p>nuevo<br></p>", base=sin)
        self.assertEqual(self.correr(), [])

    def test_una_pagina_de_contenido_hereda_el_doctype_de_su_master(self):
        (self.root / "Site.Master").write_text(XHTML + "<html></html>\n", encoding="utf-8")
        contenido = ('<%@ Page Language="vb" MasterPageFile="~/Site.Master" %>\n'
                     '<asp:Content ID="c" runat="server">\n')
        self.aspx.write_text(contenido, encoding="utf-8")
        _git(self.root, "add", ".")
        _git(self.root, "commit", "-m", "contenido")
        self.agregar("<br>", base=contenido)
        self.assertEqual(len(self.correr()), 1)

    def test_un_master_html5_no_aplica_a_sus_paginas(self):
        (self.root / "Site.Master").write_text("<!DOCTYPE html>\n<html></html>\n", encoding="utf-8")
        contenido = '<%@ Page Language="vb" MasterPageFile="~/Site.Master" %>\n'
        self.aspx.write_text(contenido, encoding="utf-8")
        _git(self.root, "add", ".")
        _git(self.root, "commit", "-m", "contenido")
        self.agregar("<br>", base=contenido)
        self.assertEqual(self.correr(), [])

    def test_comentarios_scripts_y_bloques_de_servidor_no_cuentan(self):
        self.agregar("<%-- <br> --%>\n<!-- <img src='x'> -->\n"
                     "<script type='text/javascript'>\nvar html = '<br>';\n</script>\n"
                     "<% Response.Write(\"<br>\") %>")
        self.assertEqual(self.correr(), [])

    def test_un_comentario_de_varias_lineas_no_cuenta(self):
        self.agregar("<%--\n<br>\n--%>")
        self.assertEqual(self.correr(), [])

    def test_ignora_archivos_que_no_son_markup(self):
        otro = self.root / "frm.js"
        otro.write_text("var html = '<br>';\n", encoding="utf-8")
        self.assertEqual(self.correr(otro), [])

    def test_sin_git_es_error_check(self):
        sin_git = tempfile.TemporaryDirectory()
        self.addCleanup(sin_git.cleanup)
        pagina = Path(sin_git.name) / "frm.aspx"
        pagina.write_text(BASE + "<br>\n", encoding="utf-8")
        hallazgos = self.modulo.run(Path(sin_git.name), [pagina], None)
        self.assertEqual([h["resultado"] for h in hallazgos], ["error_check"])


if __name__ == "__main__":
    unittest.main()

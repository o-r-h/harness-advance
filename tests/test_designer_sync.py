"""Perfil reviewsystemgfs: check estructural designer_sync.

Los casos de falso positivo salen de correr la heurística del plan original
contra el repo real (03-11-2026): controles comentados con <%-- --%>, controles
dentro de templates, <asp:Content>, variables locales con prefijo de control y
markup viejo que compila aunque el designer no lo declare.
"""
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
MODULO = RAIZ / "profiles" / "reviewsystemgfs" / "checks" / "designer_sync.py"
sys.path.insert(0, str(RAIZ / "harness" / "hooks"))


def cargar():
    especificacion = importlib.util.spec_from_file_location("designer_sync", MODULO)
    modulo = importlib.util.module_from_spec(especificacion)
    especificacion.loader.exec_module(modulo)
    return modulo


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


ASPX = """<%@ Page Language="vb" CodeBehind="frmReview.aspx.vb" Inherits="frmReview" %>
<form id="form1" runat="server">
<asp:HiddenField ID="hdnExistente" runat="server" />
<input type="hidden" id="hdnViejoSinDesigner" runat="server" />
<div id="soloHtml"></div>
</form>
"""

DESIGNER = """Partial Public Class frmReview
    Protected WithEvents form1 As Global.System.Web.UI.HtmlControls.HtmlForm
    Protected WithEvents hdnExistente As Global.System.Web.UI.WebControls.HiddenField
End Class
"""

CODEBEHIND = """Partial Class frmReview
    Private Sub Guardar()
        Dim valor As String = hdnExistente.Value
    End Sub
End Class
"""


class TestDesignerSync(unittest.TestCase):
    def setUp(self):
        self.modulo = cargar()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        _git(self.root, "init")
        _git(self.root, "config", "user.email", "t@t.t")
        _git(self.root, "config", "user.name", "t")
        self.aspx = self.root / "frmReview.aspx"
        self.designer = self.root / "frmReview.aspx.designer.vb"
        self.vb = self.root / "frmReview.aspx.vb"
        self.aspx.write_text(ASPX, encoding="utf-8")
        self.designer.write_text(DESIGNER, encoding="utf-8")
        self.vb.write_text(CODEBEHIND, encoding="utf-8")
        _git(self.root, "add", ".")
        _git(self.root, "commit", "-m", "base")

    def correr(self, *archivos: Path):
        return self.modulo.run(self.root, list(archivos), None)

    def agregar_al_vb(self, linea: str) -> None:
        self.vb.write_text(CODEBEHIND.replace(
            "    End Sub", f"        {linea}\n    End Sub"), encoding="utf-8")

    def agregar_al_aspx(self, markup: str) -> None:
        self.aspx.write_text(ASPX.replace("</form>", f"{markup}\n</form>"), encoding="utf-8")

    def errores(self, hallazgos):
        return [h for h in hallazgos if h["resultado"] == "fallo" and h["severidad"] == "error"]

    # --- code-behind: el error real de compilación ---

    def test_usar_un_control_del_markup_sin_declararlo_es_error(self):
        self.agregar_al_vb("hdnViejoSinDesigner.Value = \"1\"")
        hallazgos = self.correr(self.vb)
        errores = self.errores(hallazgos)
        self.assertEqual(len(errores), 1, hallazgos)
        self.assertIn("hdnViejoSinDesigner", errores[0]["detalle"])
        self.assertIn("no compila", errores[0]["detalle"])
        self.assertIn("frmReview.aspx.vb:4", errores[0]["detalle"])

    def test_pasar_el_control_como_argumento_tambien_es_uso(self):
        self.agregar_al_vb("Controls.Add(hdnViejoSinDesigner)")
        errores = self.errores(self.correr(self.vb))
        self.assertTrue(any("hdnViejoSinDesigner" in h["detalle"] for h in errores))

    def test_un_miembro_de_otro_objeto_con_el_mismo_nombre_no_es_uso(self):
        self.agregar_al_vb("valor = objRet.hdnViejoSinDesigner")
        self.assertEqual(self.correr(self.vb), [])

    def test_usar_un_control_declarado_en_el_designer_no_produce_hallazgos(self):
        self.agregar_al_vb("hdnExistente.Value = \"1\"")
        self.assertEqual(self.correr(self.vb), [])

    def test_vb_no_distingue_mayusculas(self):
        self.agregar_al_vb("HDNEXISTENTE.Value = \"1\"")
        self.assertEqual(self.correr(self.vb), [])

    def test_un_control_declarado_en_el_propio_codebehind_no_es_error(self):
        self.vb.write_text(CODEBEHIND.replace(
            "Partial Class frmReview\n",
            "Partial Class frmReview\n    Protected hdnViejoSinDesigner As HtmlInputHidden\n"
        ).replace("    End Sub", "        hdnViejoSinDesigner.Value = \"1\"\n    End Sub"),
            encoding="utf-8")
        self.assertEqual(self.correr(self.vb), [])

    def test_el_uso_en_un_comentario_o_en_una_cadena_no_cuenta(self):
        self.agregar_al_vb("Dim s As String = \"hdnViejoSinDesigner.Value\" ' hdnFalso.Value")
        self.assertEqual(self.correr(self.vb), [])

    def test_una_variable_local_con_prefijo_de_control_no_es_hallazgo(self):
        self.vb.write_text(CODEBEHIND.replace(
            "    End Sub",
            "        Dim chkRow As CheckBox = Nothing\n"
            "        If chkRow.Checked Then valor = \"1\"\n"
            "        For Each lblFila As Label In New Label() {}\n"
            "            lblFila.Text = \"\"\n"
            "        Next\n    End Sub"), encoding="utf-8")
        self.assertEqual(self.correr(self.vb), [])

    def test_otras_formas_de_declarar_un_local_o_un_parametro(self):
        # Los WebMethods reales nombran sus parámetros igual que los hidden fields.
        self.vb.write_text(CODEBEHIND.replace(
            "    End Sub",
            "    End Sub\n"
            "    Public Shared Function Guardar2(hdnViejoSinDesigner As String, "
            "Optional ByVal x As Integer = 0) As String\n"
            "        Dim a As Integer = 0, hdnOtro As String = hdnViejoSinDesigner\n"
            "        For i As Integer = 0 To 3\n        Next\n"
            "        For Each fila In New String() {}\n            fila.Trim()\n        Next\n"
            "        Return hdnViejoSinDesigner.Trim() + hdnOtro.Trim()\n"
            "    End Function"), encoding="utf-8")
        self.aspx.write_text(ASPX.replace(
            "</form>", '<input type="hidden" id="hdnOtro" runat="server" />\n</form>'),
            encoding="utf-8")
        self.assertEqual(self.errores(self.correr(self.vb)), [])

    def test_un_template_anidado_con_el_mismo_nombre(self):
        self.agregar_al_aspx('<asp:Repeater ID="rptA" runat="server"><ItemTemplate>\n'
                             '<asp:Repeater ID="rptB" runat="server"><ItemTemplate>\n'
                             '</ItemTemplate></asp:Repeater>\n'
                             '<asp:Label ID="lblDespues" runat="server" />\n'
                             '</ItemTemplate></asp:Repeater>')
        detalles = " ".join(h["detalle"] for h in self.correr(self.aspx))
        self.assertIn("rptA", detalles)
        self.assertNotIn("lblDespues", detalles)
        self.assertNotIn("rptB", detalles)

    def test_un_identificador_con_prefijo_que_no_esta_en_ningun_lado_es_warning(self):
        self.agregar_al_vb("txtInventado.Text = \"1\"")
        hallazgos = self.correr(self.vb)
        self.assertEqual([h["severidad"] for h in hallazgos], ["warning"])
        self.assertIn("txtInventado", hallazgos[0]["detalle"])

    def test_el_codigo_viejo_no_se_revisa(self):
        # Ya estaba en HEAD: si compilaba, no es asunto de esta fase.
        self.vb.write_text(CODEBEHIND.replace(
            "    End Sub", "        txtViejo.Text = \"1\"\n    End Sub"), encoding="utf-8")
        _git(self.root, "commit", "-am", "viejo")
        self.agregar_al_vb("hdnExistente.Value = \"1\"")
        self.vb.write_text(self.vb.read_text(encoding="utf-8").replace(
            "    End Sub", "        txtViejo.Text = \"1\"\n    End Sub", 1), encoding="utf-8")
        self.assertFalse(any("txtViejo" in h["detalle"] for h in self.correr(self.vb)))

    def test_si_cambia_el_designer_se_revisan_todos_los_usos(self):
        # Quitar una declaración rompe usos que ya existían.
        self.designer.write_text(DESIGNER.replace(
            "    Protected WithEvents hdnExistente As "
            "Global.System.Web.UI.WebControls.HiddenField\n", ""), encoding="utf-8")
        errores = self.errores(self.correr(self.designer))
        self.assertTrue(any("hdnExistente" in h["detalle"] for h in errores))

    # --- markup: designer desactualizado, compila igual ---

    def test_un_control_nuevo_del_markup_sin_declarar_es_warning_no_error(self):
        self.agregar_al_aspx('<asp:TextBox ID="txtNuevo" runat="server" />')
        hallazgos = self.correr(self.aspx)
        self.assertEqual([h["severidad"] for h in hallazgos], ["warning"])
        self.assertIn("txtNuevo", hallazgos[0]["detalle"])

    def test_el_markup_viejo_sin_designer_no_se_marca(self):
        self.agregar_al_aspx("<p>texto</p>")
        self.assertEqual(self.correr(self.aspx), [])

    def test_un_control_comentado_no_cuenta(self):
        self.agregar_al_aspx('<%-- <input id="hdnComentado" runat="server" /> --%>\n'
                             '<!-- <asp:Label ID="lblComentado" runat="server" /> -->')
        self.assertEqual(self.correr(self.aspx), [])

    def test_un_control_dentro_de_un_template_no_se_declara(self):
        self.agregar_al_aspx('<asp:GridView ID="grdNuevo" runat="server"><Columns>'
                             '<asp:TemplateField><ItemTemplate>\n'
                             '<asp:CheckBox ID="chkFila" runat="server" />\n'
                             '</ItemTemplate></asp:TemplateField></Columns></asp:GridView>')
        detalles = " ".join(h["detalle"] for h in self.correr(self.aspx))
        self.assertIn("grdNuevo", detalles)
        self.assertNotIn("chkFila", detalles)

    def test_un_control_dentro_de_un_contenttemplate_si_se_declara(self):
        # UpdatePanel: ContentTemplate es de instancia única y el designer sí lo declara.
        self.agregar_al_aspx('<asp:UpdatePanel ID="upd" runat="server"><ContentTemplate>\n'
                             '<asp:Label ID="lblDentro" runat="server" />\n'
                             '</ContentTemplate></asp:UpdatePanel>')
        detalles = " ".join(h["detalle"] for h in self.correr(self.aspx))
        self.assertIn("lblDentro", detalles)

    def test_asp_content_no_se_declara_en_el_designer(self):
        self.agregar_al_aspx('<asp:Content ID="Content1" ContentPlaceHolderID="x" '
                             'runat="server"></asp:Content>')
        self.assertEqual(self.correr(self.aspx), [])

    def test_atributos_en_cualquier_orden(self):
        self.agregar_al_aspx('<input runat="server" type="hidden" id="hdnAlReves" />')
        self.assertTrue(any("hdnAlReves" in h["detalle"] for h in self.correr(self.aspx)))

    # --- bordes ---

    def test_sin_designer_es_error_check_y_no_falso_positivo(self):
        self.designer.unlink()
        self.agregar_al_vb("hdnViejoSinDesigner.Value = \"1\"")
        hallazgos = self.correr(self.vb)
        self.assertTrue(any(h["resultado"] == "error_check" for h in hallazgos))
        self.assertFalse(any(h["resultado"] == "fallo" for h in hallazgos))

    def test_una_pagina_codefile_sin_designer_no_aplica(self):
        # Modelo Web Site: el runtime genera las declaraciones, no hay designer.
        self.aspx.write_text(ASPX.replace("CodeBehind=", "CodeFile="), encoding="utf-8")
        self.designer.unlink()
        self.agregar_al_vb("hdnViejoSinDesigner.Value = \"1\"")
        self.assertEqual(self.correr(self.vb), [])

    def test_ignora_archivos_de_otro_tipo(self):
        otro = self.root / "otro.js"
        otro.write_text("var hdnFalso = 1; hdnFalso.x = 2;\n", encoding="utf-8")
        self.assertEqual(self.correr(otro), [])

    def test_lee_cp1252_sin_romperse(self):
        self.vb.write_bytes(CODEBEHIND.replace(
            "    End Sub", "        ' revisión\n        hdnExistente.Value = \"año\"\n    End Sub"
        ).encode("cp1252"))
        self.assertEqual(self.correr(self.vb), [])

    def test_sin_git_es_error_check(self):
        sin_git = tempfile.TemporaryDirectory()
        self.addCleanup(sin_git.cleanup)
        raiz = Path(sin_git.name)
        for ruta, texto in ((raiz / "frmReview.aspx", ASPX),
                            (raiz / "frmReview.aspx.designer.vb", DESIGNER),
                            (raiz / "frmReview.aspx.vb", CODEBEHIND)):
            ruta.write_text(texto, encoding="utf-8")
        hallazgos = self.modulo.run(raiz, [raiz / "frmReview.aspx.vb"], None)
        self.assertTrue(hallazgos)
        self.assertTrue(all(h["resultado"] == "error_check" for h in hallazgos))


if __name__ == "__main__":
    unittest.main()

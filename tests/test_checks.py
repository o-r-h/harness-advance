import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "harness" / "hooks"))
from lib import checks  # noqa: E402

CTX = {"ticket_id": "ISR-110722", "nroticket": "110722",
       "desarrollador": "OMAR RODRIGUEZ", "fecha": "28-07-2026",
       "perfil": "perfil-demo"}
CFG = {"requerido": True, "severidad": "error", "aplica_a": [".vb", ".js", ".sql", ".aspx"]}

VB_CORRECTO = """Public Class Reporte
    '--[B] ISR 110722 OMAR RODRIGUEZ 28-07-2026
    Private Sub Guardar()
        Dim x As Integer = 1
    End Sub
    '--[E] ISR 110722 OMAR RODRIGUEZ 28-07-2026
End Class
"""


class TestRegionesDeAuditoria(unittest.TestCase):
    def test_reconoce_una_region_con_sus_metadatos(self):
        regiones, sin_cerrar = checks.audit_regions(VB_CORRECTO.splitlines())
        self.assertEqual(len(regiones), 1)
        self.assertEqual(sin_cerrar, [])
        inicio, fin, meta = regiones[0]
        self.assertEqual((inicio, fin), (2, 6))
        self.assertEqual(meta["ticket"], "110722")
        self.assertEqual(meta["dev"], "OMAR RODRIGUEZ")
        self.assertEqual(meta["fecha"], "28-07-2026")

    def test_reconoce_el_formato_de_javascript(self):
        regiones, _ = checks.audit_regions([
            "//--[B] ISR 110722 OMAR RODRIGUEZ 28-07-2026",
            "var total = 1;",
            "//--[E] ISR 110722 OMAR RODRIGUEZ 28-07-2026"])
        self.assertEqual(len(regiones), 1)

    def test_reconoce_el_formato_de_aspx(self):
        regiones, _ = checks.audit_regions([
            "<%--[B] ISR 110722 OMAR RODRIGUEZ 28-07-2026--%>",
            "<asp:HiddenField ID=\"hdnX\" runat=\"server\" />",
            "<%--[E] ISR 110722 OMAR RODRIGUEZ 28-07-2026--%>"])
        self.assertEqual(len(regiones), 1)

    def test_detecta_un_bloque_abierto_sin_cerrar(self):
        regiones, sin_cerrar = checks.audit_regions([
            "'--[B] ISR 110722 OMAR RODRIGUEZ 28-07-2026", "Dim x = 1"])
        self.assertEqual(regiones, [])
        self.assertEqual(len(sin_cerrar), 1)


class TestCheckAuditComments(unittest.TestCase):
    def test_lineas_dentro_de_un_bloque_correcto_no_producen_hallazgos(self):
        agregadas = [(2, ""), (3, ""), (4, ""), (5, ""), (6, "")]
        self.assertEqual(
            checks.check_audit_comments("x.aspx.vb", VB_CORRECTO, agregadas, CTX, CFG), [])

    def test_una_linea_agregada_fuera_de_todo_bloque_es_error(self):
        texto = VB_CORRECTO + "    Dim suelta As Integer = 9\n"
        hallazgos = checks.check_audit_comments("x.aspx.vb", texto, [(8, "    Dim suelta")], CTX, CFG)
        self.assertEqual(len(hallazgos), 1)
        self.assertEqual(hallazgos[0]["severidad"], "error")
        self.assertIn("8", hallazgos[0]["detalle"])

    def test_ticket_que_no_coincide_con_el_contexto_es_error(self):
        texto = VB_CORRECTO.replace("110722", "999999")
        hallazgos = checks.check_audit_comments("x.aspx.vb", texto, [(3, "")], CTX, CFG)
        self.assertTrue(any("999999" in h["detalle"] for h in hallazgos))

    def test_no_juzga_bloques_de_tickets_viejos_que_no_toco(self):
        texto = ("'--[B] ISR 100001 JUAN PEREZ 01-01-2020\n"
                 "Dim viejo As Integer = 1\n"
                 "'--[E] ISR 100001 JUAN PEREZ 01-01-2020\n"
                 + VB_CORRECTO)
        agregadas = [(5, ""), (6, "")]
        self.assertEqual(
            checks.check_audit_comments("x.aspx.vb", texto, agregadas, CTX, CFG), [])

    def test_fecha_distinta_a_la_del_contexto_es_error(self):
        texto = VB_CORRECTO.replace("28-07-2026", "01-01-2026")
        hallazgos = checks.check_audit_comments("x.aspx.vb", texto, [(3, "")], CTX, CFG)
        self.assertTrue(any("01-01-2026" in h["detalle"] for h in hallazgos))

    def test_sin_lineas_agregadas_no_hay_nada_que_juzgar(self):
        self.assertEqual(checks.check_audit_comments("x.aspx.vb", VB_CORRECTO, [], CTX, CFG), [])


class TestCheckProhibited(unittest.TestCase):
    def setUp(self):
        self.rules = {"prohibido": [
            {"id": "no_async", "archivos": [".vb"], "severidad": "error",
             "patron": r"\b(Async|Await)\s", "mensaje": "FW 3.5 no soporta async/await"},
            {"id": "no_fetch", "archivos": [".js"], "severidad": "error",
             "patron": r"\bfetch\s*\(", "mensaje": "IE11 no soporta fetch"}]}

    def test_detecta_la_violacion_solo_en_la_extension_declarada(self):
        hallazgos = checks.check_prohibited("frm.aspx.vb", [(10, "Dim x = Await Api()")], self.rules)
        self.assertEqual([h["id"] for h in hallazgos], ["no_async"])

    def test_no_aplica_reglas_de_vb_a_un_archivo_js(self):
        self.assertEqual(checks.check_prohibited("frm.js", [(10, "Await algo ")], self.rules), [])

    def test_el_detalle_incluye_archivo_linea_y_mensaje(self):
        hallazgos = checks.check_prohibited("frm.js", [(4, "fetch('/x')")], self.rules)
        self.assertIn("frm.js:4", hallazgos[0]["detalle"])
        self.assertIn("IE11", hallazgos[0]["detalle"])


class TestCheckProhibitedExcluir(unittest.TestCase):
    """`excluir`: prefijos de ruta (relativa a la raíz, con /) donde la regla no aplica."""

    def setUp(self):
        self.rules = {"prohibido": [
            {"id": "no_ddl", "archivos": [".cs"], "severidad": "error",
             "patron": r"(?i)\bCREATE\s+TABLE\b", "mensaje": "sin DDL",
             "excluir": ["tests/Proyecto.IntegracionSql/"]},
            {"id": "no_exec", "archivos": [".cs"], "severidad": "error",
             "patron": r"ExecuteNonQuery", "mensaje": "sin exec"}]}
        self.linea = [(3, 'sql = "CREATE TABLE T (Id INT)"; cmd.ExecuteNonQuery();')]

    def test_la_regla_no_aplica_dentro_del_prefijo_excluido(self):
        hallazgos = checks.check_prohibited("tests/Proyecto.IntegracionSql/Base.cs", self.linea, self.rules)
        self.assertEqual([h["id"] for h in hallazgos], ["no_exec"])

    def test_la_regla_sigue_aplicando_fuera_del_prefijo(self):
        for ruta in ("src/Api/Datos/Lector.cs", "tests/Proyecto.Tests/Base.cs",
                     "tests/Proyecto.IntegracionSqlOtro/Base.cs"):
            with self.subTest(ruta=ruta):
                hallazgos = checks.check_prohibited(ruta, self.linea, self.rules)
                self.assertEqual(sorted(h["id"] for h in hallazgos), ["no_ddl", "no_exec"])

    def test_acepta_barras_invertidas_y_prefijo_sin_barra_final(self):
        reglas = {"prohibido": [dict(self.rules["prohibido"][0], excluir=["tests\\Proyecto.IntegracionSql"])]}
        self.assertEqual(checks.check_prohibited("tests/Proyecto.IntegracionSql/Base.cs", self.linea, reglas), [])
        self.assertEqual(len(checks.check_prohibited("tests/Proyecto.IntegracionSqlOtro/Base.cs", self.linea, reglas)), 1)

    def test_no_permite_escapar_con_rutas_relativas(self):
        hallazgos = checks.check_prohibited("tests/Proyecto.IntegracionSql/../../src/Api/X.cs", self.linea, self.rules)
        self.assertIn("no_ddl", [h["id"] for h in hallazgos])

    def test_excluir_invalido_es_error_de_configuracion(self):
        reglas = {"prohibido": [dict(self.rules["prohibido"][0], excluir="tests/")]}
        hallazgos = checks.check_prohibited("src/X.cs", self.linea, reglas)
        self.assertEqual(hallazgos[0]["resultado"], "error_check")


class TestCheckNoNewDeps(unittest.TestCase):
    def setUp(self):
        self.rules = {"no_new_deps": {
            "severidad": "error", "vigilar": ["ReviewSystem.vbproj", "Web.config"],
            "patron": r"(<Reference\s+Include=|<package\s+id=|HintPath|\.dll)",
            "mensaje": "Ninguna dependencia nueva sin aprobación humana"}}

    def test_una_referencia_agregada_al_vbproj_es_error(self):
        hallazgos = checks.check_no_new_deps(
            "ReviewSystem.vbproj", [(40, '<Reference Include="Dapper" />')], self.rules)
        self.assertEqual(len(hallazgos), 1)
        self.assertEqual(hallazgos[0]["severidad"], "error")

    def test_ignora_archivos_que_no_estan_vigilados(self):
        self.assertEqual(checks.check_no_new_deps(
            "frm.aspx.vb", [(1, '<Reference Include="Dapper" />')], self.rules), [])

    def test_un_cambio_inocuo_en_un_archivo_vigilado_no_es_error(self):
        self.assertEqual(checks.check_no_new_deps(
            "Web.config", [(12, '<add key="Proyecto" value="Review System" />')], self.rules), [])


if __name__ == "__main__":
    unittest.main()

"""Perfil reviewsystemgfs: check estructural sp_params.

El fallo más caro del stack: el VB envía |V21= y el SP nunca lo parsea. No
falla en ninguna capa; el dato desaparece. Los casos de borde salen del repo
real (03-11-2026): SPs en UTF-16, Sps/ del repo congelado desde 2016 (de ahí
las carpetas configurables y su prioridad), ReviewGetFilters como prefijo de
ReviewGetFiltersInsitu, ramas @Validar comentadas.
"""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parents[1]
MODULO = RAIZ / "profiles" / "reviewsystemgfs" / "checks" / "sp_params.py"
sys.path.insert(0, str(RAIZ / "harness" / "hooks"))


def cargar():
    especificacion = importlib.util.spec_from_file_location("sp_params", MODULO)
    modulo = importlib.util.module_from_spec(especificacion)
    especificacion.loader.exec_module(modulo)
    return modulo


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


VB_BASE = """Partial Class frmReview
    Private Sub Guardar()
        Dim x As Integer = 1
    End Sub

    Private Sub Buscar()
        Dim y As Integer = 2
    End Sub
End Class
"""

SP_INSUPD = """CREATE Proc [dbo].[ReviewInsUpd]
(
  @Parametros Varchar(8000),
  @Resul Varchar(8000) Output,
  @Validar Int = 0
)
As
Begin
  Exec SepararCadena 'V9', @Parametros, '|', @Valor9 OutPut  --> ReviewHeaderId
  Exec SepararCadena 'V21', @Parametros, '|', @Valor21 OutPut
  --Exec SepararCadena 'V30', @Parametros, '|', @Valor30 OutPut
  /* Exec SepararCadena 'V31', @Parametros, '|', @Valor31 OutPut */

  if @Validar=7 -- guardar
  begin
     Update ReviewHeader set NewField = @Valor21 where ReviewHeaderID = @Valor9
  end
  --If @Validar = 8
End
"""

SP_FILTROS = """CREATE Proc [dbo].[ReviewGetFilters]
As
Begin
  Exec SepararCadena 'V1', @Parametros, '|', @Valor1 OutPut
  if @Validar IN (4, 13) begin Select 1 end
End
"""

SP_FILTROS_INSITU = """CREATE Proc [dbo].[ReviewGetFiltersInsitu]
As
Begin
  Exec SepararCadena 'V1', @Parametros, '|', @Valor1 OutPut
  Exec SepararCadena 'V2', @Parametros, '|', @Valor2 OutPut
  if @Validar = 4 begin Select 1 end
End
"""


class BaseSp(unittest.TestCase):
    def setUp(self):
        self.modulo = cargar()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        _git(self.root, "init")
        _git(self.root, "config", "user.email", "t@t.t")
        _git(self.root, "config", "user.name", "t")
        self.procs = self.root / "db" / "Procedimiento"
        self.procs.mkdir(parents=True)
        self.escribir_sp("ReviewInsUpd.sql", SP_INSUPD)
        self.escribir_sp("ReviewGetFilters.sql", SP_FILTROS)
        self.escribir_sp("ReviewGetFiltersInsitu.sql", SP_FILTROS_INSITU)
        self.configurar(["db/Procedimiento"])
        self.vb = self.root / "frmReview.aspx.vb"
        self.vb.write_text(VB_BASE, encoding="utf-8")
        _git(self.root, "add", ".")
        _git(self.root, "commit", "-m", "base")

    def escribir_sp(self, nombre: str, texto: str, carpeta: Path | None = None) -> None:
        # Como los exporta SQL Server Management Studio: UTF-16 con BOM.
        (carpeta or self.procs).joinpath(nombre).write_bytes(texto.encode("utf-16"))

    def configurar(self, carpetas) -> None:
        reglas = {"perfil": "reviewsystemgfs", "checks_estructurales": ["sp_params"]}
        if carpetas is not None:
            reglas["sp_params"] = {"carpetas_sp": carpetas}
        (self.root / ".claude").mkdir(exist_ok=True)
        (self.root / ".claude" / "rules.json").write_text(json.dumps(reglas), encoding="utf-8")

    def en_guardar(self, *lineas: str) -> None:
        cuerpo = "".join(f"        {l}\n" for l in lineas)
        self.vb.write_text(VB_BASE.replace("        Dim x As Integer = 1\n",
                                           "        Dim x As Integer = 1\n" + cuerpo, 1),
                           encoding="utf-8")

    def correr(self, *archivos: Path):
        return self.modulo.run(self.root, list(archivos or [self.vb]), None)

    def errores(self, hallazgos):
        return [h for h in hallazgos if h["resultado"] == "fallo" and h["severidad"] == "error"]


class TestSpParams(BaseSp):
    def test_todo_coherente_no_produce_hallazgos(self):
        self.en_guardar('lConsulta.EjecutarSp("ReviewInsUpd", 7, "|V9=" + a + "|V21=" + b + "|")')
        self.assertEqual(self.correr(), [])

    def test_un_vn_que_el_sp_no_parsea_es_error_y_explica_el_silencio(self):
        self.en_guardar('lConsulta.EjecutarSp("ReviewInsUpd", 7, "|V9=" + a + "|V22=" + b + "|")')
        errores = self.errores(self.correr())
        self.assertEqual(len(errores), 1, errores)
        self.assertIn("V22", errores[0]["detalle"])
        self.assertIn("silencio", errores[0]["detalle"].lower())
        self.assertIn("frmReview.aspx.vb:4", errores[0]["detalle"])

    def test_un_separarcadena_comentado_no_cuenta_como_parseado(self):
        self.en_guardar('lConsulta.EjecutarSp("ReviewInsUpd", 7, "|V30=" + a + "|V31=" + b + "|")')
        detalles = " ".join(h["detalle"] for h in self.errores(self.correr()))
        self.assertIn("V30", detalles)
        self.assertIn("V31", detalles)

    def test_las_variantes_de_separarcadena_cuentan(self):
        # ReviewInsUpd parsea V8 con SepararCadenaxml (ISR 102840).
        self.escribir_sp("ReviewInsUpd.sql", SP_INSUPD.replace(
            "  --Exec SepararCadena 'V30'",
            "  Exec SepararCadenaxml 'V8', @Parametros, '|', @Valor8 OutPut\n  --Exec SepararCadena 'V30'"))
        self.en_guardar('lConsulta.EjecutarSp("ReviewInsUpd", 7, "|V8=" + a + "|")')
        self.assertEqual(self.correr(), [])

    def test_los_vn_ignorados_del_perfil_no_se_exigen(self):
        # V0 repite @Validar del lado VB; ningún SP de PrimusGFS lo parsea.
        reglas = json.loads((self.root / ".claude" / "rules.json").read_text(encoding="utf-8"))
        reglas["sp_params"]["vn_ignorados"] = ["v0"]
        (self.root / ".claude" / "rules.json").write_text(json.dumps(reglas), encoding="utf-8")
        self.en_guardar('lConsulta.EjecutarSp("ReviewInsUpd", 7, "|V0=7|V9=" + a + "|")')
        self.assertEqual(self.correr(), [])

    def test_sin_vn_ignorados_el_v0_si_se_exige(self):
        self.en_guardar('lConsulta.EjecutarSp("ReviewInsUpd", 7, "|V0=7|V9=" + a + "|")')
        self.assertTrue(any("V0" in h["detalle"] for h in self.errores(self.correr())))

    def test_la_ruta_del_sp_se_muestra_sin_puntos_relativos(self):
        fuera = tempfile.TemporaryDirectory()
        self.addCleanup(fuera.cleanup)
        self.escribir_sp("ReviewInsUpd.sql", SP_INSUPD, Path(fuera.name))
        relativa = Path("..") / Path(fuera.name).name
        self.configurar([str(relativa)])
        # La carpeta temporal hermana solo es alcanzable con '..' si comparten padre.
        if not (self.root / relativa).is_dir():
            self.skipTest("las carpetas temporales no son hermanas")
        self.en_guardar('lConsulta.EjecutarSp("ReviewInsUpd", 7, "|V22=" + a + "|")')
        detalle = self.errores(self.correr())[0]["detalle"]
        self.assertNotIn("..", detalle)

    def test_un_validar_sin_rama_es_error(self):
        self.en_guardar('lConsulta.EjecutarSp("ReviewInsUpd", 9, "|V9=" + a + "|")')
        errores = self.errores(self.correr())
        self.assertEqual(len(errores), 1, errores)
        self.assertIn("@Validar = 9", errores[0]["detalle"])

    def test_una_rama_comentada_no_cuenta(self):
        self.en_guardar('lConsulta.EjecutarSp("ReviewInsUpd", 8, "|V9=" + a + "|")')
        self.assertTrue(any("@Validar = 8" in h["detalle"] for h in self.errores(self.correr())))

    def test_validar_in_lista_cuenta_como_rama(self):
        self.en_guardar('lConsulta.EjecutarSp("ReviewGetFilters", 13, "|V1=" + a + "|")')
        self.assertEqual(self.correr(), [])

    def test_validar_no_literal_no_se_verifica(self):
        self.en_guardar('lConsulta.EjecutarSp("ReviewGetFilters", tipoCombo, "")')
        self.assertEqual(self.correr(), [])

    def test_validar_como_cadena_literal_se_verifica(self):
        self.en_guardar('lConsulta.EjecutarSp("ReviewInsUpd", "9", "")')
        self.assertTrue(any("@Validar = 9" in h["detalle"] for h in self.errores(self.correr())))

    def test_el_nombre_del_sp_se_compara_exacto_y_no_por_prefijo(self):
        # V2 lo parsea ReviewGetFiltersInsitu, no ReviewGetFilters.
        self.en_guardar('lConsulta.EjecutarSp("ReviewGetFilters", 4, "|V2=" + a + "|")')
        self.assertTrue(any("V2" in h["detalle"] for h in self.errores(self.correr())))

    def test_acepta_el_nombre_que_exporta_ssms(self):
        (self.procs / "ReviewInsUpd.sql").unlink()
        self.escribir_sp("dbo.ReviewInsUpd.StoredProcedure.sql", SP_INSUPD)
        self.en_guardar('lConsulta.EjecutarSp("ReviewInsUpd", 7, "|V9=" + a + "|")')
        self.assertEqual(self.correr(), [])

    def test_la_primera_carpeta_manda_sobre_una_copia_vieja(self):
        viejas = self.root / "ReviewSystem" / "Sps"
        viejas.mkdir(parents=True)
        self.escribir_sp("dbo.ReviewInsUpd.StoredProcedure.sql",
                         SP_INSUPD.replace("if @Validar=7", "if @Validar=1"), viejas)
        self.configurar(["db/Procedimiento", "ReviewSystem/Sps"])
        self.en_guardar('lConsulta.EjecutarSp("ReviewInsUpd", 7, "|V9=" + a + "|")')
        self.assertEqual(self.correr(), [])

    def test_si_no_esta_en_la_primera_se_busca_en_la_siguiente(self):
        otra = self.root / "otra"
        otra.mkdir()
        self.escribir_sp("SoloAqui.sql", "CREATE Proc SoloAqui As\n"
                         "Exec SepararCadena 'V1', @Parametros, '|', @Valor1 OutPut\n", otra)
        self.configurar(["db/Procedimiento", "otra"])
        self.en_guardar('lConsulta.EjecutarSp("SoloAqui", 1, "|V2=" + a + "|")')
        self.assertTrue(any("V2" in h["detalle"] for h in self.errores(self.correr())))

    def test_las_carpetas_aceptan_variables_de_entorno(self):
        self.configurar(["%CARPETA_SPS_TEST%"])
        self.en_guardar('lConsulta.EjecutarSp("ReviewInsUpd", 7, "|V22=" + a + "|")')
        with mock.patch.dict("os.environ", {"CARPETA_SPS_TEST": str(self.procs)}):
            self.assertTrue(self.errores(self.correr()))

    def test_un_sp_que_no_aparece_es_solo_warning(self):
        self.en_guardar('lConsulta.EjecutarSp("NoExiste", 1, "|V1=" + a + "|")')
        hallazgos = self.correr()
        self.assertTrue(hallazgos)
        self.assertTrue(all(h["severidad"] == "warning" for h in hallazgos))
        self.assertIn("NoExiste", hallazgos[0]["detalle"])

    def test_un_sp_sin_separarcadena_no_se_puede_verificar_y_es_warning(self):
        self.escribir_sp("OtroParseo.sql", "CREATE Proc OtroParseo As\nSelect 1\n")
        self.en_guardar('lConsulta.EjecutarSp("OtroParseo", 1, "|V1=" + a + "|")')
        hallazgos = self.correr()
        self.assertTrue(hallazgos)
        self.assertEqual(self.errores(hallazgos), [])

    def test_sin_carpetas_configuradas_es_error_check(self):
        self.configurar(None)
        self.en_guardar('lConsulta.EjecutarSp("ReviewInsUpd", 7, "|V9=" + a + "|")')
        hallazgos = self.correr()
        self.assertEqual([h["resultado"] for h in hallazgos], ["error_check"])
        self.assertIn("carpetas_sp", hallazgos[0]["detalle"])

    def test_sin_carpetas_y_sin_llamadas_nuevas_no_molesta(self):
        self.configurar(None)
        self.en_guardar("Dim z As Integer = 3")
        self.assertEqual(self.correr(), [])

    def test_una_carpeta_que_no_existe_se_avisa_y_se_usan_las_demas(self):
        self.configurar(["no/existe", "db/Procedimiento"])
        self.en_guardar('lConsulta.EjecutarSp("ReviewInsUpd", 7, "|V22=" + a + "|")')
        hallazgos = self.correr()
        self.assertTrue(any(h["resultado"] == "error_check" and "no/existe" in h["detalle"]
                            for h in hallazgos))
        self.assertTrue(self.errores(hallazgos))

    def test_cada_llamada_se_atribuye_sus_propios_vn(self):
        # Dos llamadas en el mismo método: V2 va solo a ReviewGetFiltersInsitu.
        self.en_guardar('lConsulta.EjecutarSp("ReviewGetFilters", 4, "|V1=" + a + "|")',
                        'lConsulta.EjecutarSp("ReviewGetFiltersInsitu", 4, "|V1=" + a + "|V2=" + b + "|")')
        self.assertEqual(self.correr(), [])

    def test_parametros_en_una_variable_se_toman_del_metodo(self):
        self.en_guardar('Dim parametros As String = "|V9=" + a + "|V22=" + b + "|"',
                        'Dim r = lConsulta.EjecutarSp("ReviewInsUpd", 7, parametros, ds, "")')
        self.assertTrue(any("V22" in h["detalle"] for h in self.errores(self.correr())))

    def test_los_vn_en_linea_de_otra_llamada_no_se_atribuyen_a_la_variable(self):
        # Forma de GetAuditHeaderAIReportLimit (frmReviewReport.aspx.vb) + una llamada nueva.
        self.en_guardar('Dim parametros As String = "|V1=" + a + "|"',
                        'Dim r = lConsulta.EjecutarSp("ReviewGetFilters", 4, parametros, ds, "")')
        _git(self.root, "commit", "-am", "viejo")
        texto = self.vb.read_text(encoding="utf-8")
        self.vb.write_text(texto.replace(
            '        Dim r = lConsulta.EjecutarSp("ReviewGetFilters", 4, parametros, ds, "")\n',
            '        Dim r = lConsulta.EjecutarSp("ReviewGetFilters", 4, parametros, ds, "")\n'
            '        r = lConsulta.EjecutarSp("ReviewInsUpd", 7, "|V9=" + x + "|V21=" + y + "|")\n'),
            encoding="utf-8")
        self.assertEqual(self.correr(), [])

    def test_cada_variable_lleva_sus_propios_vn(self):
        self.en_guardar('Dim parametros As String = "|V1=" + a + "|"',
                        'Dim p2 As String = "|V1=" + a + "|"',
                        'p2 = p2 + "|V2=" + b + "|"',
                        'p2 &= "|V3=" + c',
                        'Dim r = lConsulta.EjecutarSp("ReviewGetFilters", 4, parametros)',
                        'r = lConsulta.EjecutarSp("ReviewGetFiltersInsitu", 4, p2)')
        detalles = [h["detalle"] for h in self.errores(self.correr())]
        # V2 es de p2 y lo parsea Insitu; V3 tambien es de p2 y Insitu no lo parsea.
        self.assertEqual(len(detalles), 1, detalles)
        self.assertIn("V3", detalles[0])
        self.assertIn("ReviewGetFiltersInsitu", detalles[0])

    def test_un_sp_que_solo_tiene_validar_0_no_despacha_y_es_warning(self):
        # 38 SPs de PrimusGFS: "If @Validar = 0" solo arma @Resul; el SELECT corre siempre.
        self.escribir_sp("SinDespacho.sql", "CREATE Proc SinDespacho As\n"
                         "Exec SepararCadena 'V1', @Parametros, '|', @Valor1 OutPut\n"
                         "Select 1\nIf @Validar = 0 Set @Resul = 'ok'\n")
        self.en_guardar('lConsulta.EjecutarSp("SinDespacho", 1, "|V1=" + a + "|")')
        hallazgos = self.correr()
        self.assertEqual(self.errores(hallazgos), [])
        self.assertTrue(any("@Validar = 1" in h["detalle"] and h["severidad"] == "warning"
                            for h in hallazgos))

    def test_los_vn_de_otro_metodo_no_se_atribuyen(self):
        self.vb.write_text(VB_BASE.replace(
            "        Dim x As Integer = 1\n",
            '        Dim parametros As String = "|V22=" + b + "|"\n').replace(
            "        Dim y As Integer = 2\n",
            '        Dim parametros As String = "|V9=" + a + "|"\n'
            '        Dim r = lConsulta.EjecutarSp("ReviewInsUpd", 7, parametros)\n'),
            encoding="utf-8")
        self.assertEqual(self.correr(), [])

    def test_continuacion_de_linea(self):
        self.en_guardar('lConsulta.EjecutarSp("ReviewInsUpd", 7, _',
                        '    "|V9=" + a + "|V22=" + b + "|")')
        errores = self.errores(self.correr())
        self.assertTrue(any("V22" in h["detalle"] for h in errores))

    def test_una_llamada_comentada_no_cuenta(self):
        self.en_guardar("' lConsulta.EjecutarSp(\"ReviewInsUpd\", 9, \"|V22=\" + a + \"|\")")
        self.assertEqual(self.correr(), [])

    def test_el_codigo_viejo_no_se_revisa(self):
        # Una llamada incoherente que ya estaba en HEAD no es asunto de esta fase.
        self.en_guardar('lConsulta.EjecutarSp("ReviewInsUpd", 9, "|V22=" + a + "|")')
        _git(self.root, "commit", "-am", "viejo")
        texto = self.vb.read_text(encoding="utf-8")
        self.vb.write_text(texto.replace("        Dim y As Integer = 2\n",
                                         "        Dim y As Integer = 3\n"), encoding="utf-8")
        self.assertEqual(self.correr(), [])

    def test_un_vn_nuevo_en_una_llamada_vieja_si_se_revisa(self):
        self.en_guardar('Dim parametros As String = "|V9=" + a + "|"',
                        'Dim r = lConsulta.EjecutarSp("ReviewInsUpd", 7, parametros)')
        _git(self.root, "commit", "-am", "viejo")
        texto = self.vb.read_text(encoding="utf-8")
        self.vb.write_text(texto.replace('"|V9=" + a + "|"', '"|V9=" + a + "|V22=" + b + "|"'),
                           encoding="utf-8")
        self.assertTrue(any("V22" in h["detalle"] for h in self.errores(self.correr())))

    def test_ignora_archivos_que_no_son_vb_y_los_designer(self):
        otro = self.root / "frm.js"
        otro.write_text("var p = '|V99=' + x;\n", encoding="utf-8")
        designer = self.root / "frmReview.aspx.designer.vb"
        designer.write_text('EjecutarSp("ReviewInsUpd", 9, "|V99=")\n', encoding="utf-8")
        self.assertEqual(self.correr(otro, designer), [])


class TestConvencionVN(BaseSp):
    """Backlog: la cadena "VN=<SP>|V0=<validar>|..." que despachan LlenaCombos/LlenaGrid.

    Cerca de la mitad de las llamadas reales (23 en Scripts/*.js y 2 en VB) no pasan
    por un EjecutarSp con el nombre literal: el SP y el @Validar van en la cadena."""

    def setUp(self):
        super().setUp()
        reglas = json.loads((self.root / ".claude" / "rules.json").read_text(encoding="utf-8"))
        reglas["sp_params"]["vn_ignorados"] = ["V0"]
        (self.root / ".claude" / "rules.json").write_text(json.dumps(reglas), encoding="utf-8")
        self.js = self.root / "Scripts" / "frmReview.js"
        self.js.parent.mkdir()
        self.js.write_text("function cargar() {\n    var x = 1;\n}\n", encoding="utf-8")
        _git(self.root, "add", ".")
        _git(self.root, "commit", "-m", "js")

    def en_js(self, *lineas: str) -> list[dict]:
        cuerpo = "".join(f"    {l}\n" for l in lineas)
        self.js.write_text("function cargar() {\n    var x = 1;\n" + cuerpo + "}\n",
                           encoding="utf-8")
        return self.modulo.run(self.root, [self.js], None)

    def test_js_coherente_no_produce_hallazgos(self):
        self.assertEqual(self.en_js('var p = "VN=ReviewInsUpd|V0=7|V9=" + a + "|V21=" + b + "|";'),
                         [])

    def test_js_un_vn_que_el_sp_no_parsea_es_error(self):
        errores = self.errores(self.en_js(
            "var p = 'VN=ReviewInsUpd|V0=7|V9=' + $('#x').val() + '|V22=' + b + '|';"))
        self.assertEqual(len(errores), 1, errores)
        self.assertIn("V22", errores[0]["detalle"])
        self.assertIn("frmReview.js:3", errores[0]["detalle"])

    def test_js_un_validar_sin_rama_es_error(self):
        errores = self.errores(self.en_js('var p = "VN=ReviewInsUpd|V0=9|V9=" + a + "|";'))
        self.assertTrue(any("@Validar = 9" in h["detalle"] for h in errores))

    def test_js_validar_no_literal_no_se_verifica(self):
        self.assertEqual(self.en_js('var p = "VN=ReviewGetFilters|V0=" + tipo + "|V1=" + a;'),
                         [])

    def test_js_comentado_no_cuenta(self):
        self.assertEqual(self.en_js('// var p = "VN=ReviewInsUpd|V0=9|V22=" + a;',
                                    '/* var q = "VN=ReviewInsUpd|V0=9|V23=" + a; */'), [])

    def test_js_un_sp_que_no_aparece_es_warning(self):
        hallazgos = self.en_js('var p = "VN=NoExiste|V0=1|V1=" + a + "|";')
        self.assertTrue(hallazgos)
        self.assertEqual(self.errores(hallazgos), [])

    def test_js_lo_viejo_no_se_revisa(self):
        self.en_js('var p = "VN=ReviewInsUpd|V0=9|V22=" + a;')
        _git(self.root, "commit", "-am", "viejo")
        self.js.write_text(self.js.read_text(encoding="utf-8").replace("var x = 1;",
                                                                        "var x = 2;"),
                           encoding="utf-8")
        self.assertEqual(self.modulo.run(self.root, [self.js], None), [])

    def test_vb_con_la_convencion_vn_tambien_se_revisa(self):
        self.en_guardar('Dim p As String = "VN=ReviewInsUpd|V0=7|V9=" + a + "|V22=" + b + "|"')
        errores = self.errores(self.correr())
        self.assertTrue(any("V22" in h["detalle"] for h in errores))

    def test_vb_vn_en_un_comentario_no_cuenta(self):
        self.en_guardar("' Dim p As String = \"VN=ReviewInsUpd|V0=9|V22=\"")
        self.assertEqual(self.correr(), [])


if __name__ == "__main__":
    unittest.main()

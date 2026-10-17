"""Perfil editornotificaciones: app .NET 10 + Vue 2 para editar notificaciones por secciones."""
import importlib.util
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parents[1]
PERFIL = RAIZ / "profiles" / "editornotificaciones"
sys.path.insert(0, str(RAIZ / "harness" / "hooks"))
from lib import contracts  # noqa: E402


def regla(rules: dict, regla_id: str) -> re.Pattern:
    datos = next(r for r in rules["prohibido"] if r["id"] == regla_id)
    return re.compile(datos["patron"])


def cargar_check(nombre: str):
    ruta = PERFIL / "checks" / f"{nombre}.py"
    especificacion = importlib.util.spec_from_file_location(f"perfil_{nombre}", ruta)
    modulo = importlib.util.module_from_spec(especificacion)
    especificacion.loader.exec_module(modulo)
    return modulo


def frontmatter(texto: str) -> dict:
    bloque = re.match(r"^---\n(.*?)\n---\n", texto, re.DOTALL)
    campos = {}
    for linea in (bloque.group(1).splitlines() if bloque else []):
        if re.match(r"^\w+:", linea):
            clave, _, valor = linea.partition(":")
            campos[clave.strip()] = valor.strip()
    return campos


class TestReglasDelPerfil(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = json.loads((PERFIL / "rules.json").read_text(encoding="utf-8"))

    def test_es_el_perfil_correcto_y_los_patrones_compilan(self):
        self.assertEqual(self.rules["perfil"], "editornotificaciones")
        for r in self.rules["prohibido"]:
            with self.subTest(regla=r["id"]):
                re.compile(r["patron"])
                self.assertGreater(len(r["mensaje"]), 15)

    def test_grupos_y_checks_estructurales_existen(self):
        for grupo, miembros in self.rules["grupos"].items():
            with self.subTest(grupo=grupo):
                _, desconocidos = contracts.resolve_check_names(miembros, self.rules)
                self.assertEqual(desconocidos, [])
        for check in self.rules["checks_estructurales"]:
            with self.subTest(check=check):
                self.assertTrue((PERFIL / "checks" / f"{check}.py").is_file())

    def test_no_sql_exec_detecta_ejecuciones_y_no_marca_lecturas(self):
        rx = regla(self.rules, "no_sql_exec")
        for malo in ("await conn.ExecuteAsync(sql, p);", "cmd.ExecuteNonQuery();",
                     "var n = cmd.ExecuteScalar();", "using var bulk = new SqlBulkCopy(conn);"):
            with self.subTest(malo=malo):
                self.assertTrue(rx.search(malo))
        for bueno in ("var filas = await conn.QueryAsync<SectionContentRow>(sql);",
                      "await db.SaveChangesAsync(ct);",
                      "sb.AppendLine(\"UPDATE dbo.SectionContent SET Content = @c\");"):
            with self.subTest(bueno=bueno):
                self.assertIsNone(rx.search(bueno))

    def test_no_sp_con_escritura_detecta_el_sp_que_actualiza_el_historial(self):
        rx = regla(self.rules, "no_sp_con_escritura")
        self.assertTrue(rx.search('const string Sp = "dbo.CSGetCustomerNotificationDetail";'))
        self.assertIsNone(rx.search('const string Sp = "dbo.CSGetTemplateNotificationConfiguration";'))

    def test_no_ddl_detecta_ddl_y_no_marca_dml_del_generador(self):
        rx = regla(self.rules, "no_ddl")
        self.assertTrue(rx.search('sb.AppendLine("ALTER TABLE dbo.SectionContent ADD x int");'))
        self.assertTrue(rx.search('"create procedure dbo.X as select 1"'))
        self.assertIsNone(rx.search('sb.AppendLine("UPDATE dbo.SectionContent SET Content = \'x\'");'))
        self.assertIsNone(rx.search("migrationBuilder.CreateTable(name: \"Borradores\");"))

    def test_no_credenciales_detecta_password_literal_y_no_la_variable(self):
        rx = regla(self.rules, "no_credenciales")
        self.assertTrue(rx.search('"Server=x;User ID=u;Password=Secreta123;"'))
        self.assertTrue(rx.search('var cs = "...;Pwd=abc;";'))
        self.assertIsNone(rx.search('var pwd = Environment.GetEnvironmentVariable("MSSQL_PASSWORD");'))
        self.assertIsNone(rx.search('builder.Password = config["MSSQL_PASSWORD"];'))

    def test_ids_tipo_fijos_es_warning_y_detecta_los_tipos_especiales(self):
        datos = next(r for r in self.rules["prohibido"] if r["id"] == "ids_tipo_fijos")
        self.assertEqual(datos["severidad"], "warning")
        rx = re.compile(datos["patron"])
        self.assertTrue(rx.search("if (tipo == 1747 || tipo == 1924)"))
        self.assertIsNone(rx.search("const int MaxFilas = 200;"))

    def test_no_vue3_detecta_apis_de_vue3_y_no_marca_vue2(self):
        rx = regla(self.rules, "no_vue3")
        for malo in ("createApp(App).mount('#app')", "import ElementPlus from 'element-plus'",
                     '<my-input v-model:title="t" />', "const router = createRouter({})"):
            with self.subTest(malo=malo):
                self.assertTrue(rx.search(malo))
        for bueno in ("new Vue({ router, render: h => h(App) }).$mount('#app')",
                      "import ElementUI from 'element-ui'", '<el-input v-model="nombre" />'):
            with self.subTest(bueno=bueno):
                self.assertIsNone(rx.search(bueno))

    def test_no_v_html_detecta_v_html(self):
        rx = regla(self.rules, "no_v_html")
        self.assertTrue(rx.search('<div v-html="contenido"></div>'))
        self.assertIsNone(rx.search('<iframe sandbox="" :srcdoc="html"></iframe>'))

    def test_no_new_deps_vigila_package_json_y_csproj(self):
        vigilados = {v.lower() for v in self.rules["no_new_deps"]["vigilar"]}
        self.assertIn("package.json", vigilados)
        self.assertTrue(any(v.endswith(".csproj") for v in vigilados))
        rx = re.compile(self.rules["no_new_deps"]["patron"])
        self.assertTrue(rx.search('<PackageReference Include="Dapper" Version="2.1.35" />'))
        self.assertTrue(rx.search('    "axios": "^1.6.8",'))
        self.assertIsNone(rx.search('    "build": "vite build",'))


class TestChecksEstructurales(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_dotnet_build_se_omite_si_la_fase_no_toco_el_backend(self):
        check = cargar_check("dotnet_build")
        hallazgos = check.run(self.root, [self.root / "src" / "Web" / "src" / "App.vue"], {})
        self.assertEqual([h["resultado"] for h in hallazgos], ["ok"])

    def test_dotnet_build_reporta_error_check_sin_dotnet(self):
        check = cargar_check("dotnet_build")
        with mock.patch.object(check.shutil, "which", return_value=None):
            hallazgos = check.run(self.root, [self.root / "src" / "Api" / "Program.cs"], {})
        self.assertEqual(hallazgos[0]["resultado"], "error_check")

    def test_web_build_se_omite_si_la_fase_no_toco_el_frontend(self):
        check = cargar_check("web_build")
        hallazgos = check.run(self.root, [self.root / "src" / "Api" / "Program.cs"], {})
        self.assertEqual([h["resultado"] for h in hallazgos], ["ok"])

    def test_web_build_reporta_error_check_sin_npm(self):
        check = cargar_check("web_build")
        with mock.patch.object(check.shutil, "which", return_value=None):
            hallazgos = check.run(self.root, [self.root / "src" / "Web" / "src" / "App.vue"], {})
        self.assertEqual(hallazgos[0]["resultado"], "error_check")


class TestAgentesDelPerfil(unittest.TestCase):
    def leer(self, nombre: str) -> str:
        return (PERFIL / "agents" / f"{nombre}.md").read_text(encoding="utf-8")

    def test_los_dos_agentes_tienen_frontmatter_con_su_nombre(self):
        for nombre in ("agent-notif-api", "agent-notif-web"):
            with self.subTest(agente=nombre):
                campos = frontmatter(self.leer(nombre))
                self.assertEqual(campos.get("name"), nombre)
                self.assertIn("description", campos)

    def test_los_dos_agentes_operan_bajo_el_harness(self):
        for nombre in ("agent-notif-api", "agent-notif-web"):
            texto = self.leer(nombre)
            for concepto in ("ticket_context.json", "historial_fallos",
                             "herramientas_permitidas", "resultado.md"):
                with self.subTest(agente=nombre, concepto=concepto):
                    self.assertIn(concepto, texto)

    def test_el_agente_api_conoce_las_reglas_criticas_del_dominio(self):
        texto = self.leer("agent-notif-api")
        for concepto in ("CSGetCustomerNotificationDetail", "XACT_ABORT", "SCOPE_IDENTITY",
                         "NotificationTypeID", "analisis_modelo_notificaciones.md",
                         "#Rollback_Backup_Table", "deshacer_<ticket>.sql",
                         "solo_dev_<ticket>.sql", "IF NOT EXISTS", "BuildType = 0"):
            with self.subTest(concepto=concepto):
                self.assertIn(concepto, texto)

    def test_el_agente_web_conoce_el_visor_y_el_stack(self):
        texto = self.leer("agent-notif-web")
        for concepto in ("Element UI", "sandbox", "srcdoc", "Vue 2.7", "Node 16",
                         "Basar en un tipo Legacy", "solo dev"):
            with self.subTest(concepto=concepto):
                self.assertIn(concepto, texto)


if __name__ == "__main__":
    unittest.main()

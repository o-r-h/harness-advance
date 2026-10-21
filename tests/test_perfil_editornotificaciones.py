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

    def test_web_contraste_se_omite_si_la_fase_no_toco_el_frontend(self):
        check = cargar_check("web_contraste")
        hallazgos = check.run(self.root, [self.root / "src" / "Api" / "Program.cs"], {})
        self.assertEqual([h["resultado"] for h in hallazgos], ["ok"])

    def test_web_contraste_reporta_error_check_sin_node(self):
        check = cargar_check("web_contraste")
        with mock.patch.object(check.shutil, "which", return_value=None):
            hallazgos = check.run(self.root, [self.root / "src" / "Web" / "src" / "App.vue"], {})
        self.assertEqual(hallazgos[0]["resultado"], "error_check")

    def test_web_contraste_reporta_error_check_sin_navegador(self):
        check = cargar_check("web_contraste")
        vite = self.root / "src" / "Web" / "node_modules" / "vite" / "bin" / "vite.js"
        vite.parent.mkdir(parents=True)
        vite.write_text("", encoding="utf-8")
        with mock.patch.object(check, "_navegador", return_value=None), \
                mock.patch.object(check.shutil, "which", return_value="node"):
            hallazgos = check.run(self.root, [self.root / "src" / "Web" / "src" / "App.vue"], {})
        self.assertEqual(hallazgos[0]["resultado"], "error_check")
        self.assertIn("Chrome", hallazgos[0]["detalle"])

    def test_web_contraste_falla_con_el_placeholder_sin_capturar(self):
        # Caso real de ISR-111269 (TablaValoresEjemplo.vue): placeholder de Element #c0c4cc = 1.75:1.
        check = cargar_check("web_contraste")
        bajo = {"tipo": "placeholder", "texto": "Sin capturar", "elemento": "td > div.el-input > input#valor-CustomerName",
                "color": "#c0c4cc", "fondo": "#ffffff", "tam": "13px", "peso": "400", "ratio": 1.75, "minimo": 4.5}
        resultado = {"estados": [
            {"nombre": "modo lectura · visor correo", "alcanzado": True, "medidos": 190, "bajos": [bajo]},
            {"nombre": "modo edición sin cambios", "alcanzado": True, "medidos": 150, "bajos": [dict(bajo)]}]}
        hallazgos = check._reporte(resultado)
        self.assertEqual(len(hallazgos), 1)
        self.assertEqual((hallazgos[0]["resultado"], hallazgos[0]["severidad"]), ("fallo", "error"))
        for dato in ("Sin capturar", "#c0c4cc", "#ffffff", "1.75:1", "input#valor-CustomerName",
                     "modo lectura · visor correo, modo edición sin cambios"):
            with self.subTest(dato=dato):
                self.assertIn(dato, hallazgos[0]["detalle"])

    def test_web_contraste_aprueba_y_avisa_estados_no_alcanzados(self):
        check = cargar_check("web_contraste")
        resultado = {"estados": [
            {"nombre": "modo lectura · visor correo", "alcanzado": True, "medidos": 190, "bajos": []},
            {"nombre": "conflicto en modo edición", "alcanzado": False, "error": "no apareció: botón \"Continuar\""}]}
        hallazgos = {h["id"]: h for h in check._reporte(resultado)}
        self.assertEqual(hallazgos["web_contraste"]["resultado"], "ok")
        cobertura = hallazgos["web_contraste_cobertura"]
        self.assertEqual((cobertura["resultado"], cobertura["severidad"]), ("fallo", "warning"))
        self.assertIn("Continuar", cobertura["detalle"])

    def test_web_contraste_api_simulada_sigue_el_contrato_de_borradores(self):
        from urllib.parse import urlparse
        check = cargar_check("web_contraste")
        api = check.ApiSimulada(check.RECURSOS / "api")
        status, _, _ = api.responder("GET", urlparse("/api/borradores/1223"), None)
        self.assertEqual(status, 404)
        status, datos, cabeceras = api.responder("PUT", urlparse("/api/borradores/1223"), {"cambios": [
            {"campo": "Asunto", "lang": 2, "sectionContentId": None, "valor": "Nuevo"},
            {"campo": "EstiloExtra", "lang": 2, "sectionContentId": None, "valor": ""}]})
        self.assertEqual((status, cabeceras["X-Borrador-Nuevo"]), (200, "true"))
        self.assertEqual([c["campo"] for c in datos["borrador"]["cambios"]], ["Asunto"])
        campos = {(b["campo"], b["lang"]) for b in datos["borrador"]["base"]}
        self.assertIn(("ContenidoSeccion", 2), campos)
        api.escenario({"borrador": "conflicto"})
        _, lista, _ = api.responder("GET", urlparse("/api/borradores"), None)
        self.assertTrue(lista[0]["tieneConflictos"])

    def test_web_contraste_api_simulada_sigue_el_contrato_de_componentes(self):
        # Ticket 5: pantalla 3 (sección compartida 3) y el aviso de componentes de la pantalla 1.
        from urllib.parse import urlparse
        check = cargar_check("web_contraste")
        api = check.ApiSimulada(check.RECURSOS / "api")
        seccion = "/api/componentes/seccion/3"
        status, datos, _ = api.responder("GET", urlparse(seccion), None)
        self.assertEqual(status, 200)
        self.assertIsNone(datos["borrador"])
        # buildType viene de la API en cada uso: hay tipos Legacy (0) para la marca de la pantalla 3.
        self.assertEqual({u["buildType"] for u in datos["impacto"]["usos"]}, {0, 1})
        self.assertEqual(api.responder("GET", urlparse(seccion + "/borrador"), None)[0], 404)
        self.assertEqual(api.responder("GET", urlparse("/api/componentes/borradores?tipoId=1223"), None)[1], [])

        # Validar sin guardar: CSS fuera de CSS2 → advertencia css2; el texto de Masterdb no la trae.
        css3 = '<td class="notificacion-cabecera" style="box-shadow:0 0 2px #000">X</td>'
        status, validado, _ = api.responder("POST", urlparse(seccion + "/validar"), {"valor": css3})
        self.assertEqual((status, validado["tieneCambio"], validado["conBorrador"]), (200, True, False))
        self.assertIn("css2", [v["codigo"] for v in validado["validaciones"]])
        _, igual, _ = api.responder("POST", urlparse(seccion + "/validar"), {"valor": datos["componente"]["valor"]})
        self.assertNotIn("css2", [v["codigo"] for v in igual["validaciones"]])
        self.assertEqual(api.responder("POST", urlparse(seccion + "/validar"), {})[0], 400)
        self.assertIsNone(api.borrador_componente, "validar no debe guardar")

        status, guardado, cabeceras = api.responder("PUT", urlparse(seccion + "/borrador"), {"valor": css3})
        self.assertEqual((status, cabeceras["X-Borrador-Nuevo"]), (200, "true"))
        self.assertTrue(guardado["borrador"]["tieneCambio"])
        self.assertIsNone(guardado["conflicto"])
        _, lista, _ = api.responder("GET", urlparse("/api/componentes/borradores?tipoId=1223"), None)
        self.assertEqual((lista[0]["clase"], lista[0]["id"], lista[0]["tieneConflicto"]), ("Seccion", 3, False))

        api.escenario({"componente": "conflicto"})
        _, conflicto, _ = api.responder("GET", urlparse(seccion + "/borrador"), None)
        self.assertEqual(conflicto["conflicto"]["motivo"], "ValorCambiado")
        _, resuelto, _ = api.responder("POST", urlparse(seccion + "/borrador/conflictos/resolver"),
                                       {"accion": "tomarActual"})
        self.assertIsNone(resuelto["conflicto"])
        self.assertEqual(api.responder("DELETE", urlparse(seccion + "/borrador"), None)[0], 204)
        self.assertEqual(api.responder("GET", urlparse("/api/componentes/seccion/9/impacto"), None)[0], 404)

    def test_web_contraste_recorre_la_pantalla_3_y_el_aviso_de_componentes(self):
        recorrido = (PERFIL / "checks" / "web_contraste" / "recorrido.js").read_text(encoding="utf-8")
        for estado in ("pantalla 1 · aviso de componentes compartidos con borrador",
                       "pantalla 3 · lectura con impacto y tipos Legacy",
                       "pantalla 3 · advertencia CSS2 antes de guardar",
                       "pantalla 3 · diálogo \"Guardar en el original\" (N)",
                       "pantalla 3 · \"Ver en el visor\" de un tipo afectado",
                       "pantalla 3 · conflicto con Masterdb"):
            with self.subTest(estado=estado):
                self.assertIn("estado('" + estado + "'", recorrido)


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

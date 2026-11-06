"""Perfil crud-api: ejercicio de una API CRUD de notas (.NET 10 + EF Core + SQLite)."""
import importlib.util
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parents[1]
PERFIL = RAIZ / "profiles" / "crud-api"
sys.path.insert(0, str(RAIZ / "harness" / "hooks"))
from lib import checks, contracts  # noqa: E402


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
        self.assertEqual(self.rules["perfil"], "crud-api")
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

    def test_no_sql_exec_detecta_ejecuciones_y_no_marca_ef_core(self):
        rx = regla(self.rules, "no_sql_exec")
        for malo in ("await conn.ExecuteAsync(sql, p);", "cmd.ExecuteNonQuery();",
                     "var n = cmd.ExecuteScalar();", "using var bulk = new SqlBulkCopy(conn);"):
            with self.subTest(malo=malo):
                self.assertTrue(rx.search(malo))
        for bueno in ("await db.SaveChangesAsync(ct);",
                      "var notas = await db.Notas.ToListAsync(ct);",
                      "sb.AppendLine(\"UPDATE dbo.Notas SET Titulo = @t\");"):
            with self.subTest(bueno=bueno):
                self.assertIsNone(rx.search(bueno))

    def test_no_credenciales_detecta_password_literal_y_no_la_variable(self):
        rx = regla(self.rules, "no_credenciales")
        self.assertTrue(rx.search('"Server=x;User ID=u;Password=Secreta123;"'))
        self.assertTrue(rx.search('var cs = "...;Pwd=abc;";'))
        self.assertTrue(rx.search('appsettings.json con "Password": "abc123"'))
        self.assertIsNone(rx.search('var pwd = Environment.GetEnvironmentVariable("DB_PASSWORD");'))
        self.assertIsNone(rx.search('builder.Password = config["DB_PASSWORD"];'))

    def test_no_guid_cliente_es_warning_y_detecta_guid_en_el_servidor(self):
        datos = next(r for r in self.rules["prohibido"] if r["id"] == "no_guid_cliente")
        self.assertEqual(datos["severidad"], "warning")
        rx = re.compile(datos["patron"])
        self.assertTrue(rx.search("nota.Id = Guid.NewGuid();"))
        self.assertIsNone(rx.search('var etiqueta = "guid-fijo-de-ejemplo";'))

    def test_no_new_deps_vigila_los_csproj_y_detecta_package_reference(self):
        vigilados = {v.lower() for v in self.rules["no_new_deps"]["vigilar"]}
        self.assertTrue(any(v.endswith(".csproj") for v in vigilados))
        rx = re.compile(self.rules["no_new_deps"]["patron"])
        self.assertTrue(rx.search('<PackageReference Include="Serilog" Version="4.0.0" />'))
        self.assertIsNone(rx.search('<TargetFramework>net10.0</TargetFramework>'))


class TestChecksEstructurales(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_dotnet_build_se_omite_si_la_fase_no_toco_el_backend(self):
        check = cargar_check("dotnet_build")
        hallazgos = check.run(self.root, [self.root / "docs" / "nota.md"], {})
        self.assertEqual([h["resultado"] for h in hallazgos], ["ok"])

    def test_dotnet_build_reporta_error_check_sin_dotnet(self):
        check = cargar_check("dotnet_build")
        with mock.patch.object(check.shutil, "which", return_value=None):
            hallazgos = check.run(self.root, [self.root / "src" / "NotasApi" / "Program.cs"], {})
        self.assertEqual(hallazgos[0]["resultado"], "error_check")


class TestAgenteDelPerfil(unittest.TestCase):
    def test_tiene_frontmatter_con_su_nombre(self):
        texto = (PERFIL / "agents" / "agent-api.md").read_text(encoding="utf-8")
        campos = frontmatter(texto)
        self.assertEqual(campos.get("name"), "agent-api")
        self.assertIn("description", campos)

    def test_operan_bajo_el_harness(self):
        texto = (PERFIL / "agents" / "agent-api.md").read_text(encoding="utf-8")
        for concepto in ("ticket_context.json", "historial_fallos",
                         "herramientas_permitidas", "resultado.md", "dotnet_build"):
            with self.subTest(concepto=concepto):
                self.assertIn(concepto, texto)

    def test_conoce_el_contrato_del_recurso_y_el_stack(self):
        texto = (PERFIL / "agents" / "agent-api.md").read_text(encoding="utf-8")
        for concepto in ("EF Core", "SQLite", "xUnit", "/api/notas", "204", "Location"):
            with self.subTest(concepto=concepto):
                self.assertIn(concepto, texto)


if __name__ == "__main__":
    unittest.main()

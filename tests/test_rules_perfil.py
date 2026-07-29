import json
import re
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "harness" / "hooks"))
from lib import contracts  # noqa: E402

RULES_PATH = RAIZ / "profiles" / "reviewsystemgfs" / "rules.json"


class TestRulesDelPerfil(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = json.loads(RULES_PATH.read_text(encoding="utf-8"))

    def test_todos_los_patrones_compilan(self):
        for regla in self.rules["prohibido"]:
            with self.subTest(regla=regla["id"]):
                re.compile(regla["patron"])

    def test_audit_comments_y_no_new_deps_son_error(self):
        self.assertEqual(self.rules["audit_comments"]["severidad"], "error")
        self.assertEqual(self.rules["no_new_deps"]["severidad"], "error")

    def test_los_grupos_solo_referencian_checks_existentes(self):
        for grupo, miembros in self.rules["grupos"].items():
            with self.subTest(grupo=grupo):
                _, desconocidos = contracts.resolve_check_names(miembros, self.rules)
                self.assertEqual(desconocidos, [])

    def test_cada_regla_prohibida_tiene_mensaje_util(self):
        for regla in self.rules["prohibido"]:
            with self.subTest(regla=regla["id"]):
                self.assertGreater(len(regla["mensaje"]), 15)

    def test_no_async_detecta_await_en_vb_y_no_marca_codigo_valido(self):
        regla = next(r for r in self.rules["prohibido"] if r["id"] == "no_async")
        rx = re.compile(regla["patron"])
        self.assertTrue(rx.search("Dim x = Await LlamarApi()"))
        self.assertIsNone(rx.search("Dim awaited As String = \"ok\""))

    def test_no_raw_sql_detecta_select_inline_y_no_marca_ejecutarsp(self):
        regla = next(r for r in self.rules["prohibido"] if r["id"] == "no_raw_sql")
        rx = re.compile(regla["patron"])
        self.assertTrue(rx.search('Dim cmd As New SqlCommand("SELECT * FROM ReviewHeader")'))
        self.assertIsNone(rx.search('objRet = lConsulta.EjecutarSp("ReviewGetFilters", 4, p)'))

    def test_no_fetch_detecta_fetch_y_no_marca_consultardatos(self):
        regla = next(r for r in self.rules["prohibido"] if r["id"] == "no_fetch")
        rx = re.compile(regla["patron"])
        self.assertTrue(rx.search("fetch('/api/x')"))
        self.assertIsNone(rx.search("Azzule.ConsultarDatos({ url: 'x.aspx' })"))


if __name__ == "__main__":
    unittest.main()

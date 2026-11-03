import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DEPLOY = (RAIZ / "deploy.ps1").read_text(encoding="utf-8")


class TestDeploy(unittest.TestCase):
    def test_deploy_llama_a_registrar_hooks(self):
        for pieza in ("registrar_hooks.py", "--settings", "--hooks-dir", "$LASTEXITCODE"):
            self.assertIn(pieza, DEPLOY)

    def test_deploy_ya_no_pisa_un_respaldo_fijo(self):
        self.assertNotIn('"$Settings.bak"', DEPLOY)

    def test_deploy_tiene_el_switch_SinHooks(self):
        self.assertIn("[switch]$SinHooks", DEPLOY)

    def test_registrar_hooks_no_se_despliega(self):
        self.assertTrue((RAIZ / "registrar_hooks.py").is_file())
        self.assertEqual(list((RAIZ / "harness").rglob("registrar_hooks.py")), [])


if __name__ == "__main__":
    unittest.main()

import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "harness" / "hooks"))
from lib import contracts, state  # noqa: E402

FASE = {"id": "fase_1", "titulo": "Agregar campo", "max_reintentos": 3,
        "prueba_manual": {"requerida": True}}


class TestMaquinaDeEstados(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def abrir(self):
        return state.abrir_fase(self.root, "ISR-110722", FASE)

    def test_abrir_fase_arranca_en_intento_1_y_en_ejecucion(self):
        estado = self.abrir()
        self.assertEqual(estado["intento_actual"], 1)
        self.assertEqual(estado["estado"], "en_ejecucion")
        self.assertEqual(estado["max_reintentos"], 3)
        self.assertEqual(estado["historial_fallos"], [])
        self.assertEqual(contracts.validate_fase_state(estado), [])

    def test_abrir_fase_es_idempotente(self):
        self.abrir()
        state.registrar_fallo(self.root, "ISR-110722", "fase_1", "check", "designer_sync falló")
        estado = self.abrir()
        self.assertEqual(estado["intento_actual"], 2)

    def test_registrar_fallo_incrementa_el_intento_y_deja_en_correccion(self):
        self.abrir()
        estado = state.registrar_fallo(self.root, "ISR-110722", "fase_1",
                                       "check", "designer_sync falló")
        self.assertEqual(estado["intento_actual"], 2)
        self.assertEqual(estado["estado"], "en_correccion")
        self.assertEqual(estado["historial_fallos"][0]["origen"], "check")
        self.assertEqual(estado["historial_fallos"][0]["intento"], 1)

    def test_al_agotar_los_reintentos_escala_y_no_pasa_del_maximo(self):
        self.abrir()
        for i in range(3):
            estado = state.registrar_fallo(self.root, "ISR-110722", "fase_1",
                                           "esceptico", f"rechazo {i}")
        self.assertEqual(estado["estado"], "escalado")
        self.assertEqual(estado["intento_actual"], 3)
        self.assertEqual(len(estado["historial_fallos"]), 3)
        self.assertEqual(contracts.validate_fase_state(estado), [])

    def test_una_fase_escalada_no_acepta_mas_fallos(self):
        self.abrir()
        for i in range(3):
            state.registrar_fallo(self.root, "ISR-110722", "fase_1", "check", f"x{i}")
        with self.assertRaises(state.TransicionInvalida):
            state.registrar_fallo(self.root, "ISR-110722", "fase_1", "check", "uno más")

    def test_registrar_fallo_guarda_el_origen_humano(self):
        self.abrir()
        estado = state.registrar_fallo(self.root, "ISR-110722", "fase_1", "humano",
                                       "falló en el paso 3: el campo volvió vacío")
        self.assertEqual(estado["historial_fallos"][0]["origen"], "humano")

    def test_rechaza_un_origen_desconocido(self):
        self.abrir()
        with self.assertRaises(state.TransicionInvalida):
            state.registrar_fallo(self.root, "ISR-110722", "fase_1", "intuicion", "porque sí")

    def test_aprobar_fase_deja_estado_aprobada(self):
        self.abrir()
        estado = state.aprobar_fase(self.root, "ISR-110722", "fase_1")
        self.assertEqual(estado["estado"], "aprobada")

    def test_no_se_puede_aprobar_una_fase_escalada(self):
        self.abrir()
        for i in range(3):
            state.registrar_fallo(self.root, "ISR-110722", "fase_1", "check", f"x{i}")
        with self.assertRaises(state.TransicionInvalida):
            state.aprobar_fase(self.root, "ISR-110722", "fase_1")

    def test_set_estado_rechaza_un_estado_fuera_del_contrato(self):
        self.abrir()
        with self.assertRaises(state.TransicionInvalida):
            state.set_estado(self.root, "ISR-110722", "fase_1", "meditando")

    def test_leer_fase_devuelve_none_si_no_existe(self):
        self.assertIsNone(state.leer_fase(self.root, "ISR-110722", "fase_9"))


if __name__ == "__main__":
    unittest.main()

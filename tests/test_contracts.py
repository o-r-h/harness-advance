import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "harness" / "hooks"))
from lib import contracts  # noqa: E402

CONTEXTO_OK = {
    "ticket_id": "ISR-110722",
    "nroticket": "110722",
    "desarrollador": "OMAR RODRIGUEZ",
    "fecha": "28-07-2026",
    "perfil": "reviewsystemgfs",
}

PLAN_OK = {
    "ticket_id": "ISR-110722",
    "perfil": "reviewsystemgfs",
    "generado_por": "task-planner-v3",
    "fases": [{
        "id": "fase_1",
        "titulo": "Agregar campo de comentario en Other Q",
        "pasos": ["Agregar el HiddenField", "Guardar vía SP"],
        "anclajes": [{"ref": "frmReviewReport.aspx.vb:412", "confianza": "verificado"}],
        "criterio_exito": "El comentario se guarda y se relee al reabrir la review",
        "checks_deterministas": ["audit_comments", "fw35_syntax"],
        "prueba_manual": {"requerida": True, "url": "frmReviewReport.aspx",
                          "datos": "review 4471, idioma EN"},
        "herramientas_permitidas": ["read", "edit"],
        "max_reintentos": 3,
        "depende_de": [],
    }],
}

REGLAS_OK = {
    "perfil": "reviewsystemgfs",
    "prohibido": [{"id": "no_async", "archivos": [".vb"], "severidad": "error",
                   "patron": r"\b(Async|Await)\b", "mensaje": "FW 3.5 no soporta async/await"}],
    "audit_comments": {"requerido": True, "severidad": "error"},
    "checks_estructurales": ["designer_sync"],
    "grupos": {"fw35_syntax": ["no_async"]},
}


class TestTicketContext(unittest.TestCase):
    def test_contexto_valido_no_produce_errores(self):
        self.assertEqual(contracts.validate_ticket_context(CONTEXTO_OK), [])

    def test_rechaza_fecha_en_formato_iso(self):
        malo = dict(CONTEXTO_OK, fecha="2026-07-28")
        errores = contracts.validate_ticket_context(malo)
        self.assertTrue(any("DD-MM-YYYY" in e for e in errores))

    def test_rechaza_desarrollador_vacio(self):
        malo = dict(CONTEXTO_OK, desarrollador="   ")
        self.assertTrue(contracts.validate_ticket_context(malo))


class TestPlan(unittest.TestCase):
    def test_plan_valido_no_produce_errores(self):
        self.assertEqual(contracts.validate_plan(PLAN_OK, REGLAS_OK), [])

    def test_rechaza_lista_de_fases_vacia(self):
        malo = dict(PLAN_OK, fases=[])
        self.assertTrue(contracts.validate_plan(malo))

    def test_rechaza_confianza_no_reconocida(self):
        malo = copy.deepcopy(PLAN_OK)
        malo["fases"][0]["anclajes"][0]["confianza"] = "quiza"
        errores = contracts.validate_plan(malo)
        self.assertTrue(any("confianza" in e for e in errores))

    def test_rechaza_max_reintentos_fuera_de_rango(self):
        malo = copy.deepcopy(PLAN_OK)
        malo["fases"][0]["max_reintentos"] = 0
        self.assertTrue(contracts.validate_plan(malo))

    def test_rechaza_dependencia_a_una_fase_inexistente(self):
        malo = copy.deepcopy(PLAN_OK)
        malo["fases"][0]["depende_de"] = ["fase_9"]
        errores = contracts.validate_plan(malo)
        self.assertTrue(any("fase_9" in e for e in errores))

    def test_rechaza_check_que_no_existe_ni_como_grupo(self):
        malo = copy.deepcopy(PLAN_OK)
        malo["fases"][0]["checks_deterministas"] = ["no_existe"]
        errores = contracts.validate_plan(malo, REGLAS_OK)
        self.assertTrue(any("no_existe" in e for e in errores))

    def test_sin_reglas_no_valida_nombres_de_checks(self):
        raro = copy.deepcopy(PLAN_OK)
        raro["fases"][0]["checks_deterministas"] = ["no_existe"]
        self.assertEqual(contracts.validate_plan(raro), [])


class TestResolucionDeChecks(unittest.TestCase):
    def test_expande_un_grupo_a_sus_checks(self):
        resueltos, desconocidos = contracts.resolve_check_names(["fw35_syntax"], REGLAS_OK)
        self.assertEqual(resueltos, ["no_async"])
        self.assertEqual(desconocidos, [])

    def test_reporta_los_nombres_desconocidos(self):
        resueltos, desconocidos = contracts.resolve_check_names(["fantasma"], REGLAS_OK)
        self.assertEqual(resueltos, [])
        self.assertEqual(desconocidos, ["fantasma"])

    def test_acepta_audit_comments_y_los_estructurales(self):
        resueltos, desconocidos = contracts.resolve_check_names(
            ["audit_comments", "designer_sync"], REGLAS_OK)
        self.assertEqual(desconocidos, [])
        self.assertEqual(sorted(resueltos), ["audit_comments", "designer_sync"])


class TestFaseState(unittest.TestCase):
    def test_estado_valido(self):
        estado = {"fase_id": "fase_1", "estado": "en_correccion", "intento_actual": 2,
                  "max_reintentos": 3,
                  "historial_fallos": [{"intento": 1, "origen": "check",
                                        "razon": "designer_sync falló",
                                        "correccion_aplicada": "se declaró el control"}]}
        self.assertEqual(contracts.validate_fase_state(estado), [])

    def test_rechaza_estado_desconocido(self):
        estado = {"fase_id": "fase_1", "estado": "meditando", "intento_actual": 1,
                  "max_reintentos": 3, "historial_fallos": []}
        self.assertTrue(contracts.validate_fase_state(estado))

    def test_rechaza_origen_de_fallo_desconocido(self):
        estado = {"fase_id": "fase_1", "estado": "en_correccion", "intento_actual": 2,
                  "max_reintentos": 3,
                  "historial_fallos": [{"intento": 1, "origen": "intuicion",
                                        "razon": "x", "correccion_aplicada": "y"}]}
        self.assertTrue(contracts.validate_fase_state(estado))

    def test_rechaza_intento_mayor_al_maximo(self):
        estado = {"fase_id": "fase_1", "estado": "en_correccion", "intento_actual": 5,
                  "max_reintentos": 3, "historial_fallos": []}
        errores = contracts.validate_fase_state(estado)
        self.assertTrue(any("max_reintentos" in e for e in errores))


class TestVeredicto(unittest.TestCase):
    def test_veredicto_valido(self):
        v = {"fase_id": "fase_1", "intento": 2, "aprobado": False,
             "juicio_esceptico": {"aprobado": True, "razones_rechazo": [],
                                  "claims_sin_evidencia": [], "anclajes_sin_resolver": []},
             "prueba_manual": {"requerida": True, "ejecutada": True, "resultado": "fallo",
                               "fallo_en_paso": 3, "observacion": "el campo volvió vacío"}}
        self.assertEqual(contracts.validate_veredicto(v), [])

    def test_no_puede_estar_aprobado_si_el_esceptico_rechazo(self):
        v = {"fase_id": "fase_1", "intento": 1, "aprobado": True,
             "juicio_esceptico": {"aprobado": False, "razones_rechazo": ["falta validación"],
                                  "claims_sin_evidencia": [], "anclajes_sin_resolver": []},
             "prueba_manual": {"requerida": False, "ejecutada": False, "resultado": "na"}}
        errores = contracts.validate_veredicto(v)
        self.assertTrue(any("aprobado" in e for e in errores))

    def test_no_puede_estar_aprobado_si_la_prueba_manual_requerida_no_paso(self):
        v = {"fase_id": "fase_1", "intento": 1, "aprobado": True,
             "juicio_esceptico": {"aprobado": True, "razones_rechazo": [],
                                  "claims_sin_evidencia": [], "anclajes_sin_resolver": []},
             "prueba_manual": {"requerida": True, "ejecutada": False, "resultado": "pendiente"}}
        self.assertTrue(contracts.validate_veredicto(v))

    def test_rechazo_del_esceptico_exige_al_menos_una_razon(self):
        v = {"fase_id": "fase_1", "intento": 1, "aprobado": False,
             "juicio_esceptico": {"aprobado": False, "razones_rechazo": [],
                                  "claims_sin_evidencia": [], "anclajes_sin_resolver": []},
             "prueba_manual": {"requerida": False, "ejecutada": False, "resultado": "na"}}
        errores = contracts.validate_veredicto(v)
        self.assertTrue(any("razones_rechazo" in e for e in errores))


class TestChecksResult(unittest.TestCase):
    def test_resultado_agregado_debe_coincidir_con_los_checks(self):
        malo = {"fase_id": "fase_1", "intento": 1, "resultado": "ok",
                "checks": [{"id": "designer_sync", "resultado": "fallo", "severidad": "error",
                            "detalle": "control sin declarar"}]}
        errores = contracts.validate_checks_result(malo)
        self.assertTrue(any("resultado" in e for e in errores))

    def test_un_warning_no_vuelve_fallido_el_agregado(self):
        bueno = {"fase_id": "fase_1", "intento": 1, "resultado": "ok",
                 "checks": [{"id": "no_es6", "resultado": "fallo", "severidad": "warning",
                             "detalle": "arrow function"}]}
        self.assertEqual(contracts.validate_checks_result(bueno), [])

    def test_error_check_no_vuelve_fallido_el_agregado(self):
        bueno = {"fase_id": "fase_1", "intento": 1, "resultado": "ok",
                 "checks": [{"id": "sp_params", "resultado": "error_check",
                             "severidad": "error", "detalle": "Traceback..."}]}
        self.assertEqual(contracts.validate_checks_result(bueno), [])


class TestGuardasPayloadNoDict(unittest.TestCase):
    """El payload top-level puede ser cualquier cosa deserializable desde JSON
    (None, string, lista, número): nunca debe provocar AttributeError."""

    def test_validate_ticket_context_con_none(self):
        errores = contracts.validate_ticket_context(None)
        self.assertIsInstance(errores, list)
        self.assertTrue(errores)

    def test_validate_plan_con_string(self):
        errores = contracts.validate_plan("not a dict")
        self.assertIsInstance(errores, list)
        self.assertTrue(errores)

    def test_validate_checks_result_con_lista(self):
        errores = contracts.validate_checks_result([1, 2, 3])
        self.assertIsInstance(errores, list)
        self.assertTrue(errores)

    def test_validate_veredicto_con_entero(self):
        errores = contracts.validate_veredicto(42)
        self.assertIsInstance(errores, list)
        self.assertTrue(errores)

    def test_validate_fase_state_con_string(self):
        errores = contracts.validate_fase_state("x")
        self.assertIsInstance(errores, list)
        self.assertTrue(errores)

    def test_resolve_check_names_con_rules_none(self):
        resueltos, desconocidos = contracts.resolve_check_names(["a"], None)
        self.assertEqual(resueltos, [])
        self.assertEqual(desconocidos, ["a"])


if __name__ == "__main__":
    unittest.main()

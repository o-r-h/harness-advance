"""Curación de la biblioteca por CLI: contrato, record-curacion y resolver-curacion."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CLI = RAIZ / "harness" / "hooks" / "cli.py"
sys.path.insert(0, str(RAIZ / "harness" / "hooks"))
from lib import biblioteca, contracts, curacion, harness  # noqa: E402

REF_A = "ISR-1/fase_1/h1"
REF_B = "ISR-1/fase_1/h2"
REF_C = "ISR-1/fase_1/h3"


def correr(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(CLI), *args],
                          capture_output=True, text=True, encoding="utf-8")


def _retirar(ref=REF_C, motivo="contradice agent-x §2"):
    return {"tipo": "retirar", "ref": ref, "motivo": motivo}


def _fusionar(refs=(REF_A, REF_B), destino=REF_A, **extra):
    accion = {"tipo": "fusionar", "refs": list(refs), "destino": destino,
              "leccion": "lección fusionada", "motivo": "dicen lo mismo"}
    accion.update(extra)
    return accion


class TestContrato(unittest.TestCase):
    def errores(self, *acciones):
        return contracts.validate_propuesta_curacion({"acciones": list(acciones)})

    def test_propuestas_validas(self):
        self.assertEqual(self.errores(), [])
        self.assertEqual(self.errores(_retirar(), _fusionar(senal="s")), [])

    def test_fusionar_con_una_sola_ref_es_invalido(self):
        self.assertTrue(self.errores(_fusionar(refs=(REF_A,))))

    def test_destino_fuera_de_refs_es_invalido(self):
        self.assertTrue(self.errores(_fusionar(destino=REF_C)))

    def test_refs_repetidas_es_invalido(self):
        self.assertTrue(self.errores(_fusionar(refs=(REF_A, REF_A))))

    def test_ref_mal_formada_o_tipo_desconocido_es_invalido(self):
        self.assertTrue(self.errores(_retirar(ref="h1")))
        self.assertTrue(self.errores({"tipo": "borrar", "ref": REF_A, "motivo": "x"}))
        self.assertTrue(self.errores(_retirar(motivo=" ")))

    def test_estado_rechazado_exige_motivo_rechazo(self):
        accion = dict(_retirar(), id="c1", estado="rechazado", fecha_propuesta="03-11-2026")
        self.assertTrue(contracts.validate_curacion({"acciones": [accion]}))
        accion["motivo_rechazo"] = "no"
        self.assertEqual(contracts.validate_curacion({"acciones": [accion]}), [])

    def test_ids_duplicados_es_invalido(self):
        accion = dict(_retirar(), id="c1", estado="propuesto", fecha_propuesta="03-11-2026")
        self.assertTrue(contracts.validate_curacion({"acciones": [accion, dict(accion)]}))


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / ".claude").mkdir()
        harness.write_json(self.root / ".claude" / "rules.json", {"perfil": "p"})
        for id in ("h1", "h2", "h3"):
            biblioteca.escribir_entrada(self.root, "ISR-1", "fase_1", {
                "id": id, "origen": "reflector", "estado": "aprobado",
                "senal": f"señal {id}", "leccion": f"lección {id}", "evidencia": "e",
                "confianza": "media", "dimension": "proceso", "componente": "check"},
                fecha="01-11-2026")

    def proponer(self, *acciones) -> subprocess.CompletedProcess:
        archivo = self.root / "propuesta.json"
        archivo.write_text(json.dumps({"acciones": list(acciones)}), encoding="utf-8")
        return correr("record-curacion", "--project", str(self.root), "--archivo", str(archivo))

    def acciones(self) -> list[dict]:
        datos = curacion.leer(self.root)
        return datos["acciones"] if datos else []


class TestRecordCuracion(Base):
    def test_registra_las_acciones_con_ids(self):
        salida = self.proponer(_fusionar(), _retirar())
        self.assertEqual(salida.returncode, 0, salida.stderr)
        acciones = self.acciones()
        self.assertEqual([(a["id"], a["tipo"], a["estado"]) for a in acciones],
                         [("c1", "fusionar", "propuesto"), ("c2", "retirar", "propuesto")])
        self.assertIn("2 acción(es) propuesta(s)", salida.stdout)
        md = (harness.harness_dir(self.root) / "curacion.md").read_text(encoding="utf-8")
        self.assertIn("/curacion-ok c1", md)
        self.assertIn('/curacion-no c2 "<motivo>"', md)

    def test_una_ref_inexistente_se_rechaza_sin_escribir(self):
        salida = self.proponer(_retirar(ref="ISR-9/fase_1/h1"))
        self.assertEqual(salida.returncode, 1)
        self.assertIn("ISR-9/fase_1/h1", salida.stderr)
        self.assertIsNone(curacion.leer(self.root))

    def test_una_ref_retirada_dice_adonde_fue(self):
        biblioteca.fusionar(self.root, REF_A, [REF_B], "x", None, "02-11-2026")
        salida = self.proponer(_retirar(ref=REF_B))
        self.assertEqual(salida.returncode, 1)
        self.assertIn(f"fusionada en {REF_A}", salida.stderr)

    def test_una_ref_en_dos_acciones_se_rechaza(self):
        salida = self.proponer(_fusionar(), _retirar(ref=REF_B))
        self.assertEqual(salida.returncode, 1)
        self.assertIn(REF_B, salida.stderr)

    def test_fusion_de_implementada_con_no_implementada_se_rechaza(self):
        biblioteca.marcar_implementada(self.root, REF_B, "check y", "02-11-2026")
        salida = self.proponer(_fusionar())
        self.assertEqual(salida.returncode, 1)
        self.assertIn("implementada", salida.stderr)

    def test_una_propuesta_nueva_reemplaza_las_pendientes_y_conserva_las_resueltas(self):
        self.proponer(_fusionar(), _retirar())
        datos = curacion.leer(self.root)
        datos["acciones"][0].update(estado="rechazado", motivo_rechazo="no",
                                    fecha_resuelta="03-11-2026")
        curacion.guardar(self.root, datos)
        salida = self.proponer(_retirar(ref=REF_A))
        self.assertEqual(salida.returncode, 0, salida.stderr)
        self.assertEqual([(a["id"], a["estado"]) for a in self.acciones()],
                         [("c1", "rechazado"), ("c3", "propuesto")])

    def test_propuesta_vacia_se_registra(self):
        salida = self.proponer()
        self.assertEqual(salida.returncode, 0, salida.stderr)
        self.assertIn("El curador no propuso acciones.", salida.stdout)
        self.assertEqual(self.acciones(), [])

    def test_no_exige_ticket_abierto(self):
        self.assertFalse(harness.tickets_dir(self.root).exists())
        self.assertEqual(self.proponer(_retirar()).returncode, 0)

    def test_solo_guarda_los_campos_del_contrato(self):
        # Revisión final M4: el curador es un modelo; un campo de más no entra al estado.
        salida = self.proponer(dict(_retirar(), fecha_resuelta="01-01-2030",
                                    motivo_rechazo="x", estado="aprobado", extra="y"))
        self.assertEqual(salida.returncode, 0, salida.stderr)
        accion = self.acciones()[0]
        self.assertEqual(set(accion), {"tipo", "ref", "motivo", "id", "estado",
                                       "fecha_propuesta"})
        self.assertEqual(accion["estado"], "propuesto")

    def test_una_propuesta_fuera_de_contrato_no_escribe(self):
        salida = self.proponer(_fusionar(refs=(REF_A,)))
        self.assertEqual(salida.returncode, 1)
        self.assertIsNone(curacion.leer(self.root))


class TestFusionQueFallaAMitad(Base):
    """Revisión final I1: un archivo bloqueado (editor, antivirus) a mitad de la fusión."""

    @unittest.skipIf(sys.platform != "win32",
                     "el escenario de archivo bloqueado (editor/antivirus) es propio "
                     "de Windows; el mock de Path.unlink no se propaga igual fuera de él")
    def test_reintentar_completa_la_fusion_sin_duplicar_fallas(self):
        import cli
        from unittest import mock
        biblioteca.registrar_falla(self.root, REF_B, "ISR-2/fase_1/h1", "b falló", "02-11-2026")
        biblioteca.registrar_falla(self.root, REF_C, "ISR-3/fase_1/h1", "c falló", "02-11-2026")
        self.proponer(_fusionar(refs=(REF_A, REF_B, REF_C)))
        bloqueado = biblioteca.entrada_path(self.root, REF_C)
        original = Path.unlink

        def unlink(self_, *a, **k):
            if self_ == bloqueado:
                raise PermissionError("archivo en uso")
            return original(self_, *a, **k)

        argumentos = ["resolver-curacion", "--project", str(self.root), "--id", "c1",
                      "--decision", "ok"]
        with mock.patch.object(Path, "unlink", unlink):
            self.assertEqual(cli.main(argumentos), 1)
        self.assertEqual(cli.main(argumentos), 0)

        entrada = biblioteca.leer_entrada(self.root, REF_A)
        self.assertEqual(len(entrada["fallas"]), 2)
        texto = biblioteca.entrada_path(self.root, REF_A).read_text(encoding="utf-8")
        self.assertEqual(texto.count(f"- **fusionada**: "), 2)
        for ref in (REF_B, REF_C):
            self.assertEqual(biblioteca.ubicacion(self.root, ref),
                             ("retiradas", f"fusionada en {REF_A}"))
        self.assertEqual(self.acciones()[0]["estado"], "aprobado")
        indice = (biblioteca.biblioteca_dir(self.root) / "INDEX.md").read_text(encoding="utf-8")
        self.assertNotIn("entradas/ISR-1-fase_1-h3.md", indice)

    def test_fusionar_dos_veces_lo_mismo_no_duplica(self):
        biblioteca.registrar_falla(self.root, REF_B, "ISR-2/fase_1/h1", "b falló", "02-11-2026")
        texto_b = biblioteca.entrada_path(self.root, REF_B).read_text(encoding="utf-8")
        biblioteca.fusionar(self.root, REF_A, [REF_B], "x", None, "03-11-2026")
        # Como si el primer intento hubiera escrito el destino y no hubiera retirado B.
        biblioteca.entrada_path(self.root, REF_B).write_text(texto_b, encoding="utf-8")
        biblioteca.fusionar(self.root, REF_A, [REF_B], "x", None, "03-11-2026")
        self.assertEqual(len(biblioteca.leer_entrada(self.root, REF_A)["fallas"]), 1)


class TestResolverCuracion(Base):
    def setUp(self):
        super().setUp()
        self.proponer(_fusionar(), _retirar())

    def resolver(self, id: str, decision: str, *extra: str) -> subprocess.CompletedProcess:
        return correr("resolver-curacion", "--project", str(self.root), "--id", id,
                      "--decision", decision, *extra)

    def accion(self, id: str) -> dict:
        return next(a for a in self.acciones() if a["id"] == id)

    def test_ok_retira(self):
        salida = self.resolver("c2", "ok")
        self.assertEqual(salida.returncode, 0, salida.stderr)
        self.assertEqual(biblioteca.ubicacion(self.root, REF_C),
                         ("retiradas", "contradice agent-x §2"))
        self.assertEqual(self.accion("c2")["estado"], "aprobado")
        self.assertRegex(self.accion("c2")["fecha_resuelta"], r"^\d{2}-\d{2}-\d{4}$")

    def test_ok_fusiona(self):
        self.assertEqual(self.resolver("c1", "ok").returncode, 0)
        self.assertEqual(biblioteca.leer_entrada(self.root, REF_A)["leccion"],
                         "lección fusionada")
        self.assertEqual(biblioteca.ubicacion(self.root, REF_B)[0], "retiradas")

    def test_editar_fusion_cambia_texto_y_senal(self):
        salida = self.resolver("c1", "editar", "--texto", "la mía", "--senal", "señal mía")
        self.assertEqual(salida.returncode, 0, salida.stderr)
        entrada = biblioteca.leer_entrada(self.root, REF_A)
        self.assertEqual((entrada["leccion"], entrada["senal"]), ("la mía", "señal mía"))
        self.assertEqual((self.accion("c1")["leccion"], self.accion("c1")["senal"]),
                         ("la mía", "señal mía"))

    def test_editar_quita_una_ref_y_esa_queda_en_entradas(self):
        self.proponer(_fusionar(refs=(REF_A, REF_B, REF_C)))
        salida = self.resolver("c3", "editar", "--quitar", REF_C)
        self.assertEqual(salida.returncode, 0, salida.stderr)
        self.assertEqual(biblioteca.ubicacion(self.root, REF_C), ("entradas", ""))
        self.assertEqual(biblioteca.ubicacion(self.root, REF_B)[0], "retiradas")
        self.assertEqual(self.accion("c3")["refs"], [REF_A, REF_B])

    def test_quitar_el_destino_o_dejar_una_sola_ref_es_error(self):
        for extra in (("--quitar", REF_A), ("--quitar", REF_B)):
            salida = self.resolver("c1", "editar", *extra)
            self.assertEqual(salida.returncode, 1, extra)
        self.assertEqual(self.accion("c1")["estado"], "propuesto")
        self.assertEqual(biblioteca.ubicacion(self.root, REF_B), ("entradas", ""))

    def test_texto_o_senal_en_blanco_fallan_sin_tocar_la_biblioteca(self):
        # Revisión final I2.
        antes = biblioteca.entrada_path(self.root, REF_A).read_text(encoding="utf-8")
        for extra in (("--texto", "   "), ("--senal", "  ")):
            with self.subTest(extra=extra):
                salida = self.resolver("c1", "editar", *extra)
                self.assertEqual(salida.returncode, 1)
                self.assertEqual(biblioteca.entrada_path(self.root, REF_A)
                                 .read_text(encoding="utf-8"), antes)
                self.assertEqual(biblioteca.ubicacion(self.root, REF_B), ("entradas", ""))
                self.assertEqual(self.accion("c1")["estado"], "propuesto")

    def test_editar_fusion_sin_nada_que_editar_es_error(self):
        self.assertEqual(self.resolver("c1", "editar").returncode, 1)

    def test_editar_retirar_exige_motivo_y_lo_usa(self):
        self.assertEqual(self.resolver("c2", "editar").returncode, 1)
        salida = self.resolver("c2", "editar", "--motivo", "obsoleta desde ISR-9")
        self.assertEqual(salida.returncode, 0, salida.stderr)
        self.assertEqual(biblioteca.ubicacion(self.root, REF_C),
                         ("retiradas", "obsoleta desde ISR-9"))

    def test_no_exige_motivo_y_escribe_el_rechazo_versionado(self):
        self.assertEqual(self.resolver("c2", "no").returncode, 1)
        salida = self.resolver("c2", "no", "--motivo", "sigue vigente")
        self.assertEqual(salida.returncode, 0, salida.stderr)
        self.assertEqual(biblioteca.ubicacion(self.root, REF_C), ("entradas", ""))
        self.assertEqual(self.accion("c2")["motivo_rechazo"], "sigue vigente")
        texto = curacion.ruta_rechazos(self.root).read_text(encoding="utf-8")
        self.assertRegex(texto, rf"- \d{{2}}-\d{{2}}-\d{{4}} · c2 · retirar · {REF_C} — "
                                r"sigue vigente\n")

    def test_el_primer_rechazo_crea_el_archivo_con_encabezado_y_el_segundo_no_lo_repite(self):
        self.resolver("c1", "no", "--motivo", "no son lo mismo")
        self.resolver("c2", "no", "--motivo", "sigue vigente")
        texto = curacion.ruta_rechazos(self.root).read_text(encoding="utf-8")
        self.assertTrue(texto.startswith(curacion.ENCABEZADO_RECHAZOS + "\n\n"))
        self.assertEqual(texto.count(curacion.ENCABEZADO_RECHAZOS), 1)
        self.assertIn(f"c1 · fusionar · {REF_A}, {REF_B} — no son lo mismo", texto)
        self.assertEqual(len(texto.strip().splitlines()), 4)

    def test_una_accion_ya_resuelta_no_se_resuelve_otra_vez(self):
        self.resolver("c2", "ok")
        salida = self.resolver("c2", "no", "--motivo", "x")
        self.assertEqual(salida.returncode, 1)
        self.assertIn("aprobado", salida.stderr)

    def test_una_ref_que_ya_no_esta_en_entradas_falla_sin_escribir(self):
        biblioteca.retirar(self.root, REF_B, "a mano", "02-11-2026")
        antes = biblioteca.entrada_path(self.root, REF_A).read_text(encoding="utf-8")
        salida = self.resolver("c1", "ok")
        self.assertEqual(salida.returncode, 1)
        self.assertIn(REF_B, salida.stderr)
        self.assertEqual(biblioteca.entrada_path(self.root, REF_A).read_text(encoding="utf-8"),
                         antes)
        self.assertEqual(self.accion("c1")["estado"], "propuesto")

    def test_una_leccion_anclada_por_el_ticket_abierto_no_se_toca(self):
        harness.write_json(harness.ticket_dir(self.root, "ISR-7") / "plan.json", {
            "ticket_id": "ISR-7", "fases": [{"id": "fase_1", "anclajes": [
                {"ref": ".claude/biblioteca/entradas/ISR-1-fase_1-h3.md",
                 "confianza": "por_confirmar"}]}]})
        harness.write_current(self.root, "ISR-7", "fase_1")
        salida = self.resolver("c2", "ok")
        self.assertEqual(salida.returncode, 1)
        self.assertIn("ISR-7", salida.stderr)
        self.assertEqual(biblioteca.ubicacion(self.root, REF_C), ("entradas", ""))

    def test_un_ticket_con_todas_sus_fases_aprobadas_ya_no_bloquea(self):
        # Revisión final I2b: current.json nunca se limpia; un ticket terminado no es "abierto".
        harness.write_json(harness.ticket_dir(self.root, "ISR-7") / "plan.json", {
            "ticket_id": "ISR-7", "fases": [{"id": "fase_1", "anclajes": [
                {"ref": ".claude/biblioteca/entradas/ISR-1-fase_1-h3.md",
                 "confianza": "por_confirmar"}]}]})
        harness.write_json(harness.fase_dir(self.root, "ISR-7", "fase_1") / "fase_state.json",
                           {"fase_id": "fase_1", "estado": "aprobada", "intento_actual": 1,
                            "max_reintentos": 3, "historial_fallos": []})
        harness.write_current(self.root, "ISR-7", None)
        salida = self.resolver("c2", "ok")
        self.assertEqual(salida.returncode, 0, salida.stderr)

    def test_un_plan_raro_en_el_ticket_abierto_no_revienta(self):
        # Revisión final M1: datos en disco fuera de contrato.
        harness.write_json(harness.ticket_dir(self.root, "ISR-7") / "plan.json",
                           {"ticket_id": "ISR-7", "fases": [5, {"anclajes": 3}]})
        harness.write_current(self.root, "ISR-7", None)
        salida = self.resolver("c2", "ok")
        self.assertEqual(salida.returncode, 0, salida.stderr)

    def test_un_id_inexistente_lista_los_validos(self):
        salida = self.resolver("c9", "ok")
        self.assertEqual(salida.returncode, 1)
        self.assertIn("c1, c2", salida.stderr)

    def test_quitar_o_senal_no_valen_en_retirar_ni_con_ok(self):
        self.assertEqual(self.resolver("c2", "editar", "--quitar", REF_A).returncode, 1)
        self.assertEqual(self.resolver("c1", "ok", "--texto", "x").returncode, 1)


if __name__ == "__main__":
    unittest.main()

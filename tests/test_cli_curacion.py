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

    def test_una_propuesta_fuera_de_contrato_no_escribe(self):
        salida = self.proponer(_fusionar(refs=(REF_A,)))
        self.assertEqual(salida.returncode, 1)
        self.assertIsNone(curacion.leer(self.root))


if __name__ == "__main__":
    unittest.main()

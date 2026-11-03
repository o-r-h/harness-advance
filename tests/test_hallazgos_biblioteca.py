import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "harness" / "hooks"))
from lib import biblioteca, hallazgos  # noqa: E402


def _h(id="h1", estado="propuesto", **extra):
    base = {"id": id, "origen": "reflector", "estado": estado,
            "senal": "Al editar un formulario", "leccion": "Agregar un check",
            "evidencia": "fase_1 falló dos veces", "confianza": "media",
            "dimension": "proceso", "componente": "check"}
    base.update(extra)
    return base


def _datos(*hs):
    return {"ticket_id": "ISR-110722", "fase_id": "fase_1", "hallazgos": list(hs)}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)


class TestHallazgos(Base):
    def test_render_lista_ids_y_comandos(self):
        txt = hallazgos.render(_datos(_h()))
        for esperado in ("h1", "/hallazgo-ok ISR-110722/fase_1/h1",
                         "/hallazgo-no ISR-110722/fase_1/h1", "No bloquean"):
            self.assertIn(esperado, txt)

    def test_render_ofrece_comandos_solo_para_los_propuestos(self):
        humano = {"id": "h1", "origen": "humano", "estado": "aprobado",
                  "leccion": "Revisar el contrato"}
        txt = hallazgos.render(_datos(humano, _h(id="h2")))
        self.assertIn("/hallazgo-ok ISR-110722/fase_1/h2", txt)
        self.assertNotIn("ISR-110722/fase_1/h1`", txt)
        self.assertNotIn("propone el reflector", txt)
        encabezado = next(linea for linea in txt.splitlines() if linea.startswith("## h1"))
        self.assertIn("humano", encabezado)

    def test_render_sin_propuestos_no_ofrece_comandos(self):
        txt = hallazgos.render(_datos(_h(estado="aprobado")))
        self.assertNotIn("/hallazgo-ok", txt)

    def test_render_colapsa_saltos_de_linea(self):
        txt = hallazgos.render(_datos(_h(leccion="Primera línea\n  segunda línea",
                                         senal="señal\ncon salto")))
        self.assertIn("- **Lección:** Primera línea segunda línea", txt)
        self.assertIn("- **Señal:** señal con salto", txt)

    def test_render_vacio_dice_que_no_hubo_lecciones(self):
        self.assertIn("no encontró lecciones", hallazgos.render(_datos()))

    def test_guardar_invalido_lanza_value_error(self):
        malo = _h()
        del malo["id"]
        with self.assertRaises(ValueError):
            hallazgos.guardar(self.root, _datos(malo))

    def test_guardar_escribe_json_y_md(self):
        datos = _datos(_h())
        md = hallazgos.guardar(self.root, datos)
        self.assertTrue(md.exists())
        self.assertTrue(hallazgos.ruta(self.root, "ISR-110722", "fase_1").exists())
        self.assertEqual(hallazgos.leer(self.root, "ISR-110722", "fase_1"), datos)
        self.assertIsNone(hallazgos.leer(self.root, "ISR-110722", "fase_9"))


class TestBiblioteca(Base):
    def test_aprobado_va_a_entradas_y_al_indice(self):
        p = biblioteca.escribir_entrada(self.root, "ISR-110722", "fase_1", _h(estado="aprobado"))
        self.assertEqual(p.parent.name, "entradas")
        indice = (biblioteca.biblioteca_dir(self.root) / "INDEX.md").read_text(encoding="utf-8")
        self.assertIn("[proceso · check]", indice)
        self.assertIn("Al editar un formulario", indice)

    def test_leccion_humana_sin_senal_aparece_en_el_indice(self):
        humano = {"id": "h1", "origen": "humano", "estado": "aprobado",
                  "leccion": "Revisar el contrato\nantes de editar"}
        biblioteca.escribir_entrada(self.root, "ISR-110722", "fase_1", humano)
        indice = (biblioteca.biblioteca_dir(self.root) / "INDEX.md").read_text(encoding="utf-8")
        self.assertIn("- Revisar el contrato antes de editar — entradas/ISR-110722-fase_1-h1.md",
                      indice)
        self.assertNotIn("[ · ]", indice)

    def test_indice_muestra_solo_la_clasificacion_que_hay(self):
        humano = {"id": "h1", "origen": "humano", "estado": "aprobado",
                  "leccion": "Revisar el contrato", "dimension": "dominio"}
        biblioteca.escribir_entrada(self.root, "ISR-110722", "fase_1", humano)
        indice = (biblioteca.biblioteca_dir(self.root) / "INDEX.md").read_text(encoding="utf-8")
        self.assertIn("- [dominio] Revisar el contrato — entradas/", indice)

    def test_rechazado_va_a_rechazados_con_motivo(self):
        p = biblioteca.escribir_entrada(self.root, "ISR-110722", "fase_1",
                                        _h(estado="rechazado", motivo="es falsa"))
        self.assertEqual(p.parent.name, "rechazados")
        indice = (biblioteca.biblioteca_dir(self.root) / "INDEX.md").read_text(encoding="utf-8")
        self.assertIn("no volver a proponer", indice)
        self.assertIn("es falsa", indice)

    def test_propuesto_no_se_escribe(self):
        with self.assertRaises(ValueError):
            biblioteca.escribir_entrada(self.root, "ISR-110722", "fase_1", _h())

    def test_indice_se_reconstruye_desde_disco(self):
        p = biblioteca.escribir_entrada(self.root, "ISR-110722", "fase_1", _h(estado="aprobado"))
        p.unlink()
        biblioteca.reconstruir_indice(self.root)
        indice = (biblioteca.biblioteca_dir(self.root) / "INDEX.md").read_text(encoding="utf-8")
        self.assertNotIn("Al editar un formulario", indice)
        self.assertIn("_(vacía)_", indice)

    def test_ningun_perfil_trae_biblioteca(self):
        for perfil in (RAIZ / "profiles").iterdir():
            if perfil.is_dir():
                self.assertFalse((perfil / "biblioteca").exists(),
                                 f"{perfil.name} trae biblioteca/: deploy la pisaría (DA6)")

    def test_acentos_sobreviven_ida_y_vuelta(self):
        senal = "Señal: acción en la sección año"
        h = _h(estado="aprobado", senal=senal, leccion="Lección: reparación del módulo")
        md = hallazgos.guardar(self.root, _datos(h))
        p = biblioteca.escribir_entrada(self.root, "ISR-110722", "fase_1", h)
        indice = biblioteca.biblioteca_dir(self.root) / "INDEX.md"
        for archivo in (md, p, indice):
            self.assertIn(senal, archivo.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()


class TestMarcasDeLaEntrada(Base):
    REF = "ISR-1/fase_1/h1"

    def setUp(self):
        super().setUp()
        self.ruta = biblioteca.escribir_entrada(
            self.root, "ISR-1", "fase_1", _h(estado="aprobado"), fecha="02-11-2026")

    def test_la_aprobada_lleva_fecha(self):
        self.assertEqual(biblioteca.leer_entrada(self.root, self.REF)["aprobada"], "02-11-2026")

    def test_sin_fecha_no_escribe_aprobada(self):
        biblioteca.escribir_entrada(self.root, "ISR-1", "fase_1", _h(estado="aprobado"))
        self.assertEqual(biblioteca.leer_entrada(self.root, self.REF)["aprobada"], "")

    def test_leer_entrada_inexistente(self):
        self.assertIsNone(biblioteca.leer_entrada(self.root, "ISR-9/fase_1/h1"))

    def test_falla_sin_pieza(self):
        biblioteca.registrar_falla(self.root, self.REF, "ISR-2/fase_3/h1",
                                   "Usar curl.exe", "03-11-2026")
        self.assertEqual(biblioteca.leer_entrada(self.root, self.REF)["fallas"],
                         [{"fecha": "03-11-2026", "ref": "ISR-2/fase_3/h1",
                           "tipo": "sin pieza", "leccion": "Usar curl.exe"}])

    def test_falla_estando_implementada(self):
        biblioteca.marcar_implementada(self.root, self.REF, "check curl", "04-11-2026")
        biblioteca.registrar_falla(self.root, self.REF, "ISR-2/fase_3/h1",
                                   "Usar curl.exe", "05-11-2026")
        self.assertEqual(biblioteca.leer_entrada(self.root, self.REF)["fallas"][0]["tipo"],
                         "implementada")

    def test_varias_fallas_se_acumulan(self):
        biblioteca.registrar_falla(self.root, self.REF, "ISR-2/fase_3/h1", "Uno", "03-11-2026")
        biblioteca.registrar_falla(self.root, self.REF, "ISR-3/fase_1/h2", "Dos", "04-11-2026")
        fallas = biblioteca.leer_entrada(self.root, self.REF)["fallas"]
        self.assertEqual([f["ref"] for f in fallas], ["ISR-2/fase_3/h1", "ISR-3/fase_1/h2"])

    def test_marcar_implementada_devuelve_la_anterior(self):
        self.assertIsNone(biblioteca.marcar_implementada(self.root, self.REF, "check curl",
                                                         "04-11-2026"))
        self.assertEqual(biblioteca.marcar_implementada(self.root, self.REF, "otra", "05-11-2026"),
                         "04-11-2026 · check curl")
        self.assertEqual(biblioteca.leer_entrada(self.root, self.REF)["implementada"],
                         "05-11-2026 · otra")

    def test_falla_o_marca_sobre_rechazada_o_inexistente(self):
        biblioteca.escribir_entrada(self.root, "ISR-1", "fase_1", _h(id="h2", estado="rechazado"))
        for ref in ("ISR-1/fase_1/h2", "ISR-9/fase_1/h1"):
            with self.assertRaises(ValueError):
                biblioteca.registrar_falla(self.root, ref, "ISR-2/fase_3/h1", "x", "03-11-2026")
            with self.assertRaises(ValueError):
                biblioteca.marcar_implementada(self.root, ref, "x", "03-11-2026")

    def test_conserva_lineas_ajenas(self):
        with open(self.ruta, "a", encoding="utf-8", newline="") as f:
            f.write("\r\n- **nota**: puesta a mano\r\n")
        biblioteca.registrar_falla(self.root, self.REF, "ISR-2/fase_3/h1", "Uno", "03-11-2026")
        biblioteca.marcar_implementada(self.root, self.REF, "check", "04-11-2026")
        texto = self.ruta.read_text(encoding="utf-8")
        self.assertIn("- **nota**: puesta a mano", texto)
        self.assertIn("- **falló**: 03-11-2026 · ISR-2/fase_3/h1 · sin pieza — Uno", texto)

    def test_indice_muestra_las_marcas(self):
        biblioteca.marcar_implementada(self.root, self.REF, "check", "04-11-2026")
        biblioteca.registrar_falla(self.root, self.REF, "ISR-2/fase_3/h1", "Uno", "05-11-2026")
        biblioteca.registrar_falla(self.root, self.REF, "ISR-3/fase_1/h2", "Dos", "06-11-2026")
        indice = (self.root / ".claude" / "biblioteca" / "INDEX.md").read_text(encoding="utf-8")
        linea = next(l for l in indice.splitlines() if "entradas/ISR-1-fase_1-h1.md" in l)
        self.assertTrue(linea.endswith("(implementada 04-11-2026) (falló 2×)"), linea)

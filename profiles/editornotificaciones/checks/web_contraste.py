"""Check estructural: contraste WCAG AA de todo texto visible de las pantallas 1, 3 y 4, si la fase tocó el frontend.

Construye src/Web en una carpeta temporal (vite build), la sirve con una API simulada (respuestas
capturadas del tipo 1223 y de la sección compartida 3 en web_contraste/api; nunca toca Masterdb, la API
real ni %LOCALAPPDATA%) y la abre en Chrome o Edge sin interfaz. web_contraste/recorrido.js lleva la app
por estados representativos (pantalla 1: lectura, cargas, visor correo y web, idiomas, lista de
borradores, edición, guardado, confirmaciones, conflictos, aviso de componentes; pantalla 3: lectura,
validación sin guardar, diálogo de N, "Ver en el visor", conflicto; pantalla 4: sin borradores, componentes,
generando, resumen y pestañas, solo dev, desactualizado, conflictos, error; ticket 7: pantalla 2 "Notificación
nueva" (ID sugerido y validado, tipo base, CRON, creando, CNTC sugerida, lista de borradores de alta), editor del
borrador de alta (lectura, disclaimer nuevo, sección propia, visor web, guardando; alta vacía con las posiciones
de la plantilla por llenar, una compartida elegida y una propia, cambio de plantilla) y pantalla 4 del alta (400 por
pendientes, scripts con solo dev); ticket 9: pantalla Ayuda (cargando, índice con README, capítulo 03 desde el
botón del encabezado, enlace seguido dentro del capítulo, capítulo inexistente, ayuda no disponible); fase 5: tipo Legacy en la pantalla 1, "migrar en el mismo ID" (pantalla 2, datos,
editor y pantalla 4) y "basar en un tipo Legacy" (búsqueda, tipos elegidos con sus avisos, archivo inexistente,
%X% fuera del catálogo, borrador creado y su editor); ticket 10: error del ISR y del ID repetido junto al campo,
conflictos completos (comparación por renglón y valores completos, pantallas 1 y 3), "Borradores" con los borradores de
alta y el visor del alta con borradores de componentes aplicados; ticket 11: agregar francés al 1259 (avisos antes de
crear, creando, pestaña del idioma nuevo con pendientes, avisos, propuesta y posiciones, propuesta quitada y su aviso de
alcance, marca de propuesta, visor correo y web en francés, pantalla 4 con resumen.idiomasNuevos y con 400, "Borradores",
quitar el idioma); foco) y web_contraste/medir.js mide cada texto, valor
y placeholder.
Falla si alguno queda bajo 4.5:1 (3:1 en texto grande), con elemento, colores y ratio.

Sin dependencias nuevas: solo la biblioteca estándar de Python y el Chrome/Edge instalado (o el que
diga la variable WEB_CONTRASTE_NAVEGADOR).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

CHECK_ID = "web_contraste"
CARPETA_WEB = Path("src") / "Web"
EXTENSIONES = {".vue", ".js", ".mjs", ".ts", ".json", ".css", ".scss", ".html"}
RECURSOS = Path(__file__).resolve().parent / "web_contraste"
TIMEOUT_BUILD_S = 600
TIMEOUT_RECORRIDO_S = 420
MAX_FILAS = 40
NAVEGADORES = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
)
TIPOS_MIME = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
              ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8",
              ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon",
              ".woff": "font/woff", ".woff2": "font/woff2", ".ttf": "font/ttf"}


def _toca_frontend(raiz: Path, archivos) -> bool:
    web = (raiz / CARPETA_WEB).resolve()
    for archivo in archivos:
        ruta = Path(archivo)
        ruta = (ruta if ruta.is_absolute() else raiz / ruta).resolve()
        if ruta.suffix.lower() in EXTENSIONES and (ruta == web or web in ruta.parents):
            return True
    return False


def _navegador() -> str | None:
    propio = os.environ.get("WEB_CONTRASTE_NAVEGADOR")
    if propio:
        return propio if Path(propio).is_file() else None
    for ruta in NAVEGADORES:
        if Path(ruta).is_file():
            return ruta
    for nombre in ("chrome", "msedge", "chromium", "google-chrome"):
        encontrado = shutil.which(nombre)
        if encontrado:
            return encontrado
    return None


def _cola(proceso: subprocess.CompletedProcess, lineas: int = 30) -> str:
    salida = ((proceso.stdout or "") + "\n" + (proceso.stderr or "")).strip().splitlines()
    return "\n".join(salida[-lineas:])


# ---------------------------------------------------------------- API simulada

def _hash(valor):
    return "null" if valor is None else hashlib.sha256(valor.encode("utf-8")).hexdigest()


class ApiSimulada:
    """Respuestas de /api con el contrato de src/Api (tickets 4 y 5) a partir de web_contraste/api/*.json.

    Los borradores (del tipo y de la sección compartida 3) viven en memoria; recorrido.js elige el
    escenario (sin borrador o con un borrador con conflictos) y los retrasos por ruta para poder medir
    los estados de carga.
    """

    def __init__(self, carpeta: Path):
        self.carpeta = carpeta
        self.tipo = self.json("tipo_1223.json")
        self.componente = self.json("componente_seccion_3.json")
        self.borrador = None
        self.borrador_componente = None
        # Ticket 7: borradores de alta en memoria ({ id: RespuestaBorradorAlta }); la base es la respuesta real
        # de POST /api/nuevas { baseTipoId: 1223 } (alta_1223.json).
        self.alta_base = self.json("alta_1223.json")
        # Alta vacía: respuesta real de POST /api/nuevas { idiomas: [2, 1], isr } (posiciones de la plantilla 1
        # por llenar) y plantillas reales con seccionesDetalle.
        self.alta_vacia = self.json("alta_vacia.json")
        self.plantillas = {p["id"]: p for p in self.json("plantillas.json") or []}
        # Fase 5: respuestas reales de POST /api/nuevas { legacy: [334 EN, 337 ES], idiomas: [2, 1] } y
        # { migrarTipoId: 334, migrarLang: 2, copiarAsunto: true }, y un extracto real de GET /api/legacy/tipos.
        self.alta_legacy = self.json("alta_legacy.json")
        self.alta_migracion = self.json("alta_migracion.json")
        self.legacy_tipos = self.json("legacy_tipos.json") or []
        # Avisos que la API dio al crear cada alta basada en Legacy o de migración ({ id: [texto] })
        self.avisos_alta: dict[int, list] = {}
        self.altas: dict[int, dict] = {}
        self.siguiente_alta = 1
        self.retrasos: dict[str, int] = {}
        self.candado = threading.Lock()
        # Ticket 9 · ayuda: índice y capítulos README y 03 capturados de la API real (GET /api/ayuda/…);
        # ayuda_error = la carpeta de la ayuda no está disponible (503).
        self.ayuda_error = False
        # Ticket 11 · idioma nuevo: borrador del tipo 1259 (ES/EN) en memoria, armado con las respuestas reales de
        # POST /api/borradores/1259/idiomas { lang: 4, langBase: 2 } (idioma_nuevo_1259_post.json), PUT /idiomas/4 con
        # asunto y cuerpo (…_put.json), PUT del tipo sin la propuesta de ES (…_sin_es.json) y DELETE /idiomas/4
        # (…_quitado.json).
        self.tipo_1259 = self.json("tipo_1259.json")
        self.borrador_1259 = None

    def json(self, nombre: str):
        ruta = self.carpeta / nombre
        return json.loads(ruta.read_text(encoding="utf-8")) if ruta.is_file() else None

    def base(self) -> list[dict]:
        entradas = []
        for idioma in self.tipo["idiomas"]:
            lang = idioma["lang"]
            valores = [("Asunto", None, idioma["subject"]),
                       ("DisclaimerSuperior", None, str((idioma["disclaimerSuperior"] or {}).get("id") or "") or None),
                       ("DisclaimerInferior", None, str((idioma["disclaimerInferior"] or {}).get("id") or "") or None),
                       ("EstiloExtra", None, idioma["styleSection"])]
            valores += [("ContenidoSeccion", s["sectionContentId"], s["resumen"])
                        for s in idioma["secciones"] if s["sectionContentId"] is not None and s["usoTipos"] <= 1]
            for campo, seccion, valor in valores:
                entradas.append({"campo": campo, "lang": lang, "sectionContentId": seccion,
                                 "valor": valor, "hash": _hash(valor)})
        return entradas

    def escenario(self, datos: dict):
        with self.candado:
            if "retrasos" in datos:
                self.retrasos = {k: int(v) for k, v in (datos.get("retrasos") or {}).items()}
            if "borrador" in datos:
                modo = datos["borrador"]
                self.borrador = self.con_conflicto() if modo == "conflicto" else (
                    self.nuevo_borrador([{"campo": "Asunto", "lang": 2, "sectionContentId": None,
                                          "valor": "Asunto cambiado en el borrador"}]) if modo == "cambio" else None)
            if "componente" in datos:
                modo = datos["componente"]
                self.borrador_componente = None if not modo else self.nuevo_borrador_componente(
                    self.componente["componente"]["valor"] + "<!-- cambio del check -->", conflicto=modo == "conflicto")
            if "ayudaError" in datos:
                self.ayuda_error = bool(datos["ayudaError"])
            if "borrador1259" in datos:
                self.borrador_1259 = None
            if "altas" in datos:
                self.altas = {}
                self.avisos_alta = {}
                self.siguiente_alta = 1

    # ---------- borradores de alta (ticket 7): /api/nuevas, validar-id, siguiente-id y scripts/nuevo

    @staticmethod
    def ahora() -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def pendientes_alta(self, b: dict) -> list[tuple[str, bool]]:
        """(mensaje, bloquea) con los textos de ValidadorAlta.PendientesDetalle (solo los casos del recorrido)."""
        p: list[tuple[str, bool]] = []
        nombres = {1: "Español (1)", 2: "Inglés (2)", 4: "Francés (4)"}
        if b.get("notificationTypeId") is None:
            p.append(("Falta confirmar el NotificationTypeID (usa el sugerido o captura uno libre).", True))
        nombre = (b.get("notificationName") or "").strip()
        if not nombre:
            p.append(("Falta el nombre (NotificationName).", True))
        elif nombre.endswith("-"):
            p.append((f"El nombre '{nombre}' solo tiene el prefijo: complétalo.", True))
        for i in b.get("idiomas") or []:
            idioma = nombres.get(i["lang"], f"Idioma {i['lang']}")
            if not (i.get("subject") or "").strip():
                p.append((f"{idioma}: falta el asunto.", True))
            for clave, texto in (("disclaimerSuperior", "superior (DisclaimerTopID = 0); el correo sale sin encabezado de disclaimer."),
                                 ("disclaimerInferior", "inferior (DisclaimerBottomID = 0); el correo sale sin pie de disclaimer.")):
                d = i.get(clave) or {"id": 0}
                if d.get("id") == 0:
                    p.append((f"{idioma}: sin disclaimer {texto}", False))
            # Una posición de la plantilla sin sección, o con la sección por llenar (los dos nulos), bloquea. La API
            # las lista en orden de RelId (Body, Bottom, Header en la plantilla 1); aquí, por nombre (mismo orden).
            # Textos reales: alta_vacia.json y alta_vacia_parcial.json (PUT con EN parcial y ES por llenar).
            plantilla = self.plantillas.get(i.get("contentId")) or {}
            llenas = {s["internalSectionId"] for s in i.get("secciones") or []
                      if s.get("sectionContentId") is not None or s.get("contenido") is not None}
            for rel in sorted(plantilla.get("seccionesDetalle") or [], key=lambda r: r["sectionName"]):
                if rel["internalSectionId"] not in llenas:
                    p.append((f"{idioma}: la sección {rel['sectionName']} de la plantilla {i.get('contentId')} "
                              "no tiene contenido.", True))
        return p

    def respuesta_alta(self, b: dict) -> dict:
        if b["id"] in self.avisos_alta:
            avisos = list(self.avisos_alta[b["id"]])
        else:
            avisos = list(self.alta_base["avisos"]) if b.get("baseTipoId") else []
        if b.get("cron"):
            avisos.append("CRON: la expresión no se valida (solo su largo, 30). La lógica que dispara la notificación "
                          "(SP o código que inserta en CustomerNotificationHistory) se hace aparte.")
        if b.get("correosDebug"):
            avisos.append("Los correos de debug van solo en el script solo_dev (NotificationTypeDebugEmails y "
                          "hasDebugMails = 1); nunca en producción.")
        detalle = self.pendientes_alta(b)
        # Ticket 10: pendientesDetalle [{ mensaje, bloquea }] (mismos textos y orden que pendientes).
        return {"borrador": b, "pendientes": [m for m, _ in detalle], "avisos": avisos, "validaciones": [],
                "pendientesDetalle": [{"mensaje": m, "bloquea": x} for m, x in detalle]}

    # ---------- ticket 10: 400 de /api/nuevas por ISR (ReglaIsr.ProblemaAlta) y por ID repetido (ValidadorAlta.IdRepetido)

    @staticmethod
    def problema_isr(isr):
        if not isr or not str(isr).strip():
            return None
        t = str(isr).strip()
        if re.match(r"^\s*ISR[\s_-]*\d", t, re.IGNORECASE):
            numero = re.search(r"\d[\w-]*", t).group(0)
            return f"ISR '{t}': va solo el número del ticket, sin el prefijo 'ISR' (escribe '{numero}')."
        if re.fullmatch(r"[A-Za-z0-9_-]{1,60}", t):
            return None
        return f"ISR '{t}' no es válido: usa letras, dígitos, '-' o '_' (máximo 60); por convención, solo el número del ticket."

    def problema_id_repetido(self, n, propio):
        if not isinstance(n, int) or n <= 0:
            return None
        otros = sorted(b["id"] for b in self.altas.values() if b.get("notificationTypeId") == n and b["id"] != propio)
        if not otros:
            return None
        lista = ", ".join("#" + str(o) for o in otros)
        quien = "el borrador de alta" if len(otros) == 1 else "los borradores de alta"
        return (f"El NotificationTypeID {n} ya lo usa {quien} {lista}: captura otro ID (o abre ese borrador). "
                "Dos borradores con el mismo ID se bloquearían entre sí.")

    @staticmethod
    def invalido(problema: str) -> tuple[int, dict, dict]:
        return 400, {"type": "https://tools.ietf.org/html/rfc9110#section-15.5.1", "title": "Borrador inválido",
                     "status": 400, "detail": problema, "problemas": [problema]}, {}

    def crear_alta(self, c: dict) -> dict:
        ahora = self.ahora()
        nombre = c.get("notificationName") or (f"{c['isr']} - " if c.get("isr") else "")
        avisos = None
        if c.get("migrarTipoId"):
            # Migración en el mismo ID: el ID y el nombre son los del tipo (respuesta real de la migración de 334).
            b = json.loads(json.dumps(self.alta_migracion["borrador"]))
            avisos = self.alta_migracion["avisos"]
            b.update(id=self.siguiente_alta, creado=ahora, modificado=ahora)
            self.siguiente_alta += 1
            self.altas[b["id"]] = b
            self.avisos_alta[b["id"]] = avisos
            return self.respuesta_alta(b)
        if c.get("legacy"):
            b = json.loads(json.dumps(self.alta_legacy["borrador"]))
            avisos = self.alta_legacy["avisos"]
        elif c.get("baseTipoId"):
            b = json.loads(json.dumps(self.alta_base["borrador"]))
        else:
            b = json.loads(json.dumps(self.alta_vacia["borrador"]))
            molde = b["idiomas"][0]
            b["idiomas"] = [dict(json.loads(json.dumps(molde)), lang=l) for l in (c.get("idiomas") or [2])]
        b.update(id=self.siguiente_alta, notificationTypeId=c.get("notificationTypeId"), notificationName=nombre,
                 creado=ahora, modificado=ahora)
        self.siguiente_alta += 1
        self.altas[b["id"]] = b
        if avisos is not None:
            self.avisos_alta[b["id"]] = avisos
        return self.respuesta_alta(b)

    def responder_altas(self, metodo: str, ruta: str, q: dict, cuerpo, no_encontrado) -> tuple[int, object, dict]:
        if metodo == "GET" and ruta == "/api/nuevas":
            return 200, [{"id": b["id"], "modo": b["modo"], "notificationTypeId": b["notificationTypeId"],
                          "notificationName": b["notificationName"], "baseTipoId": b["baseTipoId"],
                          "idiomas": [i["lang"] for i in b["idiomas"]], "creado": b["creado"],
                          "modificado": b["modificado"]} for b in self.altas.values()], {}
        if metodo == "POST" and ruta == "/api/nuevas":
            c = cuerpo or {}
            problema = self.problema_isr(c.get("isr")) or self.problema_id_repetido(
                c.get("migrarTipoId") or c.get("notificationTypeId"), None)
            if problema:
                return self.invalido(problema)
            with self.candado:
                return 201, self.crear_alta(c), {}
        usados = {b["notificationTypeId"]: b["id"] for b in self.altas.values() if b["notificationTypeId"] is not None}
        if metodo == "GET" and ruta == "/api/nuevas/siguiente-id":
            siguiente = 2050
            while siguiente in usados:
                siguiente += 1
            return 200, {"siguienteId": siguiente, "maximoMasterdb": 2049,
                         "omitidosPorBorradores": sorted(x for x in usados if x >= 2050)}, {}
        if metodo == "GET" and ruta.startswith("/api/nuevas/validar-id/"):
            n = int(ruta.rsplit("/", 1)[1])
            propio = int(q["borradorId"]) if q.get("borradorId", "").isdigit() else None
            tipos = {t["id"]: t for t in self.json("tipos.json") or []}
            if (q.get("modo") or "").lower() == "migracion":
                return 200, self.validar_migracion(n, propio, tipos, usados), {}
            if n in tipos:
                capturada = self.json("validar_id_1223.json")
                return 200, dict(capturada, id=n, tipo=dict(capturada["tipo"], id=n, nombre=tipos[n]["nombre"]),
                                 problemas=[f"El NotificationTypeID {n} ya existe en NotificationTypes: "
                                            f"'{tipos[n]['nombre']}' (BuildType = 1)."]), {}
            otros = [i for x, i in usados.items() if x == n and i != propio]
            return 200, {"id": n, "libre": not otros, "existeEnMasterdb": False, "tipo": None, "borradoresAlta": otros,
                         "problemas": [f"El NotificationTypeID {n} ya lo usa otro borrador de alta "
                                       f"({', '.join('#' + str(o) for o in otros)})."] if otros else []}, {}
        partes = ruta.split("/")
        if len(partes) != 4 or not partes[3].isdigit():
            return no_encontrado
        b = self.altas.get(int(partes[3]))
        if not b:
            return 404, {"title": "Borrador de alta no encontrado", "status": 404,
                         "detail": f"No hay borrador de alta #{partes[3]}."}, {}
        if metodo == "GET":
            return 200, self.respuesta_alta(b), {}
        if metodo == "PUT":
            c = cuerpo or {}
            problema = self.problema_id_repetido(c.get("notificationTypeId"), b["id"])
            if problema:
                return self.invalido(problema)
            with self.candado:
                b.update(notificationTypeId=c.get("notificationTypeId"), notificationName=c.get("notificationName") or "",
                         idiomas=c.get("idiomas") or [], cntc=c.get("cntc") or b["cntc"], cron=c.get("cron"),
                         correosDebug=c.get("correosDebug") or [], modificado=self.ahora())
            return 200, self.respuesta_alta(b), {}
        if metodo == "DELETE":
            del self.altas[b["id"]]
            return 204, None, {}
        return no_encontrado

    def validar_migracion(self, n: int, propio, tipos: dict, usados: dict) -> dict:
        """GET /api/nuevas/validar-id/{n}?modo=Migracion: 'libre' = es Legacy y no lo usa otro borrador de alta."""
        legacy = {t["id"]: t for t in self.legacy_tipos}
        if n in legacy:
            # Respuesta real de validar-id/334?modo=Migracion, con el ID y nombre pedidos.
            capturada = self.json("validar_id_334_migracion.json")
            otros = [i for x, i in usados.items() if x == n and i != propio]
            r = dict(capturada, id=n, tipo=dict(capturada["tipo"], id=n, nombre=legacy[n]["nombre"]), borradoresAlta=otros)
            if otros:
                r.update(libre=False, problemas=[f"El NotificationTypeID {n} ya lo usa otro borrador de alta "
                                                 f"({', '.join('#' + str(o) for o in otros)})."])
            return r
        if n in tipos:
            return {"id": n, "libre": False, "existeEnMasterdb": True,
                    "tipo": {"id": n, "nombre": tipos[n]["nombre"], "buildType": 1, "inactivo": False},
                    "borradoresAlta": [], "problemas": [f"El tipo {n} ya es BuildType = 1: no es un tipo Legacy."]}
        return {"id": n, "libre": False, "existeEnMasterdb": False, "tipo": None, "borradoresAlta": [],
                "problemas": [f"El NotificationTypeID {n} no existe en NotificationTypes."]}

    # ---------- tipos Legacy (ticket 7, fase 5): /api/legacy/tipos y /api/legacy/tipos/{id}/cuerpo

    def responder_legacy(self, metodo: str, ruta: str, q: dict, no_encontrado) -> tuple[int, object, dict]:
        if metodo != "GET":
            return no_encontrado
        if ruta == "/api/legacy/tipos":
            buscar = (q.get("buscar") or "").strip()
            lista = self.legacy_tipos
            if q.get("soloConArchivo", "").lower() == "true":
                lista = [t for t in lista if (t.get("fileName") or "").strip()]
            if buscar.isdigit():
                lista = [t for t in lista if t["id"] == int(buscar)]
            elif buscar:
                b = buscar.lower()
                lista = [t for t in lista if b in t["nombre"].lower() or b in (t.get("fileName") or "").lower()]
            return 200, lista, {}
        m = re.fullmatch(r"/api/legacy/tipos/(\d+)/cuerpo", ruta)
        if not m:
            return no_encontrado
        datos = self.json(f"legacy_cuerpo_{m.group(1)}.json")
        if not datos:
            return 404, {"title": "Tipo no encontrado", "status": 404,
                         "detail": f"No existe el tipo {m.group(1)} en NotificationTypes."}, {}
        if q.get("lang", "").isdigit():
            datos = dict(datos, lang=int(q["lang"]))
        return 200, datos, {}

    def responder_scripts_alta(self, ruta: str, ticket: str, no_encontrado) -> tuple[int, object, dict]:
        b = self.altas.get(int(ruta.rsplit("/", 1)[1])) if ruta.rsplit("/", 1)[1].isdigit() else None
        if not b:
            return 404, {"title": "Borrador de alta no encontrado", "status": 404,
                         "detail": f"No hay borrador de alta #{ruta.rsplit('/', 1)[1]}."}, {}
        bloquean = [m for m, x in self.pendientes_alta(b) if x]
        if bloquean:
            problemas = [f"El borrador de alta #{b['id']} tiene pendientes que impiden generar el script."] + bloquean
            return 400, {"title": "No se puede generar el script", "status": 400, "detail": " ".join(problemas),
                         "problemas": problemas}, {}
        if b.get("modo") == "Migracion":
            # Respuesta real de la API para la migración de 334 en el mismo ID (sin correos de debug).
            datos = self.json("scripts_migracion.json")
            return 200, dict(datos, archivos=[dict(a, nombre=a["nombre"].replace("111269", ticket))
                                              for a in datos["archivos"]]), {}
        # Respuesta real de la API (alta basada en 1223 con CRON y un correo de debug), con el ticket pedido.
        datos = self.json("scripts_nuevo.json")
        archivos = [dict(a, nombre=a["nombre"].replace("111269", ticket)) for a in datos["archivos"]
                    if b.get("correosDebug") or not a["nombre"].startswith("solo_dev_")]
        resumen = datos["resumen"] if b.get("correosDebug") else dict(datos["resumen"], soloDev=[])
        return 200, dict(datos, archivos=archivos, resumen=resumen), {}

    def nuevo_borrador(self, cambios: list[dict]) -> dict:
        ahora = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        return {"borrador": {"tipoId": self.tipo["id"], "nombreTipo": self.tipo["nombre"], "creado": ahora,
                             "modificado": ahora, "cambios": cambios, "base": self.base()},
                "tipoExiste": True, "conflictos": [], "validaciones": [], "cambiosNoAplicables": []}

    def con_conflicto(self) -> dict:
        ingles = next(i for i in self.tipo["idiomas"] if i["lang"] == 2)
        asunto, actual = ingles["subject"], ingles["subject"] + " (actualizado)"
        respuesta = self.nuevo_borrador([{"campo": "Asunto", "lang": 2, "sectionContentId": None,
                                          "valor": "Asunto cambiado en el borrador"}])
        respuesta["conflictos"] = [
            {"campo": "Asunto", "lang": 2, "sectionContentId": None, "valorBase": asunto, "valorActual": actual,
             "hashBase": _hash(asunto), "hashActual": _hash(actual), "motivo": "ValorCambiado", "conCambio": True},
            {"campo": "EstiloExtra", "lang": 2, "sectionContentId": None, "valorBase": "",
             "valorActual": ".titulo { color: #1b2430; }", "hashBase": _hash(""),
             "hashActual": _hash(".titulo { color: #1b2430; }"), "motivo": "ValorCambiado", "conCambio": False}]
        # Ticket 10: un valor de varias líneas con cambio de los dos lados (comparación por renglón y valores completos).
        base_estilo = ".titulo { color: #1b2430; }\r\n.cuerpo { font-size: 13px; }\r\n.pie { color: #5b6675; }"
        actual_estilo = ".titulo { color: #1b2430; }\r\n.cuerpo { font-size: 14px; }\r\n.pie { color: #5b6675; }"
        tuyo_estilo = ".titulo { color: #003a6b; }\r\n.cuerpo { font-size: 13px; }\r\n.pie { color: #5b6675; }\r\n.nota { margin: 0; }"
        respuesta["borrador"]["cambios"].append({"campo": "EstiloExtra", "lang": 1, "sectionContentId": None, "valor": tuyo_estilo})
        respuesta["conflictos"].append(
            {"campo": "EstiloExtra", "lang": 1, "sectionContentId": None, "valorBase": base_estilo, "valorActual": actual_estilo,
             "hashBase": _hash(base_estilo), "hashActual": _hash(actual_estilo), "motivo": "ValorCambiado", "conCambio": True})
        respuesta["validaciones"] = [{"nivel": "advertencia", "codigo": "marcador_sin_reemplazar",
                                      "mensaje": "%CustomerName% queda sin reemplazar (asunto).",
                                      "componente": "marcador:CustomerName"}]
        return respuesta

    # ---------- componentes compartidos (ticket 5): solo la sección 3

    def nuevo_borrador_componente(self, valor: str, conflicto: bool = False) -> dict:
        ahora = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        actual = self.componente["componente"]["valor"]
        base = actual + "<!-- base anterior -->" if conflicto else actual
        return {"clase": "Seccion", "id": 3, "valor": valor, "base": {"valor": base, "hash": _hash(base)},
                "creado": ahora, "modificado": ahora, "tieneCambio": valor != base}

    def validaciones_componente(self, valor) -> list[dict]:
        capturadas = (self.json("validar_seccion_3.json") or {}).get("validaciones") or []
        base = (self.borrador_componente or {}).get("base", {}).get("valor", self.componente["componente"]["valor"])
        # El texto sin cambios no agrega CSS: solo queda el aviso de reglas especiales del impacto.
        return capturadas if valor != base else [v for v in capturadas if not v["codigo"].startswith("css2")]

    def respuesta_componente(self) -> dict:
        b = self.borrador_componente
        actual = self.componente["componente"]["valor"]
        conflicto = None
        if b and b["base"]["hash"] != _hash(actual):
            conflicto = {"clase": "Seccion", "id": 3, "valorBase": b["base"]["valor"], "valorActual": actual,
                         "hashBase": b["base"]["hash"], "hashActual": _hash(actual), "motivo": "ValorCambiado",
                         "conCambio": b["valor"] != b["base"]["valor"]}
        return {"borrador": b, "componenteExiste": True, "conflicto": conflicto,
                "impacto": self.componente["impacto"],
                "validaciones": self.validaciones_componente(b["valor"]) if b else [], "eliminado": False}

    def resumen_componente(self) -> list[dict]:
        b = self.borrador_componente
        if not b:
            return []
        impacto = self.componente["impacto"]
        return [{"clase": "Seccion", "id": 3, "creado": b["creado"], "modificado": b["modificado"],
                 "tieneCambio": b["tieneCambio"], "componenteExiste": True,
                 "tieneConflicto": self.respuesta_componente()["conflicto"] is not None,
                 "cantidadTipos": impacto["cantidadTipos"], "cantidadUsos": impacto["cantidadUsos"], "error": None}]

    def responder_componente(self, metodo: str, ruta: str, cuerpo, no_encontrado) -> tuple[int, object, dict]:
        seccion = "/api/componentes/seccion/3"
        if metodo == "GET" and ruta == "/api/componentes/borradores":
            return 200, self.resumen_componente(), {}
        if not ruta.startswith(seccion):
            return no_encontrado
        resto = ruta[len(seccion):]
        b = self.borrador_componente
        if metodo == "GET" and resto == "":
            return 200, dict(self.componente, borrador=b), {}
        if metodo == "GET" and resto == "/impacto":
            return 200, self.componente["impacto"], {}
        if metodo == "POST" and resto == "/validar":
            valor = (cuerpo or {}).get("valor")
            if valor is None:
                return 400, {"title": "Borrador inválido", "status": 400, "detail": "falta 'valor'"}, {}
            base = b["base"]["valor"] if b else self.componente["componente"]["valor"]
            return 200, {"clase": "Seccion", "id": 3, "tieneCambio": valor != base, "conBorrador": b is not None,
                         "validaciones": self.validaciones_componente(valor)}, {}
        if resto == "/borrador":
            if metodo == "GET":
                return (200, self.respuesta_componente(), {}) if b else no_encontrado
            if metodo == "PUT":
                valor = (cuerpo or {}).get("valor")
                with self.candado:
                    nuevo = b is None
                    if nuevo:
                        self.borrador_componente = self.nuevo_borrador_componente(valor)
                    else:
                        b.update(valor=valor, tieneCambio=valor != b["base"]["valor"],
                                 modificado=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
                return 200, self.respuesta_componente(), {"X-Borrador-Nuevo": "true" if nuevo else "false"}
            if metodo == "DELETE":
                if not b:
                    return no_encontrado
                self.borrador_componente = None
                return 204, None, {}
        if metodo == "POST" and resto == "/borrador/conflictos/resolver" and b:
            actual = self.componente["componente"]["valor"]
            if (cuerpo or {}).get("accion") == "descartarCambio":
                self.borrador_componente = None
                return 200, dict(self.respuesta_componente(), eliminado=True), {}
            b.update(base={"valor": actual, "hash": _hash(actual)}, tieneCambio=b["valor"] != actual)
            return 200, self.respuesta_componente(), {}
        return no_encontrado

    # ---------- scripts (ticket 6): respuestas 200 capturadas de la API real; 409/404/400 armados aquí

    def responder_scripts(self, ruta: str, cuerpo, no_encontrado) -> tuple[int, object, dict]:
        c = cuerpo or {}
        ticket, autor = str(c.get("ticket") or ""), str(c.get("autor") or "").strip()
        problemas = []
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,60}", ticket):
            problemas.append(f"El ticket '{ticket}' no es válido: usa letras, dígitos, '-' o '_' (máximo 60); es el nombre de los archivos.")
        if not autor:
            problemas.append("Falta el autor.")
        if problemas:
            return 400, {"title": "No se puede generar el script", "status": 400, "detail": problemas[0],
                         "problemas": problemas}, {}
        if ruta.startswith("/api/scripts/nuevo/"):
            return self.responder_scripts_alta(ruta, ticket, no_encontrado)
        b, bc = self.borrador, self.borrador_componente
        conflicto_c = self.respuesta_componente()["conflicto"] if bc else None
        if ruta == f"/api/scripts/tipo/{self.tipo['id']}":
            excluida = any(str(x.get("clase", "")).lower() == "seccion" and x.get("id") == 3
                           for x in c.get("componentesExcluidos") or [])
            usa_c = bc is not None and not excluida
            if not b and not usa_c:
                return 404, {"title": "Sin borradores", "status": 404,
                             "detail": f"No hay borrador del tipo {self.tipo['id']} ni borradores de componentes que use: no hay nada que generar."}, {}
            con_tipo = [x for x in (b or {}).get("conflictos", []) if x["conCambio"]]
            con_comp = [conflicto_c] if usa_c and conflicto_c and conflicto_c["conCambio"] else []
            if con_tipo or con_comp:
                return 409, {"title": "Conflictos sin resolver", "status": 409,
                             "detail": "Hay conflictos con cambio sin resolver: no se genera el script.",
                             "problemas": ["Conflicto sin resolver"] * (len(con_tipo) + len(con_comp)),
                             "conflictosTipo": [dict(x, internalSectionId=None) for x in con_tipo],
                             "conflictosComponentes": con_comp}, {}
            # Respuesta real (ticket 10): 111269_tipo1223.sql, conteo { tipo: 2, componentes: 1 } y soloDev [].
            datos = self.json("scripts_tipo_1223.json")
            if excluida:
                cambios = [x for x in datos["resumen"]["cambios"] if "(compartido)" not in x]
                datos = dict(datos, componentesIncluidos=[], componentesExcluidos=[{"clase": "Seccion", "id": 3}],
                             resumen=dict(datos["resumen"], impacto=[], cambios=cambios,
                                          conteo={"tipo": len(cambios), "componentes": 0, "total": len(cambios)}))
            # Archivo solo dev de muestra (la API real no lo genera en ediciones): se mide su pestaña y su línea del resumen.
            datos = dict(datos, archivos=datos["archivos"] + [{
                "nombre": f"solo_dev_{ticket}_tipo{self.tipo['id']}.sql",
                "contenido": "-- Solo dev: no llevar a producción\r\nUSE [Masterdb];\r\nSELECT 1;\r\n"}],
                resumen=dict(datos["resumen"], soloDev=["Solo dev (archivo aparte): archivo de muestra del check."]))
            return 200, datos, {}
        if ruta == "/api/scripts/componente/seccion/3":
            if not bc:
                return 404, {"title": "Sin borrador", "status": 404, "detail": "La sección #3 no tiene borrador."}, {}
            if conflicto_c and conflicto_c["conCambio"]:
                return 409, {"title": "Conflictos sin resolver", "status": 409,
                             "detail": "Hay conflictos con cambio sin resolver: no se genera el script.",
                             "problemas": ["Conflicto sin resolver"], "conflictosTipo": [],
                             "conflictosComponentes": [conflicto_c]}, {}
            return 200, self.json("scripts_componente_seccion_3.json"), {}
        return no_encontrado

    # PNG 1x1 para las imágenes de la ayuda (el capítulo capturado las pide a /api/ayuda/img/…).
    PNG_1X1 = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
                            "0000000d49444154789c63b8fbe8c57f0008ee03a7ba52c91c0000000049454e44ae426082")

    def responder_ayuda(self, metodo: str, url) -> tuple[int, bytes, str, dict]:
        """Ticket 9 · GET /api/ayuda (JSON), /api/ayuda/{capitulo} (HTML con CSP) y /api/ayuda/img/{archivo} (PNG)."""
        ruta = url.path.rstrip("/")
        retraso = self.retrasos.get(f"{metodo} {ruta}")
        if retraso:
            time.sleep(retraso / 1000)
        problema = lambda status, titulo, detalle: (
            status, json.dumps({"title": titulo, "status": status, "detail": detalle}, ensure_ascii=False).encode("utf-8"),
            "application/problem+json", {})
        if metodo not in ("GET", "HEAD"):
            return problema(405, "Método no permitido", ruta)
        if self.ayuda_error:
            return problema(503, "Ayuda no disponible",
                            "No existe la carpeta de la ayuda (Ayuda:Carpeta). Configúrala en appsettings o con Ayuda__Carpeta.")
        if ruta == "/api/ayuda":
            return 200, (self.carpeta / "ayuda_indice.json").read_bytes(), "application/json; charset=utf-8", {}
        nombre = ruta[len("/api/ayuda/"):]
        if nombre.startswith("img/"):
            return 200, self.PNG_1X1, "image/png", {"X-Content-Type-Options": "nosniff"}
        pagina = self.carpeta / f"ayuda_{nombre}.html"
        if "/" in nombre or "\\" in nombre or ".." in nombre or not pagina.is_file():
            return problema(404, "No encontrado", f"'{nombre}' no es un capítulo de la ayuda (API simulada: README y 03).")
        return 200, pagina.read_bytes(), "text/html; charset=utf-8", {
            "Content-Security-Policy": "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'",
            "X-Content-Type-Options": "nosniff"}

    # ---------- ticket 11: idioma nuevo en el borrador del tipo 1259

    def copia(self, nombre: str) -> dict:
        return json.loads(json.dumps(self.json(nombre)))

    def armar_1259(self, configuracion: dict, es_aceptada: bool) -> dict:
        """Borrador del 1259 con francés nuevo: respuesta capturada según el estado (asunto vacío = la del POST, sin sus
        avisos de prellenado y propuesta; con asunto = la del PUT /idiomas/4; sin la propuesta de ES = la del PUT del
        tipo), con la configuración recibida."""
        completo = bool((configuracion.get("subject") or "").strip())
        if not completo:
            r = self.copia("idioma_nuevo_1259_post.json")
            nuevo = r["idiomasNuevos"][0]
            nuevo["avisos"] = [a for a in nuevo["avisos"] if a["codigo"] not in ("prellenado", "propuesta")]
            if not es_aceptada:
                plantilla = self.copia("idioma_nuevo_1259_sin_es.json")
                r["borrador"]["cambios"] = plantilla["borrador"]["cambios"]
                nuevo["propuestas"] = plantilla["idiomasNuevos"][0]["propuestas"]
                nuevo["avisos"] += [a for a in plantilla["idiomasNuevos"][0]["avisos"] if a["codigo"] == "alcance_web"]
        else:
            r = self.copia("idioma_nuevo_1259_put.json" if es_aceptada else "idioma_nuevo_1259_sin_es.json")
        nuevo = r["idiomasNuevos"][0]
        nuevo["configuracion"] = dict(configuracion, lang=4)
        ahora = self.ahora()
        creado = self.borrador_1259["borrador"]["creado"] if self.borrador_1259 else ahora
        r["borrador"].update(creado=creado, modificado=ahora)
        nuevo.update(creado=creado, modificado=ahora)
        return r

    @staticmethod
    def es_aceptada_1259(respuesta: dict) -> bool:
        return any(c["campo"] == "DisclaimerSuperior" and c["lang"] == 1 and c["valor"] == "9"
                   for c in respuesta["borrador"]["cambios"])

    def resumen_1259(self) -> list[dict]:
        b = self.borrador_1259
        if not b:
            return []
        d = b["borrador"]
        return [{"tipoId": 1259, "nombre": d["nombreTipo"], "creado": d["creado"], "modificado": d["modificado"],
                 "cantidadCambios": len(d["cambios"]), "tieneConflictos": False, "cantidadConflictos": 0,
                 "tipoExiste": True, "idiomasNuevos": [i["lang"] for i in b.get("idiomasNuevos") or []]}]

    def responder_1259(self, metodo: str, ruta: str, cuerpo, ticket: str, no_encontrado) -> tuple[int, object, dict]:
        base = "/api/borradores/1259"
        b = self.borrador_1259
        sin_borrador = (404, {"title": "Borrador no encontrado", "status": 404,
                              "detail": "No hay borrador guardado para el tipo 1259."}, {})
        if metodo == "GET" and ruta == "/api/tipos/1259":
            return 200, self.tipo_1259, {}
        if ruta == base:
            if metodo == "GET":
                return (200, b, {}) if b else sin_borrador
            if metodo == "DELETE":
                if not b:
                    return sin_borrador
                self.borrador_1259 = None
                return 204, None, {}
            if metodo == "PUT":
                cambios = (cuerpo or {}).get("cambios") or []
                es = any(c.get("campo") == "DisclaimerSuperior" and c.get("lang") == 1 and c.get("valor") == "9"
                         for c in cambios)
                with self.candado:
                    nuevo = b is None
                    if b and b.get("idiomasNuevos"):
                        self.borrador_1259 = self.armar_1259(b["idiomasNuevos"][0]["configuracion"], es)
                    else:
                        # Sin idioma nuevo el recorrido solo crea el borrador vacío (base de la respuesta del DELETE).
                        r = self.copia("idioma_nuevo_1259_quitado.json")
                        r["borrador"]["cambios"] = []
                        r["borrador"].update(creado=self.ahora(), modificado=self.ahora())
                        self.borrador_1259 = r
                return 200, self.borrador_1259, {"X-Borrador-Nuevo": "true" if nuevo else "false"}
        if ruta == base + "/conflictos" and metodo == "GET":
            if not b:
                return sin_borrador
            return 200, {"tipoId": 1259, "tipoExiste": True, "conflictos": [], "idiomasNuevosEnConflicto": []}, {}
        if ruta == base + "/idiomas" and metodo == "POST":
            if b and b.get("idiomasNuevos"):
                return self.invalido("El borrador del tipo 1259 ya agrega francés (4).")
            with self.candado:
                nuevo = b is None
                r = self.copia("idioma_nuevo_1259_post.json")
                ahora = self.ahora()
                r["borrador"].update(creado=ahora, modificado=ahora)
                r["idiomasNuevos"][0].update(creado=ahora, modificado=ahora)
                self.borrador_1259 = r
            return 201, r, {"X-Borrador-Nuevo": "true" if nuevo else "false", "Location": base}
        if ruta == base + "/idiomas/4":
            if not b or not b.get("idiomasNuevos"):
                return sin_borrador
            if metodo == "PUT":
                with self.candado:
                    self.borrador_1259 = self.armar_1259(cuerpo or {}, self.es_aceptada_1259(b))
                return 200, self.borrador_1259, {}
            if metodo == "DELETE":
                r = self.copia("idioma_nuevo_1259_quitado.json")
                r["borrador"].update(creado=b["borrador"]["creado"], modificado=self.ahora())
                self.borrador_1259 = r
                return 200, r, {}
        if metodo == "POST" and ruta == "/api/scripts/tipo/1259":
            if not b:
                return 404, {"title": "Sin borradores", "status": 404,
                             "detail": "No hay borrador del tipo 1259 ni borradores de componentes que use: no hay nada que generar."}, {}
            nuevos = b.get("idiomasNuevos") or []
            if nuevos and not (nuevos[0]["configuracion"].get("subject") or "").strip():
                return 400, self.json("scripts_tipo_1259_400.json"), {}
            # Respuesta real: 111269_tipo1259.sql con las propuestas ES/EN y francés (4), resumen.idiomasNuevos.
            datos = self.copia("scripts_tipo_1259.json")
            datos["archivos"] = [dict(a, nombre=a["nombre"].replace("111269", ticket)) for a in datos["archivos"]]
            return 200, datos, {}
        return no_encontrado

    def responder(self, metodo: str, url, cuerpo) -> tuple[int, object, dict]:
        """(status, cuerpo JSON o None, cabeceras extra)."""
        ruta = url.path.rstrip("/")
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        retraso = self.retrasos.get(f"{metodo} {ruta}")
        if retraso:
            time.sleep(retraso / 1000)
        no_encontrado = (404, {"title": "No encontrado", "status": 404, "detail": f"{ruta} no existe en la API simulada"}, {})
        tipo_id = str(self.tipo["id"])
        borradores = f"/api/borradores/{tipo_id}"
        if ruta.startswith("/api/componentes/"):
            return self.responder_componente(metodo, ruta, cuerpo, no_encontrado)
        if ruta == "/api/tipos/1259" or ruta.startswith("/api/borradores/1259") or ruta == "/api/scripts/tipo/1259":
            if ruta.startswith("/api/scripts/"):
                c = cuerpo or {}
                if not re.fullmatch(r"[A-Za-z0-9_-]{1,60}", str(c.get("ticket") or "")) or not str(c.get("autor") or "").strip():
                    return self.responder_scripts(ruta, cuerpo, no_encontrado)
                return self.responder_1259(metodo, ruta, cuerpo, str(c.get("ticket")), no_encontrado)
            return self.responder_1259(metodo, ruta, cuerpo, "", no_encontrado)
        if metodo == "POST" and ruta.startswith("/api/scripts/"):
            return self.responder_scripts(ruta, cuerpo, no_encontrado)
        if ruta == "/api/nuevas" or ruta.startswith("/api/nuevas/"):
            return self.responder_altas(metodo, ruta, q, cuerpo, no_encontrado)
        if ruta.startswith("/api/legacy/"):
            return self.responder_legacy(metodo, ruta, q, no_encontrado)

        if metodo == "GET":
            fijas = {"/api/salud": "salud.json", "/api/tipos": "tipos.json",
                     f"/api/tipos/{tipo_id}": "tipo_1223.json",
                     "/api/catalogos/plantillas": "plantillas.json", "/api/catalogos/estilos": "estilos.json"}
            if ruta in fijas:
                return 200, self.json(fijas[ruta]), {}
            if ruta == "/api/catalogos/disclaimers":
                return 200, self.json(f"disc_{q.get('lang')}_{q.get('isTop')}.json") or [], {}
            if ruta == "/api/catalogos/secciones":
                return 200, self.json(f"sec_{q.get('seccion')}_{q.get('lang')}.json") or [], {}
            if ruta == "/api/borradores":
                b = self.borrador
                if not b:
                    return 200, self.resumen_1259(), {}
                d = b["borrador"]
                return 200, [{"tipoId": d["tipoId"], "nombre": d["nombreTipo"], "creado": d["creado"],
                              "modificado": d["modificado"], "cantidadCambios": len(d["cambios"]),
                              "tieneConflictos": bool(b["conflictos"]), "cantidadConflictos": len(b["conflictos"]),
                              "tipoExiste": True}] + self.resumen_1259(), {}
            if ruta == borradores:
                return (200, self.borrador, {}) if self.borrador else no_encontrado
            if ruta == borradores + "/conflictos":
                if not self.borrador:
                    return no_encontrado
                return 200, {"tipoId": self.tipo["id"], "tipoExiste": True,
                             "conflictos": self.borrador["conflictos"]}, {}
            return no_encontrado

        if metodo == "POST" and ruta in ("/api/visor/correo", "/api/visor/web"):
            modo = "correo" if ruta.endswith("correo") else "web"
            c = cuerpo or {}
            alta = self.altas.get(c.get("borradorAltaId"))
            # Ticket 10: la API aplica los borradores de componentes compartidos con borradorAltaId (si el alta usa la
            # sección) y con tipoId + usarBorrador; lo indica en componentesAplicados (capturado: [{ Seccion, 3 }]).
            usa_3 = alta is not None and any(s.get("sectionContentId") == 3 for i in alta.get("idiomas") or []
                                             for s in i.get("secciones") or [])
            aplicados = [{"clase": "Seccion", "id": 3}] if self.borrador_componente and self.borrador_componente["tieneCambio"] and (
                usa_3 or (alta is None and c.get("usarBorrador") is True)) else []
            # Ticket 11: el 1259 con francés nuevo en el borrador (respuestas reales del visor con usarBorrador, lang 4)
            if c.get("tipoId") == 1259 and c.get("lang") == 4 and c.get("usarBorrador") is True and \
                    self.borrador_1259 and self.borrador_1259.get("idiomasNuevos"):
                return 200, self.json(f"visor_{modo}_1259_fr.json"), {}
            if alta and alta.get("origenLegacy"):
                # Respuesta real del visor de un alta basada en Legacy (334 EN + 337 ES), en inglés.
                return 200, dict(self.json(f"visor_{modo}_alta_legacy.json"), componentesAplicados=aplicados), {}
            if alta and not alta.get("baseTipoId"):
                # Respuesta real del visor de un alta vacía en inglés con la cabecera compartida 3, el cuerpo
                # propio y el pie por llenar (marcador %ContentBottom_0% sin reemplazar).
                return 200, dict(self.json(f"visor_{modo}_alta_parcial.json"), componentesAplicados=aplicados), {}
            return 200, dict(self.json(f"visor_{modo}.json"), componentesAplicados=aplicados), {}

        if metodo == "PUT" and ruta == borradores:
            base = {(b["campo"], b["lang"], b["sectionContentId"]): b["valor"] for b in self.base()}
            cambios = [{"campo": c.get("campo"), "lang": c.get("lang"), "sectionContentId": c.get("sectionContentId"),
                        "valor": c.get("valor")}
                       for c in (cuerpo or {}).get("cambios") or []
                       if base.get((c.get("campo"), c.get("lang"), c.get("sectionContentId")), object()) != c.get("valor")]
            with self.candado:
                nuevo = self.borrador is None
                if nuevo:
                    self.borrador = self.nuevo_borrador(cambios)
                else:
                    self.borrador["borrador"]["cambios"] = cambios
                    self.borrador["borrador"]["modificado"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            return 200, self.borrador, {"X-Borrador-Nuevo": "true" if nuevo else "false"}

        if metodo == "DELETE" and ruta == borradores:
            if not self.borrador:
                return no_encontrado
            self.borrador = None
            return 204, None, {}

        if metodo == "POST" and ruta == borradores + "/conflictos/resolver":
            if not self.borrador:
                return no_encontrado
            c = cuerpo or {}
            llave = (c.get("campo"), c.get("lang"), c.get("sectionContentId"))
            self.borrador["conflictos"] = [x for x in self.borrador["conflictos"]
                                           if (x["campo"], x["lang"], x["sectionContentId"]) != llave]
            return 200, self.borrador, {}

        return no_encontrado


# ---------------------------------------------------------------- servidor

def _servidor(dist: Path, api: ApiSimulada, resultado: dict, listo: threading.Event) -> ThreadingHTTPServer:
    inyectar = ('<script src="/__contraste/medir.js"></script>'
                '<script src="/__contraste/recorrido.js"></script></body>')
    indice = (dist / "index.html").read_text(encoding="utf-8").replace("</body>", inyectar).encode("utf-8")

    class Manejador(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def _enviar(self, status: int, cuerpo: bytes, tipo: str, extra: dict | None = None):
            self.send_response(status)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(cuerpo)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(cuerpo)

        def _cuerpo(self):
            largo = int(self.headers.get("Content-Length") or 0)
            datos = self.rfile.read(largo) if largo else b""
            try:
                return json.loads(datos.decode("utf-8")) if datos else None
            except ValueError:
                return None

        def _atender(self):
            url = urlparse(self.path)
            cuerpo = self._cuerpo() if self.command in ("POST", "PUT") else None
            if url.path == "/api/ayuda" or url.path.startswith("/api/ayuda/"):
                status, contenido, tipo, extra = api.responder_ayuda(self.command, url)
                return self._enviar(status, contenido, tipo, extra)
            if url.path.startswith("/api/"):
                status, datos, extra = api.responder(self.command, url, cuerpo)
                tipo = "application/problem+json" if status >= 400 else "application/json; charset=utf-8"
                contenido = b"" if datos is None else json.dumps(datos, ensure_ascii=False).encode("utf-8")
                return self._enviar(status, contenido, tipo, extra)
            if url.path == "/__contraste/escenario" and self.command == "POST":
                api.escenario(cuerpo or {})
                return self._enviar(204, b"", "text/plain")
            if url.path == "/__contraste/resultado" and self.command == "POST":
                resultado.update(cuerpo or {})
                listo.set()
                return self._enviar(204, b"", "text/plain")
            if url.path in ("/__contraste/medir.js", "/__contraste/recorrido.js"):
                archivo = RECURSOS / url.path.rsplit("/", 1)[1]
                return self._enviar(200, archivo.read_bytes(), TIPOS_MIME[".js"])
            archivo = (dist / url.path.lstrip("/")).resolve()
            if url.path != "/" and archivo.is_file() and dist.resolve() in archivo.parents:
                return self._enviar(200, archivo.read_bytes(),
                                    TIPOS_MIME.get(archivo.suffix.lower(), "application/octet-stream"))
            # rutas del router (history mode) → index.html con el medidor inyectado
            return self._enviar(200, indice, TIPOS_MIME[".html"])

        do_GET = do_POST = do_PUT = do_DELETE = do_HEAD = _atender

    class Servidor(ThreadingHTTPServer):
        daemon_threads = True

        def handle_error(self, request, client_address):
            pass  # el navegador corta conexiones al cerrarse: no es un fallo del check

    return Servidor(("127.0.0.1", 0), Manejador)


def _cerrar_navegador(proceso: subprocess.Popen):
    if proceso.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proceso.pid)], capture_output=True)
    else:
        proceso.kill()
    try:
        proceso.wait(timeout=15)
    except subprocess.TimeoutExpired:
        pass


def _recorrer(dist: Path, navegador: str, perfil: Path) -> dict:
    api = ApiSimulada(RECURSOS / "api")
    resultado: dict = {}
    listo = threading.Event()
    servidor = _servidor(dist, api, resultado, listo)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    url = f"http://127.0.0.1:{servidor.server_address[1]}/editor"
    proceso = subprocess.Popen(
        [navegador, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
         "--disable-extensions", "--disable-sync", "--disable-background-networking",
         "--disable-background-timer-throttling", "--disable-renderer-backgrounding",
         "--force-device-scale-factor=1", "--window-size=1280,1000", f"--user-data-dir={perfil}", url],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        if not listo.wait(TIMEOUT_RECORRIDO_S):
            resultado["error"] = (f"el recorrido no terminó en {TIMEOUT_RECORRIDO_S} s "
                                  f"(¿la app no arrancó o el navegador no abrió {url}?)")
    finally:
        _cerrar_navegador(proceso)
        servidor.shutdown()
        servidor.server_close()
    return resultado


# ---------------------------------------------------------------- reporte

def _reporte(resultado: dict) -> list[dict]:
    estados = resultado.get("estados") or []
    alcanzados = [e for e in estados if e.get("alcanzado")]
    hallazgos: list[dict] = []

    # Un mismo texto bajo AA suele repetirse en muchos estados: una fila por texto/elemento/colores.
    filas: dict[tuple, dict] = {}
    for e in alcanzados:
        for b in e.get("bajos") or []:
            llave = (b["texto"], b["elemento"], b["color"], b["fondo"], b["tipo"].split("·")[0])
            fila = filas.setdefault(llave, dict(b, estados=[]))
            if e["nombre"] not in fila["estados"]:
                fila["estados"].append(e["nombre"])
    if filas:
        ordenadas = sorted(filas.values(), key=lambda f: (f["ratio"], f["texto"]))
        lineas = [f"- «{f['texto']}» ({f['tipo']}) en {f['elemento']}: {f['color']} sobre {f['fondo']} = "
                  f"{f['ratio']}:1 (mínimo {f['minimo']}:1, {f['tam']}/{f['peso']}) · estados: "
                  + ", ".join(f["estados"][:3]) + (f" y {len(f['estados']) - 3} más" if len(f["estados"]) > 3 else "")
                  for f in ordenadas[:MAX_FILAS]]
        if len(ordenadas) > MAX_FILAS:
            lineas.append(f"- … y {len(ordenadas) - MAX_FILAS} textos más")
        hallazgos.append({"id": CHECK_ID, "resultado": "fallo", "severidad": "error",
                          "detalle": f"{len(ordenadas)} texto(s) visibles bajo el contraste WCAG AA "
                                     f"(4.5:1; 3:1 en texto grande) en {len(alcanzados)} estados medidos:\n"
                                     + "\n".join(lineas)})

    no_alcanzados = [e for e in estados if not e.get("alcanzado")]
    if resultado.get("error") or no_alcanzados or not estados:
        motivos = [f"- {e['nombre']}: {e.get('error', 'sin detalle')}" for e in no_alcanzados]
        if resultado.get("error"):
            motivos.append(f"- recorrido: {resultado['error']}")
        hallazgos.append({"id": CHECK_ID + "_cobertura", "resultado": "fallo", "severidad": "warning",
                          "detalle": "estados de las pantallas 1, 2, 3 y 4 que el recorrido no pudo medir (revisa "
                                     ".claude/checks/web_contraste/recorrido.js si la pantalla cambió):\n"
                                     + ("\n".join(motivos) or "- ningún estado medido")})

    if not filas:
        medidos = sum(e.get("medidos") or 0 for e in alcanzados)
        hallazgos.insert(0, {"id": CHECK_ID, "resultado": "ok",
                             "detalle": f"{medidos} textos medidos en {len(alcanzados)} estados: "
                                        f"todos cumplen WCAG AA"})
    return hallazgos


def run(project_root, archivos, ctx) -> list[dict]:
    raiz = Path(project_root).resolve()
    if not _toca_frontend(raiz, archivos):
        return [{"id": CHECK_ID, "resultado": "ok",
                 "detalle": "la fase no tocó el frontend: contraste omitido"}]
    web = raiz / CARPETA_WEB
    vite = web / "node_modules" / "vite" / "bin" / "vite.js"
    node = shutil.which("node")
    if node is None:
        return [{"id": CHECK_ID, "resultado": "error_check", "severidad": "error",
                 "detalle": "node no está en el PATH: no se pudo construir el frontend"}]
    if not vite.is_file():
        return [{"id": CHECK_ID, "resultado": "error_check", "severidad": "error",
                 "detalle": f"no existe {vite.relative_to(raiz).as_posix()}: corre npm ci en {CARPETA_WEB.as_posix()}"}]
    navegador = _navegador()
    if navegador is None:
        return [{"id": CHECK_ID, "resultado": "error_check", "severidad": "error",
                 "detalle": "no se encontró Chrome ni Edge (define WEB_CONTRASTE_NAVEGADOR con la ruta del ejecutable)"}]

    with tempfile.TemporaryDirectory(prefix="web_contraste_", ignore_cleanup_errors=True) as tmp:
        dist = Path(tmp) / "dist"
        proceso = subprocess.run([node, str(vite), "build", "--outDir", str(dist), "--emptyOutDir",
                                  "--logLevel", "warn"],
                                 cwd=web, capture_output=True, text=True, encoding="utf-8",
                                 errors="replace", timeout=TIMEOUT_BUILD_S)
        if proceso.returncode != 0 or not (dist / "index.html").is_file():
            return [{"id": CHECK_ID, "resultado": "error_check", "severidad": "error",
                     "detalle": f"vite build falló, no se pudo medir el contraste:\n{_cola(proceso)}"}]
        perfil = Path(tmp) / "perfil-navegador"
        resultado = _recorrer(dist, navegador, perfil)
        # el navegador puede tardar en soltar su perfil; TemporaryDirectory no debe fallar por eso
        for _ in range(10):
            shutil.rmtree(perfil, ignore_errors=True)
            if not perfil.exists():
                break
            time.sleep(0.5)
    return _reporte(resultado)

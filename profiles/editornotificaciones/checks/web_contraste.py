"""Check estructural: contraste WCAG AA de todo texto visible de la pantalla 1, si la fase tocó el frontend.

Construye src/Web en una carpeta temporal (vite build), la sirve con una API simulada (respuestas
capturadas del tipo 1223 en web_contraste/api; nunca toca Masterdb, la API real ni %LOCALAPPDATA%) y
la abre en Chrome o Edge sin interfaz. web_contraste/recorrido.js lleva la app por estados
representativos (lectura, cargas, visor correo y web, idiomas, lista de borradores, edición, guardado,
confirmaciones, conflictos, foco) y web_contraste/medir.js mide cada texto, valor y placeholder.
Falla si alguno queda bajo 4.5:1 (3:1 en texto grande), con elemento, colores y ratio.

Sin dependencias nuevas: solo la biblioteca estándar de Python y el Chrome/Edge instalado (o el que
diga la variable WEB_CONTRASTE_NAVEGADOR).
"""
from __future__ import annotations

import hashlib
import json
import os
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
TIMEOUT_RECORRIDO_S = 240
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
    """Respuestas de /api con el contrato de src/Api (ticket 4) a partir de web_contraste/api/*.json.

    El borrador vive en memoria; recorrido.js elige el escenario (sin borrador o con un borrador con
    conflictos) y los retrasos por ruta para poder medir los estados de carga.
    """

    def __init__(self, carpeta: Path):
        self.carpeta = carpeta
        self.tipo = self.json("tipo_1223.json")
        self.borrador = None
        self.retrasos: dict[str, int] = {}
        self.candado = threading.Lock()

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
                self.borrador = self.con_conflicto() if datos["borrador"] == "conflicto" else None

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
        respuesta["validaciones"] = [{"nivel": "advertencia", "codigo": "marcador_sin_reemplazar",
                                      "mensaje": "%CustomerName% queda sin reemplazar (asunto).",
                                      "componente": "marcador:CustomerName"}]
        return respuesta

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
                    return 200, [], {}
                d = b["borrador"]
                return 200, [{"tipoId": d["tipoId"], "nombre": d["nombreTipo"], "creado": d["creado"],
                              "modificado": d["modificado"], "cantidadCambios": len(d["cambios"]),
                              "tieneConflictos": bool(b["conflictos"]), "cantidadConflictos": len(b["conflictos"]),
                              "tipoExiste": True}], {}
            if ruta == borradores:
                return (200, self.borrador, {}) if self.borrador else no_encontrado
            if ruta == borradores + "/conflictos":
                if not self.borrador:
                    return no_encontrado
                return 200, {"tipoId": self.tipo["id"], "tipoExiste": True,
                             "conflictos": self.borrador["conflictos"]}, {}
            return no_encontrado

        if metodo == "POST" and ruta in ("/api/visor/correo", "/api/visor/web"):
            return 200, self.json("visor_correo.json" if ruta.endswith("correo") else "visor_web.json"), {}

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
                          "detalle": "estados de la pantalla 1 que el recorrido no pudo medir (revisa "
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

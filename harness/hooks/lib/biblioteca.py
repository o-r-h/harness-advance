"""Biblioteca de lecciones del proyecto: entradas aprobadas/rechazadas e INDEX.md derivado.

Vive en <proyecto>/.claude/biblioteca/ y se versiona con el proyecto (DA6).
"""
from __future__ import annotations

import re
from pathlib import Path

# (campo en el JSON, etiqueta en la entrada), en el orden de la entrada.
_CAMPOS = (("senal", "señal"), ("leccion", "lección"), ("evidencia", "evidencia"),
           ("confianza", "confianza"), ("dimension", "dimension"),
           ("componente", "componente"), ("origen", "origen"),
           ("leccion_original", "lección original"), ("motivo", "motivo"))

_INTRO = ("Índice derivado: se reconstruye desde las entradas en disco. **Toda lección es "
          "hipótesis hasta re-verificarla en el código (DA8).**")


def biblioteca_dir(project_root: Path) -> Path:
    return Path(project_root) / ".claude" / "biblioteca"


def entrada_path(project_root: Path, ref: str, subdir: str = "entradas") -> Path:
    return biblioteca_dir(project_root) / subdir / f"{ref.replace('/', '-')}.md"


def escribir_entrada(project_root: Path, ticket_id: str, fase_id: str, hallazgo: dict,
                     fecha: str | None = None) -> Path:
    estado = hallazgo.get("estado")
    if estado == "aprobado":
        subdir = "entradas"
    elif estado == "rechazado":
        subdir = "rechazados"
    else:
        raise ValueError(f"solo se guardan hallazgos aprobados o rechazados, no '{estado}'")
    destino = biblioteca_dir(project_root) / subdir / f"{ticket_id}-{fase_id}-{hallazgo['id']}.md"
    destino.parent.mkdir(parents=True, exist_ok=True)
    lineas = [f"# {ticket_id}/{fase_id}/{hallazgo['id']}", ""]
    for clave, etiqueta in _CAMPOS:
        valor = hallazgo.get(clave)
        if valor:
            lineas.append(f"- **{etiqueta}**: {' '.join(str(valor).split())}")
    if estado == "aprobado" and fecha:
        lineas.append(f"- **aprobada**: {fecha}")
    destino.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    reconstruir_indice(project_root)
    return destino


def _campo(texto: str, etiqueta: str) -> str:
    m = re.search(rf"^- \*\*{re.escape(etiqueta)}\*\*: (.*)$", texto, re.MULTILINE)
    return m.group(1).strip() if m else ""


_RE_FALLA = re.compile(r"^- \*\*falló\*\*: (\S+) · (\S+) · (implementada|sin pieza) — (.*)$",
                       re.MULTILINE)


def _fallas(texto: str) -> list[dict]:
    return [{"fecha": f, "ref": r, "tipo": t, "leccion": l.strip()}
            for f, r, t, l in _RE_FALLA.findall(texto)]


def leer_entrada(project_root: Path, ref: str) -> dict | None:
    ruta = entrada_path(project_root, ref)
    if not ruta.is_file():
        return None
    texto = ruta.read_text(encoding="utf-8")
    entrada = {"ref": ref}
    for clave, etiqueta in (("senal", "señal"), ("leccion", "lección"),
                            ("componente", "componente"), ("dimension", "dimension"),
                            ("origen", "origen"), ("aprobada", "aprobada"),
                            ("implementada", "implementada")):
        entrada[clave] = _campo(texto, etiqueta)
    entrada["fallas"] = _fallas(texto)
    return entrada


def _editar_lineas(project_root: Path, ref: str) -> tuple[Path, list[str]]:
    ruta = entrada_path(project_root, ref)
    if not ruta.is_file():
        raise ValueError(f"no hay una entrada aprobada para '{ref}'")
    return ruta, ruta.read_text(encoding="utf-8").split("\n")


def _guardar_lineas(project_root: Path, ruta: Path, lineas: list[str]) -> Path:
    ruta.write_text("\n".join(lineas), encoding="utf-8")
    reconstruir_indice(project_root)
    return ruta


def _agregar_al_final(lineas: list[str], nueva: str) -> None:
    # El texto termina en "\n", así que el último elemento es "": la línea nueva va antes.
    if lineas and lineas[-1] == "":
        lineas.insert(len(lineas) - 1, nueva)
    else:
        lineas.append(nueva)


def registrar_falla(project_root: Path, ref_original: str, ref_nueva: str, leccion: str,
                    fecha: str) -> Path:
    ruta, lineas = _editar_lineas(project_root, ref_original)
    tipo = "implementada" if _campo("\n".join(lineas), "implementada") else "sin pieza"
    _agregar_al_final(lineas, f"- **falló**: {fecha} · {ref_nueva} · {tipo} — "
                              f"{' '.join(leccion.split())}")
    return _guardar_lineas(project_root, ruta, lineas)


def marcar_implementada(project_root: Path, ref: str, nota: str, fecha: str) -> str | None:
    ruta, lineas = _editar_lineas(project_root, ref)
    nueva = f"- **implementada**: {fecha} · {' '.join(nota.split())}"
    anterior = None
    for i, linea in enumerate(lineas):
        if linea.startswith("- **implementada**: "):
            anterior = linea[len("- **implementada**: "):].strip()
            lineas[i] = nueva
            break
    else:
        _agregar_al_final(lineas, nueva)
    _guardar_lineas(project_root, ruta, lineas)
    return anterior


def _motivo_retirada(texto: str) -> str:
    """El motivo de la línea `retirada` (`<fecha> · <motivo>`)."""
    valor = _campo(texto, "retirada")
    return valor.split(" · ", 1)[1].strip() if " · " in valor else valor


def _copiar_a_retiradas(project_root: Path, ref: str, motivo: str, fecha: str) -> Path:
    """Escribe la copia retirada; la de entradas/ sigue hasta que se borre aparte.

    Siempre parte del texto de entradas/: repetir la copia tras un fallo la
    reescribe igual, sin una segunda línea `retirada`."""
    _, lineas = _editar_lineas(project_root, ref)
    _agregar_al_final(lineas, f"- **retirada**: {fecha} · {' '.join(motivo.split())}")
    destino = entrada_path(project_root, ref, subdir="retiradas")
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text("\n".join(lineas), encoding="utf-8")
    return destino


def retirar(project_root: Path, ref: str, motivo: str, fecha: str) -> Path:
    """Mueve la entrada a retiradas/ con su motivo. Nada se borra: las líneas
    `falló` e `implementada` viajan con ella."""
    destino = _copiar_a_retiradas(project_root, ref, motivo, fecha)
    entrada_path(project_root, ref).unlink()
    reconstruir_indice(project_root)
    return destino


def _indice_de(lineas: list[str], etiqueta: str) -> int | None:
    prefijo = f"- **{etiqueta}**: "
    for i, linea in enumerate(lineas):
        if linea.rstrip("\r").startswith(prefijo):
            return i
    return None


def _poner(lineas: list[str], indice: int, nueva: str) -> None:
    """Reemplaza la línea conservando su CRLF si lo tenía."""
    lineas[indice] = nueva + ("\r" if lineas[indice].endswith("\r") else "")


def fusionar(project_root: Path, destino: str, absorbidas: list[str], leccion: str,
             senal: str | None, fecha: str) -> Path:
    """Fusiona las absorbidas en el destino: el destino toma la lección (y la señal)
    nuevas y las líneas `falló` de las otras; las absorbidas se retiran como
    `fusionada en <destino>`. Valida todo antes de escribir.

    Repetirla tras un fallo a mitad (un archivo bloqueado en Windows) termina el
    trabajo sin duplicar: no copia una `falló` ni una `fusionada` que el destino ya
    tenga. El orden deja siempre una copia de cada absorbida: primero retiradas/,
    después el destino y al final se borran de entradas/."""
    if not absorbidas:
        raise ValueError("una fusión necesita al menos una lección que absorber")
    if destino in absorbidas or len(set(absorbidas)) != len(absorbidas):
        raise ValueError("el destino no puede absorberse y las absorbidas no se repiten")
    textos: dict[str, str] = {}
    for ref in [destino, *absorbidas]:
        ruta = entrada_path(project_root, ref)
        if not ruta.is_file():
            raise ValueError(f"no hay una entrada aprobada para '{ref}'")
        textos[ref] = ruta.read_text(encoding="utf-8")
    if len({bool(_campo(t, "implementada")) for t in textos.values()}) > 1:
        raise ValueError("no se fusionan lecciones implementadas con no implementadas: "
                         "sus fallas quedarían fuera de las dos secciones del reporte")

    ruta, lineas = _editar_lineas(project_root, destino)
    i_leccion = _indice_de(lineas, "lección")
    nueva_leccion = f"- **lección**: {' '.join(leccion.split())}"
    if i_leccion is None:
        _agregar_al_final(lineas, nueva_leccion)
    else:
        anterior = _campo(textos[destino], "lección")
        _poner(lineas, i_leccion, nueva_leccion)
        if _indice_de(lineas, "lección original") is None and anterior:
            lineas.insert(i_leccion + 1, f"- **lección original**: {anterior}")
    if senal and senal.strip():
        nueva_senal = f"- **señal**: {' '.join(senal.split())}"
        i_senal = _indice_de(lineas, "señal")
        if i_senal is None:
            lineas.insert(_indice_de(lineas, "lección") or 1, nueva_senal)
        else:
            _poner(lineas, i_senal, nueva_senal)
    presentes = {l.rstrip("\r") for l in lineas}
    for ref in absorbidas:
        texto = textos[ref]
        for linea in texto.split("\n"):
            linea = linea.rstrip("\r")
            if linea.startswith("- **falló**: ") and linea not in presentes:
                _agregar_al_final(lineas, linea)
                presentes.add(linea)
        if any(re.match(rf"^- \*\*fusionada\*\*: \S+ · {re.escape(ref)}(?: |$)", l)
               for l in presentes):
            continue
        implementada = _campo(texto, "implementada")
        marca = f" · implementada {implementada}" if implementada else ""
        _agregar_al_final(lineas, f"- **fusionada**: {fecha} · {ref}{marca}")

    for ref in absorbidas:
        _copiar_a_retiradas(project_root, ref, f"fusionada en {destino}", fecha)
    ruta.write_text("\n".join(lineas), encoding="utf-8")
    for ref in absorbidas:
        entrada_path(project_root, ref).unlink()
    reconstruir_indice(project_root)
    return ruta


def ubicacion(project_root: Path, ref: str) -> tuple[str, str]:
    """Dónde está una lección: ("entradas", ""), ("retiradas", motivo) o ("ninguna", "")."""
    if entrada_path(project_root, ref).is_file():
        return "entradas", ""
    retirada = entrada_path(project_root, ref, subdir="retiradas")
    if retirada.is_file():
        return "retiradas", _motivo_retirada(retirada.read_text(encoding="utf-8"))
    return "ninguna", ""


def _marcas(texto: str) -> str:
    """` (implementada <fecha>) (falló N×)`, solo con las marcas que la entrada trae."""
    marcas = ""
    implementada = _campo(texto, "implementada")
    if implementada:
        marcas += f" (implementada {implementada.split(' · ')[0]})"
    fallas = len(_fallas(texto))
    if fallas:
        marcas += f" (falló {fallas}×)"
    return marcas


def _archivos(carpeta: Path) -> list[Path]:
    return sorted(carpeta.glob("*.md"), key=lambda p: p.name) if carpeta.is_dir() else []


def _resumen(texto: str) -> str:
    """Señal de la entrada; una lección humana puede no traerla y entonces va la lección."""
    return _campo(texto, "señal") or _campo(texto, "lección")


def _clasificacion(texto: str) -> str:
    """`[dimension · componente] `, solo con lo que la entrada trae; vacío si no trae nada."""
    partes = [v for v in (_campo(texto, "dimension"), _campo(texto, "componente")) if v]
    return f"[{' · '.join(partes)}] " if partes else ""


def reconstruir_indice(project_root: Path) -> Path:
    base = biblioteca_dir(project_root)
    aprobadas = []
    for f in _archivos(base / "entradas"):
        t = f.read_text(encoding="utf-8")
        aprobadas.append(f"- {_clasificacion(t)}{_resumen(t)} — entradas/{f.name}"
                         f"{_marcas(t)}")
    retiradas = []
    for f in _archivos(base / "retiradas"):
        t = f.read_text(encoding="utf-8")
        retiradas.append(f"- {_resumen(t)} — retiradas/{f.name} — motivo: "
                         f"{_motivo_retirada(t)}")
    rechazadas = []
    for f in _archivos(base / "rechazados"):
        t = f.read_text(encoding="utf-8")
        rechazadas.append(f"- {_resumen(t)} — motivo: {_campo(t, 'motivo')}")
    lineas = ["# Biblioteca de lecciones", "", _INTRO, "", "## Aprobadas", "",
              *(aprobadas or ["_(vacía)_"]), "",
              "## Retiradas — no aplicar", "",
              *(retiradas or ["_(vacía)_"]), "",
              "## Rechazadas — no volver a proponer", "",
              *(rechazadas or ["_(vacía)_"])]
    destino = base / "INDEX.md"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    return destino

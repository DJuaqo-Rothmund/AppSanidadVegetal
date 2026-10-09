"""Importa el libro «Malezas presentes en Chile» (N. Espinoza, INIA 1996) desde su PDF.

Genera:
  * un JSON con una ficha por especie: familia, nombres comunes, nombre
    científico, nombre en inglés, descripción, ciclo de vida, reproducción,
    hábitat, origen y página;
  * las dos fotos de cada ficha (planta y detalle/plántula), recortadas de la
    página, para mostrarlas en la app y como referencias iniciales de la IA.

El texto viene del OCR del escaneo (ABBYY FineReader) y trae errores: los
nombres se corrigen después con `--correcciones` (JSON {pagina: {campo: valor}}).

Requiere poppler-utils (pdftotext, pdftoppm) y Pillow + numpy.

Uso:
    python scripts/importar_malezas_pdf.py libro.pdf datos/especies-malezas.json \\
        --fotos assets/especies --correcciones datos/correcciones-malezas.json
"""

import argparse
import json
import re
import subprocess
import tempfile
import unicodedata
from pathlib import Path

import numpy as np
from PIL import Image

SECCIONES = {
    "descripcion": r"DESCRIP\w*",
    "ciclo_de_vida": r"CICLO\s+[DO]E\s+VI[DO]A",
    "reproduccion": r"REPRODUC\w*",
    "habitat": r"H[AÁ]BITAT",
    "origen": r"ORIGEN",
}
CAMPOS_DESCRIPCION = ["Tallo", "Hoja", "Flor", "Inflorescencia", "Fruto", "Semilla", "Raíz", "Rizoma"]
ENCABEZADO_FIN = re.compile(r"DESCRIP|CICLO|REPRODUC|H[AÁ]BITAT|ORIGEN|^\s*(Tallo|Hoja)\b")


def texto_pagina(pdf, pagina):
    return subprocess.run(["pdftotext", "-layout", "-f", str(pagina), "-l", str(pagina), str(pdf), "-"],
                          capture_output=True, text=True, check=True).stdout


def sin_acentos(t):
    return "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")


def compactar(t):
    """Quita espacios del OCR dentro de palabras en mayúsculas: 'A M A R A N TH' -> 'AMARANTH'."""
    return re.sub(r"\s+", "", t)


def trozos(linea):
    return [t.strip() for t in re.split(r"\s{3,}", linea.strip()) if t.strip()]


def es_mayusculas(t):
    letras = [c for c in t if c.isalpha()]
    return len(letras) >= 3 and sum(c.isupper() for c in letras) / len(letras) > 0.8


def leer_encabezado(lineas):
    familia, comunes, otros = None, [], []
    for linea in lineas:
        for t in trozos(linea):
            compacto = compactar(t).upper()
            if re.fullmatch(r"[A-Z]+ACEA[ES]", sin_acentos(compacto)):
                familia = compacto[:-1] + "E"  # el OCR a veces lee «...ACEAS»
            elif es_mayusculas(t):
                comunes.append(re.sub(r"\s+", " ", t).strip(" .,"))
            elif re.search(r"[A-Za-z]{3}", t):
                otros.append(t)
    cientifico = next((o for o in otros if re.match(r"^[A-Z£][a-z]", o) and not re.search(r"\b(weed|grass|common|wild)\b", o, re.I)), None)
    ingles = next((o for o in otros if o is not cientifico and re.match(r"^[A-Z]", o)), None)
    subespecie = next((o for o in otros if re.match(r"^(ssp|spp|subsp|var)\.?", o)), None)
    if cientifico and subespecie:
        cientifico = f"{cientifico} {subespecie}"
    return familia, comunes, cientifico, ingles


def separar_columnas(lineas):
    """Divide las líneas del cuerpo en columna izquierda y derecha."""
    izq, der = [], []
    for linea in lineas:
        if not linea.strip():
            continue
        m = re.search(r"\S(\s{3,})(\S)", linea)
        if m and 25 <= m.start(2) <= 90:
            izq.append(linea[:m.start(1) + 1].strip())
            der.append(linea[m.start(2):].strip())
        elif len(linea) - len(linea.lstrip()) >= 30:
            der.append(linea.strip())
        else:
            izq.append(linea.strip())
    return izq, der


def unir(lineas):
    t = ""
    for linea in lineas:
        if t.endswith(("\xad", "-")) and not t.endswith(" -"):
            t = t[:-1] + linea
        else:
            t = f"{t} {linea}" if t else linea
    return re.sub(r"\s+", " ", t).strip()


def leer_secciones(cuerpo):
    patron = re.compile(r"^(%s)\s*$" % "|".join(f"(?P<{k}>{v})" for k, v in SECCIONES.items()))
    secciones, actual = {}, None
    for linea in cuerpo:
        m = patron.match(linea)
        if m:
            actual = next(k for k, v in m.groupdict().items() if v)
            secciones.setdefault(actual, [])
        elif actual:
            secciones[actual].append(linea)
        elif re.match(r"^(%s)\s*[:;]" % "|".join(CAMPOS_DESCRIPCION), linea):
            actual = "descripcion"
            secciones.setdefault(actual, []).append(linea)
    resultado = {k: unir(v) for k, v in secciones.items()}
    if "descripcion" in resultado:
        partes = re.split(r"\b(%s)\s*[:;]" % "|".join(CAMPOS_DESCRIPCION), resultado["descripcion"])
        resultado["descripcion"] = {partes[i]: partes[i + 1].strip() for i in range(1, len(partes) - 1, 2)}
    for k in ("ciclo_de_vida", "reproduccion", "origen"):
        if k in resultado:
            resultado[k] = re.sub(r"\s*\d{1,3}\s*$", "", resultado[k]).strip(" .■") or None
    return resultado


def leer_pagina(pdf, pagina):
    lineas = texto_pagina(pdf, pagina).splitlines()
    i = next((k for k, l in enumerate(lineas) if ENCABEZADO_FIN.search(l)), None)
    if i is None:
        return None
    familia, comunes, cientifico, ingles = leer_encabezado(lineas[:i])
    if not familia or not cientifico:
        return None
    izq, der = separar_columnas(lineas[i:])
    ficha = {
        "pagina": pagina,
        "familia": familia,
        "nombres_comunes": comunes,
        "cientifico": cientifico,
        "ingles": ingles,
    }
    ficha.update(leer_secciones(izq + der))
    return ficha


# --- fotos ----------------------------------------------------------------------

def _tramos(valores, minimo):
    """Tramos continuos de True con largo >= minimo: [(inicio, fin), ...]."""
    tramos, inicio = [], None
    for i, v in enumerate(list(valores) + [False]):
        if v and inicio is None:
            inicio = i
        elif not v and inicio is not None:
            if i - inicio >= minimo:
                tramos.append((inicio, i))
            inicio = None
    return tramos


def recortar_fotos(png):
    """Recorta las fotos de la ficha: columnas de foto y, en cada una, su alto propio.

    Las fotos están entre el encabezado y la descripción (zona central de la
    página); se reconocen por ser bloques densos de píxeles 'no papel'.
    """
    im = Image.open(png).convert("RGB")
    a = np.asarray(im).astype(np.int16)
    foto = ((a.max(axis=2) - a.min(axis=2)) > 40) | (a.mean(axis=2) < 200)
    alto, ancho = foto.shape
    z0, z1 = int(alto * 0.08), int(alto * 0.75)
    zona = foto[z0:z1]
    recortes = []
    for x0, x1 in _tramos(zona.mean(axis=0) > 0.30, int(ancho * 0.2)):
        filas = _tramos(zona[:, x0:x1].mean(axis=1) > 0.6, int(alto * 0.1))
        if not filas:
            continue
        y0, y1 = max(filas, key=lambda t: t[1] - t[0])
        recortes.append(im.crop((x0, z0 + y0, x1, z0 + y1)))
    return recortes[:2]


def identificador(cientifico):
    t = sin_acentos(cientifico).lower()
    palabras = re.findall(r"[a-z][a-z\-]*", t)
    return "_".join(palabras[:2]) if len(palabras) >= 2 else "_".join(palabras)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("pdf")
    ap.add_argument("salida")
    ap.add_argument("--fotos", help="carpeta donde guardar las fotos recortadas")
    ap.add_argument("--correcciones", help="JSON {pagina: {campo: valor}} con nombres corregidos a mano")
    ap.add_argument("--lado", type=int, default=384, help="lado mayor de las fotos guardadas (px)")
    a = ap.parse_args()

    paginas = int(re.search(r"Pages:\s+(\d+)", subprocess.run(
        ["pdfinfo", a.pdf], capture_output=True, text=True, check=True).stdout).group(1))
    correcciones = {}
    if a.correcciones and Path(a.correcciones).is_file():
        correcciones = {int(k): v for k, v in json.loads(Path(a.correcciones).read_text("utf-8")).items()}

    fichas = []
    for p in range(1, paginas + 1):
        f = leer_pagina(a.pdf, p)
        if f is None:
            continue
        f.update(correcciones.get(p, {}))
        if f.get("omitir"):
            continue
        f["id"] = identificador(f["cientifico"])
        fichas.append(f)

    vistos = {}
    for f in fichas:  # ids únicos (subespecies, variedades)
        n = vistos.get(f["id"], 0)
        vistos[f["id"]] = n + 1
        if n:
            f["id"] = f"{f['id']}_{n + 1}"

    if a.fotos:
        carpeta = Path(a.fotos)
        carpeta.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as tmp:
            for f in fichas:
                base = Path(tmp) / f"p{f['pagina']}"
                subprocess.run(["pdftoppm", "-r", "150", "-f", str(f["pagina"]), "-l", str(f["pagina"]),
                                "-png", "-singlefile", a.pdf, str(base)], check=True)
                f["fotos"] = []
                for k, im in enumerate(recortar_fotos(f"{base}.png"), 1):
                    im.thumbnail((a.lado, a.lado))
                    nombre = f"{f['id']}_{k}.jpg"
                    im.save(carpeta / nombre, "JPEG", quality=85)
                    f["fotos"].append(nombre)

    salida = {
        "fuente": "Espinoza N. (1996). Malezas presentes en Chile. INIA Carillanca, Temuco.",
        "nota": "Texto obtenido por OCR del escaneo; puede traer errores. Uso interno.",
        "especies": fichas,
    }
    Path(a.salida).write_text(json.dumps(salida, ensure_ascii=False, indent=1) + "\n", "utf-8")
    con_fotos = sum(1 for f in fichas if len(f.get("fotos", [])) == 2)
    print(f"{len(fichas)} especies; {con_fotos} con sus 2 fotos")


if __name__ == "__main__":
    main()

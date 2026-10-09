"""Calcula los vectores (MobileNet) de las fotos del catálogo: referencias iniciales de la IA.

    python scripts/precalcular_referencias.py datos/especies-malezas.json assets/especies \\
        datos/referencias-malezas.npz --grupo maleza

Cada foto aporta 3 vectores (original, espejo y recorte cerrado). Al final
imprime la precisión dejando fuera cada foto, como referencia de calidad.
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sanidad import rutas  # noqa: E402
from sanidad.ia.identificador import MODELO, Identificador, vectores_de_foto  # noqa: E402
from sanidad.ia.mobilenet import MobileNet  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("catalogo")
    ap.add_argument("fotos")
    ap.add_argument("salida")
    ap.add_argument("--grupo", default="maleza")
    a = ap.parse_args()

    red = MobileNet(rutas.MODELO_MOBILENET)
    especies = json.loads(Path(a.catalogo).read_text("utf-8"))["especies"]
    vectores, ids, fotos = [], [], []
    for e in especies:
        for nombre in e.get("fotos", []):
            v = vectores_de_foto(red, Path(a.fotos) / nombre)
            vectores.append(v)
            ids += [e["id"]] * len(v)
            fotos += [nombre] * len(v)
    vectores = np.vstack(vectores)
    np.savez_compressed(a.salida, vectores=vectores.astype(np.float16), especies=np.array(ids),
                        fotos=np.array(fotos), grupo=np.array(a.grupo), modelo=np.array(MODELO))
    ident = Identificador(vectores, ids)
    r = ident.evaluar(fotos)
    print(f"{len(set(ids))} especies, {len(set(fotos))} fotos, {len(ids)} vectores -> {a.salida}")
    print(f"Dejando fuera cada foto: top-1 {r['top1']:.0f} %, top-3 {r['top3']:.0f} % ({r['fotos']} fotos)")


if __name__ == "__main__":
    main()

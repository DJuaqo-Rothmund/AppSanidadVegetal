"""Identificación de especies por foto: vecinos más cercanos sobre vectores de MobileNet.

Cada referencia es una foto con su especie (las del libro y las que confirma
el monitor en terreno). Para una foto nueva se calcula su vector, se compara
por similitud coseno con las referencias y cada especie se puntúa por sus
referencias más parecidas. Confirmar una sugerencia agrega una referencia:
así la IA aprende sin reentrenar la red.
"""

from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageOps

from .mobilenet import TAM_ENTRADA

MODELO = "mobilenet_v3_small_imagenet_f16"
TEMPERATURA = 0.04  # más baja = confianza más concentrada en la mejor especie
VECTORES_POR_FOTO = 3  # original, espejo y recorte cerrado (vectores_de_foto)


def preparar_imagen(ruta_o_imagen, recorte=0.9, espejo=False):
    """Abre la foto, corrige la orientación EXIF, recorta un cuadrado central y la lleva a 224 px."""
    im = ruta_o_imagen if isinstance(ruta_o_imagen, Image.Image) else Image.open(ruta_o_imagen)
    im.draft("RGB", (TAM_ENTRADA * 2, TAM_ENTRADA * 2))  # JPEG grande: decodifica reducido
    im = ImageOps.exif_transpose(im).convert("RGB")
    ancho, alto = im.size
    lado = int(min(ancho, alto) * recorte)
    x0, y0 = (ancho - lado) // 2, (alto - lado) // 2
    im = im.crop((x0, y0, x0 + lado, y0 + lado)).resize((TAM_ENTRADA, TAM_ENTRADA), Image.BILINEAR)
    if espejo:
        im = ImageOps.mirror(im)
    return np.asarray(im, dtype=np.uint8)


def normalizar(v):
    v = np.asarray(v, dtype=np.float32)
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.maximum(n, 1e-8)


def vectores_de_foto(red, ruta, aumentos=True):
    """Vectores de una foto: la original y, si `aumentos`, su espejo y un recorte más cerrado."""
    variantes = [dict()]
    if aumentos:
        variantes += [dict(espejo=True), dict(recorte=0.7)]
    return normalizar([red.embedding(preparar_imagen(ruta, **v)) for v in variantes])


@dataclass
class Sugerencia:
    especie_id: str
    confianza: float     # 0..1, repartida entre las especies candidatas
    similitud: float     # coseno con la referencia más parecida
    referencias: int     # cuántas fotos de referencia tiene la especie


class Identificador:
    """k vecinos más cercanos por especie sobre referencias normalizadas."""

    def __init__(self, vectores=None, especies=None):
        self.vectores = np.zeros((0, 576), dtype=np.float32)
        self.especies = np.array([], dtype=object)
        if vectores is not None and len(vectores):
            self.agregar(vectores, especies)

    def agregar(self, vectores, especies):
        vectores = normalizar(np.atleast_2d(vectores))
        if isinstance(especies, str):
            especies = [especies] * len(vectores)
        self.vectores = np.vstack([self.vectores, vectores])
        self.especies = np.concatenate([self.especies, np.array(especies, dtype=object)])

    @property
    def cantidad(self):
        return len(self.especies)

    def sugerir(self, vector, k=3, vecinos=2, permitidas=None, excluir=None):
        """Las k especies más probables para el vector de una foto.

        La puntuación de cada especie es el promedio de sus `vecinos`
        referencias más parecidas; la confianza sale de un softmax sobre esas
        puntuaciones. `permitidas` limita las especies (por ejemplo, solo
        malezas); `excluir` es una máscara de referencias a ignorar (para evaluar).
        """
        if not self.cantidad:
            return []
        sims = self.vectores @ normalizar(vector)
        if excluir is not None:
            sims = np.where(excluir, -np.inf, sims)
        puntajes = {}
        for especie in np.unique(self.especies):
            if permitidas is not None and especie not in permitidas:
                continue
            s = np.sort(sims[self.especies == especie])[::-1]
            s = s[np.isfinite(s)]
            if len(s):
                fotos = max(1, -(-len(s) // VECTORES_POR_FOTO))
                puntajes[especie] = (float(s[:vecinos].mean()), float(s[0]), fotos)
        if not puntajes:
            return []
        nombres = list(puntajes)
        valores = np.array([puntajes[n][0] for n in nombres])
        pesos = np.exp((valores - valores.max()) / TEMPERATURA)
        prob = pesos / pesos.sum()
        orden = np.argsort(-prob)[:k]
        return [Sugerencia(nombres[i], float(prob[i]), puntajes[nombres[i]][1], puntajes[nombres[i]][2])
                for i in orden]

    def evaluar(self, grupos_foto):
        """Precisión dejando fuera cada foto (todas sus variantes) y prediciendo con el resto.

        grupos_foto: arreglo con el identificador de foto de cada referencia.
        Devuelve {"fotos": n, "top1": %, "top3": %}.
        """
        grupos_foto = np.asarray(grupos_foto)
        fotos = np.unique(grupos_foto)
        acierto1 = acierto3 = evaluadas = 0
        for foto in fotos:
            mascara = grupos_foto == foto
            i = int(np.flatnonzero(mascara)[0])
            especie = self.especies[i]
            if np.sum((self.especies == especie) & ~mascara) == 0:
                continue  # la especie no tiene otra foto: no se puede evaluar
            top = [s.especie_id for s in self.sugerir(self.vectores[i], k=3, excluir=mascara)]
            evaluadas += 1
            acierto1 += top[:1] == [especie]
            acierto3 += especie in top
        if not evaluadas:
            return {"fotos": 0, "top1": None, "top3": None}
        return {"fotos": evaluadas, "top1": 100 * acierto1 / evaluadas, "top3": 100 * acierto3 / evaluadas}

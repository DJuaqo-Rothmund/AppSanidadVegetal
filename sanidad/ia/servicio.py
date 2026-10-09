"""Servicio de identificación: catálogo de especies, referencias (libro + terreno) y sugerencias.

Sin Kivy, para probarlo con pytest. La red se carga recién al primer uso.
"""

import json
import os
import shutil
import threading
import unicodedata
from pathlib import Path

import numpy as np

from .identificador import MODELO, Identificador, vectores_de_foto

GRUPOS = ("maleza", "enfermedad", "plaga")


def _plano(texto):
    t = unicodedata.normalize("NFD", texto or "").lower()
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


class CatalogoEspecies:
    """Especies identificables: las del libro de malezas y los organismos del catálogo de monitoreo."""

    def __init__(self, especies_malezas=None, catalogo_monitoreo=None):
        self.especies = {}
        if especies_malezas:
            for e in especies_malezas.get("especies", []):
                self.especies[e["id"]] = dict(e, grupo="maleza")
        if catalogo_monitoreo is not None:
            for o in catalogo_monitoreo.organismos:
                if o["id"] in self.especies:
                    continue
                self.especies[o["id"]] = {
                    "id": o["id"], "grupo": o["grupo"], "cientifico": o.get("cientifico") or "",
                    "nombres_comunes": [o["nombre"].upper()], "familia": None, "fotos": [],
                }

    @classmethod
    def desde_archivos(cls, ruta_malezas, catalogo_monitoreo=None):
        datos = None
        if ruta_malezas and Path(ruta_malezas).is_file():
            datos = json.loads(Path(ruta_malezas).read_text("utf-8"))
        return cls(datos, catalogo_monitoreo)

    def __len__(self):
        return len(self.especies)

    def ficha(self, especie_id):
        return self.especies.get(especie_id)

    @staticmethod
    def nombre(ficha):
        comunes = ficha.get("nombres_comunes") or []
        return comunes[0].capitalize() if comunes else ficha.get("cientifico", ficha["id"])

    def del_grupo(self, grupo):
        return [e for e in self.especies.values() if e["grupo"] == grupo]

    def buscar(self, texto, grupo=None, limite=30):
        """Busca por nombre común, científico o familia, sin importar tildes ni mayúsculas."""
        t = _plano(texto).strip()
        resultados = []
        for e in self.especies.values():
            if grupo and e["grupo"] != grupo:
                continue
            campos = [e.get("cientifico", "")] + list(e.get("nombres_comunes") or []) + [e.get("familia") or ""]
            textos = [_plano(c) for c in campos]
            if not t or any(t in c for c in textos):
                empieza = any(c.startswith(t) for c in textos)
                resultados.append((not empieza, self.nombre(e), e))
        return [e for *_, e in sorted(resultados, key=lambda r: (r[0], r[1]))[:limite]]


class ServicioIdentificacion:
    def __init__(self, base, catalogo, ruta_modelo, ruta_referencias_libro=None, carpeta_fotos=None,
                 cargar_red=None):
        self.base = base
        self.catalogo = catalogo
        self.ruta_modelo = ruta_modelo
        self.ruta_referencias_libro = ruta_referencias_libro
        self.carpeta_fotos = carpeta_fotos
        self._cargar_red = cargar_red  # para pruebas
        self._red = None
        self._ident = None
        self._candado = threading.Lock()
        self.referencias_libro = 0

    # --- carga perezosa ---------------------------------------------------------

    @property
    def red(self):
        if self._red is None:
            if self._cargar_red:
                self._red = self._cargar_red()
            else:
                from .mobilenet import MobileNet
                self._red = MobileNet(self.ruta_modelo)
        return self._red

    @property
    def identificador(self):
        with self._candado:
            if self._ident is None:
                ident = Identificador()
                ruta = self.ruta_referencias_libro
                if ruta and Path(ruta).is_file():
                    d = np.load(ruta)
                    if str(d["modelo"]) == MODELO:
                        ident.agregar(d["vectores"].astype(np.float32), list(d["especies"]))
                        self.referencias_libro = len(set(d["fotos"]))
                for r in self.base.listar("referencias_ia", modelo=MODELO):
                    v = np.frombuffer(r["vector"], dtype=np.float16).astype(np.float32).reshape(-1, 576)
                    ident.agregar(v, r["especie_id"])
                self._ident = ident
            return self._ident

    # --- uso ----------------------------------------------------------------------

    def identificar(self, ruta_foto, grupo="maleza", k=3):
        """Sugerencias [(Sugerencia, ficha)] para la foto, solo de especies del grupo."""
        vector = vectores_de_foto(self.red, ruta_foto, aumentos=False)[0]
        permitidas = {e["id"] for e in self.catalogo.del_grupo(grupo)}
        sugerencias = self.identificador.sugerir(vector, k=k, permitidas=permitidas)
        return [(s, self.catalogo.ficha(s.especie_id)) for s in sugerencias]

    def confirmar(self, ruta_foto, especie_id, uid=None):
        """Guarda la foto como referencia de la especie: la IA la usa desde ya."""
        ficha = self.catalogo.ficha(especie_id)
        if ficha is None:
            raise KeyError(f"Especie desconocida: {especie_id}")
        destino = str(ruta_foto)
        if self.carpeta_fotos:
            os.makedirs(self.carpeta_fotos, exist_ok=True)
            n = len(self.base.listar("referencias_ia", especie_id=especie_id)) + 1
            destino = os.path.join(self.carpeta_fotos, f"{especie_id}_{n:03d}_{os.getpid()}.jpg")
            shutil.copyfile(ruta_foto, destino)
        vectores = vectores_de_foto(self.red, destino)
        rid = self.base.insertar("referencias_ia", {
            "especie_id": especie_id, "grupo": ficha["grupo"], "foto": destino,
            "vector": vectores.astype(np.float16).tobytes(), "modelo": MODELO, "origen": "usuario",
        }, uid=uid)
        self.identificador.agregar(vectores, especie_id)
        return rid

    def referencias_de(self, especie_id):
        return self.base.listar("referencias_ia", especie_id=especie_id)

    def quitar_referencia(self, referencia_id, uid=None):
        self.base.anular("referencias_ia", referencia_id, uid=uid)
        with self._candado:
            self._ident = None  # se reconstruye sin esa referencia

    def resumen(self):
        ident = self.identificador
        propias = len(self.base.listar("referencias_ia", modelo=MODELO))
        return {"fotos_libro": self.referencias_libro, "fotos_terreno": propias,
                "vectores": ident.cantidad, "especies": len(self.catalogo)}

"""Cloud Firestore por API REST: leer, guardar, listar y consultar cambios."""

import requests

from .errores import ErrorFirebase, SinConexion, revisar_respuesta

URL_BASE = "https://firestore.googleapis.com/v1/projects/{proyecto}/databases/(default)/documents"
TIEMPO_ESPERA_S = 30


# --- conversión entre valores de Python y el formato tipado de Firestore ------

def a_valor(v):
    if v is None:
        return {"nullValue": None}
    if isinstance(v, bool):
        return {"booleanValue": v}
    if isinstance(v, int):
        return {"integerValue": str(v)}
    if isinstance(v, float):
        return {"doubleValue": v}
    if isinstance(v, str):
        return {"stringValue": v}
    if isinstance(v, (list, tuple)):
        return {"arrayValue": {"values": [a_valor(x) for x in v]}}
    if isinstance(v, dict):
        return {"mapValue": {"fields": a_campos(v)}}
    raise TypeError(f"Tipo no admitido en Firestore: {type(v).__name__}")


def a_campos(d):
    return {str(k): a_valor(v) for k, v in d.items()}


def desde_valor(v):
    (tipo, x), = v.items()
    if tipo == "nullValue":
        return None
    if tipo == "integerValue":
        return int(x)
    if tipo == "doubleValue":
        return float(x)
    if tipo in ("booleanValue", "stringValue", "timestampValue", "referenceValue", "bytesValue"):
        return x
    if tipo == "arrayValue":
        return [desde_valor(e) for e in x.get("values", [])]
    if tipo == "mapValue":
        return desde_campos(x.get("fields", {}))
    if tipo == "geoPointValue":
        return {"lat": x.get("latitude", 0.0), "lng": x.get("longitude", 0.0)}
    raise TypeError(f"Tipo de Firestore desconocido: {tipo}")


def desde_campos(campos):
    return {k: desde_valor(v) for k, v in campos.items()}


def desde_documento(doc):
    """Convierte un documento REST en dict, con su id en la clave `id`."""
    datos = desde_campos(doc.get("fields", {}))
    datos["id"] = doc["name"].rsplit("/", 1)[-1]
    return datos


class ClienteFirestore:
    """Cliente mínimo; `token` es una función que devuelve un ID token vigente."""

    def __init__(self, proyecto, token, http=None):
        self.url_base = URL_BASE.format(proyecto=proyecto)
        self.token = token
        self.http = http or requests.Session()

    def _pedir(self, metodo, ruta, **kwargs):
        # `ruta` relativa a .../documents; las que empiezan con ":" son métodos (":runQuery").
        url = f"{self.url_base}{ruta}" if ruta.startswith(":") else f"{self.url_base}/{ruta}"
        cabeceras = {"Authorization": f"Bearer {self.token()}"}
        try:
            r = self.http.request(metodo, url, headers=cabeceras, timeout=TIEMPO_ESPERA_S, **kwargs)
        except requests.RequestException as e:
            raise SinConexion() from e
        return revisar_respuesta(r)

    @staticmethod
    def _validar_ruta(ruta, par):
        partes = ruta.strip("/").split("/")
        if not all(partes) or (len(partes) % 2 == 0) != par:
            tipo = "un documento" if par else "una colección"
            raise ValueError(f"'{ruta}' no es la ruta de {tipo}")
        return ruta.strip("/")

    def obtener(self, ruta_doc):
        """Devuelve el documento como dict, o None si no existe."""
        ruta_doc = self._validar_ruta(ruta_doc, par=True)
        try:
            return desde_documento(self._pedir("GET", ruta_doc))
        except ErrorFirebase as e:
            if e.estado_http == 404:
                return None
            raise

    def guardar(self, ruta_doc, datos):
        """Crea o reemplaza el documento completo (el id va en la ruta, no en los campos)."""
        ruta_doc = self._validar_ruta(ruta_doc, par=True)
        campos = {k: v for k, v in datos.items() if k != "id"}
        return desde_documento(self._pedir("PATCH", ruta_doc, json={"fields": a_campos(campos)}))

    def listar(self, ruta_coleccion, tam_pagina=300):
        """Recorre todas las páginas de una colección."""
        ruta_coleccion = self._validar_ruta(ruta_coleccion, par=False)
        docs, token_pagina = [], None
        while True:
            params = {"pageSize": tam_pagina}
            if token_pagina:
                params["pageToken"] = token_pagina
            d = self._pedir("GET", ruta_coleccion, params=params)
            docs.extend(desde_documento(x) for x in d.get("documents", []))
            token_pagina = d.get("nextPageToken")
            if not token_pagina:
                return docs

    def actualizados_desde(self, ruta_coleccion, desde_iso, campo="actualizadoEn", limite=500):
        """Documentos de una colección con `campo` > desde_iso (texto ISO 8601), en orden."""
        ruta_coleccion = self._validar_ruta(ruta_coleccion, par=False)
        padre, _, coleccion = ruta_coleccion.rpartition("/")
        consulta = {"structuredQuery": {
            "from": [{"collectionId": coleccion}],
            "where": {"fieldFilter": {
                "field": {"fieldPath": campo}, "op": "GREATER_THAN",
                "value": a_valor(desde_iso),
            }},
            "orderBy": [{"field": {"fieldPath": campo}, "direction": "ASCENDING"}],
            "limit": limite,
        }}
        ruta = f"{padre}:runQuery" if padre else ":runQuery"
        respuesta = self._pedir("POST", ruta, json=consulta)
        return [desde_documento(x["document"]) for x in respuesta if "document" in x]

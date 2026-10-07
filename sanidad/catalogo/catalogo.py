"""Carga y validación del catálogo de organismos (protocolos y umbrales como datos)."""

import json

GRUPOS = ("enfermedad", "plaga", "maleza")
TIPOS_CAMPO = {"entero", "decimal", "escala", "bool", "opcion", "clase", "fecha"}
TIPOS_INDICADOR = {"porcentaje", "por_n", "campo"}


class CatalogoInvalido(Exception):
    pass


class Catalogo:
    def __init__(self, datos):
        errores = validar(datos)
        if errores:
            raise CatalogoInvalido("; ".join(errores))
        self.datos = datos
        self.id = datos["id"]
        self.organismos = datos["organismos"]
        self._por_id = {o["id"]: o for o in self.organismos}

    def organismo(self, id):
        return self._por_id[id]

    def por_grupo(self, grupo):
        return [o for o in self.organismos if o["grupo"] == grupo and o.get("activo", True)]

    def umbrales(self, organismo):
        """Lista de umbrales del organismo (uno por indicador con umbral)."""
        if "umbrales" in organismo:
            return organismo["umbrales"]
        return [dict(organismo["umbral"], indicador=organismo["indicadores"][0]["id"])]

    @staticmethod
    def en_ventana(organismo, bbch):
        """True si el BBCH cae en la ventana del organismo (o si no tiene ventana)."""
        v = organismo.get("ventana_bbch")
        if not v or bbch is None:
            return True
        desde, hasta = v.get("desde"), v.get("hasta")
        return (desde is None or bbch >= desde) and (hasta is None or bbch <= hasta)

    def lista_rapida(self, grupo, bbch):
        """Organismos del grupo; los que están fuera de su ventana BBCH van al final."""
        return sorted(self.por_grupo(grupo), key=lambda o: not self.en_ventana(o, bbch))


def validar(datos):
    """Devuelve una lista de errores (vacía si el catálogo es válido)."""
    errores = []
    for clave in ("id", "cultivo", "version", "organismos"):
        if clave not in datos:
            errores.append(f"falta '{clave}' en el catálogo")
    if errores:
        return errores
    especiales = set(datos.get("reglas_especiales", {}))
    vistos = set()
    for o in datos["organismos"]:
        oid = o.get("id", "?")
        if oid in vistos:
            errores.append(f"{oid}: id repetido")
        vistos.add(oid)
        if o.get("grupo") not in GRUPOS:
            errores.append(f"{oid}: grupo inválido {o.get('grupo')!r}")
        campos = {c["id"]: c for c in o.get("campos", [])}
        for c in campos.values():
            if c.get("tipo") not in TIPOS_CAMPO:
                errores.append(f"{oid}.{c['id']}: tipo de campo inválido {c.get('tipo')!r}")
        indicadores = {i["id"]: i for i in o.get("indicadores", [])}
        if not indicadores:
            errores.append(f"{oid}: no tiene indicadores")
        for i in indicadores.values():
            if i.get("tipo") not in TIPOS_INDICADOR:
                errores.append(f"{oid}.{i['id']}: tipo de indicador inválido {i.get('tipo')!r}")
            for k in ("numerador", "denominador", "campo"):
                if k in i and i[k] not in campos:
                    errores.append(f"{oid}.{i['id']}: {k} '{i[k]}' no es un campo")
        umbrales = o.get("umbrales") or ([o["umbral"]] if "umbral" in o else [])
        if not umbrales:
            errores.append(f"{oid}: no tiene umbral")
        medibles = set(campos) | set(indicadores)
        for u in umbrales:
            if "indicador" in u and u["indicador"] not in indicadores:
                errores.append(f"{oid}: umbral de indicador desconocido '{u['indicador']}'")
            for nivel in ("cerca", "sobre"):
                lim = u.get(nivel)
                if lim is not None and lim.get("medida") not in medibles:
                    errores.append(f"{oid}: umbral '{nivel}' mide '{lim.get('medida')}', que no existe")
        if not o.get("estados"):
            errores.append(f"{oid}: no tiene estados")
        for r in o.get("reglas_especiales", []):
            if r not in especiales:
                errores.append(f"{oid}: regla especial sin definir '{r}'")
    return errores


def cargar_catalogo(ruta):
    with open(ruta, encoding="utf-8") as f:
        return Catalogo(json.load(f))

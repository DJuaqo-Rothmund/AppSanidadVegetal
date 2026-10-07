"""Acceso a la base SQLite local, fuente de verdad de la app sin señal."""

import json
import sqlite3
import uuid
from datetime import datetime, timezone

from .esquema import COLUMNAS_JSON, TABLAS, VERSION_ESQUEMA, sentencias_creacion

AUDITORIA = {
    "id", "creado_en", "creado_por", "editado_en", "editado_por",
    "actualizado_en", "eliminado", "pendiente",
}


def ahora_iso():
    """Fecha y hora UTC en ISO 8601 con milisegundos, por ejemplo 2026-10-07T18:00:00.000Z."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def nuevo_id():
    return str(uuid.uuid4())


class BaseLocal:
    """Envuelve la conexión SQLite con altas, ediciones y anulaciones auditadas."""

    def __init__(self, ruta=":memory:", reloj=ahora_iso):
        self.ruta = ruta
        self.reloj = reloj
        self.con = sqlite3.connect(ruta)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA foreign_keys = ON")
        self._migrar()
        self._columnas = {
            t: {f[1] for f in self.con.execute(f"PRAGMA table_info({t})")} for t in TABLAS
        }

    def _migrar(self):
        version = self.con.execute("PRAGMA user_version").fetchone()[0]
        if version < VERSION_ESQUEMA:
            with self.con:
                for sql in sentencias_creacion():
                    self.con.execute(sql)
                self.con.execute(f"PRAGMA user_version = {VERSION_ESQUEMA}")

    def cerrar(self):
        self.con.close()

    # --- validación y conversión -------------------------------------------

    def _validar(self, tabla, datos):
        if tabla not in TABLAS:
            raise ValueError(f"Tabla desconocida: {tabla}")
        desconocidas = set(datos) - self._columnas[tabla]
        if desconocidas:
            raise ValueError(f"Columnas desconocidas en {tabla}: {sorted(desconocidas)}")
        protegidas = set(datos) & AUDITORIA
        if protegidas:
            raise ValueError(f"Campos de auditoría no editables: {sorted(protegidas)}")

    @staticmethod
    def _a_sql(tabla, datos):
        json_cols = COLUMNAS_JSON.get(tabla, set())
        return {
            k: json.dumps(v, ensure_ascii=False) if k in json_cols and v is not None else v
            for k, v in datos.items()
        }

    @staticmethod
    def _desde_sql(tabla, fila):
        if fila is None:
            return None
        d = dict(fila)
        for k in COLUMNAS_JSON.get(tabla, ()):
            if d.get(k) is not None:
                d[k] = json.loads(d[k])
        return d

    # --- escritura ----------------------------------------------------------

    def insertar(self, tabla, datos, uid=None, id=None):
        """Crea un registro pendiente de subir y devuelve su ID (UUID)."""
        self._validar(tabla, datos)
        momento = self.reloj()
        fila = self._a_sql(tabla, datos)
        fila.update(
            id=id or nuevo_id(), creado_en=momento, creado_por=uid,
            actualizado_en=momento, eliminado=0, pendiente=1,
        )
        cols = ", ".join(fila)
        marcas = ", ".join("?" for _ in fila)
        with self.con:
            self.con.execute(f"INSERT INTO {tabla} ({cols}) VALUES ({marcas})", list(fila.values()))
        return fila["id"]

    def actualizar(self, tabla, id, cambios, uid=None):
        """Edita campos de un registro y lo deja pendiente de subir."""
        self._validar(tabla, cambios)
        if not cambios:
            raise ValueError("No hay cambios que guardar")
        momento = self.reloj()
        fila = self._a_sql(tabla, cambios)
        fila.update(editado_en=momento, editado_por=uid, actualizado_en=momento, pendiente=1)
        asignaciones = ", ".join(f"{k} = ?" for k in fila)
        with self.con:
            cur = self.con.execute(
                f"UPDATE {tabla} SET {asignaciones} WHERE id = ?", [*fila.values(), id]
            )
        if cur.rowcount == 0:
            raise KeyError(f"No existe {tabla}/{id}")

    def anular(self, tabla, id, uid=None):
        """Oculta un registro sin borrarlo (queda la auditoría)."""
        if tabla not in TABLAS:
            raise ValueError(f"Tabla desconocida: {tabla}")
        momento = self.reloj()
        with self.con:
            cur = self.con.execute(
                f"UPDATE {tabla} SET eliminado = 1, editado_en = ?, editado_por = ?, "
                f"actualizado_en = ?, pendiente = 1 WHERE id = ?",
                [momento, uid, momento, id],
            )
        if cur.rowcount == 0:
            raise KeyError(f"No existe {tabla}/{id}")

    # --- lectura ------------------------------------------------------------

    def obtener(self, tabla, id):
        if tabla not in TABLAS:
            raise ValueError(f"Tabla desconocida: {tabla}")
        fila = self.con.execute(f"SELECT * FROM {tabla} WHERE id = ?", [id]).fetchone()
        return self._desde_sql(tabla, fila)

    def listar(self, tabla, incluir_eliminados=False, **filtros):
        """Lista registros; los filtros son igualdades por columna."""
        self._validar(tabla, {k: None for k in filtros if k not in ("eliminado", "pendiente")})
        condiciones, valores = [], []
        if not incluir_eliminados:
            condiciones.append("eliminado = 0")
        for k, v in filtros.items():
            condiciones.append(f"{k} = ?")
            valores.append(v)
        where = f" WHERE {' AND '.join(condiciones)}" if condiciones else ""
        filas = self.con.execute(
            f"SELECT * FROM {tabla}{where} ORDER BY creado_en", valores
        ).fetchall()
        return [self._desde_sql(tabla, f) for f in filas]

    def pendientes(self, tabla):
        """Registros por subir, incluidos los anulados (la anulación también se sube)."""
        return self.listar(tabla, incluir_eliminados=True, pendiente=1)

    def marcar_sincronizado(self, tabla, id, actualizado_en):
        """Quita la marca pendiente solo si el registro no cambió mientras se subía."""
        if tabla not in TABLAS:
            raise ValueError(f"Tabla desconocida: {tabla}")
        with self.con:
            self.con.execute(
                f"UPDATE {tabla} SET pendiente = 0 WHERE id = ? AND actualizado_en = ?",
                [id, actualizado_en],
            )

    # --- ajustes locales ----------------------------------------------------

    def leer_ajuste(self, clave, defecto=None):
        fila = self.con.execute("SELECT valor FROM ajustes WHERE clave = ?", [clave]).fetchone()
        return json.loads(fila[0]) if fila else defecto

    def guardar_ajuste(self, clave, valor):
        with self.con:
            self.con.execute(
                "INSERT INTO ajustes (clave, valor) VALUES (?, ?) "
                "ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor",
                [clave, json.dumps(valor, ensure_ascii=False)],
            )

    def borrar_ajuste(self, clave):
        with self.con:
            self.con.execute("DELETE FROM ajustes WHERE clave = ?", [clave])

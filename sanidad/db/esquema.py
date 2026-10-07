"""Esquema SQLite local, espejo del modelo de datos de Firestore (SPEC.md).

Cada tabla lleva un ID UUID generado en el teléfono y los mismos campos de
auditoría. Nada se borra físicamente: `eliminado = 1` oculta el registro.
`pendiente = 1` marca lo que falta subir a Firestore.
"""

VERSION_ESQUEMA = 1

# Campos de auditoría comunes a todas las tablas de datos.
AUDITORIA = """
    creado_en       TEXT NOT NULL,
    creado_por      TEXT,
    editado_en      TEXT,
    editado_por     TEXT,
    actualizado_en  TEXT NOT NULL,
    eliminado       INTEGER NOT NULL DEFAULT 0 CHECK (eliminado IN (0, 1)),
    pendiente       INTEGER NOT NULL DEFAULT 1 CHECK (pendiente IN (0, 1))
"""

# Columnas propias de cada tabla (sin id ni auditoría).
TABLAS = {
    "usuarios": """
        nombre      TEXT,
        email       TEXT
    """,
    "predios": """
        nombre      TEXT NOT NULL,
        cultivo     TEXT,
        ha          REAL,
        centro_lat  REAL,
        centro_lng  REAL,
        miembros    TEXT    -- JSON {uid: "admin" | "monitor"}
    """,
    "sectores": """
        predio_id   TEXT NOT NULL REFERENCES predios(id),
        equipo      TEXT,
        sector      TEXT,
        variedad    TEXT,
        ha          REAL,
        hileras     INTEGER,
        geometria   TEXT    -- GeoJSON como texto
    """,
    "temporadas": """
        predio_id   TEXT NOT NULL REFERENCES predios(id),
        inicio      TEXT NOT NULL,
        fin         TEXT NOT NULL,
        etiqueta    TEXT
    """,
    "organismos": """
        catalogo_id TEXT NOT NULL,
        grupo       TEXT NOT NULL CHECK (grupo IN ('enfermedad', 'plaga', 'maleza')),
        nombre      TEXT NOT NULL,
        cientifico  TEXT,
        datos       TEXT    -- JSON con el protocolo completo
    """,
    "puntos": """
        predio_id     TEXT NOT NULL REFERENCES predios(id),
        tipo          TEXT NOT NULL CHECK (tipo IN ('fijo', 'trampa')),
        lat           REAL NOT NULL,
        lng           REAL NOT NULL,
        sector_id     TEXT,
        organismo_id  TEXT,
        ultimo_estado TEXT,
        ultima_visita TEXT,
        activo        INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0, 1))
    """,
    "observaciones": """
        predio_id           TEXT NOT NULL REFERENCES predios(id),
        punto_id            TEXT,
        organismo_id        TEXT NOT NULL,
        catalogo_version    TEXT NOT NULL,
        sector_id           TEXT,
        variedad            TEXT,
        lat                 REAL,
        lng                 REAL,
        precision_m         REAL,
        fecha_hora_telefono TEXT NOT NULL,
        fecha_hora_servidor TEXT,
        monitor_uid         TEXT,
        bbch                INTEGER,
        bbch_fuente         TEXT,
        clima               TEXT,  -- JSON {tempC, humedad, vientoKmh, lluvia24hMm, fuente, cielo, hojaMojada}
        valores             TEXT,  -- JSON {campo: valor}
        resultado           TEXT,  -- JSON {indicador, valor, estado}
        estados_biologicos  TEXT,  -- JSON [..]
        fotos               TEXT,  -- JSON [..]
        nota                TEXT
    """,
    "revisiones_trampa": """
        predio_id    TEXT NOT NULL REFERENCES predios(id),
        trampa_id    TEXT NOT NULL REFERENCES puntos(id),
        fecha_hora   TEXT NOT NULL,
        machos       INTEGER,
        hembras      INTEGER,
        total        INTEGER,
        cambio_cebo  INTEGER NOT NULL DEFAULT 0 CHECK (cambio_cebo IN (0, 1)),
        cambio_piso  INTEGER NOT NULL DEFAULT 0 CHECK (cambio_piso IN (0, 1)),
        foto         TEXT
    """,
    "aplicaciones": """
        predio_id           TEXT NOT NULL REFERENCES predios(id),
        fecha               TEXT NOT NULL,
        sectores            TEXT,  -- JSON [sectorId]
        producto            TEXT NOT NULL,
        dosis               REAL,
        dosis_unidad        TEXT,
        organismos_objetivo TEXT,  -- JSON [organismoId]
        nota                TEXT,
        uid                 TEXT
    """,
}

# Columnas que se guardan como texto JSON y se devuelven como objetos.
COLUMNAS_JSON = {
    "predios": {"miembros"},
    "organismos": {"datos"},
    "observaciones": {"clima", "valores", "resultado", "estados_biologicos", "fotos"},
    "aplicaciones": {"sectores", "organismos_objetivo"},
}

INDICES = [
    "CREATE INDEX IF NOT EXISTS ix_{t}_pendiente ON {t}(pendiente)",
    "CREATE INDEX IF NOT EXISTS ix_{t}_actualizado ON {t}(actualizado_en)",
]

# Ajustes locales (sesión, última sincronización); no se sincroniza.
AJUSTES = """
CREATE TABLE IF NOT EXISTS ajustes (
    clave TEXT PRIMARY KEY,
    valor TEXT
)
"""


def _sin_comentarios(columnas):
    """Quita los comentarios `--` para poder unir las columnas con comas."""
    return "\n".join(linea.split("--")[0].rstrip() for linea in columnas.strip().splitlines())


def sentencias_creacion():
    """Devuelve las sentencias SQL que crean el esquema completo."""
    sql = []
    for tabla, columnas in TABLAS.items():
        columnas = _sin_comentarios(columnas)
        sql.append(
            f"CREATE TABLE IF NOT EXISTS {tabla} (\n"
            f"    id TEXT PRIMARY KEY,\n{columnas},\n{AUDITORIA.rstrip()}\n)"
        )
        sql.extend(i.format(t=tabla) for i in INDICES)
    sql.append(AJUSTES)
    return sql

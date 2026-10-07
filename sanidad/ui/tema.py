"""Paleta de la app, igual a la de la app hermana de fenología (PhenoRubus).

Verdes de hoja + rojo frambuesa sobre fondo claro, con la tipografía estándar
de KivyMD (Roboto). KivyMD 1.2 solo acepta paletas con nombre, así que se
re-definen las rampas «Green» (verde hoja) y «Pink» (frambuesa) antes de
construir la app, como en PhenoRubus (ui/theme.py).
"""

from kivy.utils import get_color_from_hex

# --- PhenoRubus -----------------------------------------------------------
LEAF_DARK = "#1E4A3A"     # tinta principal / trazos
LEAF = "#2F6B4F"
LEAF_LIGHT = "#6FA86A"
LEAF_SOFT = "#DDEFD8"
BERRY = "#A8184A"         # acción principal
BERRY_DARK = "#7E1238"
BERRY_SOFT = "#F8DCE4"
INK = "#1B2A23"
INK_2 = "#41534A"
MUTED = "#6E7E75"
FONDO = "#F2F4EE"         # mismo color que el presplash

LEAF_RAMP = {
    "50": "EEF7EC", "100": "DDEFD8", "200": "BCDDB4", "300": "96C78C", "400": "6FA86A",
    "500": "2F6B4F", "600": "295E46", "700": "22513C", "800": "1E4A3A", "900": "143326",
    "A100": "C9EBC0", "A200": "9CD68E", "A400": "6FB85F", "A700": "4F9A45",
}
BERRY_RAMP = {
    "50": "FCEEF2", "100": "F8DCE4", "200": "F0B3C4", "300": "E78AA4", "400": "E0718F",
    "500": "A8184A", "600": "961541", "700": "7E1238", "800": "690F2F", "900": "4D0A22",
    "A100": "FF9FBA", "A200": "FF6E97", "A400": "F23D72", "A700": "D81B5A",
}

HEX = {
    "fondo": FONDO,
    "superficie": "#FFFFFF",
    "texto": INK,
    "texto_2": INK_2,
    "texto_suave": MUTED,
    "primario": LEAF_DARK,
    "hoja": LEAF,
    "accion": BERRY,
    "borde_suave": "#1E4A3A2E",
    "mapa_fondo": "#E7ECE3",
    "sector_relleno": LEAF_SOFT,
    "sector_borde": "#2F6B4F99",
    "sector_texto": LEAF_DARK,
    "sector_activo": BERRY_SOFT,
    "sector_activo_borde": BERRY,
    "ubicacion": "#2B6CB0",
    # Estados de umbral (SPEC.md, Reglas de negocio)
    "sobre": "#9E2A22",
    "cerca": "#D69A2D",
    "bajo": "#3E8A57",
    "sin_visitar": "#9AA096",
}
COLOR = {k: get_color_from_hex(v) for k, v in HEX.items()}


def instalar_paleta():
    from kivymd.color_definitions import colors
    colors["Green"].update(LEAF_RAMP)
    colors["Pink"].update(BERRY_RAMP)
    colors["Light"].update({"StatusBar": "1E4A3A", "AppBar": "2F6B4F",
                            "Background": "F3F7F2", "CardsDialogs": "FBFDFB"})


def aplicar_tema(theme_cls):
    theme_cls.theme_style = "Light"
    theme_cls.primary_palette = "Green"
    theme_cls.primary_hue = "500"
    theme_cls.accent_palette = "Pink"
    theme_cls.material_style = "M2"

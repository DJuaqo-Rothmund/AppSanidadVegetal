"""Paleta y tipografías de la app (tomadas del boceto "Monitoreo Sanitario")."""

from kivy.core.text import LabelBase
from kivy.utils import get_color_from_hex

from .. import rutas

HEX = {
    "fondo": "#EEF1EA",
    "superficie": "#FFFFFF",
    "texto": "#18231B",
    "texto_suave": "#4F5C50",
    "primario": "#1F4A30",
    "primario_oscuro": "#163522",
    "primario_claro": "#E3ECE0",
    "borde": "#CBD3C6",
    "borde_suave": "#D5DBD1",
    "mapa_fondo": "#E2E8DC",
    "sector_relleno": "#CBD9C1",
    "sector_borde": "#8FA584",
    "sector_texto": "#55684C",
    "sector_activo": "#A9C59A",
    "ubicacion": "#2B6CB0",
    # Estados de umbral (SPEC.md, Reglas de negocio)
    "sobre": "#9E2A22",
    "cerca": "#D69A2D",
    "bajo": "#3E8A57",
    "sin_visitar": "#9AA096",
}
COLOR = {k: get_color_from_hex(v) for k, v in HEX.items()}

FUENTE_TEXTO = "Manrope"
FUENTE_TITULO = "FrauncesItalic"


def registrar_fuentes():
    f = rutas.FUENTES
    LabelBase.register(
        name=FUENTE_TEXTO,
        fn_regular=str(f / "Manrope-Regular.ttf"),
        fn_bold=str(f / "Manrope-Bold.ttf"),
    )
    LabelBase.register(name="ManropeSemiBold", fn_regular=str(f / "Manrope-SemiBold.ttf"))
    LabelBase.register(name="ManropeExtraBold", fn_regular=str(f / "Manrope-ExtraBold.ttf"))
    LabelBase.register(name=FUENTE_TITULO, fn_regular=str(f / "Fraunces-SemiBoldItalic.ttf"))
    LabelBase.register(name="Fraunces", fn_regular=str(f / "Fraunces-SemiBold.ttf"))


def aplicar_tema(theme_cls):
    """Ajusta el tema de KivyMD: modo claro, verde y Manrope/Fraunces en los estilos."""
    theme_cls.theme_style = "Light"
    theme_cls.primary_palette = "Green"
    theme_cls.primary_hue = "900"
    theme_cls.accent_palette = "Amber"
    for estilo, valores in theme_cls.font_styles.items():
        if estilo == "Icon":
            continue
        valores[0] = FUENTE_TITULO if estilo in ("H1", "H2", "H3", "H4", "H5") else FUENTE_TEXTO
    theme_cls.font_styles["Button"][0] = "ManropeExtraBold"
    theme_cls.font_styles["Overline"][0] = "ManropeExtraBold"

"""Cámara y galería del teléfono (Pyjnius); en el computador, un selector de archivos.

Adaptado de PhenoRubus (android_bridge.py):
* Cámara: ACTION_IMAGE_CAPTURE escribiendo en un URI de MediaStore
  (Imágenes › Sanidad El Amanecer). No necesita FileProvider y deja la foto
  original en la galería; luego se copia al almacenamiento de la app.
* Galería: ACTION_GET_CONTENT.

Los resultados llegan en el hilo principal: al_terminar(ruta | None).
"""

import datetime as dt
import os
import threading

from kivy.clock import Clock
from kivy.utils import platform

CARPETA_PUBLICA = "Sanidad El Amanecer"
RC_CAMARA = 0x5301
RC_GALERIA = 0x5302


def _en_hilo_principal(funcion, *args):
    Clock.schedule_once(lambda dt_: funcion(*args), 0)


class MediosAndroid:
    def __init__(self, carpeta_temporal):
        from android import activity  # type: ignore
        from jnius import autoclass  # type: ignore
        self.tmp = carpeta_temporal
        os.makedirs(carpeta_temporal, exist_ok=True)
        self.PythonActivity = autoclass("org.kivy.android.PythonActivity")
        self.Intent = autoclass("android.content.Intent")
        self.MediaStore = autoclass("android.provider.MediaStore")
        self.MediaColumns = autoclass("android.provider.MediaStore$MediaColumns")
        self.ImagesMedia = autoclass("android.provider.MediaStore$Images$Media")
        self.ContentValues = autoclass("android.content.ContentValues")
        self.Activity = autoclass("android.app.Activity")
        self.api = autoclass("android.os.Build$VERSION").SDK_INT
        self._pendientes = {}
        activity.bind(on_activity_result=self._resultado)

    @property
    def actividad(self):
        return self.PythonActivity.mActivity

    @property
    def resolver(self):
        return self.actividad.getContentResolver()

    def tomar_foto(self, al_terminar):
        from jnius import autoclass, cast  # type: ignore
        nombre = f"sanidad_{dt.datetime.now():%Y-%m-%d_%H%M%S}.jpg"
        valores = self.ContentValues()
        valores.put(self.MediaColumns.DISPLAY_NAME, nombre)
        valores.put(self.MediaColumns.MIME_TYPE, "image/jpeg")
        if self.api >= 29:
            valores.put(self.MediaColumns.RELATIVE_PATH, f"Pictures/{CARPETA_PUBLICA}")
        else:  # Android 8-9: ruta explícita (WRITE_EXTERNAL_STORAGE)
            Environment = autoclass("android.os.Environment")
            carpeta = os.path.join(Environment.getExternalStoragePublicDirectory(
                Environment.DIRECTORY_PICTURES).getAbsolutePath(), CARPETA_PUBLICA)
            os.makedirs(carpeta, exist_ok=True)
            valores.put(self.MediaColumns.DATA, os.path.join(carpeta, nombre))
        uri = self.resolver.insert(self.ImagesMedia.EXTERNAL_CONTENT_URI, valores)
        intent = self.Intent(self.MediaStore.ACTION_IMAGE_CAPTURE)
        intent.putExtra(self.MediaStore.EXTRA_OUTPUT, cast("android.os.Parcelable", uri))
        intent.addFlags(self.Intent.FLAG_GRANT_WRITE_URI_PERMISSION | self.Intent.FLAG_GRANT_READ_URI_PERMISSION)
        self._pendientes[RC_CAMARA] = (al_terminar, uri)
        self.actividad.startActivityForResult(intent, RC_CAMARA)

    def elegir_de_galeria(self, al_terminar):
        try:
            intent = self.Intent(self.Intent.ACTION_GET_CONTENT)
            intent.addCategory(self.Intent.CATEGORY_OPENABLE)
            intent.setType("image/*")
            self._pendientes[RC_GALERIA] = (al_terminar, None)
            self.actividad.startActivityForResult(intent, RC_GALERIA)
        except Exception as e:  # noqa: BLE001 - nunca cerrar la app por el selector
            print("galería:", e)
            self._pendientes.pop(RC_GALERIA, None)
            al_terminar(None)

    def _resultado(self, codigo, resultado, intent):
        if codigo not in self._pendientes:
            return
        al_terminar, uri = self._pendientes.pop(codigo)
        ok = resultado == self.Activity.RESULT_OK
        # La copia (varios MB) va fuera del hilo de la interfaz.
        threading.Thread(target=self._procesar, daemon=True,
                         args=(codigo, ok, intent, al_terminar, uri)).start()

    def _procesar(self, codigo, ok, intent, al_terminar, uri):
        try:
            if codigo == RC_CAMARA:
                if not ok:
                    self.resolver.delete(uri, None, None)
                    return _en_hilo_principal(al_terminar, None)
                origen = uri
            else:
                if not ok or intent is None or intent.getData() is None:
                    return _en_hilo_principal(al_terminar, None)
                origen = intent.getData()
            destino = os.path.join(self.tmp, f"foto_{dt.datetime.now():%H%M%S%f}.jpg")
            _en_hilo_principal(al_terminar, self._copiar(origen, destino))
        except Exception as e:  # noqa: BLE001 - informar a la interfaz
            print("medios:", e)
            _en_hilo_principal(al_terminar, None)
        finally:
            from jnius import detach  # type: ignore
            detach()

    def _copiar(self, uri, destino):
        from jnius import autoclass  # type: ignore
        entrada = self.resolver.openInputStream(uri)
        try:
            if self.api >= 29:
                salida = autoclass("java.io.FileOutputStream")(destino)
                try:
                    autoclass("android.os.FileUtils").copy(entrada, salida)
                finally:
                    salida.close()
            else:
                File = autoclass("java.io.File")
                autoclass("java.nio.file.Files").copy(entrada, File(destino).toPath())
        finally:
            entrada.close()
        return destino


class MediosEscritorio:
    """En el computador no hay cámara: ambos botones abren un selector de imágenes."""

    def __init__(self, carpeta_temporal):
        self.tmp = carpeta_temporal

    def tomar_foto(self, al_terminar):
        self.elegir_de_galeria(al_terminar)

    def elegir_de_galeria(self, al_terminar):
        from kivymd.uix.filemanager import MDFileManager

        gestor = None

        def elegir(ruta):
            gestor.close()
            al_terminar(ruta if os.path.isfile(ruta) else None)

        def salir(*_):
            gestor.close()
            al_terminar(None)

        gestor = MDFileManager(select_path=elegir, exit_manager=salir, preview=False,
                               ext=[".jpg", ".jpeg", ".png", ".webp"])
        gestor.show(os.environ.get("SANIDAD_CARPETA_FOTOS", os.path.expanduser("~")))


def crear_medios(carpeta_temporal):
    if platform == "android":
        return MediosAndroid(carpeta_temporal)
    return MediosEscritorio(carpeta_temporal)

[app]

# Nombre visible en el teléfono
title = Sanidad · El Amanecer

# Identificador del paquete: cl.elamanecer.sanidad
# OJO: cambiarlo después de instalar en los teléfonos obliga a desinstalar
# la app (se pierden los datos locales no sincronizados).
package.name = sanidad
package.domain = cl.elamanecer

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,ttf,json
source.exclude_dirs = tests, bin, docs, .github, .buildozer, venv, .venv, __pycache__
source.exclude_patterns = firebase_config.example.json, requirements*.txt, README.md, SPEC.md

# La versión se lee de sanidad/__init__.py (__version__)
version.regex = __version__ = ['"](.*)['"]
version.filename = %(source.dir)s/sanidad/__init__.py

requirements = python3,kivy==2.3.1,kivymd==1.2.0,pillow,requests,urllib3,charset-normalizer,idna,certifi,android

icon.filename = %(source.dir)s/assets/icono.png
presplash.filename = %(source.dir)s/assets/presplash.png
android.presplash_color = #EEF1EA

orientation = portrait
fullscreen = 0

# Internet (Firebase, clima), ubicación (GPS) y cámara (fotos)
android.permissions = INTERNET, ACCESS_NETWORK_STATE, ACCESS_FINE_LOCATION, ACCESS_COARSE_LOCATION, CAMERA

# Android 8 (API 26) o superior, según SPEC.md
android.api = 34
android.minapi = 26
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True
android.allow_backup = True

[buildozer]
log_level = 2
warn_on_root = 1

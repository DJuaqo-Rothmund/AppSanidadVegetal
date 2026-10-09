[app]

# Nombre visible en el teléfono
title = Sanidad · El Amanecer

# Identificador del paquete: cl.elamanecer.sanidad
# OJO: cambiarlo después de instalar en los teléfonos obliga a desinstalar
# la app (se pierden los datos locales no sincronizados).
package.name = sanidad
package.domain = cl.elamanecer

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json,npz
source.exclude_dirs = tests, bin, docs, .github, .buildozer, venv, .venv, __pycache__
source.exclude_patterns = firebase_config.example.json, requirements*.txt, README.md, SPEC.md

# La versión se lee de sanidad/__init__.py (__version__)
version.regex = __version__ = ['"](.*)['"]
version.filename = %(source.dir)s/sanidad/__init__.py

# Mismas versiones que la app de fenología (PhenoRubus). sqlite3 y openssl tienen
# receta p4a (base local y HTTPS). requests usa chardet 5.2.0 (Python puro): las
# versiones 7.x y charset-normalizer traen partes compiladas para computador (x86_64)
# que no cargan en el teléfono.
requirements = python3,kivy==2.3.1,kivymd==1.2.0,kivy_garden.mapview==1.0.6,plyer,pillow,numpy,requests,urllib3,chardet==5.2.0,idna,certifi,sqlite3,openssl,pyjnius,android

icon.filename = %(source.dir)s/assets/icono.png
presplash.filename = %(source.dir)s/assets/presplash.png
android.presplash_color = #F2F4EE

orientation = portrait
fullscreen = 0

# Internet (Firebase, clima), ubicación (GPS) y cámara (fotos)
android.permissions = INTERNET, ACCESS_NETWORK_STATE, ACCESS_FINE_LOCATION, ACCESS_COARSE_LOCATION, CAMERA

# Android 8 (API 26) o superior, según SPEC.md
android.api = 34
android.minapi = 26
# Solo 64 bits, como la app de fenología (todos los teléfonos Android 8+ actuales)
android.archs = arm64-v8a
android.accept_sdk_license = True
android.allow_backup = False

p4a.bootstrap = sdl2
android.debug_artifact = apk

[buildozer]
log_level = 2
warn_on_root = 1

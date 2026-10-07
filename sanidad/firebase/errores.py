"""Errores de Firebase traducidos a mensajes para el monitor."""

MENSAJES = {
    "EMAIL_NOT_FOUND": "Correo o contraseña incorrectos.",
    "INVALID_PASSWORD": "Correo o contraseña incorrectos.",
    "INVALID_LOGIN_CREDENTIALS": "Correo o contraseña incorrectos.",
    "INVALID_EMAIL": "El correo no tiene un formato válido.",
    "USER_DISABLED": "Esta cuenta está desactivada. Habla con el administrador.",
    "TOO_MANY_ATTEMPTS_TRY_LATER": "Demasiados intentos. Espera unos minutos.",
    "TOKEN_EXPIRED": "La sesión venció. Vuelve a iniciar sesión.",
    "INVALID_REFRESH_TOKEN": "La sesión venció. Vuelve a iniciar sesión.",
    "USER_NOT_FOUND": "La cuenta ya no existe. Habla con el administrador.",
    "PERMISSION_DENIED": "No tienes permiso para ver estos datos.",
    "UNAUTHENTICATED": "La sesión venció. Vuelve a iniciar sesión.",
    "DATOS_INCOMPLETOS": "Escribe tu correo y tu contraseña.",
    "SIN_CONEXION": "Sin conexión. Revisa la señal e intenta de nuevo.",
}


class ErrorFirebase(Exception):
    def __init__(self, codigo, detalle=None, estado_http=None):
        self.codigo = codigo
        self.detalle = detalle
        self.estado_http = estado_http
        super().__init__(f"{codigo}: {detalle}" if detalle else codigo)

    @property
    def mensaje(self):
        return MENSAJES.get(self.codigo, f"Error de Firebase ({self.codigo}).")


class SinConexion(ErrorFirebase):
    def __init__(self):
        super().__init__("SIN_CONEXION")


def revisar_respuesta(respuesta):
    """Devuelve el JSON de una respuesta exitosa o lanza ErrorFirebase."""
    if respuesta.status_code < 400:
        return respuesta.json() if respuesta.content else {}
    try:
        error = respuesta.json().get("error", {})
    except ValueError:
        error = {}
    if isinstance(error, str):  # securetoken responde {"error": "invalid_grant", ...}
        codigo = error.upper()
    else:
        # Auth: "INVALID_PASSWORD" o "TOO_MANY_ATTEMPTS_TRY_LATER : detalle"; Firestore: status.
        codigo = (error.get("message") or "").split(" ")[0] or error.get("status")
        if error.get("status") in ("PERMISSION_DENIED", "UNAUTHENTICATED", "NOT_FOUND"):
            codigo = error["status"]
    raise ErrorFirebase(codigo or f"HTTP_{respuesta.status_code}",
                        detalle=error if error else None, estado_http=respuesta.status_code)

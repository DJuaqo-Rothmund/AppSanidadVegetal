"""MobileNetV3-Small (ImageNet) ejecutada con numpy: convierte una foto en un vector de 576 valores.

Los pesos vienen de scripts/exportar_mobilenet.py (BatchNorm ya plegada).
Sin TensorFlow ni TFLite, para que funcione en el APK con la receta de numpy.
"""

import json

import numpy as np

TAM_ENTRADA = 224


def _act(x, tipo):
    if tipo == "relu":
        return np.maximum(x, 0, out=x)
    if tipo == "relu6":
        return np.clip(x, 0, 6, out=x)
    if tipo == "hswish":
        return x * (np.clip(x + 3.0, 0.0, 6.0) / 6.0)
    raise ValueError(tipo)


def _hsigmoid(x):
    return np.clip(x + 3.0, 0.0, 6.0) / 6.0


def _rellenar(x, t, b, l, r):
    return np.pad(x, ((t, b), (l, r), (0, 0)))


def _conv_tallo(x, w, b):
    """Conv 3x3, paso 2, 'same' de TensorFlow (relleno extra al final) por im2col."""
    k = w.shape[0]
    alto, ancho, _ = x.shape
    sal_h, sal_w = -(-alto // 2), -(-ancho // 2)
    pad_h = max((sal_h - 1) * 2 + k - alto, 0)
    pad_w = max((sal_w - 1) * 2 + k - ancho, 0)
    x = _rellenar(x, pad_h // 2, pad_h - pad_h // 2, pad_w // 2, pad_w - pad_w // 2)
    columnas = np.stack([x[i:i + 2 * sal_h:2, j:j + 2 * sal_w:2, :]
                         for i in range(k) for j in range(k)], axis=2)  # (h, w, k*k, cin)
    return columnas.reshape(sal_h, sal_w, -1) @ w.reshape(-1, w.shape[-1]) + b


def _depthwise(x, w, b, s, pad):
    k = w.shape[0]
    x = _rellenar(x, *pad)
    alto = (x.shape[0] - k) // s + 1
    ancho = (x.shape[1] - k) // s + 1
    y = np.zeros((alto, ancho, x.shape[2]), dtype=np.float32)
    for i in range(k):
        for j in range(k):
            y += x[i:i + s * alto:s, j:j + s * ancho:s, :] * w[i, j]
    return y + b


class MobileNet:
    def __init__(self, ruta):
        datos = np.load(ruta)
        self.plan = json.loads(str(datos["plan"]))
        self.p = {k: datos[k].astype(np.float32) for k in datos.files if k != "plan"}

    def embedding(self, imagen):
        """imagen: arreglo uint8 (224, 224, 3) RGB. Devuelve un vector float32 de 576."""
        p = self.p
        x = imagen.astype(np.float32) / 127.5 - 1.0
        for paso in self.plan:
            if paso["op"] == "tallo":
                x = _act(_conv_tallo(x, p["tallo_w"], p["tallo_b"]), paso["act"])
            elif paso["op"] == "bloque":
                i = paso["id"]
                atajo = x
                if f"b{i}_exp_w" in p:
                    x = _act(x @ p[f"b{i}_exp_w"] + p[f"b{i}_exp_b"], paso["act"])
                x = _act(_depthwise(x, p[f"b{i}_dw_w"], p[f"b{i}_dw_b"], paso["s"], paso["pad"]),
                         paso["act_dw"])
                if paso.get("se"):
                    m = x.mean(axis=(0, 1))
                    m = np.maximum(m @ p[f"b{i}_se1_w"] + p[f"b{i}_se1_b"], 0)
                    x = x * _hsigmoid(m @ p[f"b{i}_se2_w"] + p[f"b{i}_se2_b"])
                x = x @ p[f"b{i}_proj_w"] + p[f"b{i}_proj_b"]
                if paso["residual"]:
                    x = x + atajo
            elif paso["op"] == "final":
                x = _act(x @ p["final_w"] + p["final_b"], paso["act"])
        return x.mean(axis=(0, 1)).astype(np.float32)

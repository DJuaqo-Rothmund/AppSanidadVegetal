"""Exporta MobileNetV3-Small (Keras, ImageNet, sin cabeza) a un .npz para correrlo con numpy.

El teléfono no lleva TensorFlow: sanidad/ia/mobilenet.py ejecuta la red con
numpy a partir de este archivo. Las BatchNorm se pliegan en las convoluciones
y se guarda un "plan" (JSON) con el orden de las capas.

Se corre una sola vez en un computador con TensorFlow:

    pip install tensorflow-cpu h5py
    python scripts/exportar_mobilenet.py pesos_keras_no_top.h5 assets/modelos/mobilenet_v3_small.npz \\
        --referencia tests/datos/mobilenet_referencia.npz

Pesos: https://storage.googleapis.com/tensorflow/keras-applications/mobilenet_v3/
       weights_mobilenet_v3_small_224_1.0_float_no_top_v2.h5  (licencia Apache 2.0)
"""

import argparse
import json

import numpy as np


def plegar(conv_w, bn, bias=None):
    """Pliega BatchNorm en los pesos de la convolución: devuelve (w, b)."""
    gamma, beta, media, var = bn.get_weights()
    escala = gamma / np.sqrt(var + bn.epsilon)
    w = conv_w * escala  # último eje = canales de salida (o canal en depthwise)
    b = beta - media * escala if bias is None else beta + (bias - media) * escala
    return w.astype(np.float32), b.astype(np.float32)


def activacion(capa):
    c = capa.get_config()
    if capa.__class__.__name__ == "ReLU":
        return "relu6" if c.get("max_value") == 6.0 else "relu"
    return {"hard_silu": "hswish", "hard_swish": "hswish", "relu": "relu"}[c["activation"]]


def exportar(modelo):
    capas = {c.name: c for c in modelo.layers}
    lista = modelo.layers
    pesos, plan = {}, []

    def siguiente(nombre):
        return lista[lista.index(capas[nombre]) + 1]

    # Tallo: conv 3x3 / 2 + BN + h-swish
    w, b = plegar(capas["conv"].get_weights()[0], capas["conv_bn"])
    pesos["tallo_w"], pesos["tallo_b"] = w, b
    plan.append({"op": "tallo", "act": activacion(siguiente("conv_bn"))})

    i = 0
    while True:
        p = "expanded_conv_" if i == 0 else f"expanded_conv_{i}_"
        if f"{p}depthwise" not in capas:
            break
        bloque = {"op": "bloque", "id": i}
        entrada = None
        if f"{p}expand" in capas:
            w, b = plegar(capas[f"{p}expand"].get_weights()[0], capas[f"{p}expand_bn"])
            pesos[f"b{i}_exp_w"], pesos[f"b{i}_exp_b"] = w[0, 0], b
            bloque["act"] = activacion(siguiente(f"{p}expand_bn"))
            entrada = w.shape[2]
        dw = capas[f"{p}depthwise"]
        w, b = plegar(dw.get_weights()[0][:, :, :, 0], capas[f"{p}depthwise_bn"])
        pesos[f"b{i}_dw_w"], pesos[f"b{i}_dw_b"] = w, b
        cfg = dw.get_config()
        bloque["k"] = cfg["kernel_size"][0]
        bloque["s"] = cfg["strides"][0]
        if f"{p}depthwise_pad" in capas:
            (t, bo), (l, r) = capas[f"{p}depthwise_pad"].get_config()["padding"]
            bloque["pad"] = [t, bo, l, r]
        else:
            k = bloque["k"]
            bloque["pad"] = [k // 2] * 4
        bloque["act_dw"] = activacion(siguiente(f"{p}depthwise_bn"))
        bloque.setdefault("act", bloque["act_dw"])
        if f"{p}squeeze_excite_conv" in capas:
            w1, b1 = capas[f"{p}squeeze_excite_conv"].get_weights()
            w2, b2 = capas[f"{p}squeeze_excite_conv_1"].get_weights()
            pesos[f"b{i}_se1_w"], pesos[f"b{i}_se1_b"] = w1[0, 0], b1
            pesos[f"b{i}_se2_w"], pesos[f"b{i}_se2_b"] = w2[0, 0], b2
            bloque["se"] = True
        w, b = plegar(capas[f"{p}project"].get_weights()[0], capas[f"{p}project_bn"])
        pesos[f"b{i}_proj_w"], pesos[f"b{i}_proj_b"] = w[0, 0], b
        bloque["residual"] = f"{p}add" in capas
        bloque["entrada"] = entrada
        plan.append(bloque)
        i += 1

    # Última conv 1x1 + BN + h-swish (576 canales) y promedio global
    w, b = plegar(capas["conv_1"].get_weights()[0], capas["conv_1_bn"])
    pesos["final_w"], pesos["final_b"] = w[0, 0], b
    plan.append({"op": "final", "act": activacion(siguiente("conv_1_bn"))})
    return pesos, plan


def imagenes_de_prueba():
    """Tres imágenes 224x224 definidas por fórmula (la prueba las regenera igual)."""
    yy, xx = np.mgrid[0:224, 0:224].astype(np.float32)
    salida = []
    for k in range(3):
        r = 128 + 100 * np.sin(xx / (11.0 + 5 * k)) * np.cos(yy / (19.0 - 3 * k))
        g = 128 + 90 * np.cos((xx + yy) / (23.0 + 4 * k))
        b = 128 + 70 * np.sin(xx * yy / (900.0 + 300 * k))
        salida.append(np.stack([r, g, b], axis=-1).clip(0, 255).astype(np.uint8))
    return np.stack(salida)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("h5")
    ap.add_argument("salida")
    ap.add_argument("--referencia", help="guarda imágenes de prueba y la salida de TensorFlow")
    a = ap.parse_args()

    import tensorflow as tf
    modelo = tf.keras.applications.MobileNetV3Small(
        input_shape=(224, 224, 3), include_top=False, weights=a.h5,
        pooling="avg", include_preprocessing=True)
    pesos, plan = exportar(modelo)
    np.savez_compressed(a.salida, plan=np.array(json.dumps(plan)),
                        **{k: v.astype(np.float16) for k, v in pesos.items()})
    print(f"{len(plan)} pasos, {sum(v.size for v in pesos.values()):,} parámetros -> {a.salida}")

    if a.referencia:
        imagenes = imagenes_de_prueba()
        salida = modelo.predict(imagenes.astype(np.float32), verbose=0)
        np.savez_compressed(a.referencia, embeddings=salida.astype(np.float32))
        print(f"referencia: {salida.shape} -> {a.referencia}")


if __name__ == "__main__":
    main()

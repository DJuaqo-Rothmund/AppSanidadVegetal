# Modelos

`mobilenet_v3_small.npz`: MobileNetV3-Small preentrenada en ImageNet (Keras
Applications, sin cabeza, 224 px, alpha 1.0), con BatchNorm plegada y pesos en
float16. La genera `scripts/exportar_mobilenet.py` y la ejecuta con numpy
`sanidad/ia/mobilenet.py`. Convierte cada foto en un vector de 576 valores para
comparar especies.

Pesos originales: Copyright The TensorFlow Authors, licencia Apache 2.0.
https://github.com/keras-team/keras/blob/master/LICENSE

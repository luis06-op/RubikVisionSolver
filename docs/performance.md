# Rendimiento del procesamiento

## Medición local · 18 de noviembre de 2026

Comparación del código de `d3616ad` con el rediseño. Se ejecutó el mismo script
`scripts/benchmark.py` contra ambas versiones, con el mismo entorno Python
3.14, NumPy 2.5.5 y OpenCV 5.1.0, en esta máquina Linux. Son mediciones locales,
no una garantía de rendimiento en otros equipos.

### Escaneo completo: análisis y renderizado

| Resolución | Antes: mediana | Ahora: mediana | Antes: p95 | Ahora: p95 |
|---|---:|---:|---:|---:|
| 640 × 480 | 5,71 ms | 3,00 ms | 6,15 ms | 5,99 ms |
| 1280 × 720 | 11,36 ms | 5,60 ms | 12,43 ms | 6,14 ms |
| 1920 × 1080 | 21,37 ms | 10,31 ms | 22,77 ms | 11,32 ms |

En esta ejecución, la mediana del procesamiento a 720p bajó aproximadamente
un **51 %**. El rediseño incluye la copia defensiva del fotograma y los nuevos
paneles de lectura.

### Solo clasificación de las nueve celdas

| Resolución | Antes: mediana | Ahora: mediana |
|---|---:|---:|
| 640 × 480 | 3,41 ms | 2,58 ms |
| 1280 × 720 | 6,27 ms | 2,12 ms |
| 1920 × 1080 | 11,70 ms | 3,87 ms |

## Método reproducible

```bash
python -m scripts.benchmark --frames 300
```

- 300 muestras por resolución y operación, tras 10 de calentamiento.
- Ruido BGR `uint8` generado con semilla 42: hay más variación de píxeles que
  en una pegatina uniforme. Se usa el mismo contenido en ambas versiones.
- Un hilo de OpenCV, para reducir variaciones entre configuraciones.
- Cada iteración recibe una copia nueva. Crear esa entrada queda fuera de la
  medición; la copia que realiza `Application.process()` sí queda incluida.
- Las versiones se ejecutaron por separado y secuencialmente. La frecuencia
  dinámica de CPU y la carga del sistema pueden alterar las cifras, sobre todo
  las primeras muestras. No interpretes el orden entre resoluciones como una
  propiedad del algoritmo.
- Se excluyen cámara, ventana, máscara de depuración y cálculo de Kociemba.
  **Milisegundos de procesamiento no equivalen a FPS de cámara.**

## Qué cambió

1. **Filtro localizado.** Mediana y conversión HSV sobre la cuadrícula con un
   halo del radio del filtro. Así se evita filtrar todo el vídeo sin cambiar
   los píxeles utilizados para clasificar.
2. **Máscaras de 8 bits.** Composición y conteo con operaciones de OpenCV, sin
   convertir repetidamente las máscaras a booleanos de NumPy.
3. **Cachés acotadas.** Superficies de color y medidas de texto reutilizadas,
   con límites de entradas para evitar crecimiento indefinido.
4. **Presupuesto por fotograma.** La espera de eventos resta el tiempo empleado
   por captura y procesamiento, con un mínimo de 1 ms para atender la GUI.
5. **Fotogramas originales intactos.** El dibujo se aplica a una copia, evitando
   que una segunda lectura de la misma imagen analice las etiquetas de la UI.

Las pruebas comparan el filtro localizado contra el filtrado completo con
distintos kernels y márgenes, incluyendo margen cero. También comprueban la
inmutabilidad de la captura, la liberación de cámara ante fallos de ventana,
el cierre de la GUI y el presupuesto temporal.

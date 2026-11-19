# Guía de diseño · RubikVision Studio

Esta guía es la "skill" visual del proyecto: cualquier cambio de interfaz debe
seguirla para mantener coherencia.

## 1. Principios

1. **El cubo es el protagonista.** La animación 3D ocupa el mayor espacio y
   nunca queda tapada por paneles flotantes.
2. **Una acción por pantalla.** Introducir colores y seguir la guía son dos
   fases separadas; no se mezclan.
3. ** Instrucciones en español, sin ambigüedad.** Cada giro indica cara,
   ángulo, sentido y desde dónde mirar.
4. **Cero dependencia de red.** Todo el cálculo ocurre en el navegador.
5. **Accesible.** Contraste alto, etiquetas `aria-label`, navegación por
   teclado y respeto a `prefers-reduced-motion`.

## 2. Paleta

| Rol | Color | Uso |
|---|---|---|
| Fondo | `#070c18` / `#0c1426` | Degradado base y rejilla tenue |
| Superficie | `rgba(17,27,47,.78)` | Paneles con `backdrop-filter` |
| Texto | `#eef5ff` | Titulares y datos |
| Texto secundario | `#9bb0cc` | Ayudas y descripciones |
| Acento primario | `#5eead4` (menta) | Botón principal, cubo resaltado, progreso |
| Acento secundario | `#a78bfa` (violeta) | Movimientos, degradados |
| Alerta | `#fbbf24` / `#fb7185` | Validación y errores |

Los colores de las pegatinas son los estándar: blanco `#f8fafc`, amarillo
`#facc15`, rojo `#ef4444`, naranja `#fb923c`, azul `#3b82f6`, verde `#22c55e`.

## 3. Tipografía

- Inter / Segoe UI / system-ui para cuerpo y títulos.
- Monoespacio para notación (`R'`, `F2`) y contadores.
- Titulares: `font-weight: 800`, `letter-spacing: -3px` en hero; `-0.6px` en h2.
- Etiquetas: mayúsculas, `letter-spacing: 2.6px`, 11 px, color menta.

## 4. Componentes

| Componente | Regla |
|---|---|
| `.panel` | Radio 18 px, borde translúcido, sombra profunda, blur 18 px. |
| `.btn.primary` | Degradado menta, texto oscuro; una sola por pantalla. |
| `.btn.ghost` | Fondo translúcido para acciones secundarias. |
| `.sticker` | Cuadrado con brillo diagonal; borde menta al pasar el cursor. |
| `.swatch` | Muestra el color y su nombre; borde del color seleccionado. |
| `.cube-stage` | Fondo radial, esquinas decorativas, sombra elíptica bajo el cubo. |
| `.move-notation` | 54–90 px mono, brillo menta; la notación nunca se traduce. |

## 5. Movimiento

- La animación del giro dura 1,8 s con 0,3 s de pausa inicial y se repite en
  bucle; `smoothstep` evita arranques bruscos.
- Cambiar de paso reinicia la animación desde cero.
- Pausa, velocidad y vista son controles explícitos con atajo de teclado.
- Transiciones CSS de 150–350 ms; nada de rebotes largos.

## 6. Respuesta y accesibilidad

- Dos columnas desde 980 px; una columna por debajo.
- La vista previa del cubo sube arriba en móvil.
- Cada pegatina tiene `aria-label` con cara, fila, columna y color.
- Los botones desactivados conservan contraste pero indican estado.
- `prefers-reduced-motion` reduce animaciones y transiciones a casi cero.

## 7. Prohibido

- Fuentes externas obligatorias o CDN de terceros.
- Enviar los colores a un servidor.
- Mostrar notación sola sin explicación en español.
- Tapar el cubo con diálogos modales.

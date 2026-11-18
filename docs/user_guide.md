# Guía del usuario de RubikVisionSolver

Esta guía explica, paso a paso, cómo usar RubikVisionSolver con un cubo de
Rubik 3×3×3 y una webcam. No hace falta saber programar: solo instalar el
programa una vez y seguir las instrucciones de la pantalla.

---

## 1. Qué necesitas

- Un ordenador con **Windows, macOS o Linux** y entorno de escritorio.
- **Python 3.10 o superior**.
- Una **webcam** conectada (la integrada del portátil sirve).
- Un **cubo de Rubik 3×3×3** estándar, con los colores bien diferenciados.
- Una mesa y una luz blanca razonablemente difusa. Evita focos directos y fondos
  de colores intensos.

> La aplicación abre una ventana con el vídeo en directo. No funciona en un
> servidor sin pantalla ni por SSH sin reenvío gráfico.

---

## 2. Instalación (solo la primera vez)

1. Abre una terminal (PowerShell en Windows, Terminal en macOS/Linux).
2. Descarga el proyecto y entra en su carpeta:

   ```bash
   # Clona el repositorio o descarga y descomprime el ZIP desde GitHub.
   cd RubikVisionSolver
   ```

3. Crea un entorno virtual e instala las dependencias:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate        # Windows: .venv\Scripts\activate
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. Comprueba que la cámara responde:

   ```bash
   python -m src.main --probe-camera
   ```

   Debe imprimir algo como `Camara 0 operativa: 1280x720 px`. Si falla, prueba
   otro índice con `--camera 1`, `--camera 2`, etc.

---

## 3. Iniciar la aplicación

Con el entorno virtual activado:

```bash
python -m src.main
```

Se abre una ventana con:

- el vídeo de la cámara;
- una **cuadrícula 3×3** en el centro;
- un panel con el progreso de las seis caras;
- el mensaje con la cara que debes mostrar.

Para salir en cualquier momento, pulsa `Q` o `ESC`.

---

## 4. Escanear el cubo

El programa pide las caras en un orden concreto. La clave es **no girar el cubo
al revés**: la cara superior del cubo debe quedar siempre hacia arriba, salvo
en las caras superior e inferior, donde se inclina el cubo hacia ti o hacia
atrás.

### Cara 1: superior (`U`)

1. Sujeta el cubo con la cara blanca (o la que hayas elegido como superior)
   mirando hacia arriba.
2. Inclínalo **hacia ti** hasta que esa cara mire a la cámara. La cara frontal
   quedará abajo.
3. Centra el cubo dentro de la cuadrícula.
4. Pulsa **ESPACIO**.

### Cara 2: izquierda (`L`)

1. Vuelve a poner el cubo con la cara superior arriba.
2. Gíralo sobre su eje vertical hasta que la cara **izquierda** mire a la
   cámara.
3. Centra y pulsa **ESPACIO**.

### Cara 3: frontal (`F`)

1. Coloca la cara **frontal** mirando a la cámara, con la superior arriba.
2. Centra y pulsa **ESPACIO**.

### Cara 4: derecha (`R`)

1. Gira el cubo sobre su eje vertical hasta que la cara **derecha** mire a la
   cámara.
2. Centra y pulsa **ESPACIO**.

### Cara 5: trasera (`B`)

1. Gira el cubo **180°** hasta que la cara **trasera** mire a la cámara.
2. Centra y pulsa **ESPACIO**.

### Cara 6: inferior (`D`)

1. Inclina el cubo **hacia atrás** (alejándolo de ti) hasta que la cara
   **inferior** mire a la cámara. La frontal quedará arriba.
2. Centra y pulsa **ESPACIO**.

> Consejo: mantén la misma distancia y la misma orientación durante todo el
> escaneo. Si una celda no se reconoce, la aplicación no avanza y te avisa:
> ajusta la luz o el encuadre y vuelve a pulsar ESPACIO. No hace falta reiniciar
> salvo que quieras empezar de cero.

---

## 5. Revisar el desarrollo plano

Al capturar la sexta cara, la aplicación muestra el **desarrollo plano** del
cubo y un informe:

- **Cubo válido**: aparece el mensaje «Cubo completo. Revisa el esquema y pulsa
  ESPACIO». Comprueba que los colores del dibujo coinciden con tu cubo.
- **Cubo no válido**: se listan los problemas detectados (por ejemplo, «Hay 10
  pegatinas de color rojo en lugar de 9»). Pulsa `R` para repetir el escaneo.

Si el esquema es correcto, pulsa **ESPACIO** para calcular la solución.

---

## 6. Seguir la solución

La pantalla de guía muestra un movimiento por vez:

```
R'
Gira la cara derecha 90 grados en sentido antihorario
```

- **ESPACIO**: marcar el movimiento como aplicado y pasar al siguiente.
- **ENTER**, **N** o **→**: confirmar y avanzar igual que ESPACIO.
- **B**: volver al movimiento anterior. No deshace el giro físico; corrige el
  cubo antes de volver a ejecutar ese paso.
- `R`: reiniciar el escaneo desde cero.

La notación es la de Singmaster:

| Símbolo | Significado |
|---|---|
| `R`, `L`, `U`, `D`, `F`, `B` | Cara derecha, izquierda, superior, inferior, frontal o trasera. |
| Sin sufijo | 90° en sentido horario mirando esa cara de frente. |
| `'` | 90° en sentido antihorario. |
| `2` | 180° (media vuelta). |

La guía mantiene la cámara a la izquierda y el movimiento a la derecha. La
flecha indica el sentido **mirando de frente la cara que debes girar**, no
necesariamente desde la vista frontal de la cámara. En la parte inferior verás
los próximos movimientos y el progreso de los pasos confirmados.

Al confirmar el último movimiento, aparece «Secuencia completada». Comprueba
las seis caras: la aplicación no verifica automáticamente los giros mediante
vídeo. Pulsa `R` si quieres escanear otro cubo.

---

## 7. Teclas

| Tecla | Acción |
|---|---|
| `ESPACIO` | Capturar la cara, confirmar el esquema o avanzar de movimiento. |
| `ENTER`, `N`, `→` | Confirmar o avanzar fuera del escaneo. |
| `B`, `←` | Movimiento anterior. |
| `R` | Reiniciar el escaneo / reintentar la cámara. |
| `M` | Ver u ocultar la máscara de colores (depuración). |
| `Q`, `ESC` | Salir. |

---

## 8. Problemas frecuentes

### «No se encontró ninguna cámara»

- Comprueba que la cámara no la está usando otra aplicación (videollamada,
  OBS, etc.).
- Prueba otro índice: `python -m src.main --camera 1`.
- En Linux, verifica que tu usuario tenga permiso sobre `/dev/video*`.

### La imagen se ve muy oscura o demasiado clara

- Enciende una luz frontal difusa.
- Evita el sol directo y los focos sobre las pegatinas.
- La aplicación muestra un aviso cuando la iluminación no es adecuada.

### Una pegatina aparece como `?` o la captura no avanza

- Acerca el cubo para que llene la cuadrícula.
- Mantén el cubo perpendicular a la cámara.
- Pulsa `M` y observa la máscara: si la pegatina sale negra, el tono queda fuera
  de los rangos. Consulta la sección de calibración del `README.md`.

### El cubo se detecta, pero la validación falla

- Es probable que una cara se haya escaneado en la orientación equivocada.
  Reinicia con `R` y revisa el orden y la inclinación de las caras `U` y `D`.
- Comprueba el desarrollo plano: un color de más o de menos suele indicar una
  celda mal leída.

### La solución no resuelve el cubo

- Vuelve a escanear con más luz y el cubo centrado.
- Asegúrate de aplicar cada movimiento en el sentido indicado y mirando la cara
  que se nombra.
- Si el cubo tiene pegatinas cambiadas o colores no estándar, el estado puede
  ser válido pero no corresponder a un cubo real; revisa la calibración.

### La ventana no se abre

- La aplicación necesita un entorno gráfico. En un servidor remoto, usa
  escritorio remoto o reenvío X11.
- No instales `opencv-python-headless`; usa `opencv-python`.

---

## 9. Preguntas rápidas

**¿Tengo que desmontar o girar el cubo de forma especial?**
No. Solo presentar cada cara a la cámara en el orden indicado, manteniendo la
cara superior arriba.

**¿Puedo usar cualquier cubo?**
Sí, siempre que sea 3×3×3 con seis colores distintos y centros fijos. Si los
colores no son los habituales, puede ser necesario calibrar los rangos HSV.

**¿Cuánto tarda?**
El escaneo depende de ti (seis capturas). El cálculo suele tardar menos de un
segundo en un ordenador moderno.

**¿La solución es la más corta posible?**
No necesariamente, pero es correcta y normalmente alrededor de 20 movimientos.

**¿Se guarda alguna imagen o dato?**
No. Todo el procesamiento ocurre en tu equipo y no se envía nada a internet.

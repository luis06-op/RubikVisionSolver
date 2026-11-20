# RubikVision Studio · interfaz web

Aplicación estática que permite **pintar los 54 colores de un cubo** en un
desarrollo plano y seguir una **solución corta tipo Kociemba** con una
animación 3D por movimiento, inspirada en Cyber Solver.

- Sin cámara y sin servidor: el solver corre en un Web Worker.
- React 19 + TypeScript + Vite.
- `cubejs` (MIT) para el algoritmo de dos fases; el modelo 3D es propio.
- Guía de estilo: [DESIGN.md](DESIGN.md).

**URL de producción:** <https://web-six-fawn-g49c6cx1zg.vercel.app>

## Desarrollo

```bash
cd web
npm install
npm run dev        # http://127.0.0.1:5173
npm test           # geometría, validación y corte por tiempo (17 pruebas)
npm run typecheck
npm run build      # dist/
```

## Cómo funciona la animación

Cada giro tiene una matriz de rotación propia que **solo se aplica a las 21
pegatinas y 9 cuerpos de la capa activa**; el resto del cubo no se mueve. La
matriz se deduce de la misma geometría que genera la permutación del modelo, y
`npm test` comprueba, movimiento a movimiento, que la posición final de cada
pieza coincide con el estado lógico. Por eso al pasar al paso siguiente no hay
ningún salto: el final de un giro ya es el estado inicial del siguiente.

## Qué se valida antes de calcular

`validateFacelets` comprueba que estén las 54 pegatinas, que haya nueve de cada
color y que los seis centros sean distintos. Después, `validateSolvable` agrupa
las pegatinas en las 8 esquinas y las 12 aristas y verifica los tres invariantes
del cubo: giro de esquinas, volteo de aristas y paridad de la permutación. Un
dibujo imposible se rechaza al instante con un mensaje que nombra los colores a
revisar, porque Kociemba no termina con esos estados.

Como red de seguridad, el cliente del worker corta el cálculo a los 8 segundos,
reinicia el motor y avisa: la interfaz nunca se queda en «Calculando…». Los
estados válidos tardan mucho menos (mediana de 85 ms en 200 cubos aleatorios).

## Despliegue en Vercel

```bash
cd web
npx vercel --prod       # primera vez: crea el proyecto
```

`vercel.json` define `npm run build` y `dist` como directorio de salida.
Las rutas son estáticas (`cleanUrls`), sin funciones ni variables de entorno.

## Estructura

```
web/
├── index.html
├── vercel.json
├── DESIGN.md              # sistema visual
├── src/
│   ├── App.tsx            # fases: pintar / guía
│   ├── styles.css         # paleta y componentes
│   ├── cube/
│   │   ├── geometry.ts    # modelo entero, proyección y dibujo
│   │   ├── solver.worker.ts
│   │   ├── solver.ts      # cliente del worker
│   │   ├── types.ts
│   │   └── validation.ts
│   └── components/
│       ├── NetInput.tsx   # desarrollo plano clicable
│       └── CubeStage.tsx  # lienzo animado
```

Tecnologías: React · TypeScript · Vite · cubejs · Canvas 2D.

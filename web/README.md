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
npm test           # verifica que cada giro anima solo su capa
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

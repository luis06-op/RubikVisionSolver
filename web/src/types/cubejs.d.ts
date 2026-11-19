declare module "cubejs" {
  export interface CubeInstance {
    asString(): string;
    solve(maxDepth?: number): string;
    isSolved(): boolean;
    move(algorithm: string): void;
    identity(): void;
  }

  export interface CubeConstructor {
    new (state?: unknown): CubeInstance;
    fromString(value: string): CubeInstance;
    initSolver(): void;
    inverse(algorithm: string): string;
  }

  const Cube: CubeConstructor;
  export default Cube;
}

"""Cálculo aislado y cancelable: la ventana sigue atendiendo vídeo y controles."""

from __future__ import annotations

import multiprocessing as mp
import time
from multiprocessing.connection import Connection

from .solver import RubikSolver, Solution, SolverError


def _solve(cubestring: str, depth: int, sender: Connection) -> None:
    """Entrada importable por spawn en Windows y Linux."""
    try:
        sender.send((RubikSolver(depth).solve(cubestring), ""))
    except Exception as error:
        sender.send((None, f"{type(error).__name__}: {error}"))
    finally:
        sender.close()


class SolveTask:
    """Un solo proceso por cálculo, con cancelación y límite de tiempo.

    Args:
        cubestring: Estado validado en orden URFDLB.
        depth: Profundidad del solucionador.
        timeout: Tiempo máximo, incluida la inicialización del motor.
    """

    def __init__(self, cubestring: str, depth: int, timeout: float = 60.0) -> None:
        context = mp.get_context("spawn")
        self._receiver, sender = context.Pipe(duplex=False)
        self._process = context.Process(
            target=_solve, args=(cubestring, depth, sender), daemon=True
        )
        self._closed = False
        self._deadline = time.monotonic() + timeout
        try:
            self._process.start()
        except Exception:
            self._receiver.close()
            raise
        finally:
            sender.close()

    def poll(self) -> Solution | None:
        """Obtiene el resultado sin bloquear o devuelve None mientras calcula.

        Raises:
            SolverError: Si falla el proceso, vence el plazo o el motor rechaza el cubo.
        """
        if self._closed:
            raise SolverError("El calculo ya fue cerrado")
        if self._receiver.poll():
            try:
                solution, error = self._receiver.recv()
            except (EOFError, OSError) as failure:
                raise SolverError("El proceso de resolucion termino sin resultado") from failure
            finally:
                self.close()
            if error:
                raise SolverError(str(error))
            if not isinstance(solution, Solution):
                raise SolverError("El motor devolvio un resultado inesperado")
            return solution
        if time.monotonic() > self._deadline:
            self.close()
            raise SolverError("El calculo supero 60 segundos. Revisa el escaneo y reintenta")
        if not self._process.is_alive():
            self.close()
            raise SolverError("El proceso de resolucion se cerro inesperadamente")
        return None

    def close(self) -> None:
        """Cancela el cálculo pendiente y libera sus recursos de forma idempotente."""
        if self._closed:
            return
        self._closed = True
        self._receiver.close()
        if self._process.is_alive():
            self._process.terminate()
        self._process.join(timeout=1.0)
        self._process.close()

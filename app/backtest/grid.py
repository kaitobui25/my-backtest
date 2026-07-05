from __future__ import annotations

from itertools import product

import numpy as np


def build_config_grid(
    sl_values: list[float],
    tp_values: list[float],
    max_holds: list[int],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    combos = list(product(sl_values, tp_values, max_holds))
    if not combos:
        return (
            np.array([], dtype=np.float64),
            np.array([], dtype=np.float64),
            np.array([], dtype=np.int64),
        )
    sl_arr = np.array([c[0] for c in combos], dtype=np.float64)
    tp_arr = np.array([c[1] for c in combos], dtype=np.float64)
    max_hold_arr = np.array([c[2] for c in combos], dtype=np.int64)
    return sl_arr, tp_arr, max_hold_arr

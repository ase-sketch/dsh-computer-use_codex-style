"""Software cursor overlay pose — Swift Animation fields from helper reflection.

baseRotationDegrees / scootTiltDegrees / stretchAxisDegrees / scaleX / scaleY
are recovered from ComputerUseCore.Animation. This module computes the pose;
Win32 / Composition drawing lives in overlay_win and composition_overlay.
"""

from __future__ import annotations

import math

SCOOT_TILT_DEGREES = 16.0
STRETCH_AXIS_DEGREES = 10.0
PRESS_SCALE = 0.86
FOLLOW = 0.35
MAGIC_MOVE_STEPS = 12
P0_P6_COUNT = 7


def scoot_pose(dx: float, dy: float, *, press: bool = False) -> dict[str, float]:
    speed = math.hypot(dx, dy)
    base = math.degrees(math.atan2(dy, dx)) if speed > 0.5 else 0.0
    tilt = max(-SCOOT_TILT_DEGREES, min(SCOOT_TILT_DEGREES, dx * 0.08))
    stretch = max(-STRETCH_AXIS_DEGREES, min(STRETCH_AXIS_DEGREES, dy * 0.05))
    scale = PRESS_SCALE if press else 1.0
    stretch_x = 1.0 + min(0.12, speed * 0.002)
    return {
        "baseRotationDegrees": base * 0.12 if not press else 0.0,
        "scootTiltDegrees": 0.0 if press else tilt,
        "stretchAxisDegrees": 0.0 if press else stretch,
        "scaleX": scale if press else stretch_x,
        "scaleY": scale if press else (1.0 / stretch_x),
        "compositeOpacity": 1.0,
        "press": 1.0 if press else 0.0,
    }


def follow(current: float, target: float, alpha: float = FOLLOW) -> float:
    return current + (target - current) * alpha


def cubic_bezier(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    t: float,
) -> tuple[float, float]:
    """Official motion.rs cubic (3(1-t)^2 t / 3(1-t)t^2 / t^3)."""
    t = 0.0 if t < 0.0 else 1.0 if t > 1.0 else float(t)
    omt = 1.0 - t
    a = omt * omt * omt
    b = 3.0 * omt * omt * t
    c = 3.0 * omt * t * t
    d = t * t * t
    return (
        a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0],
        a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1],
    )


def resample_p0_p6(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Pad/downsample onto the official 7-point P0–P6 property set."""
    if not points:
        return [(0.0, 0.0)] * P0_P6_COUNT
    samples = [(float(p[0]), float(p[1])) for p in points]
    while len(samples) < P0_P6_COUNT:
        samples.append(samples[-1])
    if len(samples) == P0_P6_COUNT:
        return samples
    step = (len(samples) - 1) / 6.0
    return [samples[int(round(i * step))] for i in range(P0_P6_COUNT)]


def p0_p6_samples(x: float, y: float, tx: float, ty: float) -> list[tuple[float, float]]:
    return resample_p0_p6(magic_move_samples(x, y, tx, ty, steps=6))


def magic_move_samples(x: float, y: float, tx: float, ty: float, steps: int = MAGIC_MOVE_STEPS) -> list[tuple[float, float]]:
    """Official overlay sampled / Magic Move path (P0–P6 choreography, eased)."""
    steps = max(int(steps), 1)
    dx = tx - x
    dy = ty - y
    dist = math.hypot(dx, dy)
    if dist < 0.5:
        return [(x, y), (tx, ty)]
    nx, ny = -dy / dist, dx / dist
    bulge = min(24.0, dist * 0.08)
    cx = (x + tx) / 2.0 + nx * bulge
    cy = (y + ty) / 2.0 + ny * bulge
    points: list[tuple[float, float]] = [(x, y)]
    for i in range(1, steps + 1):
        t = i / float(steps)
        ease = t * t * (3.0 - 2.0 * t)
        omt = 1.0 - ease
        px = omt * omt * x + 2.0 * omt * ease * cx + ease * ease * tx
        py = omt * omt * y + 2.0 * omt * ease * cy + ease * ease * ty
        points.append((px, py))
    return points


def sampled_poses(
    x: float,
    y: float,
    tx: float,
    ty: float,
    *,
    press: bool = False,
    steps: int = MAGIC_MOVE_STEPS,
) -> list[tuple[float, float, dict[str, float]]]:
    samples = magic_move_samples(x, y, tx, ty, steps=steps)
    out: list[tuple[float, float, dict[str, float]]] = []
    px, py = x, y
    for i, (sx, sy) in enumerate(samples):
        last = i == len(samples) - 1
        out.append((sx, sy, scoot_pose(sx - px, sy - py, press=press and last)))
        px, py = sx, sy
    return out


def step_cursor(
    x: float,
    y: float,
    tx: float,
    ty: float,
    *,
    press: bool = False,
) -> tuple[float, float, dict[str, float]]:
    nx = follow(x, tx)
    ny = follow(y, ty)
    return nx, ny, scoot_pose(tx - x, ty - y, press=press)

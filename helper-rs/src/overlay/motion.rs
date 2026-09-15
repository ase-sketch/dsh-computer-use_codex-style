//! Official cursor motion model (helper src/overlay/cursor/motion.rs).
//!
//! All values were recovered from the official binary: the distance classes from
//! the branch structure, the 46-degree bow axis from the hard-coded
//! cos46 = 0.6946584 / sin46 = 0.7193398 pair, the long-move duration
//! polynomial and its 0.9 * 0.9 scale, the 60 Hz spring integrator
//! (zeta = 1.68 short / 1.8 long, dt = 1/60, |v| epsilon 12.0/0.01,
//! q >= 0.999, 5 s cap) and the Scale squash
//! (1, 1/(1 + 1.5*min(|v|/3000, 1)), 1).
//!
//! Fidelity note (VIS-09/R1): the duration and the two-segment shape are now
//! taken from the *externally measured* official motion (11-official-sampling.md
//! section 3), not from the binary polynomial, because the polynomial is refuted:
//! with blend=curve=0 it predicts 0.42 s at L=400 px where the official takes
//! 0.691 s, and it is monotone where the official settles faster on a diagonal
//! (L=760 px horizontal 786 ms, L=998 px diagonal 651 ms). The measured law is a
//! piecewise-linear settle curve over the chord distance plus a diagonal
//! shortening term. The two-segment path is a 7-point chain that reproduces the
//! measured features: a reverse pre-move (backswing) of 21-28 px along the chord
//! and a bow perpendicular to the chord of 5-10.5% of its length. The old fixed
//! 46-degree bow axis is retained below only as provenance.
//!
//! The official writes these onto a DirectComposition property set
//! (motion with Progress/SegmentCount/P0..P6/Offset/RotationAngleInDegrees/Scale)
//! and lets the compositor interpolate. This module produces the same samples in
//! Rust so the overlay can drive the sprite directly, which keeps the motion
//! identical without depending on expression-animation support.

/// Below this distance the cursor snaps instead of animating.
pub const SNAP_DISTANCE_PX: f32 = 0.5;
/// At or below this distance the move is a single straight cubic segment.
pub const SINGLE_SEGMENT_MAX_PX: f32 = 196.0;
/// The binary's single-segment duration literal, kept as provenance only (see
/// `SHORT_DURATION_S`).
pub const BINARY_SHORT_DURATION_S: f32 = 0.24;
/// Duration of a single-segment move, in seconds. The binary carries a 0.24 s
/// literal here, but the externally observed settle of the official helper for
/// L = 80/120/180 px is 304-383 ms (11-official-sampling.md section 3). 0.34 s
/// is the value that lands inside every one of those +/-40 ms windows; the
/// 0.24 s literal is kept in parity/official-constants.json as
/// `cursorMotion.binaryShortDurationS` for provenance.
pub const SHORT_DURATION_S: f32 = 0.34;
/// Empirical settle curve knots `(chord px, settle ms)` read off the official
/// helper. Interpolated linearly, then extended with DURATION_TAIL_MS_PER_PX.
pub const DURATION_KNOTS_PX_MS: [(f32, f32); 4] =
    [(196.0, 340.0), (269.0, 492.0), (400.0, 691.0), (760.0, 786.0)];
/// Slope of the settle curve beyond the last knot (ms per chord px).
pub const DURATION_TAIL_MS_PER_PX: f32 = 0.264;
/// Chord length below which the vertical component does not shorten the move.
pub const DIAGONAL_ONSET_PX: f32 = 300.0;
/// Chord span over which the diagonal shortening ramps in.
pub const DIAGONAL_SPAN_PX: f32 = 1_600.0;
/// Maximum fraction of the settle removed by a fully diagonal move.
pub const DIAGONAL_MAX_SHORTEN: f32 = 0.45;
/// Settle clamps for the measured law, in seconds.
pub const DURATION_MIN_S: f32 = SHORT_DURATION_S;
pub const DURATION_MAX_S: f32 = 2.2;
/// Reverse pre-move (backswing) along the chord, in px. The official helper moves
/// 21 px (L=400), 22 px (L=760) and 28 px (L=998) backwards before moving forward;
/// single-segment moves do not back up.
pub const BACKSWING_BASE_PX: f32 = 18.0;
pub const BACKSWING_PER_PX: f32 = 0.01;
pub const BACKSWING_MAX_PX: f32 = 28.0;
/// Perpendicular bow amplitude as a fraction of the chord. Measured: 5.0% at
/// L=400, 6.2% at L=760, 9.0% at L=898, 10.5% at L=998; single-segment moves are
/// straight (<=1%).
pub const BOW_RATIO_BASE: f32 = 0.060;
pub const BOW_RATIO_PER_PX: f32 = 0.000_075;
pub const BOW_RATIO_MAX: f32 = 0.16;
/// Two-segment control points in chord coordinates `(s along, r perpendicular)`,
/// as multiples of the backswing / bow amplitude.
pub const BACKSWING_P1_FACTOR: f32 = 2.0;
pub const BACKSWING_P2_FACTOR: f32 = 1.0;
pub const BOW_R1_FACTOR: f32 = 0.50;
pub const BOW_R2_FACTOR: f32 = 1.00;
pub const BOW_R3_FACTOR: f32 = 0.72;
pub const BOW_R4_FACTOR: f32 = 0.30;
pub const BOW_R5_FACTOR: f32 = 0.05;
pub const BOW_S3_FRACTION: f32 = 0.45;
pub const BOW_S4_FRACTION: f32 = 0.72;
pub const BOW_S5_FRACTION: f32 = 0.90;
/// The official binary's fixed 46-degree bow axis, retained as provenance. The
/// measured trajectories bow perpendicular to the chord, so the axis no longer
/// builds the path; the empirical bow above replaces it.
pub const BOW_AXIS_RAD: f32 = 0.802_851_3;
pub const BOW_AXIS_COS: f32 = 0.694_658_4;
pub const BOW_AXIS_SIN: f32 = 0.719_339_8;
/// Binary bow length coefficients and clamps for the first and second halves.
pub const BOW1_FACTOR: f32 = 0.419_602_96;
pub const BOW2_FACTOR: f32 = 0.15;
pub const BOW_MIN_PX: f32 = 48.0;
pub const BOW_MAX_PX: f32 = 640.0;
pub const BOW_SCALE: f32 = 0.65;
/// Binary long-move duration polynomial (14004b7e8:556-636), retained as the
/// *refuted* hypothesis. See `binary_duration_polynomial_s`.
pub const LONG_DURATION_MIN_S: f32 = 0.12;
pub const LONG_DURATION_MAX_S: f32 = 2.2;
/// Overall scale applied to the long-move duration polynomial: 0.9 * (0.9 if flag).
pub const LONG_DURATION_SCALE: f32 = 0.9 * 0.9;
/// Duration polynomial terms (official 14004b7e8:597-616).
pub const DURATION_BIAS: f32 = 0.42;
pub const DURATION_FLAG_BIAS: f32 = 0.04;
pub const DURATION_BLEND_WEIGHT: f32 = 0.12;
pub const DURATION_LEN_WEIGHT: f32 = 0.22;
pub const DURATION_CURVE_WEIGHT: f32 = 0.28;
/// len_norm = clamp((L - 180) / 760) on the path arclength in px.
pub const LEN_NORM_OFFSET_PX: f32 = 180.0;
pub const LEN_NORM_SPAN_PX: f32 = 760.0;
/// over_n = clamp((L / chord - 1) / 0.55).
pub const OVER_REF: f32 = 0.55;
/// turn_n = clamp(sum(|dtheta|) / 4.3982296).
pub const TURN_REF_RAD: f32 = 4.398_229_6;
/// extra_n = clamp(sum(dtheta^2) / 1.25).
pub const EXTRA_REF: f32 = 1.25;
/// blend = 0.2*extra_n + 0.38*turn_n + 0.42*over_n.
pub const BLEND_EXTRA_WEIGHT: f32 = 0.2;
pub const BLEND_TURN_WEIGHT: f32 = 0.38;
pub const BLEND_OVER_WEIGHT: f32 = 0.42;
/// Official FUN_140054cf1: clamp((cos(theta + 46deg) - 0.08) / 0.92) on the
/// normalised chord direction.
pub const CURVE_OFFSET: f32 = 0.08;
pub const CURVE_SPAN: f32 = 0.92;
/// Polyline steps per path segment when measuring length and turning (the
/// official walker samples 0x18 = 24 points per record).
pub const PATH_SAMPLES_PER_SEGMENT: usize = 32;
/// Spring integration step (60 Hz).
pub const SPRING_DT: f32 = 0.016_666_668;
pub const SPRING_ZETA_SHORT: f32 = 1.68;
pub const SPRING_ZETA_LONG: f32 = 1.8;
pub const SPRING_VELOCITY_EPS_SHORT: f32 = 12.0;
pub const SPRING_VELOCITY_EPS_LONG: f32 = 0.01;
pub const SPRING_PROGRESS_EPS: f32 = 0.999;
pub const SPRING_MAX_SECONDS: f32 = 5.0;
/// Safety bound for the 60 Hz spring sampler: 5 s at 60 Hz. The official caps the
/// *path record* count at 20 (14004b7e8:454-457); the spring sampler itself only
/// stops on convergence or the 5 s deadline, so a 20-frame cap here was a misread
/// and is what flattened every move to about 0.32 s.
pub const MAX_KEYFRAMES: usize = (SPRING_MAX_SECONDS / SPRING_DT) as usize;
/// Scale squash reference velocity.
pub const SQUASH_REFERENCE_VELOCITY: f32 = 3000.0;
pub const SQUASH_FACTOR: f32 = 1.5;

/// A 2-D point in physical screen pixels.
pub type Point = (f32, f32);

/// How a move is animated.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum MoveKind {
    /// dist < SNAP_DISTANCE_PX: no animation at all.
    Snap,
    /// dist <= SINGLE_SEGMENT_MAX_PX: one straight cubic segment.
    SingleSegment,
    /// Everything longer: two cubic segments bowed along the 46-degree axis.
    TwoSegments,
}

/// Resolved move parameters: the control points to interpolate through and the
/// duration to interpolate over.
#[derive(Clone, Debug)]
pub struct CursorMove {
    pub kind: MoveKind,
    /// Bezier control points: 1 for a snap, 4 for a single segment, 7 for two.
    pub points: Vec<Point>,
    /// Total duration in seconds (0.0 for a snap).
    pub duration_s: f32,
}

impl CursorMove {
    pub fn segment_count(&self) -> usize {
        match self.kind {
            MoveKind::Snap => 0,
            MoveKind::SingleSegment => 1,
            MoveKind::TwoSegments => 2,
        }
    }
}

fn clamp(value: f32, lo: f32, hi: f32) -> f32 {
    if value < lo {
        lo
    } else if value > hi {
        hi
    } else {
        value
    }
}

/// Cubic Bezier evaluation, matching the official expanded polynomial
/// 3t(1-t)^2, 3t^2(1-t), t^3 weights seen in the binary.
pub fn cubic(p0: Point, p1: Point, p2: Point, p3: Point, t: f32) -> Point {
    let omt = 1.0 - t;
    let w0 = omt * omt * omt;
    let w1 = 3.0 * omt * omt * t;
    let w2 = 3.0 * omt * t * t;
    let w3 = t * t * t;
    (
        w0 * p0.0 + w1 * p1.0 + w2 * p2.0 + w3 * p3.0,
        w0 * p0.1 + w1 * p1.1 + w2 * p2.1 + w3 * p3.1,
    )
}

/// Sample a CursorMove at progress in [0, 1], mirroring the official expression
/// graph: one segment for a single segment, otherwise the first half for
/// progress < 0.5 and the second half afterwards.
pub fn sample(motion: &CursorMove, progress: f32) -> Point {
    let t = clamp(progress, 0.0, 1.0);
    match motion.kind {
        MoveKind::Snap => motion.points.first().copied().unwrap_or((0.0, 0.0)),
        MoveKind::SingleSegment => cubics(&motion.points, 0, t),
        MoveKind::TwoSegments => {
            if t < 0.5 {
                cubics(&motion.points, 0, clamp(t * 2.0, 0.0, 1.0))
            } else {
                cubics(&motion.points, 3, clamp((t - 0.5) * 2.0, 0.0, 1.0))
            }
        }
    }
}

fn cubics(points: &[Point], start: usize, t: f32) -> Point {
    cubic(points[start], points[start + 1], points[start + 2], points[start + 3], t)
}

/// Geometric signals the official duration polynomial consumes. They are the four
/// floats FUN_1400549b2 writes for a path: arclength, summed squared turning,
/// peak turning and summed absolute turning, plus the straight chord.
#[derive(Clone, Copy, Debug, Default)]
pub struct PathMetrics {
    /// Arclength of the sampled path in px (out[0]).
    pub length: f32,
    /// sum(dtheta^2) over the polyline (out[1]).
    pub turn_sq_sum: f32,
    /// sum(|dtheta|) over the polyline (out[3]).
    pub turn_sum: f32,
    /// Straight-line distance between the path ends.
    pub chord: f32,
}

impl PathMetrics {
    /// Official blend: 0.2*extra_n + 0.38*turn_n + 0.42*over_n, clamped to 1.
    pub fn blend(&self) -> f32 {
        let over_n = clamp((self.length / self.chord.max(1.0) - 1.0) / OVER_REF, 0.0, 1.0);
        let turn_n = clamp(self.turn_sum / TURN_REF_RAD, 0.0, 1.0);
        let extra_n = clamp(self.turn_sq_sum / EXTRA_REF, 0.0, 1.0);
        clamp(
            BLEND_EXTRA_WEIGHT * extra_n + BLEND_TURN_WEIGHT * turn_n + BLEND_OVER_WEIGHT * over_n,
            0.0,
            1.0,
        )
    }

    /// len_norm = clamp((L - 180) / 760).
    pub fn len_norm(&self) -> f32 {
        clamp((self.length - LEN_NORM_OFFSET_PX) / LEN_NORM_SPAN_PX, 0.0, 1.0)
    }
}

/// Walk the planned path as a polyline and accumulate the official signals.
pub fn path_metrics(motion: &CursorMove) -> PathMetrics {
    if motion.kind == MoveKind::Snap || motion.points.len() < 4 {
        return PathMetrics::default();
    }
    let steps = PATH_SAMPLES_PER_SEGMENT;
    let segments = motion.segment_count();
    let mut points: Vec<Point> = Vec::with_capacity(segments * steps + 1);
    for seg in 0..segments {
        let start = seg * 3;
        for step in 0..=steps {
            if seg > 0 && step == 0 {
                continue;
            }
            points.push(cubics(&motion.points, start, step as f32 / steps as f32));
        }
    }
    let mut metric = PathMetrics::default();
    let mut previous_angle: Option<f32> = None;
    for pair in points.windows(2) {
        let dx = pair[1].0 - pair[0].0;
        let dy = pair[1].1 - pair[0].1;
        let distance = (dx * dx + dy * dy).sqrt();
        metric.length += distance;
        if distance <= 0.01 {
            continue;
        }
        let angle = dy.atan2(dx);
        if let Some(previous) = previous_angle {
            let mut delta = angle - previous;
            while delta > std::f32::consts::PI {
                delta -= 2.0 * std::f32::consts::PI;
            }
            while delta < -std::f32::consts::PI {
                delta += 2.0 * std::f32::consts::PI;
            }
            metric.turn_sum += delta.abs();
            metric.turn_sq_sum += delta * delta;
        }
        previous_angle = Some(angle);
    }
    let first = points[0];
    let last = *points.last().expect("sampled path");
    metric.chord = ((last.0 - first.0).powi(2) + (last.1 - first.1).powi(2)).sqrt();
    metric
}

/// Official FUN_140054cf1: how far the chord direction leans into the bow axis,
/// mapped from cos(theta + 46deg) in [0.08, 1.0] to [0, 1].
pub fn curve_term(from: Point, to: Point) -> f32 {
    let dx = to.0 - from.0;
    let dy = to.1 - from.1;
    let length = (dx * dx + dy * dy).sqrt();
    // Official fallback when the direction is degenerate is -cos46.
    let (nx, ny) = if length >= 0.001 { (dx / length, dy / length) } else { (-BOW_AXIS_COS, 0.0) };
    clamp((nx * BOW_AXIS_COS - ny * BOW_AXIS_SIN - CURVE_OFFSET) / CURVE_SPAN, 0.0, 1.0)
}

/// The binary long-move duration polynomial (14004b7e8:556-636), kept as the
/// documented and *refuted* hypothesis: the sampling report shows it is 25-63%
/// short from L>=269 px and monotone where the official settles faster on a
/// diagonal. `official_duration_s` is what `plan` uses.
pub fn binary_duration_polynomial_s(dist: f32, metrics: &PathMetrics, curve: f32) -> f32 {
    let blend = metrics.blend();
    let len_norm = metrics.len_norm();
    let _ = dist;
    clamp(
        (DURATION_BIAS
            + DURATION_FLAG_BIAS
            + DURATION_BLEND_WEIGHT * blend
            + DURATION_LEN_WEIGHT * len_norm
            + DURATION_CURVE_WEIGHT * curve)
            * LONG_DURATION_SCALE,
        LONG_DURATION_MIN_S,
        LONG_DURATION_MAX_S,
    )
}

/// Empirical settle curve: piecewise-linear through the measured knots, then a
/// fixed slope. Returns milliseconds for a chord length in px.
pub fn base_duration_ms(length: f32) -> f32 {
    let mut previous = DURATION_KNOTS_PX_MS[0];
    if length <= previous.0 {
        return previous.1;
    }
    for knot in DURATION_KNOTS_PX_MS.iter().skip(1) {
        if length <= knot.0 {
            let t = (length - previous.0) / (knot.0 - previous.0);
            return previous.1 + (knot.1 - previous.1) * t;
        }
        previous = *knot;
    }
    previous.1 + DURATION_TAIL_MS_PER_PX * (length - previous.0)
}

/// Diagonal shortening: a move with a vertical component settles sooner than a
/// horizontal one of the same chord length (L=998 px, dy/L=0.541 -> 651 ms vs
/// L=760 px horizontal -> 786 ms), and the effect only appears past ~300 px.
pub fn diagonal_shorten(length: f32, dy: f32) -> f32 {
    if length <= 0.0 {
        return 1.0;
    }
    let share = (dy.abs() / length).clamp(0.0, 1.0);
    let k = ((length - DIAGONAL_ONSET_PX) / DIAGONAL_SPAN_PX)
        .clamp(0.0, DIAGONAL_MAX_SHORTEN);
    1.0 - k * share
}

/// The official *measured* settle for a chord of `(dx, dy)`, in seconds. Keyed on
/// the straight chord (the report's net displacement), which is exactly what the
/// external PrintWindow-centroid measurement observes.
pub fn official_duration_s(dx: f32, dy: f32) -> f32 {
    let length = (dx * dx + dy * dy).sqrt();
    if length < SNAP_DISTANCE_PX {
        return 0.0;
    }
    if length <= SINGLE_SEGMENT_MAX_PX {
        return SHORT_DURATION_S;
    }
    clamp(
        base_duration_ms(length) * diagonal_shorten(length, dy) / 1000.0,
        DURATION_MIN_S,
        DURATION_MAX_S,
    )
}

/// Compute how a cursor move from `from` to `to` is animated.
pub fn plan(from: Point, to: Point) -> CursorMove {
    let dx = to.0 - from.0;
    let dy = to.1 - from.1;
    let dist = (dx * dx + dy * dy).sqrt();

    if dist < SNAP_DISTANCE_PX {
        return CursorMove { kind: MoveKind::Snap, points: vec![to], duration_s: 0.0 };
    }

    if dist <= SINGLE_SEGMENT_MAX_PX {
        let p1 = (from.0 + dx / 3.0, from.1 + dy / 3.0);
        let p2 = (from.0 + dx * 2.0 / 3.0, from.1 + dy * 2.0 / 3.0);
        return CursorMove {
            kind: MoveKind::SingleSegment,
            points: vec![from, p1, p2, to],
            duration_s: SHORT_DURATION_S,
        };
    }

    // Two segments: a reverse pre-move (backswing) along the chord plus a bow
    // perpendicular to it, both taken from the official trajectory
    // (11-official-sampling.md section 3). The old fixed 46-degree axis is not
    // used to build the path: the measured path bows perpendicular to the chord.
    let ux = dx / dist;
    let uy = dy / dist;
    let nx = -uy;
    let ny = ux;
    let backswing = clamp(BACKSWING_BASE_PX + BACKSWING_PER_PX * dist, 0.0, BACKSWING_MAX_PX);
    let bow = clamp(BOW_RATIO_BASE + BOW_RATIO_PER_PX * dist, 0.0, BOW_RATIO_MAX) * dist;
    // Control points in chord coordinates: s along the chord, r perpendicular.
    let shape = [
        (0.0, 0.0),
        (-BACKSWING_P1_FACTOR * backswing, bow * BOW_R1_FACTOR),
        (-BACKSWING_P2_FACTOR * backswing, bow * BOW_R2_FACTOR),
        (BOW_S3_FRACTION * dist, bow * BOW_R3_FACTOR),
        (BOW_S4_FRACTION * dist, bow * BOW_R4_FACTOR),
        (BOW_S5_FRACTION * dist, bow * BOW_R5_FACTOR),
        (dist, 0.0),
    ];
    let points: Vec<Point> = shape
        .iter()
        .map(|(s, r)| (from.0 + ux * s + nx * r, from.1 + uy * s + ny * r))
        .collect();
    CursorMove { kind: MoveKind::TwoSegments, points, duration_s: official_duration_s(dx, dy) }
}

/// One sampled frame of an animated move.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Frame {
    pub progress: f32,
    pub point: Point,
    /// The Scale squash value the official writes each keyframe.
    pub scale_y: f32,
}

/// Sample the motion into the keyframes the official compositor would receive.
///
/// The official integrates a 60 Hz spring rather than interpolating linearly:
/// omega = 2*pi/T, zeta 1.68 (short) / 1.8 (long), dt = 1/60, stopping when the
/// velocity and the remaining distance both collapse, capped at 5 s. Scale
/// squashes proportionally to the instantaneous velocity.
/// Raw 60 Hz spring trajectory: `(progress, velocity)` per sample, *unclamped*, so
/// the under-damped overshoot the official integrator produces is observable.
pub fn spring_samples(motion: &CursorMove) -> Vec<(f32, f32)> {
    let total = motion.duration_s.max(LONG_DURATION_MIN_S);
    let omega = 2.0 * std::f32::consts::PI / total;
    let (zeta, velocity_eps) = if motion.kind == MoveKind::SingleSegment {
        (SPRING_ZETA_SHORT, SPRING_VELOCITY_EPS_SHORT)
    } else {
        (SPRING_ZETA_LONG, SPRING_VELOCITY_EPS_LONG)
    };
    let mut q = 0.0f32;
    let mut v = 0.0f32;
    let mut elapsed = 0.0f32;
    let mut samples = Vec::with_capacity(MAX_KEYFRAMES.min(256));
    while samples.len() < MAX_KEYFRAMES && elapsed < SPRING_MAX_SECONDS {
        let accel = omega * omega * (1.0 - q) - zeta * omega * v;
        v += accel * SPRING_DT;
        q += v * SPRING_DT;
        elapsed += SPRING_DT;
        samples.push((q, v));
        if v.abs() <= velocity_eps && q >= SPRING_PROGRESS_EPS {
            break;
        }
    }
    samples
}

pub fn keyframes(motion: &CursorMove) -> Vec<Frame> {
    if motion.kind == MoveKind::Snap {
        return vec![Frame { progress: 1.0, point: motion.points[0], scale_y: 1.0 }];
    }
    // The official clamps the emitted keyframe value to [0, 1] (`fVar7`), so the
    // overshoot only shows in the raw trajectory, not in the keyframe list.
    let mut frames: Vec<Frame> = spring_samples(motion)
        .into_iter()
        .map(|(q, v)| {
            let clamped = clamp(q, 0.0, 1.0);
            let scale_y = 1.0
                / (1.0 + SQUASH_FACTOR * clamp(v.abs() / SQUASH_REFERENCE_VELOCITY, 0.0, 1.0));
            Frame { progress: clamped, point: sample(motion, clamped), scale_y }
        })
        .collect();
    if frames.is_empty() {
        frames.push(Frame { progress: 0.0, point: motion.points[0], scale_y: 1.0 });
    }

    // The official always lands exactly on the destination.
    if let Some(last) = frames.last_mut() {
        last.progress = 1.0;
        last.point = *motion.points.last().expect("control points");
        last.scale_y = 1.0;
    }
    frames
}

/// Wall-clock milliseconds between two painted frames.
///
/// The official inserts its n sampled keyframes into an animation whose
/// SetDuration is the computed T (14004b7e8:1167-1188): the samples *span* T
/// instead of being replayed at a fixed 16 ms per frame. That is the whole of
/// VIS-08 - n is a sampling resolution, T is the animation length.
pub fn frame_interval_ms(motion: &CursorMove, frames: usize) -> u64 {
    if frames == 0 || motion.duration_s <= 0.0 {
        return 0;
    }
    // n samples at times 0, T/(n-1), ..., T: the last one lands exactly on the
    // destination at the end of the animation.
    let steps = frames.saturating_sub(1).max(1) as f32;
    ((motion.duration_s * 1000.0) / steps).round().max(1.0) as u64
}

#[cfg(test)]
mod tests {
    use super::*;

    fn dist(a: Point, b: Point) -> f32 {
        ((a.0 - b.0).powi(2) + (a.1 - b.1).powi(2)).sqrt()
    }

    #[test]
    fn short_moves_snap() {
        let motion = plan((10.0, 10.0), (10.2, 10.2));
        assert_eq!(motion.kind, MoveKind::Snap);
        assert_eq!(motion.duration_s, 0.0);
        assert_eq!(motion.segment_count(), 0);
    }

    #[test]
    fn medium_moves_use_one_fixed_duration_segment() {
        let motion = plan((0.0, 0.0), (150.0, 0.0));
        assert_eq!(motion.kind, MoveKind::SingleSegment);
        assert_eq!(motion.points.len(), 4);
        assert!((motion.duration_s - SHORT_DURATION_S).abs() < 1e-6);
        let mid = sample(&motion, 0.5);
        assert!(dist(mid, (75.0, 0.0)) < 1e-3, "midpoint {mid:?}");
    }

    #[test]
    fn long_moves_use_two_bowed_segments() {
        let motion = plan((0.0, 0.0), (600.0, 0.0));
        assert_eq!(motion.kind, MoveKind::TwoSegments);
        assert_eq!(motion.points.len(), 7);
        assert_eq!(motion.segment_count(), 2);
        assert!(motion.duration_s >= LONG_DURATION_MIN_S && motion.duration_s <= LONG_DURATION_MAX_S);
        let mid = sample(&motion, 0.5);
        assert!(mid.1.abs() > 1.0, "expected lateral bow, got {mid:?}");
        assert!(dist(sample(&motion, 0.0), (0.0, 0.0)) < 1e-3);
        assert!(dist(sample(&motion, 1.0), (600.0, 0.0)) < 1e-3);
    }

    #[test]
    fn keyframes_end_exactly_on_the_destination() {
        for (to, expected_kind) in [
            ((150.0f32, 40.0f32), MoveKind::SingleSegment),
            ((900.0, -300.0), MoveKind::TwoSegments),
        ] {
            let motion = plan((0.0, 0.0), to);
            assert_eq!(motion.kind, expected_kind);
            let frames = keyframes(&motion);
            assert!(!frames.is_empty());
            assert!(frames.len() <= MAX_KEYFRAMES, "cap is {MAX_KEYFRAMES}, got {}", frames.len());
            let last = frames.last().unwrap();
            assert!((last.progress - 1.0).abs() < 1e-6);
            assert!(dist(last.point, to) < 1e-3, "landed at {:?}", last.point);
            assert!((last.scale_y - 1.0).abs() < 1e-6);
            for pair in frames.windows(2) {
                assert!(pair[1].progress >= pair[0].progress - 1e-6);
            }
        }
    }

    #[test]
    fn squash_shrinks_only_while_moving() {
        let motion = plan((0.0, 0.0), (600.0, 0.0));
        let frames = keyframes(&motion);
        assert!(frames.iter().any(|f| f.scale_y < 0.999), "expected squash mid-move");
        assert!((frames.last().unwrap().scale_y - 1.0).abs() < 1e-6);
    }

    #[test]
    fn bow_axis_matches_the_official_constants() {
        assert!((BOW_AXIS_COS.powi(2) + BOW_AXIS_SIN.powi(2) - 1.0).abs() < 1e-5);
        assert!((BOW_AXIS_RAD.cos() - BOW_AXIS_COS).abs() < 1e-5);
        assert!((BOW_AXIS_RAD.sin() - BOW_AXIS_SIN).abs() < 1e-5);
    }

    // --- VIS-07: single (not doubled) damping. ---------------------------------

    #[test]
    fn single_damping_settles_faster_than_doubled_damping() {
        // Independent reference integrator: the official `v += ((1-q)*w^2 - v*w*z)*dt`
        // versus the old `- 2*z*w*v`. `zeta/2` is the equivalent standard ratio
        // (0.84 / 0.9), i.e. only marginally under-damped, so the *observable*
        // difference at 60 Hz is a faster approach, not a visible overshoot: with
        // the official convergence thresholds the raw trajectory peaks at
        // 1.0000001, far below any renderable difference. The coefficient itself is
        // what the fix pins, and `damping_term_has_no_factor_two` checks it exactly.
        let reference = |zeta: f32, frames: usize| {
            let total = 0.65f32;
            let omega = 2.0 * std::f32::consts::PI / total;
            let mut q = 0.0f32;
            let mut v = 0.0f32;
            for _ in 0..frames {
                v += (omega * omega * (1.0 - q) - zeta * omega * v) * SPRING_DT;
                q += v * SPRING_DT;
            }
            q
        };
        let official = reference(SPRING_ZETA_LONG, 30);
        let doubled = reference(2.0 * SPRING_ZETA_LONG, 30);
        assert!(
            official > doubled + 0.1,
            "single damping must lead the doubled form: {official} vs {doubled}"
        );
    }

    #[test]
    fn damping_term_has_no_factor_two() {
        // Closed form of the first integration steps: q0 = 0 and v0 = 0, so the
        // first two frames pin omega^2 and the damping coefficient separately.
        let motion = plan((0.0, 0.0), (900.0, 0.0));
        let omega = 2.0 * std::f32::consts::PI / motion.duration_s;
        let v1 = omega * omega * SPRING_DT;
        let q1 = v1 * SPRING_DT;
        let v2 = v1 + (omega * omega * (1.0 - q1) - v1 * omega * SPRING_ZETA_LONG) * SPRING_DT;
        let q2 = q1 + v2 * SPRING_DT;
        let frames = keyframes(&motion);
        assert!((frames[0].progress - q1).abs() < 1e-6, "q1 {} vs {}", frames[0].progress, q1);
        assert!((frames[1].progress - q2).abs() < 1e-6, "q2 {} vs {}", frames[1].progress, q2);
    }

    // --- VIS-08/VIS-10: duration scales with distance. -----------------------

    #[test]
    fn binary_duration_polynomial_is_refuted_by_the_measured_settle() {
        // 14004b7e8:556-636 evaluated on the model's own path metrics. The
        // polynomial is the *old* hypothesis, retained for provenance: for the
        // measured L=400 px horizontal move it predicts well under the observed
        // 691 ms, which is why `plan` uses `official_duration_s` instead.
        let motion = plan((0.0, 0.0), (900.0, 400.0));
        let metrics = path_metrics(&motion);
        let curve = curve_term((0.0, 0.0), (900.0, 400.0));
        let polynomial = binary_duration_polynomial_s(900.0f32.hypot(400.0), &metrics, curve);
        // Independent reference implementation of 14004b7e8:556-636.
        let over_n = clamp((metrics.length / metrics.chord.max(1.0) - 1.0) / 0.55, 0.0, 1.0);
        let turn_n = clamp(metrics.turn_sum / 4.398_229_6, 0.0, 1.0);
        let extra_n = clamp(metrics.turn_sq_sum / 1.25, 0.0, 1.0);
        let blend = clamp(0.2 * extra_n + 0.38 * turn_n + 0.42 * over_n, 0.0, 1.0);
        let len_norm = clamp((metrics.length - 180.0) / 760.0, 0.0, 1.0);
        let reference =
            clamp((0.42 + 0.04 + 0.12 * blend + 0.22 * len_norm + 0.28 * curve) * 0.9 * 0.9, 0.12, 2.2);
        assert!((polynomial - reference).abs() < 1e-5, "{polynomial} vs {reference}");

        // The refutation itself, on the measured L=400 px horizontal move, with the
        // polynomial's unknown blend/curve terms taken at 0 (report section 3.3).
        let len_norm = clamp((400.0 - LEN_NORM_OFFSET_PX) / LEN_NORM_SPAN_PX, 0.0, 1.0);
        let bare = (DURATION_BIAS + DURATION_FLAG_BIAS + DURATION_LEN_WEIGHT * len_norm)
            * LONG_DURATION_SCALE;
        let horizontal = plan((0.0, 0.0), (400.0, 0.0)).duration_s;
        assert!(
            bare < 0.5 && horizontal > 0.65,
            "measured L=400 horizontal settle {horizontal} s must refute the bare polynomial {bare} s"
        );
    }

    #[test]
    fn measured_settle_curve_is_monotone_and_hits_its_knots() {
        for (px, ms) in DURATION_KNOTS_PX_MS {
            assert!((base_duration_ms(px) - ms).abs() < 1e-3, "knot {px} -> {ms} ms");
        }
        let mut previous = 0.0;
        for length in [196.0f32, 250.0, 300.0, 400.0, 500.0, 600.0, 760.0, 900.0, 1200.0] {
            let value = base_duration_ms(length);
            assert!(value > previous, "{length}: {value} <= {previous}");
            previous = value;
        }
    }

    #[test]
    fn duration_grows_with_distance() {
        // The official polynomial is monotone in the path length signal; the old
        // fixed 20 x 16 ms replay made every distance identical.
        let mut previous = 0.0;
        for target in [220.0f32, 400.0, 700.0, 1000.0, 1400.0] {
            let motion = plan((0.0, 0.0), (target, 0.0));
            assert_eq!(motion.kind, MoveKind::TwoSegments);
            assert!(motion.duration_s >= previous, "{target}: {} < {previous}", motion.duration_s);
            previous = motion.duration_s;
        }
        let near = plan((0.0, 0.0), (267.0 * 0.824, 267.0 * 0.568)).duration_s;
        let far = plan((0.0, 0.0), (941.0 * 0.841, 941.0 * 0.541)).duration_s;
        assert!(far > near, "far {far} must outlast near {near}");
    }

    #[test]
    fn frames_span_the_duration_instead_of_a_fixed_16ms() {
        // VIS-08 regression guard: total replay length = frames x interval = T.
        for to in [(120.0f32, 0.0f32), (900.0, 400.0)] {
            let motion = plan((0.0, 0.0), to);
            let frames = keyframes(&motion);
            let interval = frame_interval_ms(&motion, frames.len());
            let total = interval as f32 * frames.len() as f32;
            let expected = motion.duration_s * 1000.0;
            assert!(
                (total - expected).abs() <= frames.len() as f32 + 1.0,
                "replay {total} ms must match T {expected} ms"
            );
        }
        let short = plan((0.0, 0.0), (300.0, 0.0));
        let long = plan((0.0, 0.0), (1200.0, 0.0));
        let short_ms = frame_interval_ms(&short, keyframes(&short).len());
        let long_ms = frame_interval_ms(&long, keyframes(&long).len());
        assert!(long_ms > short_ms, "long {long_ms}ms vs short {short_ms}ms");
    }

    #[test]
    fn short_moves_keep_the_official_fixed_duration() {
        let motion = plan((0.0, 0.0), (196.0, 0.0));
        assert_eq!(motion.kind, MoveKind::SingleSegment);
        assert!((motion.duration_s - SHORT_DURATION_S).abs() < 1e-6);
        let just_over = plan((0.0, 0.0), (197.0, 0.0));
        assert_eq!(just_over.kind, MoveKind::TwoSegments);
        assert!(just_over.duration_s > SHORT_DURATION_S);
    }

    // --- VIS-11: the bow flips with the chord direction. ----------------------

    #[test]
    fn bow_flips_with_the_chord_direction() {
        // Two moves in opposite directions along the same screen line. The bow is
        // perpendicular to the chord, so the signed deviation from the chord flips
        // side when the chord points the other way.
        let east = plan((0.0, 0.0), (700.0, 0.0));
        let west = plan((0.0, 0.0), (-700.0, 0.0));
        let deviation = |m: &CursorMove| sample(m, 0.5).1 - 0.0;
        let a = deviation(&east);
        let b = deviation(&west);
        assert!(a.abs() > 1.0 && b.abs() > 1.0, "expected a bow both ways: {a} {b}");
        assert!(a * b < 0.0, "bow must flip side: {a} vs {b}");
    }

    #[test]
    fn path_metrics_measure_a_straight_line() {
        let motion = plan((0.0, 0.0), (150.0, 0.0));
        let metrics = path_metrics(&motion);
        assert!((metrics.length - 150.0).abs() < 0.5, "length {}", metrics.length);
        assert!(metrics.turn_sum < 1e-3, "straight path turns: {}", metrics.turn_sum);
        assert!((metrics.chord - 150.0).abs() < 1e-3);
        assert!(metrics.blend() < 1e-3);
    }

    // --- VIS-09 / R1: the official *measured* settle law and path shape. -------
    //
    // Source: analysis/deep-dive/11-official-sampling.md section 3. Each row is one
    // externally observed move of the official helper (PrintWindow centroid of the
    // `CodexComputerUseCursorOverlay` layer, ~30 Hz, resolution +/-40 ms). tmin/tmax
    // are the measured settle window widened by that sampling resolution. They are
    // *observations*, not model output: the binary duration polynomial (with
    // blend=curve=0) is refuted by this table, so a model that reproduces the
    // polynomial but not these rows is wrong.
    //
    // (label, dx, dy, tmin_ms, tmax_ms)
    const OFFICIAL_MOTION_SAMPLES: [(&str, f32, f32, f32, f32); 10] = [
        ("d0", 0.0, 0.0, 0.0, 0.0),
        ("d80", 80.0, 0.0, 316.0, 406.0),
        ("d120", 120.0, 0.0, 264.0, 344.0),
        ("d180", 180.0, 0.0, 324.0, 423.0),
        ("d269", 200.0, 180.0, 452.0, 532.0),
        ("d400", 400.0, 0.0, 651.0, 731.0),
        ("d613", 580.0, 200.0, 638.0, 718.0),
        ("d760", 760.0, 0.0, 746.0, 826.0),
        ("d898", 860.0, 260.0, 695.0, 775.0),
        ("d998", 840.0, 540.0, 611.0, 691.0),
    ];

    /// Min/max of the path in chord coordinates: along the start->target chord and
    /// perpendicular to it. The official path backs up along the chord first
    /// (backswing) and bows out perpendicular to it.
    fn chord_profile(motion: &CursorMove) -> (f32, f32) {
        let first = motion.points[0];
        let last = *motion.points.last().expect("control points");
        let dx = last.0 - first.0;
        let dy = last.1 - first.1;
        let length = (dx * dx + dy * dy).sqrt().max(1e-6);
        let (ux, uy) = (dx / length, dy / length);
        let (nx, ny) = (-uy, ux);
        let mut min_along = f32::INFINITY;
        let mut max_perp: f32 = f32::NEG_INFINITY;
        for seg in 0..motion.segment_count() {
            let start = seg * 3;
            for step in 0..=800 {
                let p = cubics(&motion.points, start, step as f32 / 800.0);
                let along = (p.0 - first.0) * ux + (p.1 - first.1) * uy;
                let perp = (p.0 - first.0) * nx + (p.1 - first.1) * ny;
                if along < min_along { min_along = along; }
                if perp > max_perp { max_perp = perp; }
            }
        }
        (min_along, max_perp)
    }

    #[test]
    fn durations_match_the_official_measured_settle_intervals() {
        for (tag, dx, dy, tmin, tmax) in OFFICIAL_MOTION_SAMPLES {
            let motion = plan((0.0, 0.0), (dx, dy));
            if dx == 0.0 && dy == 0.0 {
                assert_eq!(motion.kind, MoveKind::Snap, "{tag}");
                assert_eq!(motion.duration_s, 0.0, "{tag}");
                continue;
            }
            assert_ne!(motion.kind, MoveKind::Snap, "{tag}");
            let ms = motion.duration_s * 1000.0;
            assert!(ms >= tmin && ms <= tmax, "{tag}: model {ms} ms outside official measured [{tmin}, {tmax}] ms");
        }
    }

    #[test]
    fn two_segment_moves_start_with_a_backswing() {
        let mut checked = 0;
        for (tag, dx, dy, _, _) in OFFICIAL_MOTION_SAMPLES {
            let motion = plan((0.0, 0.0), (dx, dy));
            let (min_along, _) = chord_profile(&motion);
            match motion.kind {
                MoveKind::Snap => {}
                MoveKind::SingleSegment => {
                    assert!(min_along > -0.75, "{tag}: single-segment move must stay straight ({min_along})");
                }
                MoveKind::TwoSegments => {
                    checked += 1;
                    assert!(min_along <= -10.0, "{tag}: official backswing missing (min along {min_along})");
                    assert!(min_along >= -45.0, "{tag}: backswing far too deep ({min_along})");
                }
            }
        }
        assert!(checked >= 6, "expected the long cases to be two-segment, got {checked}");
    }

    #[test]
    fn bow_amplitude_matches_the_official_measured_band() {
        for (tag, dx, dy, _, _) in OFFICIAL_MOTION_SAMPLES {
            let motion = plan((0.0, 0.0), (dx, dy));
            let length = (dx * dx + dy * dy).sqrt();
            let (_, max_perp) = chord_profile(&motion);
            let ratio = max_perp / length.max(1.0);
            match motion.kind {
                MoveKind::Snap => {}
                MoveKind::SingleSegment => {
                    assert!(ratio <= 0.012, "{tag}: single segment must be straight (ratio {ratio})");
                }
                MoveKind::TwoSegments => {
                    assert!(
                        (0.045..=0.145).contains(&ratio),
                        "{tag}: bow ratio {ratio} outside the official measured band 0.045..0.145"
                    );
                }
            }
        }
    }

    /// C8 for this domain: parity/official-constants.json is the single source of
    /// truth. Drift in either the Rust consts or the measured sample table fails.
    #[test]
    fn cursor_motion_constants_match_the_single_source() {
        let raw = include_str!("../../../parity/official-constants.json");
        let c: serde_json::Value =
            serde_json::from_str(raw).expect("parity/official-constants.json must be valid JSON");
        let m = &c["cursorMotion"];
        let num = |key: &str| m[key].as_f64().unwrap_or_else(|| panic!("{key} missing")) as f32;
        assert_eq!(num("snapDistancePx"), SNAP_DISTANCE_PX);
        assert_eq!(num("singleSegmentMaxPx"), SINGLE_SEGMENT_MAX_PX);
        assert_eq!(num("singleSegmentDurationS"), SHORT_DURATION_S);
        assert_eq!(num("durationMinS"), DURATION_MIN_S);
        assert_eq!(num("durationMaxS"), DURATION_MAX_S);
        assert_eq!(num("durationTailMsPerPx"), DURATION_TAIL_MS_PER_PX);
        assert_eq!(num("diagonalOnsetPx"), DIAGONAL_ONSET_PX);
        assert_eq!(num("diagonalSpanPx"), DIAGONAL_SPAN_PX);
        assert_eq!(num("diagonalMaxShorten"), DIAGONAL_MAX_SHORTEN);
        assert_eq!(num("backswingBasePx"), BACKSWING_BASE_PX);
        assert_eq!(num("backswingPerPx"), BACKSWING_PER_PX);
        assert_eq!(num("backswingMaxPx"), BACKSWING_MAX_PX);
        assert_eq!(num("bowRatioBase"), BOW_RATIO_BASE);
        assert_eq!(num("bowRatioPerPx"), BOW_RATIO_PER_PX);
        assert_eq!(num("bowRatioMax"), BOW_RATIO_MAX);
        assert_eq!(num("backswingP1Factor"), BACKSWING_P1_FACTOR);
        assert_eq!(num("backswingP2Factor"), BACKSWING_P2_FACTOR);
        assert_eq!(num("bowR1Factor"), BOW_R1_FACTOR);
        assert_eq!(num("bowR2Factor"), BOW_R2_FACTOR);
        assert_eq!(num("bowR3Factor"), BOW_R3_FACTOR);
        assert_eq!(num("bowR4Factor"), BOW_R4_FACTOR);
        assert_eq!(num("bowR5Factor"), BOW_R5_FACTOR);
        assert_eq!(num("bowS3Fraction"), BOW_S3_FRACTION);
        assert_eq!(num("bowS4Fraction"), BOW_S4_FRACTION);
        assert_eq!(num("bowS5Fraction"), BOW_S5_FRACTION);
        assert_eq!(num("binaryShortDurationS"), BINARY_SHORT_DURATION_S);
        assert_eq!(num("binaryBowAxisRad"), BOW_AXIS_RAD);
        assert_eq!(num("binaryBowAxisCos"), BOW_AXIS_COS);
        assert_eq!(num("binaryBowAxisSin"), BOW_AXIS_SIN);
        let clamp_s = m["binaryDurationClampS"].as_array().expect("binaryDurationClampS");
        assert_eq!(clamp_s[0].as_f64().unwrap() as f32, LONG_DURATION_MIN_S);
        assert_eq!(clamp_s[1].as_f64().unwrap() as f32, LONG_DURATION_MAX_S);
        let knots = m["durationKnotsPxMs"].as_array().expect("durationKnotsPxMs");
        assert_eq!(knots.len(), DURATION_KNOTS_PX_MS.len());
        for (row, (px, ms)) in knots.iter().zip(DURATION_KNOTS_PX_MS) {
            let pair = row.as_array().expect("knot pair");
            assert_eq!(pair[0].as_f64().unwrap() as f32, px);
            assert_eq!(pair[1].as_f64().unwrap() as f32, ms);
        }
        let samples = m["samples"].as_array().expect("samples");
        assert_eq!(samples.len(), OFFICIAL_MOTION_SAMPLES.len());
        for (row, (tag, dx, dy, tmin, tmax)) in samples.iter().zip(OFFICIAL_MOTION_SAMPLES) {
            assert_eq!(row["label"].as_str(), Some(tag));
            assert_eq!(row["dx"].as_f64().unwrap() as f32, dx, "{tag} dx");
            assert_eq!(row["dy"].as_f64().unwrap() as f32, dy, "{tag} dy");
            assert_eq!(row["tSettleMinMs"].as_f64().unwrap() as f32, tmin, "{tag} tmin");
            assert_eq!(row["tSettleMaxMs"].as_f64().unwrap() as f32, tmax, "{tag} tmax");
        }
    }
}

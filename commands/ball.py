import asyncio
import colorsys
import logging
import math
import os
import random
import tempfile

import imageio
import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

logger = logging.getLogger(__name__)

SIZE = 720
FPS = 60
RENDER_STEP = 2
SUPERSAMPLE = 2

DEFAULT_RINGS = 12
MIN_RINGS, MAX_RINGS = 3, 20
INNER_RADIUS = 105
OUTER_RADIUS = 335

GAP_HALF = 0.75
GAP_STEP = (0.15, 0.45)
GAP_JITTER = 0.25

SEAL_RINGS = True
SEAL_DELAY = 12
SEAL_FRAMES = 30

VANISH_FRAMES = 12

ROT_SPEED = 0.018
ROT_EASE = 0.08
ROT_SPEED_SPREAD = 0.9

GRAVITY = 0.18
SPEED_MIN, SPEED_MAX = 3.5, 9.0
BOUNCE_JITTER = 0.05

TAIL_SEC = 1.0
HARD_LIMIT_SEC = 90
SIM_ATTEMPTS = 40
TRAIL_LENGTH = 14

TAU = math.tau


def _duration_window(rings):
    return 0.5 * rings + 1, 2.0 * rings + 4


def _layout(n):
    spacing = (OUTER_RADIUS - INNER_RADIUS) / (n - 1)
    thickness = min(max(spacing * 0.22, 2.0), 4.5)
    ball_r = min(max((spacing - thickness) * 0.36, 3.0), 7.0)
    radii = [INNER_RADIUS + i * spacing for i in range(n)]
    return radii, thickness, ball_r


class _Timeline:
    def __init__(self, seed, n, hue, frames, done_frame, passes):
        self.seed = seed
        self.n = n
        self.hue = hue
        self.frames = frames
        self.done_frame = done_frame
        self.passes = passes

    @property
    def duration(self):
        return len(self.frames) / FPS


class _Sim:
    def __init__(self, seed, n):
        self.rng = random.Random(seed)
        self.seed = seed
        self.n = n
        self.radii, self.th, self.r = _layout(n)
        self.h = self.th / 2

        rng = self.rng
        self.hue = rng.random()
        base = rng.uniform(0, TAU)
        step = rng.choice((-1, 1)) * rng.uniform(*GAP_STEP)
        self.gap = [base + i * step for i in range(n)]

        r_in = self.radii[0]
        r_out = self.radii[-1]
        self.rot_speeds = []
        for R in self.radii:
            t = (R - r_in) / max(1e-9, (r_out - r_in))
            k = (1.0 - t) * ROT_SPEED_SPREAD + (1.0 - ROT_SPEED_SPREAD) * 0.5
            self.rot_speeds.append(ROT_SPEED * (0.4 + 1.6 * k))
        self.omegas = [0.0] * n
        start_phase = rng.uniform(0, TAU)
        self.phases = [start_phase] * n

        a = rng.uniform(0, TAU)
        dist = rng.uniform(0, self.radii[0] * 0.45)
        self.px, self.py = dist * math.cos(a), dist * math.sin(a)
        a = rng.uniform(0, TAU)
        self.vx, self.vy = 5 * math.cos(a), 5 * math.sin(a)

        self.direction = rng.choice((-1, 1))
        self.region = 0
        self.committed = set()
        self.committed_prev = set()
        self.passed = set()
        self.flash = [0.0] * n
        self.pulse = 0.0
        self.best_region = 0
        self.passes = []
        self.seal_t = [0] * n
        self.seal = [0.0] * n
        self.vanish = [0.0] * n
        self.done = None

    def _in_gap(self, i, phi):
        diff = (phi - (self.gap[i] + self.phases[i]) + math.pi) % TAU - math.pi
        margin = (self.r + self.h) / self.radii[i] + 0.02
        return abs(diff) <= GAP_HALF * (1 - self.seal[i]) - margin

    def _bounce(self, i, outer):
        d = math.hypot(self.px, self.py) or 1e-9
        nx, ny = self.px / d, self.py / d
        if outer:
            target = self.radii[i] - self.h - self.r
            vn = self.vx * nx + self.vy * ny
            if vn > 0:
                self.vx -= 2 * vn * nx
                self.vy -= 2 * vn * ny
        else:
            target = self.radii[i] + self.h + self.r
            vn = self.vx * nx + self.vy * ny
            if vn < 0:
                self.vx -= 2 * vn * nx
                self.vy -= 2 * vn * ny
        self.px, self.py = nx * target, ny * target

        j = self.rng.uniform(-BOUNCE_JITTER, BOUNCE_JITTER)
        c, s = math.cos(j), math.sin(j)
        self.vx, self.vy = self.vx * c - self.vy * s, self.vx * s + self.vy * c
        speed = math.hypot(self.vx, self.vy) or 1e-9
        k = min(max(speed, SPEED_MIN), SPEED_MAX) / speed
        self.vx *= k
        self.vy *= k

        self.pulse = 1.0

    def _substep(self, frame, steps):
        n, r, h, radii = self.n, self.r, self.h, self.radii
        self.vy += GRAVITY / steps
        self.px += self.vx / steps
        self.py += self.vy / steps
        if self.done is not None:
            return

        d = math.hypot(self.px, self.py) or 1e-9

        for c in [c for c in self.committed if abs(d - radii[c]) > h + r + 0.5]:
            self.committed.discard(c)

        while self.region < n and d > radii[self.region]:
            self.flash[self.region] = 1.0
            self.region += 1
            if self.region > self.best_region:
                self.best_region = self.region
                self.passes.append(frame)
                self.direction = -self.direction
                for i in range(n):
                    self.omegas[i] = self.direction * self.rot_speeds[i]
        while self.region > 0 and d < radii[self.region - 1]:
            self.region -= 1
            self.flash[self.region] = 0.6

        if self.region < n and self.region not in self.passed \
                and self.region not in self.committed \
                and d + r > radii[self.region] - h:
            if self._in_gap(self.region, math.atan2(self.py, self.px)):
                self.committed.add(self.region)
                self.passed.add(self.region)
            else:
                self._bounce(self.region, outer=True)
                d = math.hypot(self.px, self.py) or 1e-9

        if self.region > 0 and (self.region - 1) not in self.passed \
                and (self.region - 1) not in self.committed \
                and d - r < radii[self.region - 1] + h:
            if self._in_gap(self.region - 1, math.atan2(self.py, self.px)):
                self.committed.add(self.region - 1)
                self.passed.add(self.region - 1)
            else:
                self._bounce(self.region - 1, outer=False)
                d = math.hypot(self.px, self.py) or 1e-9

        if self.region == n and d - r > radii[n - 1] + h:
            self.done = frame
            self.flash = [1.0] * n

    def run(self):
        hard = int(HARD_LIMIT_SEC * FPS)
        tail = int(TAIL_SEC * FPS)
        frames = []
        for f in range(hard):
            for i in range(self.n):
                target = self.direction * self.rot_speeds[i]
                self.omegas[i] += (target - self.omegas[i]) * ROT_EASE
                self.phases[i] += self.omegas[i]

            speed = math.hypot(self.vx, self.vy)
            steps = max(1, int(math.ceil(speed / (self.r * 0.5))))
            for _ in range(steps):
                self._substep(f, steps)

            if SEAL_RINGS:
                for i in range(self.n):
                    if self.region > i and i not in self.passed:
                        self.seal_t[i] += 1
                    else:
                        self.seal_t[i] = max(0, self.seal_t[i] - 2)
                    t = min(1.0, max(0.0, (self.seal_t[i] - SEAL_DELAY) / SEAL_FRAMES))
                    self.seal[i] = t * t * (3 - 2 * t)

            for i in range(self.n):
                if i in self.passed:
                    self.vanish[i] = min(1.0, max(0.001, self.vanish[i] + 1.0 / VANISH_FRAMES))
            self.committed_prev = set(self.committed)

            frames.append((self.px, self.py, self.pulse,
                           tuple(self.phases),
                           tuple(self.flash), tuple(self.seal), tuple(self.vanish)))
            self.flash = [v * 0.90 for v in self.flash]
            self.pulse *= 0.86

            if self.done is not None and f - self.done >= tail:
                return _Timeline(self.seed, self.n, self.hue, frames, self.done, self.passes)
        return None


def _plan(rings):
    lo, hi = _duration_window(rings)
    best, best_miss = None, float("inf")
    for _ in range(SIM_ATTEMPTS):
        tl = _Sim(random.getrandbits(32), rings).run()
        if tl is None:
            continue
        d = tl.duration
        if lo <= d <= hi:
            return tl
        miss = lo - d if d < lo else d - hi
        if miss < best_miss:
            best, best_miss = tl, miss
    if best is None:
        raise RuntimeError("не удалось получить подходящий прогон")
    return best


def _ring_color(hue, i, n, flash):
    v = 1.0 - 0.35 * (i / max(1, n - 1))
    r, g, b = colorsys.hsv_to_rgb(hue, 0.92, v)
    k = min(1.0, flash) * 0.55
    return (int((r + (1 - r) * k) * 255),
            int((g + (1 - g) * k) * 255),
            int((b + (1 - b) * k) * 255))


def _glow(base):
    out = base
    for div, blur, gain in ((4, 2, 0.9), (10, 3, 0.8)):
        small = base.reduce(div).filter(ImageFilter.GaussianBlur(blur))
        big = small.resize((SIZE, SIZE), Image.BILINEAR)
        if gain != 1.0:
            big = big.point(lambda v, g=gain: int(v * g))
        out = ImageChops.add(out, big)
    return out


def _render_frame(tl, idx, geom):
    radii, th, ball_r = geom
    S = SIZE * SUPERSAMPLE
    c = S / 2
    h = th / 2 * SUPERSAMPLE
    x, y, pulse, phases, flash, seal, vanish = tl.frames[idx]

    img = Image.new("RGB", (S, S), (0, 0, 0))
    dr = ImageDraw.Draw(img)

    start = max(0, idx - TRAIL_LENGTH)
    count = idx - start
    for j in range(start, idx):
        t = (j - start + 1) / (count + 1)
        tx, ty = tl.frames[j][0], tl.frames[j][1]
        rr = ball_r * (0.25 + 0.55 * t) * SUPERSAMPLE
        g = int(190 * t ** 1.6)
        px, py = c + tx * SUPERSAMPLE, c + ty * SUPERSAMPLE
        dr.ellipse([px - rr, py - rr, px + rr, py + rr], fill=(g, g, g))

    for i, R in enumerate(radii):
        v = vanish[i]
        if v >= 1.0:
            continue
        color = _ring_color(tl.hue, i, tl.n, flash[i])
        if v > 0:
            k = 1.0 - v
            color = (int(color[0] * k), int(color[1] * k), int(color[2] * k))
        Rs = R * SUPERSAMPLE
        half = GAP_HALF * (1 - seal[i])
        if half < 0.02:
            if v <= 0:
                dr.ellipse([c - Rs - h, c - Rs - h, c + Rs + h, c + Rs + h],
                           outline=color, width=max(1, int(round(2 * h))))
            continue
        centre = tl.gap_base[i] + phases[i]
        a0, a1 = centre + half, centre + TAU - half
        steps = max(8, int((a1 - a0) * Rs / 6))
        t = np.linspace(a0, a1, steps)
        cs, sn = np.cos(t), np.sin(t)
        outer = np.stack([c + (Rs + h) * cs, c + (Rs + h) * sn], axis=1)
        inner = np.stack([c + (Rs - h) * cs[::-1], c + (Rs - h) * sn[::-1]], axis=1)
        dr.polygon([tuple(p) for p in np.vstack([outer, inner])], fill=color)
        for a in (a0, a1):
            ex, ey = c + Rs * math.cos(a), c + Rs * math.sin(a)
            dr.ellipse([ex - h, ey - h, ex + h, ey + h], fill=color)

    rr = ball_r * (1 + 0.5 * pulse) * SUPERSAMPLE
    bx, by = c + x * SUPERSAMPLE, c + y * SUPERSAMPLE
    dr.ellipse([bx - rr, by - rr, bx + rr, by + rr], fill=(255, 255, 255))

    img = img.reduce(SUPERSAMPLE)
    img = _glow(img)
    return img


def render_ring_video(tl, path):
    geom = _layout(tl.n)
    tl.gap_base = _Sim(tl.seed, tl.n).gap
    with imageio.get_writer(path, fps=FPS // RENDER_STEP, macro_block_size=1, quality=6,
                            ffmpeg_params=["-preset", "veryfast"]) as writer:
        for i in range(0, len(tl.frames), RENDER_STEP):
            writer.append_data(np.asarray(_render_frame(tl, i, geom)))


def generate_ring_video(rings=DEFAULT_RINGS):
    rings = max(MIN_RINGS, min(MAX_RINGS, int(rings)))
    tl = _plan(rings)
    logger.info("Ring video: seed=%s rings=%s duration=%.1fs passes=%s",
                tl.seed, rings, tl.duration, len(tl.passes))

    tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    tmp.close()
    try:
        render_ring_video(tl, tmp.name)
    except Exception:
        if os.path.exists(tmp.name):
            os.remove(tmp.name)
        raise
    return tmp.name, tl.duration, rings


def register_ball_handler(bot):
    @bot.message_handler(commands=["ball"])
    async def handle_ball_command(message):
        try:
            rings = DEFAULT_RINGS
            args = (message.text or "").split()
            if len(args) > 1 and args[1].isdigit():
                rings = max(MIN_RINGS, min(MAX_RINGS, int(args[1])))

            msg = await bot.reply_to(message, "<b>Генерирую видео...</b>", parse_mode="HTML")
            try:
                video_path, duration, rings = await asyncio.to_thread(generate_ring_video, rings)
            except Exception as e:
                logger.error(f"Ошибка при генерации видео: {e}")
                await bot.reply_to(message, "Не удалось сгенерировать видео.", parse_mode="HTML")
                await bot.delete_message(message.chat.id, msg.message_id)
                return

            try:
                with open(video_path, "rb") as f:
                    await bot.send_video(
                        message.chat.id, f,
                        duration=int(round(duration)), width=SIZE, height=SIZE,
                        caption=f"{rings} колец · {duration:.0f} сек",
                        supports_streaming=True,
                    )
            finally:
                if os.path.exists(video_path):
                    os.remove(video_path)
            await bot.delete_message(message.chat.id, msg.message_id)
        except Exception as e:
            logger.error(f"Ошибка в обработчике команды /ball: {e}")
            await bot.reply_to(message, f"<b>Ошибка!</b> {str(e)}", parse_mode="HTML")

    return handle_ball_command
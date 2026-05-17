import math, random, time
from .constants import WALK_SPEED, SLEEP_AFTER


class PetState:
    """Platform-agnostic animation and movement state machine.

    Coordinates use whatever system the platform provides — PetState does not
    assume a top-left origin.  Pass sx/sy as the minimum x/y of the usable
    screen area and sw/sh as its width/height.  macOS uses a bottom-left
    origin, so callers should supply the visibleFrame values directly and pass
    an explicit start_y (sy + 80) to position the pet near the bottom.
    """

    def __init__(
        self,
        sx: float, sy: float,
        sw: float, sh: float,
        tw: int,   th: int,
        start_x: float | None = None,
        start_y: float | None = None,
    ):
        self.sx, self.sy = sx, sy
        self.sw, self.sh = sw, sh
        self.tw, self.th = tw, th

        self.x = start_x if start_x is not None else float(sx + sw - tw - 120)
        self.y = start_y if start_y is not None else float(sy + sh - th - 80)

        self.anim        = "idle"
        self.fidx        = 0
        self.is_dragging = False
        self.moving      = False

        self._ftimer        = 0.0
        self._state         = "idle"
        self._stimer        = random.uniform(4.0, 8.0)
        self._target_x      = self.x
        self._target_y      = self.y
        self._last_interact = time.monotonic()

    # ── Drag & click events ───────────────────────────────────────────────────

    def on_drag_start(self) -> None:
        self.is_dragging = True
        self.anim        = "jumping"
        self.fidx        = 0
        self._ftimer     = 0.0

    def on_drag(self, x: float, y: float) -> None:
        """Update position during drag, clamped to screen bounds."""
        self.x = max(self.sx, min(self.sx + self.sw - self.tw, x))
        self.y = max(self.sy, min(self.sy + self.sh - self.th, y))

    def on_release(self) -> None:
        """Called on any mouse release (click or drag end)."""
        self.is_dragging    = False
        self._last_interact = time.monotonic()
        self.enter("action")

    # ── Movement toggle ───────────────────────────────────────────────────────

    def set_moving(self, val: bool) -> None:
        self.moving = val
        if val:
            self.enter("walking")
        elif self._state == "walking":
            self.enter("idle")

    # ── Tick ──────────────────────────────────────────────────────────────────

    def tick(self, dt: float, anims: dict) -> bool:
        """Advance one frame.  Returns True if (x, y) changed."""
        _, nf, fps = anims[self.anim]
        self._ftimer += dt
        if self._ftimer >= 1.0 / fps:
            self._ftimer = 0.0
            self.fidx    = (self.fidx + 1) % nf

        if self.is_dragging:
            return False

        self._stimer -= dt

        if self._state == "walking":
            dx   = self._target_x - self.x
            dy   = self._target_y - self.y
            dist = math.hypot(dx, dy)
            if dist < WALK_SPEED * 2:
                self.enter("idle")
                return True
            expected = "run_right" if dx >= 0 else "run_left"
            if self.anim != expected:
                self.anim    = expected
                self.fidx    = 0
                self._ftimer = 0.0
            self.x += dx / dist * WALK_SPEED
            self.y += dy / dist * WALK_SPEED
            self.x  = max(self.sx, min(self.sx + self.sw - self.tw, self.x))
            self.y  = max(self.sy, min(self.sy + self.sh - self.th, self.y))
            return True

        if self._stimer <= 0:
            self._pick_next()

        return False

    # ── State machine ─────────────────────────────────────────────────────────

    def enter(self, state: str) -> None:
        self._state  = state
        self.fidx    = 0
        self._ftimer = 0.0

        if state == "idle":
            self.anim    = "idle"
            self._stimer = random.uniform(4.0, 10.0)
        elif state == "walking":
            margin         = 80
            self._target_x = random.uniform(self.sx + margin, self.sx + self.sw - self.tw - margin)
            self._target_y = random.uniform(self.sy + margin, self.sy + self.sh - self.th - margin)
            self.anim      = "run_right" if self._target_x >= self.x else "run_left"
            self._stimer   = 999.0
        elif state == "sleeping":
            self.anim    = "failed"
            self._stimer = random.uniform(10.0, 20.0)
        elif state == "action":
            self.anim    = "waving"
            self._stimer = 2.0
        elif state == "jump":
            self.anim    = "jumping"
            self._stimer = 1.5
        elif state == "special":
            self.anim    = "review"
            self._stimer = 2.5

    def _pick_next(self) -> None:
        if time.monotonic() - self._last_interact > SLEEP_AFTER:
            self.enter("sleeping")
            return
        r = random.random()
        if self.moving:
            if   r < 0.55: self.enter("walking")
            elif r < 0.90: self.enter("idle")
            elif r < 0.95: self.enter("action")
            elif r < 0.98: self.enter("jump")
            else:          self.enter("special")
        else:
            if   r < 0.90: self.enter("idle")
            elif r < 0.96: self.enter("action")
            elif r < 0.98: self.enter("jump")
            else:          self.enter("special")

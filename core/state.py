import math, random, time
from .constants import WALK_SPEED, SLEEP_AFTER

# Personality bias tables: (cumulative_probability, next_state)
# Scanned in order — first threshold that exceeds random() wins.
_BIASES: dict[str, dict[str, list[tuple[float, str]]]] = {
    "friendly": {
        "moving": [(0.55, "walking"), (0.90, "idle"), (0.95, "action"), (0.98, "jump"), (1.0, "special")],
        "still":  [(0.90, "idle"),    (0.96, "action"), (0.98, "jump"), (1.0, "special")],
    },
    "focused": {
        # Stays mostly idle; nudge fires on a separate timer (see tick)
        "moving": [(0.10, "walking"), (0.95, "idle"), (0.98, "action"), (1.0, "special")],
        "still":  [(0.95, "idle"),    (0.98, "action"), (1.0, "special")],
    },
    "playful": {
        # Chases cursor when movement is on; very active otherwise
        "moving": [(0.38, "walking"), (0.55, "idle"), (0.73, "chasing"), (0.84, "action"), (0.93, "jump"), (1.0, "special")],
        "still":  [(0.55, "idle"),    (0.75, "action"), (0.90, "jump"),  (1.0, "special")],
    },
}


class PetState:
    """Platform-agnostic animation, movement, and personality state machine.

    Coordinates use whatever system the platform provides — PetState does not
    assume a top-left origin.  Pass sx/sy as the minimum x/y of the usable
    screen area and sw/sh as its width/height.  macOS uses a bottom-left
    origin, so callers pass the visibleFrame values directly and supply an
    explicit start_y (sy + 80) to position the pet near the bottom.
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
        self.personality = "friendly"

        self._ftimer        = 0.0
        self._state         = "idle"
        self._stimer        = random.uniform(4.0, 8.0)
        self._target_x      = self.x
        self._target_y      = self.y
        self._last_interact = time.monotonic()
        self._cursor_x      = self.x
        self._cursor_y      = self.y
        # Focused nudge: fire a "waiting" animation every 60–180 s
        self._nudge_timer   = random.uniform(60.0, 180.0)

    # ── Cursor tracking (Playful mouse-chase) ─────────────────────────────────

    def update_cursor(self, x: float, y: float) -> None:
        self._cursor_x = x
        self._cursor_y = y

    # ── Personality ───────────────────────────────────────────────────────────

    def set_personality(self, name: str) -> None:
        self.personality  = name
        self._nudge_timer = random.uniform(60.0, 180.0)
        if self._state == "chasing" and name != "playful":
            self.enter("idle")

    # ── Hot-resize (scale change without restart) ─────────────────────────────

    def resize(self, tw: int, th: int) -> None:
        self.tw, self.th = tw, th
        self.x = max(self.sx, min(self.sx + self.sw - tw, self.x))
        self.y = max(self.sy, min(self.sy + self.sh - th, self.y))

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
        elif self._state in ("walking", "chasing"):
            self.enter("idle")

    # ── Tick ──────────────────────────────────────────────────────────────────

    def tick(self, dt: float, anims: dict) -> bool:
        """Advance one frame.  Returns True if (x, y) changed."""
        _, nf, fps = anims[self.anim]
        self._ftimer += dt
        if self._ftimer >= 1.0 / fps:
            self._ftimer = 0.0
            self.fidx    = (self.fidx + 1) % nf

        # Focused nudge: fire the "waiting" animation every 60–180 s while idle
        if self.personality == "focused" and not self.is_dragging:
            self._nudge_timer -= dt
            if self._nudge_timer <= 0:
                self._nudge_timer = random.uniform(60.0, 180.0)
                if self._state in ("idle", "sleeping"):
                    self.enter("nudge")

        if self.is_dragging:
            return False

        self._stimer -= dt

        if self._state == "walking":
            return self._step_toward(self._target_x, self._target_y)

        if self._state == "chasing":
            return self._step_toward(self._cursor_x, self._cursor_y, stop_dist=WALK_SPEED * 4)

        if self._stimer <= 0:
            self._pick_next()

        return False

    def _step_toward(self, tx: float, ty: float, stop_dist: float = WALK_SPEED * 2) -> bool:
        dx   = tx - self.x
        dy   = ty - self.y
        dist = math.hypot(dx, dy)
        if dist < stop_dist:
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
        elif state == "chasing":
            # Target is the live cursor position, updated each tick
            self.anim    = "run_right" if self._cursor_x >= self.x else "run_left"
            self._stimer = 999.0
        elif state == "sleeping":
            self.anim    = "failed"
            self._stimer = random.uniform(10.0, 20.0)
        elif state == "action":
            self.anim    = "waving"
            self._stimer = 2.0
        elif state == "nudge":
            self.anim    = "waiting"
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
        key    = "moving" if self.moving else "still"
        biases = _BIASES[self.personality][key]
        r      = random.random()
        chosen = biases[-1][1]
        for threshold, state_name in biases:
            if r < threshold:
                chosen = state_name
                break
        # "chasing" only valid in Playful with movement enabled
        if chosen == "chasing" and not self.moving:
            chosen = "walking"
        self.enter(chosen)

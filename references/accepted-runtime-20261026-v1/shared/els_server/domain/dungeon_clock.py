"""Server monotonic active-stage time; resource loading is excluded."""
import math
import time


class DungeonClock:
    def __init__(self, now=None):
        self.now = now or time.monotonic
        self.total = 0.0
        self.started = None

    def resume(self):
        if self.started is None:
            self.started = self.now()

    def pause(self):
        if self.started is not None:
            self.total += max(0.0, self.now() - self.started)
            self.started = None

    def seconds(self):
        elapsed = self.total
        if self.started is not None:
            elapsed += max(0.0, self.now() - self.started)
        if not math.isfinite(elapsed) or elapsed > 2**31 - 1:
            raise ValueError('Dungeon elapsed time out of wire range')
        return int(elapsed)

"""Decode Pawprint sensor reports and classify gestures using raw sensor counts."""

MAX_SAMPLE_GAP = 0.65


def signed(value):
    return value if value < 128 else value - 256


def decode(data):
    if len(data) != 9 or data[0] != 0xD0:
        return None
    return bool(data[3]), tuple(signed(value) for value in data[5:8])


class Gesture:
    """Interpret a continuous series of button states and orientation samples."""

    def __init__(self, axis=0, left=-60, right=60, hold=0.5, motion=12, speed=35):
        self.axis = axis
        self.left = left
        self.right = right
        self.hold = hold
        self.motion = motion
        self.speed = speed
        self.reset()

    def reset(self):
        self.armed = False
        self.start = None
        self.last = None
        self.peak = 0
        self.axis_peak = 0
        self.velocity = 0
        self.dimming = False
        self.sent = None
        self.sent_at = 0

    def feed(self, timestamp, pressed, angles):
        if self.last is not None and timestamp - self.last[0] > MAX_SAMPLE_GAP:
            self.reset()
        previous = self.last
        self.last = (timestamp, angles)
        if not self.armed:
            self.armed = not pressed
            return None

        if not pressed:
            if self.start is None:
                return None
            duration = timestamp - self.start[0]
            action = None
            if self.dimming:
                if self.target != self.sent:
                    action = ("brightness", self.target)
            elif self.peak < self.motion:
                action = ("color", None) if duration < self.hold else ("off", None)
            self.start = None
            self.dimming = False
            return action

        if self.start is None:
            self.start = (timestamp, angles)
            self.peak = 0
            self.axis_peak = 0
            self.velocity = 0
            self.dimming = False
            self.sent = None
            self.sent_at = 0
            return None

        delta = [abs(value - start) for value, start in zip(angles, self.start[1])]
        self.peak = max(self.peak, *delta)
        self.axis_peak = max(self.axis_peak, delta[self.axis])
        if previous and timestamp > previous[0]:
            change = abs(angles[self.axis] - previous[1][self.axis])
            self.velocity = max(self.velocity, change / (timestamp - previous[0]))
        if timestamp - self.start[0] >= self.hold and (
            self.axis_peak >= self.motion
            or (self.axis_peak >= self.motion / 2 and self.velocity >= self.speed)
        ):
            self.dimming = True

        if self.dimming:
            fraction = (angles[self.axis] - self.left) / (self.right - self.left)
            self.target = round(max(0, min(1, fraction)) * 100)
            if self.sent is None or (
                timestamp - self.sent_at >= 0.2 and abs(self.target - self.sent) >= 2
            ):
                self.sent = self.target
                self.sent_at = timestamp
                return ("brightness", self.target)
        return None

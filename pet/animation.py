import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QLinearGradient, QPainter, QPainterPath,
                           QPen, QPixmap, QRadialGradient)

from .state_machine import PetState

AWAKE_TOP = QColor(150, 226, 255)
AWAKE_BOTTOM = QColor(66, 160, 226)
SLEEP_TOP = QColor(178, 190, 205)
SLEEP_BOTTOM = QColor(122, 134, 150)
BELLY = QColor(235, 250, 255, 200)
CHEEK = QColor(255, 150, 165, 170)
EYE_WHITE = QColor(255, 255, 255)
PUPIL = QColor(38, 50, 66)
MOUTH = QColor(60, 66, 84)
SHADOW = QColor(0, 0, 0, 55)

DORO_BODY_TOP = QColor(253, 251, 246)
DORO_BODY_BOTTOM = QColor(228, 222, 210)
DORO_SLEEP_TOP = QColor(233, 231, 226)
DORO_SLEEP_BOTTOM = QColor(203, 199, 192)
DORO_EAR = QColor(244, 233, 230)
DORO_OUTLINE = QColor(150, 140, 128, 120)
DORO_BELLY = QColor(255, 255, 255, 150)
DORO_BLUSH = QColor(255, 170, 182, 170)
DORO_EYE = QColor(46, 44, 42)
DORO_MOUTH = QColor(90, 80, 78)

GHOST_TOP = QColor(255, 255, 255, 238)
GHOST_BOTTOM = QColor(206, 224, 245, 228)
GHOST_SLEEP_TOP = QColor(236, 242, 250, 212)
GHOST_SLEEP_BOTTOM = QColor(196, 210, 228, 200)
GHOST_EYE = QColor(43, 53, 80)
GHOST_MOUTH = QColor(70, 82, 110)
GHOST_BLUSH = QColor(255, 170, 190, 120)
GHOST_GLOW = QColor(180, 210, 240, 55)
GHOST_OUTLINE = QColor(160, 185, 215, 90)

STYLES = ("girl", "ghost", "doro", "blob")


def render_frame(size, state, t, facing=1, look=None, style="blob", transition=None,
                 blink_t=None):
    look = look or QPointF(0.0, 0.0)
    if style == "girl":
        from .girl import _render_girl

        return _render_girl(size, state, t, facing, look, transition, blink_t)
    if style == "ghost":
        return _render_ghost(size, state, t, facing, look, transition, blink_t)
    if style == "doro":
        return _render_doro(size, state, t, facing, look, transition, blink_t)

    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing, True)

    bob, squash, stretch, tilt, eye_open, mouth_open, blink = _transition_pose(
        state, t, size, transition, blink_t)

    cx = size / 2.0
    cy = size * 0.55 + bob
    rx = size * 0.30 * squash
    ry = size * 0.29 * stretch
    asleep = state == PetState.SLEEP

    _draw_shadow(painter, size, cx, cy + ry, state, t, asleep)
    _draw_feet(painter, state, t, cx, cy + ry, rx, size, asleep)

    painter.save()
    painter.translate(cx, cy)
    painter.rotate(tilt)
    gradient = QLinearGradient(0, -ry, 0, ry)
    top = SLEEP_TOP if asleep else AWAKE_TOP
    bottom = SLEEP_BOTTOM if asleep else AWAKE_BOTTOM
    gradient.setColorAt(0.0, top)
    gradient.setColorAt(1.0, bottom)
    path = QPainterPath()
    path.addEllipse(QPointF(0, 0), rx, ry)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(gradient))
    painter.drawPath(path)

    belly = QRadialGradient(QPointF(0, ry * 0.25), rx * 0.9)
    belly.setColorAt(0.0, BELLY)
    belly.setColorAt(1.0, QColor(235, 250, 255, 0))
    painter.setBrush(QBrush(belly))
    painter.drawEllipse(QPointF(0, ry * 0.28), rx * 0.62, ry * 0.6)
    _draw_tuft(painter, facing, rx, ry)
    painter.restore()

    eye_y = cy - ry * 0.16
    eye_dx = rx * 0.40
    _draw_cheeks(painter, cx, cy, rx, ry, asleep)
    _draw_eyes(painter, cx - eye_dx, cx + eye_dx, eye_y, size, look, eye_open, blink, asleep)
    _draw_mouth(painter, cx + facing * size * 0.02, cy + ry * 0.42, size, mouth_open, asleep)

    painter.end()
    return pm


def _pose(state, t, size, blink_t=None):
    bob = squash = stretch = tilt = 0.0
    squash = 1.0
    stretch = 1.0
    eye_open = 1.0
    mouth_open = 0.0
    blink = 0.0
    if state == PetState.IDLE:
        phase = math.sin(t * 2.2)
        bob = phase * size * 0.018
        squash = 1.0 + phase * 0.02
        stretch = 1.0 - phase * 0.02
    elif state == PetState.WALK:
        step = t * 9.0
        bob = -abs(math.sin(step)) * size * 0.055
        tilt = math.sin(step) * 7.0
        squash = 1.0 + math.sin(step) * 0.05
        stretch = 1.0 - math.sin(step) * 0.05
    elif state == PetState.SLEEP:
        bob = math.sin(t * 1.6) * size * 0.010
        eye_open = 0.0
    elif state == PetState.DRAG:
        squash = 0.90
        stretch = 1.12
        eye_open = 1.15
        mouth_open = 0.35
    elif state == PetState.FALL:
        squash = 0.86
        stretch = 1.18
        eye_open = 1.2
        mouth_open = 0.5
    elif state == PetState.REACT:
        hop = abs(math.sin(t * 11.0))
        bob = -hop * size * 0.05
        eye_open = 1.2
        mouth_open = 0.35 + hop * 0.2
    elif state == PetState.TALK:
        bob = math.sin(t * 6.0) * size * 0.018
        mouth_open = math.sin(t * 13.0) * 0.5 + 0.5
    elif state == PetState.HOP:
        squash = 0.94
        stretch = 1.08
        eye_open = 1.15
        mouth_open = 0.3
    elif state == PetState.THROWN:
        tilt = math.sin(t * 16.0) * 26.0
        squash = 0.92
        stretch = 1.10
        eye_open = 1.25
        mouth_open = 0.55
    elif state == PetState.PET:
        phase = math.sin(t * 5.0)
        bob = phase * size * 0.02
        squash = 1.0 + phase * 0.05
        stretch = 1.0 - phase * 0.05
        eye_open = 0.30
        mouth_open = 0.28
    elif state == PetState.DIZZY:
        tilt = math.sin(t * 9.0) * 18.0
        eye_open = 0.75
        mouth_open = 0.2
    if state != PetState.SLEEP:
        cycle = (t if blink_t is None else blink_t) % 3.4
        if cycle > 3.20:
            blink = max(0.0, 1.0 - (cycle - 3.20) / 0.12)
        elif cycle > 3.0:
            blink = min(1.0, (cycle - 3.0) / 0.20)
    return bob, squash, stretch, tilt, eye_open, mouth_open, blink


def _transition_pose(state, t, size, transition, blink_t=None):
    current = _pose(state, t, size, blink_t)
    if not transition:
        return current
    old_state, old_t, elapsed = transition
    mix = max(0.0, min(1.0, elapsed / 0.12))
    previous = _pose(old_state, old_t, size, blink_t)
    return tuple(a + (b - a) * mix for a, b in zip(previous, current))


def _draw_shadow(painter, size, cx, by, state, t, asleep):
    if state in (PetState.DRAG, PetState.FALL):
        return
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(SHADOW))
    w = size * 0.30
    h = size * 0.045
    painter.drawEllipse(QPointF(cx, min(by, size * 0.94)), w, h)


def _draw_feet(painter, state, t, cx, by, rx, size, asleep):
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(SLEEP_BOTTOM if asleep else AWAKE_BOTTOM))
    offset = 0.0
    if state == PetState.WALK:
        offset = math.sin(t * 9.0) * size * 0.05
    for sign in (-1, 1):
        painter.drawEllipse(QPointF(cx + sign * rx * 0.48 + sign * offset, by - size * 0.01),
                            size * 0.075, size * 0.045)


def _draw_tuft(painter, facing, rx, ry):
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(AWAKE_TOP.lighter(110)))
    path = QPainterPath()
    base_x = -facing * rx * 0.15
    path.moveTo(base_x - rx * 0.16, -ry * 0.92)
    path.quadTo(base_x + facing * rx * 0.55, -ry * 1.5,
                base_x + facing * rx * 0.20, -ry * 1.85)
    path.quadTo(base_x + facing * rx * 0.05, -ry * 1.35,
                base_x + rx * 0.18, -ry * 0.9)
    path.closeSubpath()
    painter.drawPath(path)


def _draw_cheeks(painter, cx, cy, rx, ry, asleep):
    if asleep:
        return
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(CHEEK))
    for sign in (-1, 1):
        painter.drawEllipse(QPointF(cx + sign * rx * 0.62, cy + ry * 0.28),
                            rx * 0.17, rx * 0.12)


def _draw_eyes(painter, left_x, right_x, y, size, look, eye_open, blink, asleep):
    r = size * 0.085
    open_ratio = 0.0 if asleep else max(0.0, eye_open * (1.0 - blink))
    for x in (left_x, right_x):
        if open_ratio <= 0.05:
            painter.setPen(QPen(PUPIL, max(1.5, size * 0.014), Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(QPointF(x - r * 0.8, y), QPointF(x + r * 0.8, y))
            continue
        h = r * open_ratio
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(EYE_WHITE))
        painter.drawEllipse(QPointF(x, y), r, h)
        px = x + look.x() * r * 0.42
        py = y + look.y() * h * 0.42
        pupil_r = min(r * 0.55, h * 0.72)
        painter.setBrush(QBrush(PUPIL))
        painter.drawEllipse(QPointF(px, py), pupil_r, pupil_r)
        painter.setBrush(QBrush(QColor(255, 255, 255, 210)))
        painter.drawEllipse(QPointF(px - pupil_r * 0.3, py - pupil_r * 0.35),
                            pupil_r * 0.32, pupil_r * 0.32)


def _draw_mouth(painter, x, y, size, mouth_open, asleep):
    painter.setPen(QPen(MOUTH, max(1.5, size * 0.013), Qt.SolidLine, Qt.RoundCap))
    painter.setBrush(Qt.NoBrush)
    if asleep:
        w = size * 0.05
        painter.drawLine(QPointF(x - w, y), QPointF(x + w, y))
        return
    open_h = mouth_open * size * 0.07
    if open_h < size * 0.01:
        painter.drawArc(int(x - size * 0.045), int(y - size * 0.03),
                        int(size * 0.09), int(size * 0.06), 200 * 16, 140 * 16)
    else:
        painter.setBrush(QBrush(QColor(120, 60, 70)))
        painter.drawEllipse(QPointF(x, y), size * 0.045, open_h)


def _render_doro(size, state, t, facing, look, transition=None, blink_t=None):
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)

    bob, squash, stretch, tilt, eye_open, mouth_open, blink = _transition_pose(state, t, size, transition, blink_t)
    asleep = state == PetState.SLEEP

    cx = size * 0.5
    cy = size * 0.60 + bob
    rx = size * 0.32 * squash
    ry = size * 0.26 * stretch
    head_y = -ry * 1.15
    head_r = rx * 0.86

    _draw_shadow(p, size, cx, cy + ry, state, t, asleep)
    _draw_doro_legs(p, state, t, cx, cy + ry * 0.92, rx, size, asleep)

    p.save()
    p.translate(cx, cy)
    p.rotate(tilt)

    body = QPainterPath()
    body.addEllipse(QPointF(0.0, 0.0), rx, ry)
    head = QPainterPath()
    head.addEllipse(QPointF(0.0, head_y), head_r, head_r * 0.92)
    shape = body.united(head)

    grad = QLinearGradient(0.0, head_y - head_r, 0.0, ry)
    grad.setColorAt(0.0, DORO_SLEEP_TOP if asleep else DORO_BODY_TOP)
    grad.setColorAt(1.0, DORO_SLEEP_BOTTOM if asleep else DORO_BODY_BOTTOM)
    p.setPen(QPen(DORO_OUTLINE, max(1.0, size * 0.009)))
    p.setBrush(QBrush(grad))
    p.drawPath(shape)

    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(DORO_EAR))
    for sign in (-1, 1):
        p.save()
        p.translate(sign * head_r * 0.56, head_y - head_r * 0.60)
        p.rotate(sign * 24.0)
        p.drawEllipse(QPointF(0.0, 0.0), head_r * 0.26, head_r * 0.42)
        p.restore()

    p.setBrush(QBrush(DORO_BELLY))
    p.drawEllipse(QPointF(0.0, ry * 0.30), rx * 0.55, ry * 0.55)
    p.restore()

    rad = math.radians(tilt)
    hcx = cx - head_y * math.sin(rad)
    hcy = cy + head_y * math.cos(rad)
    _draw_doro_face(p, hcx, hcy, head_r, size, look, eye_open, blink, mouth_open, asleep)

    p.end()
    return pm


def _draw_doro_legs(painter, state, t, cx, by, rx, size, asleep):
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(DORO_SLEEP_BOTTOM if asleep else DORO_BODY_BOTTOM))
    for index, x in enumerate((-0.62, -0.24, 0.24, 0.62)):
        lift = 0.0
        if state == PetState.WALK:
            lift = max(0.0, math.sin(t * 9.0 + index * 1.5)) * size * 0.05
        painter.drawEllipse(QPointF(cx + x * rx, by - lift + size * 0.02),
                           size * 0.058, size * 0.075)


def _draw_doro_face(painter, cx, cy, head_r, size, look, eye_open, blink, mouth_open, asleep):
    eye_dx = head_r * 0.40
    eye_y = cy - head_r * 0.10
    eye_r = size * 0.032
    open_ratio = 0.0 if asleep else max(0.0, eye_open * (1.0 - blink))

    if not asleep:
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(DORO_BLUSH))
        for sign in (-1, 1):
            painter.drawEllipse(QPointF(cx + sign * head_r * 0.64, eye_y + head_r * 0.30),
                                eye_r * 1.8, eye_r * 1.2)

    painter.setBrush(QBrush(DORO_EYE))
    for sign in (-1, 1):
        x = cx + sign * eye_dx
        if open_ratio <= 0.05:
            painter.setPen(QPen(DORO_EYE, max(1.2, size * 0.011), Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(QPointF(x - eye_r, eye_y), QPointF(x + eye_r, eye_y))
            continue
        painter.setPen(Qt.NoPen)
        h = eye_r * open_ratio
        px = x + look.x() * eye_r * 0.35
        py = eye_y + look.y() * h * 0.35
        painter.drawEllipse(QPointF(px, py), eye_r, h)

    painter.setPen(QPen(DORO_MOUTH, max(1.2, size * 0.011), Qt.SolidLine, Qt.RoundCap))
    painter.setBrush(Qt.NoBrush)
    my = eye_y + head_r * 0.44
    if asleep:
        painter.drawLine(QPointF(cx - size * 0.03, my), QPointF(cx + size * 0.03, my))
    elif mouth_open * size < size * 0.012:
        w = size * 0.05
        h = size * 0.045
        painter.drawArc(int(cx - w), int(my - h * 0.4), int(w), int(h), 180 * 16, -180 * 16)
        painter.drawArc(int(cx), int(my - h * 0.4), int(w), int(h), 180 * 16, -180 * 16)
    else:
        painter.setBrush(QBrush(QColor(150, 90, 96)))
        painter.drawEllipse(QPointF(cx, my), size * 0.035, mouth_open * size * 0.06)


def _render_ghost(size, state, t, facing, look, transition=None, blink_t=None):
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)

    bob, squash, stretch, tilt, eye_open, mouth_open, blink = _transition_pose(state, t, size, transition, blink_t)
    asleep = state == PetState.SLEEP

    cx = size * 0.5
    dome_cy = size * 0.44 + bob
    rx = size * 0.29 * squash
    ry = size * 0.30 * stretch
    bottom_y = size * 0.84 + bob
    if state == PetState.FALL:
        bottom_y = size * 0.90 + bob
    elif state == PetState.DRAG:
        bottom_y = size * 0.87 + bob
    amp = rx * 0.24

    glow = QRadialGradient(QPointF(cx, dome_cy + ry * 0.2), max(rx * 1.45, 1.0))
    glow.setColorAt(0.0, GHOST_GLOW)
    glow.setColorAt(1.0, QColor(180, 210, 240, 0))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(glow))
    p.drawEllipse(QPointF(cx, dome_cy + ry * 0.2), rx * 1.45, ry * 1.75)

    path = _ghost_path(cx, dome_cy, rx, ry, bottom_y, t, state, amp)
    grad = QLinearGradient(0.0, dome_cy - ry, 0.0, bottom_y)
    grad.setColorAt(0.0, GHOST_SLEEP_TOP if asleep else GHOST_TOP)
    grad.setColorAt(1.0, GHOST_SLEEP_BOTTOM if asleep else GHOST_BOTTOM)
    p.setPen(QPen(GHOST_OUTLINE, max(1.0, size * 0.008)))
    p.setBrush(QBrush(grad))
    p.drawPath(path)

    _draw_ghost_face(p, cx, dome_cy, rx, ry, size, look,
                     eye_open, blink, mouth_open, asleep)
    p.end()
    return pm


def _ghost_path(cx, dome_cy, rx, ry, bottom_y, t, state, amp):
    path = QPainterPath()
    dome = QRectF(cx - rx, dome_cy - ry, rx * 2.0, ry * 2.0)
    path.moveTo(cx + rx, dome_cy)
    path.arcTo(dome, 0.0, 180.0)
    path.lineTo(cx - rx, bottom_y)

    segments = 4
    seg = (rx * 2.0) / segments
    speed = 8.0 if state == PetState.WALK else 3.2
    for i in range(segments):
        x0 = cx - rx + i * seg
        phase = math.sin(t * speed + i * 1.3)
        dip = bottom_y + amp * (0.45 + 0.55 * phase)
        path.cubicTo(x0 + seg * 0.33, dip, x0 + seg * 0.66, dip, x0 + seg, bottom_y)

    path.lineTo(cx + rx, dome_cy)
    path.closeSubpath()
    return path


def _draw_ghost_face(painter, cx, dome_cy, rx, ry, size, look,
                     eye_open, blink, mouth_open, asleep):
    eye_dx = rx * 0.42
    eye_y = dome_cy - ry * 0.02
    ew = size * 0.040
    eh = size * 0.052
    open_ratio = 0.0 if asleep else max(0.0, eye_open * (1.0 - blink))

    if not asleep:
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(GHOST_BLUSH))
        for sign in (-1, 1):
            painter.drawEllipse(QPointF(cx + sign * rx * 0.66, eye_y + ry * 0.42),
                                ew * 1.5, eh * 0.8)

    for sign in (-1, 1):
        x = cx + sign * eye_dx
        if open_ratio <= 0.05:
            painter.setPen(QPen(GHOST_EYE, max(1.3, size * 0.012), Qt.SolidLine, Qt.RoundCap))
            painter.setBrush(Qt.NoBrush)
            painter.drawArc(int(x - ew), int(eye_y - eh * 0.3),
                            int(ew * 2), int(eh * 1.2), 200 * 16, 140 * 16)
            continue
        painter.setPen(Qt.NoPen)
        h = eh * open_ratio
        painter.setBrush(QBrush(GHOST_EYE))
        painter.drawEllipse(QPointF(x, eye_y), ew, h)
        painter.setBrush(QBrush(QColor(255, 255, 255, 220)))
        painter.drawEllipse(QPointF(x - ew * 0.3 + look.x() * ew * 0.3,
                                    eye_y - h * 0.35 + look.y() * h * 0.3),
                            ew * 0.3, h * 0.3)

    my = eye_y + ry * 0.5
    painter.setPen(QPen(GHOST_MOUTH, max(1.2, size * 0.011), Qt.SolidLine, Qt.RoundCap))
    painter.setBrush(Qt.NoBrush)
    if asleep:
        painter.drawLine(QPointF(cx - size * 0.02, my), QPointF(cx + size * 0.02, my))
    elif mouth_open * size < size * 0.012:
        painter.drawArc(int(cx - size * 0.035), int(my - size * 0.02),
                        int(size * 0.07), int(size * 0.05), 200 * 16, 140 * 16)
    else:
        painter.setBrush(QBrush(QColor(120, 140, 175)))
        painter.drawEllipse(QPointF(cx, my), size * 0.03, mouth_open * size * 0.05)


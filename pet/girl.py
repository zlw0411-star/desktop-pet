import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QLinearGradient, QPainter, QPainterPath,
                           QPen, QPixmap, QRadialGradient)

from .state_machine import PetState
from .animation import _pose

SKIN = QColor(255, 228, 214)
SKIN_SHADE = QColor(244, 201, 182)
HAIR = QColor(236, 168, 198)
HAIR_DARK = QColor(202, 126, 166)
HAIR_LIGHT = QColor(250, 208, 226)
EYE_IRIS = QColor(96, 200, 224)
EYE_IRIS_DARK = QColor(42, 116, 158)
EYE_DARK = QColor(48, 40, 62)
WHITE = QColor(255, 255, 255)
DRESS_TOP = QColor(150, 200, 245)
DRESS_BOTTOM = QColor(96, 150, 214)
DRESS_TRIM = QColor(255, 255, 255, 220)
SHOE = QColor(86, 92, 130)
BLUSH = QColor(255, 150, 170, 120)
MOUTH = QColor(210, 96, 116)
RIBBON = QColor(255, 122, 150)
OUTLINE = QColor(120, 92, 120, 70)


def _render_girl(size, state, t, facing, look, transition=None, blink_t=None):
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)

    from .animation import _transition_pose
    bob, squash, stretch, tilt, eye_open, mouth_open, blink = _transition_pose(
        state, t, size, transition, blink_t)
    if state == PetState.SLEEP:
        bob += size * 0.012
    asleep = state == PetState.SLEEP

    cx = size * 0.5
    base_y = size * 0.60

    _draw_ground_shadow(p, size, cx, state)

    p.save()
    p.translate(cx, base_y)
    p.rotate(tilt * 0.8)
    p.scale(squash, stretch)
    p.translate(-cx, -base_y + bob)

    hcx = size * 0.50
    hcy = size * 0.36
    hrx = size * 0.255
    hry = size * 0.275

    _draw_back_hair(p, hcx, hcy, hrx, hry)
    _draw_twintails(p, size, hcx, hcy, hrx, hry, t, asleep)
    _draw_legs(p, size, cx)
    _draw_body(p, size, hcx, hcy, hry)
    _draw_head(p, hcx, hcy, hrx, hry)
    _draw_side_locks(p, hcx, hcy, hrx, hry)
    _draw_bangs(p, hcx, hcy, hrx, hry)
    _draw_ahoge(p, size, hcx, hcy, hrx, hry, t)
    _draw_ribbon(p, hcx, hcy, hrx, hry)
    _draw_face(p, size, hcx, hcy, hrx, hry, look, eye_open, blink, mouth_open, asleep)
    p.restore()

    p.end()
    return pm


def _draw_ground_shadow(painter, size, cx, state):
    if state in (PetState.DRAG, PetState.FALL):
        return
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(QColor(0, 0, 0, 45)))
    painter.drawEllipse(QPointF(cx, size * 0.955), size * 0.16, size * 0.028)


def _draw_back_hair(painter, hcx, hcy, hrx, hry):
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(HAIR_DARK))
    painter.drawEllipse(QPointF(hcx, hcy + hry * 0.04), hrx * 1.10, hry * 1.06)
    back = QPainterPath()
    back.moveTo(hcx - hrx * 1.0, hcy)
    back.cubicTo(hcx - hrx * 1.12, hcy + hry * 1.0,
                 hcx - hrx * 0.76, hcy + hry * 1.8,
                 hcx, hcy + hry * 1.95)
    back.cubicTo(hcx + hrx * 0.76, hcy + hry * 1.8,
                 hcx + hrx * 1.12, hcy + hry * 1.0,
                 hcx + hrx * 1.0, hcy)
    back.closeSubpath()
    painter.drawPath(back)


def _draw_twintails(painter, size, hcx, hcy, hrx, hry, t, asleep):
    for sign in (-1, 1):
        base_x = hcx + sign * hrx * 0.96
        base_y = hcy - hry * 0.06
        sway = math.sin(t * (1.4 if asleep else 2.4) + (0.0 if sign > 0 else 1.4))
        sway *= size * (0.012 if asleep else 0.030)
        tail = QPainterPath()
        tail.moveTo(base_x, base_y)
        tail.cubicTo(base_x + sign * size * 0.21, base_y + size * 0.03 + sway,
                     base_x + sign * size * 0.20, base_y + size * 0.30 + sway,
                     base_x + sign * size * 0.075, base_y + size * 0.42 + sway)
        tail.cubicTo(base_x + sign * size * 0.03, base_y + size * 0.28 + sway * 0.5,
                     base_x - sign * size * 0.02, base_y + size * 0.12,
                     base_x - sign * size * 0.05, base_y)
        tail.closeSubpath()
        painter.setPen(QPen(OUTLINE, max(0.8, size * 0.005)))
        painter.setBrush(QBrush(HAIR))
        painter.drawPath(tail)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(HAIR_LIGHT))
        painter.drawEllipse(QPointF(base_x + sign * size * 0.055, base_y + size * 0.15 + sway),
                            size * 0.03, size * 0.06)
        painter.setBrush(QBrush(RIBBON))
        painter.drawEllipse(QPointF(base_x, base_y), size * 0.032, size * 0.026)


def _draw_ahoge(painter, size, hcx, hcy, hrx, hry, t):
    sway = math.sin(t * 2.0) * size * 0.012
    ahoge = QPainterPath()
    ahoge.moveTo(hcx - hrx * 0.06, hcy - hry * 1.0)
    ahoge.cubicTo(hcx + hrx * 0.10, hcy - hry * 1.42,
                  hcx + hrx * 0.34 + sway, hcy - hry * 1.52,
                  hcx + hrx * 0.52 + sway, hcy - hry * 1.22)
    ahoge.cubicTo(hcx + hrx * 0.28, hcy - hry * 1.32,
                  hcx + hrx * 0.06, hcy - hry * 1.10,
                  hcx + hrx * 0.02, hcy - hry * 0.98)
    ahoge.closeSubpath()
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(HAIR))
    painter.drawPath(ahoge)


def _draw_legs(painter, size, cx):
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(SKIN))
    for sign in (-1, 1):
        painter.drawRoundedRect(QRectF(cx + sign * size * 0.075 - size * 0.032,
                                       size * 0.855, size * 0.064, size * 0.075),
                                size * 0.03, size * 0.03)
    painter.setBrush(QBrush(SHOE))
    for sign in (-1, 1):
        painter.drawEllipse(QPointF(cx + sign * size * 0.075, size * 0.928),
                            size * 0.042, size * 0.024)


def _draw_body(painter, size, hcx, hcy, hry):
    shoulder_y = hcy + hry * 0.80
    grad = QLinearGradient(0.0, shoulder_y, 0.0, size * 0.86)
    grad.setColorAt(0.0, DRESS_TOP)
    grad.setColorAt(1.0, DRESS_BOTTOM)

    neck = QPainterPath()
    neck.addRoundedRect(QRectF(hcx - size * 0.035, shoulder_y - size * 0.05,
                               size * 0.07, size * 0.08), size * 0.03, size * 0.03)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(SKIN_SHADE))
    painter.drawPath(neck)

    for sign in (-1, 1):
        painter.setBrush(QBrush(SKIN))
        painter.drawEllipse(QPointF(hcx + sign * size * 0.145, shoulder_y + size * 0.075),
                            size * 0.05, size * 0.085)

    dress = QPainterPath()
    dress.moveTo(hcx - size * 0.125, shoulder_y)
    dress.cubicTo(hcx - size * 0.135, shoulder_y + size * 0.09,
                  hcx - size * 0.20, size * 0.79,
                  hcx - size * 0.205, size * 0.86)
    dress.lineTo(hcx + size * 0.205, size * 0.86)
    dress.cubicTo(hcx + size * 0.20, size * 0.79,
                  hcx + size * 0.135, shoulder_y + size * 0.09,
                  hcx + size * 0.125, shoulder_y)
    dress.cubicTo(hcx + size * 0.06, shoulder_y - size * 0.03,
                  hcx - size * 0.06, shoulder_y - size * 0.03,
                  hcx - size * 0.125, shoulder_y)
    dress.closeSubpath()
    painter.setPen(QPen(OUTLINE, max(1.0, size * 0.006)))
    painter.setBrush(QBrush(grad))
    painter.drawPath(dress)

    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(DRESS_TRIM))
    painter.drawEllipse(QPointF(hcx, shoulder_y + size * 0.015), size * 0.045, size * 0.018)
    trim = QPainterPath()
    trim.moveTo(hcx - size * 0.205, size * 0.83)
    trim.cubicTo(hcx - size * 0.10, size * 0.80, hcx + size * 0.10, size * 0.80,
                 hcx + size * 0.205, size * 0.83)
    trim.lineTo(hcx + size * 0.205, size * 0.86)
    trim.lineTo(hcx - size * 0.205, size * 0.86)
    trim.closeSubpath()
    painter.drawPath(trim)


def _draw_head(painter, hcx, hcy, hrx, hry):
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(SKIN))
    painter.drawEllipse(QPointF(hcx, hcy), hrx, hry)


def _draw_side_locks(painter, hcx, hcy, hrx, hry):
    painter.setPen(Qt.NoPen)
    for sign in (-1, 1):
        x = hcx + sign * hrx * 0.94
        lock = QPainterPath()
        lock.moveTo(x, hcy - hry * 0.35)
        lock.cubicTo(x + sign * hrx * 0.16, hcy + hry * 0.6,
                     x + sign * hrx * 0.06, hcy + hry * 1.5,
                     x - sign * hrx * 0.06, hcy + hry * 1.85)
        lock.cubicTo(x - sign * hrx * 0.16, hcy + hry * 1.2,
                     x - sign * hrx * 0.14, hcy + hry * 0.5,
                     x - sign * hrx * 0.04, hcy - hry * 0.35)
        lock.closeSubpath()
        painter.setBrush(QBrush(HAIR))
        painter.drawPath(lock)


def _draw_bangs(painter, hcx, hcy, hrx, hry):
    bangs = QPainterPath()
    bangs.moveTo(hcx - hrx * 1.0, hcy - hry * 0.12)
    bangs.cubicTo(hcx - hrx * 1.04, hcy - hry * 1.16,
                  hcx + hrx * 1.04, hcy - hry * 1.16,
                  hcx + hrx * 1.0, hcy - hry * 0.12)
    bangs.cubicTo(hcx + hrx * 0.66, hcy - hry * 0.02,
                  hcx + hrx * 0.30, hcy - hry * 0.10,
                  hcx + hrx * 0.16, hcy - hry * 0.02)
    bangs.cubicTo(hcx + hrx * 0.04, hcy - hry * 0.16,
                  hcx - hrx * 0.04, hcy - hry * 0.16,
                  hcx - hrx * 0.16, hcy - hry * 0.02)
    bangs.cubicTo(hcx - hrx * 0.30, hcy - hry * 0.10,
                  hcx - hrx * 0.66, hcy - hry * 0.02,
                  hcx - hrx * 1.0, hcy - hry * 0.12)
    bangs.closeSubpath()
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(HAIR))
    painter.drawPath(bangs)

    shine = QPainterPath()
    shine.moveTo(hcx - hrx * 0.62, hcy - hry * 0.60)
    shine.cubicTo(hcx - hrx * 0.30, hcy - hry * 0.90,
                  hcx + hrx * 0.30, hcy - hry * 0.90,
                  hcx + hrx * 0.62, hcy - hry * 0.56)
    shine.cubicTo(hcx + hrx * 0.30, hcy - hry * 0.72,
                  hcx - hrx * 0.30, hcy - hry * 0.72,
                  hcx - hrx * 0.62, hcy - hry * 0.60)
    shine.closeSubpath()
    painter.setBrush(QBrush(HAIR_LIGHT))
    painter.drawPath(shine)


def _draw_ribbon(painter, hcx, hcy, hrx, hry):
    x = hcx - hrx * 0.82
    y = hcy - hry * 0.72
    painter.setPen(QPen(OUTLINE, max(0.8, hrx * 0.03)))
    painter.setBrush(QBrush(RIBBON))
    for sign in (-1, 1):
        path = QPainterPath()
        path.moveTo(x, y)
        path.cubicTo(x + sign * hrx * 0.14, y - hrx * 0.30,
                     x + sign * hrx * 0.46, y - hrx * 0.26,
                     x + sign * hrx * 0.40, y + hrx * 0.02)
        path.cubicTo(x + sign * hrx * 0.32, y + hrx * 0.22,
                     x + sign * hrx * 0.10, y + hrx * 0.14, x, y)
        path.closeSubpath()
        painter.drawPath(path)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(RIBBON.lighter(118)))
    painter.drawEllipse(QPointF(x, y), hrx * 0.12, hrx * 0.12)


def _draw_face(painter, size, hcx, hcy, hrx, hry, look, eye_open, blink, mouth_open, asleep):
    eye_y = hcy + hry * 0.12
    eye_dx = hrx * 0.46
    eye_w = hrx * 0.40
    eye_h = hry * 0.47
    open_ratio = 0.0 if asleep else max(0.0, eye_open * (1.0 - blink))
    ix = look.x() * eye_w * 0.24
    iy = look.y() * eye_h * 0.20

    if not asleep:
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(BLUSH))
        for sign in (-1, 1):
            painter.drawEllipse(QPointF(hcx + sign * hrx * 0.70, eye_y + hry * 0.36),
                                hrx * 0.20, hrx * 0.12)

    for sign in (-1, 1):
        ex = hcx + sign * eye_dx
        if open_ratio <= 0.06:
            painter.setPen(QPen(EYE_DARK, max(1.4, size * 0.016), Qt.SolidLine, Qt.RoundCap))
            painter.setBrush(Qt.NoBrush)
            closed = QPainterPath()
            closed.moveTo(ex - eye_w * 0.9, eye_y)
            closed.quadTo(ex, eye_y + eye_h * 0.7, ex + eye_w * 0.9, eye_y)
            painter.drawPath(closed)
            continue

        painter.save()
        painter.translate(ex, eye_y)
        painter.scale(1.0, open_ratio)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(WHITE))
        painter.drawEllipse(QPointF(0.0, 0.0), eye_w, eye_h)

        iris = QRadialGradient(QPointF(0.0, -eye_h * 0.2), eye_h * 1.1)
        iris.setColorAt(0.0, EYE_IRIS.lighter(125))
        iris.setColorAt(0.7, EYE_IRIS)
        iris.setColorAt(1.0, EYE_IRIS_DARK)
        painter.setBrush(QBrush(iris))
        painter.drawEllipse(QPointF(ix, eye_h * 0.05 + iy), eye_w * 0.74, eye_h * 0.9)

        painter.setBrush(QBrush(EYE_DARK))
        painter.drawEllipse(QPointF(ix, eye_h * 0.05 + iy), eye_w * 0.34, eye_h * 0.48)

        painter.setBrush(QBrush(WHITE))
        painter.drawEllipse(QPointF(ix - eye_w * 0.24, iy - eye_h * 0.36),
                            eye_w * 0.30, eye_h * 0.30)
        painter.drawEllipse(QPointF(ix + eye_w * 0.24, iy + eye_h * 0.34),
                            eye_w * 0.14, eye_h * 0.16)
        painter.restore()

        painter.setPen(QPen(EYE_DARK, max(1.6, size * 0.018), Qt.SolidLine, Qt.RoundCap))
        painter.setBrush(Qt.NoBrush)
        painter.drawArc(QRectF(ex - eye_w * 1.02, eye_y - eye_h * 1.05,
                               eye_w * 2.04, eye_h * 2.0), 25 * 16, 130 * 16)

    painter.setPen(QPen(HAIR_DARK, max(1.2, size * 0.010), Qt.SolidLine, Qt.RoundCap))
    painter.setBrush(Qt.NoBrush)
    for sign in (-1, 1):
        ex = hcx + sign * eye_dx
        brow = QPainterPath()
        brow.moveTo(ex - eye_w * 0.7, eye_y - eye_h * 1.35)
        brow.quadTo(ex, eye_y - eye_h * 1.62, ex + eye_w * 0.7, eye_y - eye_h * 1.35)
        painter.drawPath(brow)

    my = hcy + hry * 0.66
    painter.setPen(QPen(MOUTH, max(1.2, size * 0.012), Qt.SolidLine, Qt.RoundCap))
    painter.setBrush(Qt.NoBrush)
    if asleep:
        painter.drawLine(QPointF(hcx - size * 0.018, my), QPointF(hcx + size * 0.018, my))
    elif mouth_open * size < size * 0.012:
        smile = QPainterPath()
        smile.moveTo(hcx - size * 0.022, my)
        smile.quadTo(hcx, my + size * 0.028, hcx + size * 0.022, my)
        painter.drawPath(smile)
    else:
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(MOUTH))
        painter.drawEllipse(QPointF(hcx, my + size * 0.006),
                            size * 0.020, mouth_open * size * 0.034)

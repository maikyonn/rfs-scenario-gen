"""Inline vehicle, pedestrian, and misc-object entity definitions."""

from scenariogeneration import xosc

# ── Helpers ──────────────────────────────────────────────────────────────────

def _bb(w, l, h, cx, cy, cz):
    return xosc.BoundingBox(w, l, h, cx, cy, cz)

def _axle(maxsteer, dia, track, xpos, zpos):
    return xosc.Axle(maxsteer, dia, track, xpos, zpos)

# ── Vehicles ─────────────────────────────────────────────────────────────────

def sedan():
    return xosc.Vehicle(
        "sedan",
        xosc.VehicleCategory.car,
        _bb(1.8, 4.5, 1.5, 1.4, 0.0, 0.75),
        _axle(0.5, 0.6, 1.68, 2.98, 0.3),
        _axle(0.0, 0.6, 1.68, 0.0, 0.3),
        max_speed=70,
        max_acceleration=10,
        max_deceleration=10,
    )

def suv():
    return xosc.Vehicle(
        "suv",
        xosc.VehicleCategory.car,
        _bb(2.0, 4.9, 1.8, 1.5, 0.0, 0.9),
        _axle(0.5, 0.7, 1.8, 3.1, 0.35),
        _axle(0.0, 0.7, 1.8, 0.0, 0.35),
        max_speed=65,
        max_acceleration=8,
        max_deceleration=10,
    )

def pickup():
    return xosc.Vehicle(
        "pickup",
        xosc.VehicleCategory.car,
        _bb(2.0, 5.4, 1.85, 1.6, 0.0, 0.93),
        _axle(0.5, 0.75, 1.8, 3.4, 0.38),
        _axle(0.0, 0.75, 1.8, 0.0, 0.38),
        max_speed=60,
        max_acceleration=7,
        max_deceleration=10,
    )

def motorcycle():
    return xosc.Vehicle(
        "motorcycle",
        xosc.VehicleCategory.motorbike,
        _bb(0.8, 2.2, 1.5, 0.7, 0.0, 0.75),
        _axle(0.6, 0.6, 0.4, 1.5, 0.3),
        _axle(0.0, 0.6, 0.4, 0.0, 0.3),
        max_speed=80,
        max_acceleration=12,
        max_deceleration=10,
    )

def bicycle():
    return xosc.Vehicle(
        "bicycle",
        xosc.VehicleCategory.bicycle,
        _bb(0.6, 1.8, 1.6, 0.5, 0.0, 0.8),
        _axle(0.5, 0.6, 0.4, 1.1, 0.3),
        _axle(0.0, 0.6, 0.4, 0.0, 0.3),
        max_speed=15,
        max_acceleration=3,
        max_deceleration=5,
    )

# ── Pedestrian ───────────────────────────────────────────────────────────────

def pedestrian():
    return xosc.Pedestrian(
        "pedestrian",
        mass=75,
        category=xosc.PedestrianCategory.pedestrian,
        boundingbox=_bb(0.5, 0.3, 1.75, 0.0, 0.0, 0.88),
        model="EPTa",
    )

# ── Misc objects ─────────────────────────────────────────────────────────────

def road_debris():
    return xosc.MiscObject(
        "debris",
        mass=50,
        category=xosc.MiscObjectCategory.obstacle,
        boundingbox=_bb(0.8, 1.0, 0.4, 0.0, 0.0, 0.2),
    )

def parked_car_door():
    """Stationary obstacle representing an open car door."""
    return xosc.MiscObject(
        "open_door",
        mass=20,
        category=xosc.MiscObjectCategory.obstacle,
        boundingbox=_bb(1.0, 0.1, 1.2, 0.0, 0.0, 0.6),
    )

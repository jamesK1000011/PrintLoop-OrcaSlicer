# SPDX-License-Identifier: AGPL-3.0-only
"""Per-layer extrusion regions behind one small interface.

The real backend is shapely (>= 2, GEOS). When shapely is not installed,
a pure-Python fallback gives the same answers by sampling (step
geom.sample_mm, 0.1 mm). The fallback is for tests and small files; the
performance target (§16.4) is for the shapely backend.

A region is the union of extrusion segments, each buffered by w/2 with
flat caps. Operations: outside(x0, y0, x1, y1) gives the length of a
segment outside the region and the midpoint of that part; ribbon_outside
gives the fraction of a segment's own ribbon outside the region; grow(d)
buffers the region; area; contains; distance.
"""
import math

try:  # pragma: no cover - depends on the machine
    import shapely
    from shapely.geometry import LineString, Point, Polygon
    from shapely.ops import unary_union

    HAVE_SHAPELY = int(shapely.__version__.split(".")[0]) >= 2
except Exception:  # noqa: BLE001
    HAVE_SHAPELY = False

BACKEND = "shapely" if HAVE_SHAPELY else "python"
_FORCE = None


def use(backend):
    """Force a backend ("shapely", "python") or None for the best one."""
    global _FORCE
    if backend == "shapely" and not HAVE_SHAPELY:
        raise RuntimeError("shapely >= 2 is not installed")
    _FORCE = backend


def backend():
    return _FORCE or BACKEND


def region(segs, sample=0.1):
    """segs: [(x0, y0, x1, y1, w)] -> a Region."""
    if backend() == "shapely":
        return _ShapelyRegion.from_segs(segs)
    return _PyRegion([(x0, y0, x1, y1, w / 2.0, 0.0) for x0, y0, x1, y1, w in segs if (x1 - x0) or (y1 - y0)], sample)


def filled(segs, loops_, sample=0.1):
    """The extrusion region plus the inside of the outer-wall loops (even-odd,
    so a hole stays a hole): the part's cross-section, with sparse infill
    counted as inside the part."""
    loops_ = [lp for lp in loops_ if len(lp) >= 3]
    if backend() == "shapely":  # pragma: no cover - needs shapely
        base = _ShapelyRegion.from_segs(segs).g
        sec = Polygon()
        for lp in loops_:
            pg = Polygon(lp).buffer(0)
            sec = sec.symmetric_difference(pg)
        return _ShapelyRegion(unary_union([base, sec]))
    r = region(segs, sample)
    if loops_:
        r.polys = [(lp, (min(p[0] for p in lp), min(p[1] for p in lp), max(p[0] for p in lp), max(p[1] for p in lp))) for lp in loops_]
    return r


def _in_poly(x, y, pts):
    inside = False
    n = len(pts)
    j = n - 1
    for i in range(n):
        xi, yi = pts[i]
        xj, yj = pts[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def union(regions, sample=0.1):
    regions = [r for r in regions if r is not None]
    if backend() == "shapely":
        return _ShapelyRegion(unary_union([r.g for r in regions]) if regions else Polygon())
    els = []
    for r in regions:
        els += r.els
    return _PyRegion(els, sample)


# -- pure Python ---------------------------------------------------------------------------
class _PyRegion:
    CELL = 2.0

    polys = ()

    def __init__(self, els, sample=0.1):
        # Element: a segment (x0, y0, x1, y1), half width hw, end extension ext.
        self.els = els
        self.sample = sample
        self.grid = {}
        for i, (x0, y0, x1, y1, hw, ext) in enumerate(els):
            r = hw + ext
            for cx in range(int(math.floor((min(x0, x1) - r) / self.CELL)), int(math.floor((max(x0, x1) + r) / self.CELL)) + 1):
                for cy in range(int(math.floor((min(y0, y1) - r) / self.CELL)), int(math.floor((max(y0, y1) + r) / self.CELL)) + 1):
                    self.grid.setdefault((cx, cy), []).append(i)

    @staticmethod
    def _inside_el(el, x, y):
        x0, y0, x1, y1, hw, ext = el
        dx, dy = x1 - x0, y1 - y0
        L = math.hypot(dx, dy)
        if L < 1e-12:
            return False
        ux, uy = dx / L, dy / L
        px, py = x - x0, y - y0
        t = px * ux + py * uy
        if t < -ext - 1e-9 or t > L + ext + 1e-9:
            return False
        return abs(px * uy - py * ux) <= hw + 1e-9

    def contains(self, x, y):
        for i in self.grid.get((int(math.floor(x / self.CELL)), int(math.floor(y / self.CELL))), ()):
            if self._inside_el(self.els[i], x, y):
                return True
        if self.polys:
            inside = False
            for pts, b in self.polys:
                if b[0] <= x <= b[2] and b[1] <= y <= b[3] and _in_poly(x, y, pts):
                    inside = not inside
            return inside
        return False

    def _samples(self, x0, y0, x1, y1):
        L = math.hypot(x1 - x0, y1 - y0)
        n = max(1, int(math.ceil(L / self.sample)))
        return L, n, [((k + 0.5) / n) for k in range(n)]

    def outside(self, x0, y0, x1, y1):
        L, n, ts = self._samples(x0, y0, x1, y1)
        if L < 1e-12:
            return 0.0, None
        out = [t for t in ts if not self.contains(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t)]
        if not out:
            return 0.0, None
        # The midpoint of the longest outside run.
        runs, run = [], [out[0]]
        step = 1.0 / n
        for t in out[1:]:
            if t - run[-1] <= step * 1.5:
                run.append(t)
            else:
                runs.append(run)
                run = [t]
        runs.append(run)
        best = max(runs, key=len)
        tm = (best[0] + best[-1]) / 2.0
        return L * len(out) / n, (x0 + (x1 - x0) * tm, y0 + (y1 - y0) * tm)

    def ribbon_outside(self, x0, y0, x1, y1, w):
        L, n, ts = self._samples(x0, y0, x1, y1)
        if L < 1e-12:
            return 0.0
        nx, ny = -(y1 - y0) / L, (x1 - x0) / L
        offs = [w * (k / 6.0 - 0.5) for k in range(7)]
        tot = out = 0
        for t in ts:
            cx, cy = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
            for o in offs:
                tot += 1
                if not self.contains(cx + nx * o, cy + ny * o):
                    out += 1
        return out / tot

    def grow(self, d):
        r = _PyRegion([(x0, y0, x1, y1, hw + d, ext + d) for x0, y0, x1, y1, hw, ext in self.els], self.sample)
        r.polys = self.polys
        return r

    def bounds(self):
        if not self.els:
            return None
        xs = [v for e in self.els for v in (e[0] - e[4] - e[5], e[2] - e[4] - e[5], e[0] + e[4] + e[5], e[2] + e[4] + e[5])]
        ys = [v for e in self.els for v in (e[1] - e[4] - e[5], e[3] - e[4] - e[5], e[1] + e[4] + e[5], e[3] + e[4] + e[5])]
        return min(xs), min(ys), max(xs), max(ys)

    def area(self, cell=None):
        b = self.bounds()
        if b is None:
            return 0.0
        c = cell or max(self.sample, 0.1)
        nx, ny = int(math.ceil((b[2] - b[0]) / c)), int(math.ceil((b[3] - b[1]) / c))
        hit = 0
        for i in range(nx):
            x = b[0] + (i + 0.5) * c
            for j in range(ny):
                if self.contains(x, b[1] + (j + 0.5) * c):
                    hit += 1
        return hit * c * c

    def distance(self, x, y, limit=10.0):
        if self.contains(x, y):
            return 0.0
        best = limit
        r = int(math.ceil(limit / self.CELL))
        cx0, cy0 = int(math.floor(x / self.CELL)), int(math.floor(y / self.CELL))
        seen = set()
        for cx in range(cx0 - r, cx0 + r + 1):
            for cy in range(cy0 - r, cy0 + r + 1):
                for i in self.grid.get((cx, cy), ()):
                    if i in seen:
                        continue
                    seen.add(i)
                    x0, y0, x1, y1, hw, ext = self.els[i]
                    d = _seg_dist(x, y, x0, y0, x1, y1) - hw
                    best = min(best, max(0.0, d))
        return best


def _seg_dist(x, y, x0, y0, x1, y1):
    dx, dy = x1 - x0, y1 - y0
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 < 1e-18 else max(0.0, min(1.0, ((x - x0) * dx + (y - y0) * dy) / L2))
    return math.hypot(x - (x0 + t * dx), y - (y0 + t * dy))


# -- shapely --------------------------------------------------------------------------------
class _ShapelyRegion:  # pragma: no cover - runs where shapely is installed
    def __init__(self, g):
        self.g = g
        shapely.prepare(self.g)

    @classmethod
    def from_segs(cls, segs):
        polys = [LineString([(x0, y0), (x1, y1)]).buffer(w / 2.0, cap_style="flat") for x0, y0, x1, y1, w in segs if (x1 - x0) or (y1 - y0)]
        return cls(unary_union(polys) if polys else Polygon())

    def contains(self, x, y):
        return self.g.covers(Point(x, y))

    def outside(self, x0, y0, x1, y1):
        ln = LineString([(x0, y0), (x1, y1)])
        if ln.length < 1e-12:
            return 0.0, None
        d = ln.difference(self.g)
        if d.is_empty or d.length < 1e-9:
            return 0.0, None
        parts = list(getattr(d, "geoms", [d]))
        best = max(parts, key=lambda p: p.length)
        m = best.interpolate(0.5, normalized=True)
        return d.length, (m.x, m.y)

    def ribbon_outside(self, x0, y0, x1, y1, w):
        rb = LineString([(x0, y0), (x1, y1)]).buffer(w / 2.0, cap_style="flat")
        if rb.area < 1e-12:
            return 0.0
        return rb.difference(self.g).area / rb.area

    def grow(self, d):
        return _ShapelyRegion(self.g.buffer(d, join_style="mitre"))

    def area(self, cell=None):
        return self.g.area

    def bounds(self):
        return None if self.g.is_empty else self.g.bounds

    def distance(self, x, y, limit=10.0):
        return min(limit, self.g.distance(Point(x, y)))

    def exterior(self):
        g = self.g.buffer(0.3, join_style="mitre").buffer(-0.3, join_style="mitre").simplify(0.2)
        polys = list(getattr(g, "geoms", [g]))
        if not polys or g.is_empty:
            return []
        return list(max(polys, key=lambda p: p.area).exterior.coords)[:-1]


# -- corners --------------------------------------------------------------------------------
def acute_corners(points, limit_deg):
    """Convex corners of a closed polygon (points, no repeat of the first)
    with an interior angle under limit_deg."""
    n = len(points)
    if n < 3:
        return 0
    area2 = sum(points[i][0] * points[(i + 1) % n][1] - points[(i + 1) % n][0] * points[i][1] for i in range(n))
    sign = 1 if area2 > 0 else -1
    count = 0
    for i in range(n):
        ax, ay = points[i - 1]
        bx, by = points[i]
        cx, cy = points[(i + 1) % n]
        v1, v2 = (ax - bx, ay - by), (cx - bx, cy - by)
        l1, l2 = math.hypot(*v1), math.hypot(*v2)
        if l1 < 1e-9 or l2 < 1e-9:
            continue
        cross = (bx - ax) * (cy - by) - (by - ay) * (cx - bx)
        if cross * sign <= 0:
            continue  # concave or straight
        ang = math.degrees(math.acos(max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (l1 * l2)))))
        if ang < limit_deg - 0.5:
            count += 1
    return count


def simplify(points, tol):
    """Douglas-Peucker on a closed loop."""
    if len(points) < 4:
        return points

    def dp(pts):
        if len(pts) < 3:
            return pts
        a, b = pts[0], pts[-1]
        idx, dmax = 0, -1.0
        for i in range(1, len(pts) - 1):
            d = _seg_dist(pts[i][0], pts[i][1], a[0], a[1], b[0], b[1])
            if d > dmax:
                idx, dmax = i, d
        if dmax <= tol:
            return [a, b]
        return dp(pts[: idx + 1])[:-1] + dp(pts[idx:])

    # Split at the point farthest from the first, so the loop has two ends.
    far = max(range(len(points)), key=lambda i: math.hypot(points[i][0] - points[0][0], points[i][1] - points[0][1]))
    first = dp(points[: far + 1])
    second = dp(points[far:] + [points[0]])
    return first[:-1] + second[:-1]


def loops(segs, tol=0.05, close_tol=1.0):
    """Chain segments [(x0, y0, x1, y1)] into closed loops (point lists).
    A loop closes when its end comes within close_tol of its start (the
    seam gap)."""
    out, cur = [], []
    for x0, y0, x1, y1 in segs:
        if cur and math.hypot(cur[-1][0] - x0, cur[-1][1] - y0) <= tol:
            cur.append((x1, y1))
        else:
            if len(cur) >= 4:
                out.append(cur)
            cur = [(x0, y0), (x1, y1)]
        if len(cur) >= 4 and math.hypot(cur[-1][0] - cur[0][0], cur[-1][1] - cur[0][1]) <= max(tol, close_tol) and _loop_span(cur) > 2 * close_tol:
            out.append(cur[:-1] if math.hypot(cur[-1][0] - cur[0][0], cur[-1][1] - cur[0][1]) <= tol else cur)
            cur = []
    if len(cur) >= 4 and math.hypot(cur[-1][0] - cur[0][0], cur[-1][1] - cur[0][1]) <= max(tol, close_tol):
        out.append(cur)
    return out


def _loop_span(pts):
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return max(max(xs) - min(xs), max(ys) - min(ys))


def polygon_area(points):
    n = len(points)
    return abs(sum(points[i][0] * points[(i + 1) % n][1] - points[(i + 1) % n][0] * points[i][1] for i in range(n))) / 2.0

"""Renders one camera's view of the scene.

Pipeline per frame:
1. board plane: cached perspective warp of the board texture (supersampled), ideal pixels
2. shadows of darts/occluders projected along the light direction onto the board
3. darts and occluders rasterised as shaded 3D primitives (painter's algorithm, 2x
   supersampled inside their bounding box)
4. illumination (gain, gradient over the board, tint, per-frame flicker)
5. lens distortion (remap ideal → distorted pixels)
6. sensor noise and optional JPEG compression (most USB cameras stream MJPEG)
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np

from vision.geometry.board import BoardGeometry
from vision.imaging import linear_to_srgb, srgb_to_linear
from vision.geometry.camera_model import CameraModel
from vision.simulation.board_texture import BoardTexture
from vision.simulation.scene import (
    Capsule,
    DartInstance,
    Lighting,
    Occluder,
    Sphere,
    perpendicular_basis,
)

_SS = 2  # supersampling factor for the board warp and the dart layer


@dataclass
class _Poly:
    depth: float
    pts: np.ndarray  # (N,2) ideal pixels at supersampled scale
    color: tuple[float, float, float]


@dataclass
class RenderOptions:
    noise_sigma: float = 1.8
    jpeg_quality: int | None = 88
    flicker: float = 0.004


class CameraRenderer:
    def __init__(self, camera: CameraModel, board: BoardGeometry, texture: BoardTexture,
                 options: RenderOptions | None = None, seed: int = 0) -> None:
        self.camera = camera
        self.board = board
        self.texture = texture
        self.options = options or RenderOptions()
        self.rng = np.random.default_rng(seed)
        w, h = camera.image_size
        self.size = (w, h)
        self._cam_ss = camera.scaled(_SS)
        self._board_xy, self._plane_valid = self._board_coordinates()
        self._background = self._render_background()
        self._map_x, self._map_y = self._distortion_maps()
        self._noise_bank = self.rng.normal(0.0, 1.0, (h + 64, w + 64, 3)).astype(np.float32)

    # ------------------------------------------------------------------ static parts
    def _render_background(self) -> np.ndarray:
        """Board plane in *ideal* (undistorted) pixels, float32 BGR."""
        w, h = self.size
        H_board_to_px = self._cam_ss.homography()
        H_tex_to_board = np.linalg.inv(self.texture.board_to_texture())
        H = H_board_to_px @ H_tex_to_board
        wall = tuple(float(v) for v in srgb_to_linear(np.array([150, 160, 168])) * 255.0)
        big = cv2.warpPerspective(self.texture.linear, H, (w * _SS, h * _SS), flags=cv2.INTER_LINEAR,
                                  borderMode=cv2.BORDER_CONSTANT, borderValue=wall)
        small = cv2.resize(big, (w, h), interpolation=cv2.INTER_AREA).astype(np.float32)
        # Rays that never reach the wall plane (above the horizon) see the room instead;
        # without this the homography would wrap around and paint the board there.
        room = srgb_to_linear(np.linspace(95, 70, h))[:, None, None] * 255.0 * np.ones((1, w, 3), np.float32)
        invalid = ~self._plane_valid
        small[invalid] = room[invalid]
        return small

    def _board_coordinates(self) -> tuple[np.ndarray, np.ndarray]:
        """Board-plane xy for every ideal pixel and whether the pixel's ray hits the plane
        in front of the camera (within 3 m)."""
        w, h = self.size
        xs, ys = np.meshgrid(np.arange(w, dtype=np.float64), np.arange(h, dtype=np.float64))
        Kinv = np.linalg.inv(self.camera.K)
        rays = np.stack([xs, ys, np.ones_like(xs)], axis=-1) @ Kinv.T @ self.camera.R  # board frame
        c = self.camera.center
        with np.errstate(divide="ignore", invalid="ignore"):
            s = -c[2] / rays[..., 2]
        valid = (rays[..., 2] < 0) & (s * np.linalg.norm(rays, axis=-1) < 3000.0)
        xy = c[None, None, :2] + s[..., None] * rays[..., :2]
        xy[~valid] = 1e4
        return xy.astype(np.float32), valid

    def _distortion_maps(self) -> tuple[np.ndarray, np.ndarray]:
        w, h = self.size
        if not np.any(self.camera.dist):
            return None, None  # type: ignore[return-value]
        xs, ys = np.meshgrid(np.arange(w, dtype=np.float64), np.arange(h, dtype=np.float64))
        grid = np.stack([xs.ravel(), ys.ravel()], axis=1)
        ideal = self.camera.undistort_pixels(grid)
        return (ideal[:, 0].reshape(h, w).astype(np.float32),
                ideal[:, 1].reshape(h, w).astype(np.float32))

    # ------------------------------------------------------------------ frame
    def render(self, darts: list[DartInstance], occluders: list[Occluder] | None = None,
               lighting: Lighting | None = None) -> np.ndarray:
        lighting = lighting or Lighting()
        occluders = occluders or []
        img = self._background.copy()

        shadow = self._shadow_mask(darts, occluders, lighting)
        if shadow is not None:
            img *= (1.0 - lighting.shadow_strength * shadow)[..., None]

        img = self._illuminate(img, lighting)

        polys: list[_Poly] = []
        for dart in darts:
            poses = [(dart.surface_point(), dart.axis)] + [
                (np.append(p, 0.0) if len(p) == 2 else p, a) for p, a in dart.blur_poses
            ]
            if len(poses) == 1:
                polys.extend(self._dart_polys(dart, poses[0][0], poses[0][1], lighting))
            else:
                img = self._composite_blurred(img, dart, poses, lighting)
        for occ in occluders:
            polys.extend(self._occluder_polys(occ, lighting))
        if polys:
            img = self._composite(img, polys, lighting.gain)

        flicker = 1.0 + self.rng.normal(0.0, self.options.flicker)
        img *= flicker

        if self._map_x is not None:
            img = cv2.remap(img, self._map_x, self._map_y, cv2.INTER_LINEAR,
                            borderMode=cv2.BORDER_REPLICATE)
        img = linear_to_srgb(img / 255.0)
        img = self._add_noise(img)
        out = np.clip(img, 0, 255).astype(np.uint8)
        if self.options.jpeg_quality:
            ok, buf = cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, self.options.jpeg_quality])
            if ok:
                out = cv2.imdecode(buf, cv2.IMREAD_COLOR)
        return out

    def _illuminate(self, img: np.ndarray, lighting: Lighting) -> np.ndarray:
        gx, gy = lighting.gradient
        if gx or gy:
            field = 1.0 + gx * self._board_xy[..., 0] / 200.0 + gy * self._board_xy[..., 1] / 200.0
            field = np.clip(field, 0.3, 2.0)
            img = img * field[..., None]
        tint = np.array(lighting.tint, dtype=np.float32) * lighting.gain
        return img * tint[None, None, :]

    def _add_noise(self, img: np.ndarray) -> np.ndarray:
        h, w = img.shape[:2]
        oy, ox = self.rng.integers(0, 64, size=2)
        noise = self._noise_bank[oy:oy + h, ox:ox + w]
        # Read noise + shot noise (variance grows with intensity).
        sigma = self.options.noise_sigma * (0.7 + 0.3 * np.sqrt(np.clip(img, 0, 255) / 64.0))
        return img + noise * sigma

    # ------------------------------------------------------------------ geometry → polygons
    def _project_ss(self, pts: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Ideal (undistorted) pixel projection at supersampled scale + camera depth."""
        cam_pts = self.camera.to_camera(pts)
        z = cam_pts[:, 2]
        uv = cam_pts[:, :2] / np.maximum(z, 1e-6)[:, None]
        px = uv @ self._cam_ss.K[:2, :2].T + self._cam_ss.K[:2, 2]
        return px, z

    def _shade(self, base: tuple[int, int, int], normal: np.ndarray, view: np.ndarray,
               lighting: Lighting, specular: float = 0.0) -> tuple[float, float, float]:
        n = normal / (np.linalg.norm(normal) + 1e-12)
        L = lighting.direction
        base = tuple(float(c) for c in srgb_to_linear(np.array(base, dtype=np.float32)) * 255.0)
        diff = max(0.0, float(n @ L))
        intensity = lighting.ambient + lighting.diffuse * diff
        spec = 0.0
        if specular > 0:
            refl = 2 * (n @ L) * n - L
            spec = specular * max(0.0, float(refl @ view)) ** 12 * 255
        return tuple(min(255.0, c * intensity + spec * 0.6) for c in base)  # type: ignore[return-value]

    def _cylinder_polys(self, p0: np.ndarray, p1: np.ndarray, r0: float, r1: float,
                        color: tuple[int, int, int], lighting: Lighting, specular: float = 0.0,
                        strips: int = 5) -> list[_Poly]:
        axis = p1 - p0
        length = np.linalg.norm(axis)
        if length < 1e-6:
            return []
        a = axis / length
        mid = (p0 + p1) / 2
        view = self.camera.center - mid
        view /= np.linalg.norm(view)
        side = np.cross(a, view)
        if np.linalg.norm(side) < 1e-6:
            return []
        side /= np.linalg.norm(side)
        facing = np.cross(side, a)  # towards the camera, perpendicular to the axis
        polys: list[_Poly] = []
        us = np.linspace(-1.0, 1.0, strips + 1)
        for k in range(strips):
            u0, u1 = us[k], us[k + 1]
            uc = (u0 + u1) / 2
            normal = uc * side + math.sqrt(max(0.0, 1 - uc * uc)) * facing
            col = self._shade(color, normal, view, lighting, specular)
            quad3 = np.array([
                p0 + side * r0 * u0, p1 + side * r1 * u0,
                p1 + side * r1 * u1, p0 + side * r0 * u1,
            ])
            px, z = self._project_ss(quad3)
            if np.any(z <= 1.0):
                continue
            polys.append(_Poly(depth=float(z.mean()), pts=px, color=col))
        return polys

    def _dart_polys(self, dart: DartInstance, start: np.ndarray, axis: np.ndarray,
                    lighting: Lighting) -> list[_Poly]:
        s = dart.style
        a = axis / np.linalg.norm(axis)
        polys: list[_Poly] = []
        pos = 0.0
        vis_point = dart.visible_point_length() if dart.tip_position is None else s.point_length
        frac_hidden = 1.0 - vis_point / s.point_length
        r_start = max(0.25, s.point_radius * (0.35 + 0.65 * frac_hidden))
        # Point (steel cone).
        p0 = start
        p1 = start + a * vis_point
        polys += self._cylinder_polys(p0, p1, r_start, s.point_radius, (175, 175, 180), lighting, 0.6, 3)
        pos = vis_point
        # Barrel with knurl bands and tapered ends.
        n_b = max(3, s.barrel_knurl_bands)
        band_len = s.barrel_length / n_b
        for k in range(n_b):
            b0 = start + a * (pos + k * band_len)
            b1 = start + a * (pos + (k + 1) * band_len)
            t0 = k / n_b
            t1 = (k + 1) / n_b
            r0 = s.barrel_radius * _barrel_profile(t0)
            r1 = s.barrel_radius * _barrel_profile(t1)
            shade = 1.0 if k % 2 == 0 else 0.78
            col = tuple(int(c * shade) for c in s.barrel_color)
            polys += self._cylinder_polys(b0, b1, r0, r1, col, lighting, s.specular)
        pos += s.barrel_length
        # Shaft.
        polys += self._cylinder_polys(start + a * pos, start + a * (pos + s.shaft_length),
                                      s.shaft_radius * 0.9, s.shaft_radius, s.shaft_color, lighting, 0.3)
        pos += s.shaft_length
        # Flight: four wings.
        f0 = pos - s.flight_overlap
        e1, e2 = perpendicular_basis(a)
        roll = math.radians(dart.roll_deg)
        for k in range(4):
            ang = roll + k * math.pi / 2
            radial = math.cos(ang) * e1 + math.sin(ang) * e2
            normal = np.cross(a, radial)
            outline = [(0.0, 0.08), (0.35, 1.0), (1.0, 1.0), (1.0, 0.0)]
            pts3 = np.array([start + a * (f0 + u * s.flight_length) + radial * (v * s.flight_span)
                             for u, v in outline])
            view = self.camera.center - pts3.mean(0)
            view /= np.linalg.norm(view)
            n = normal if normal @ view > 0 else -normal
            col = self._shade(s.flight_color, n, view, lighting)
            px, z = self._project_ss(pts3)
            if np.all(z > 1.0):
                polys.append(_Poly(depth=float(z.mean()), pts=px, color=col))
            if s.flight_pattern_color is not None:
                stripe = [(0.55, 0.0), (0.55, 0.95), (0.7, 0.95), (0.7, 0.0)]
                pts3s = np.array([start + a * (f0 + u * s.flight_length) + radial * (v * s.flight_span)
                                  for u, v in stripe])
                pc = self._shade(s.flight_pattern_color, n, view, lighting)
                pxs, zs = self._project_ss(pts3s)
                if np.all(zs > 1.0):
                    polys.append(_Poly(depth=float(z.mean()) - 0.01, pts=pxs, color=pc))
        return polys

    def _occluder_polys(self, occ: Occluder, lighting: Lighting) -> list[_Poly]:
        polys: list[_Poly] = []
        for cap in occ.capsules:
            polys += self._cylinder_polys(np.asarray(cap.p0, float), np.asarray(cap.p1, float),
                                          cap.radius, cap.radius, cap.color, lighting, 0.0, 4)
            polys += self._sphere_polys(Sphere(np.asarray(cap.p1, float), cap.radius, cap.color), lighting)
        for sph in occ.spheres:
            polys += self._sphere_polys(sph, lighting)
        return polys

    def _sphere_polys(self, sph: Sphere, lighting: Lighting) -> list[_Poly]:
        c = np.asarray(sph.center, float)
        view = self.camera.center - c
        dist = np.linalg.norm(view)
        view /= dist
        e1, e2 = perpendicular_basis(view)
        angles = np.linspace(0, 2 * np.pi, 24, endpoint=False)
        rim = np.array([c + sph.radius * (math.cos(t) * e1 + math.sin(t) * e2) for t in angles])
        px, z = self._project_ss(rim)
        if np.any(z <= 1.0):
            return []
        col = self._shade(sph.color, view, view, lighting)
        return [_Poly(depth=float(z.mean()), pts=px, color=col)]

    # ------------------------------------------------------------------ compositing
    def _rasterize(self, polys: list[_Poly]) -> tuple[np.ndarray, np.ndarray, tuple[int, int]] | None:
        """Draw polygons (far→near) into a supersampled crop. Returns (premultiplied colour,
        alpha, (x0, y0) of the crop at 1x scale)."""
        w, h = self.size
        all_pts = np.concatenate([p.pts for p in polys])
        x0 = int(max(0, math.floor(all_pts[:, 0].min() / _SS) - 2))
        y0 = int(max(0, math.floor(all_pts[:, 1].min() / _SS) - 2))
        x1 = int(min(w, math.ceil(all_pts[:, 0].max() / _SS) + 2))
        y1 = int(min(h, math.ceil(all_pts[:, 1].max() / _SS) + 2))
        if x1 <= x0 or y1 <= y0:
            return None
        cw, ch = (x1 - x0) * _SS, (y1 - y0) * _SS
        color = np.zeros((ch, cw, 3), dtype=np.float32)
        alpha = np.zeros((ch, cw), dtype=np.float32)
        offset = np.array([x0 * _SS, y0 * _SS], dtype=np.float64)
        shift = 4
        for poly in sorted(polys, key=lambda p: -p.depth):
            pts = np.round((poly.pts - offset) * (1 << shift)).astype(np.int32)
            cv2.fillPoly(color, [pts], poly.color, lineType=cv2.LINE_AA, shift=shift)
            cv2.fillPoly(alpha, [pts], 1.0, lineType=cv2.LINE_AA, shift=shift)
        color = cv2.resize(color, (x1 - x0, y1 - y0), interpolation=cv2.INTER_AREA)
        alpha = cv2.resize(alpha, (x1 - x0, y1 - y0), interpolation=cv2.INTER_AREA)
        return color, alpha, (x0, y0)

    def _composite(self, img: np.ndarray, polys: list[_Poly], gain: float) -> np.ndarray:
        if not polys:
            return img
        res = self._rasterize(polys)
        if res is None:
            return img
        color, alpha, (x0, y0) = res
        hh, ww = alpha.shape
        roi = img[y0:y0 + hh, x0:x0 + ww]
        a = np.clip(alpha, 0.0, 1.0)[..., None]
        # fillPoly with LINE_AA blends edges against the black canvas, so colour is
        # (approximately) premultiplied by alpha already.
        img[y0:y0 + hh, x0:x0 + ww] = roi * (1.0 - a) + color * gain
        return img

    def _composite_blurred(self, img: np.ndarray, dart: DartInstance,
                           poses: list[tuple[np.ndarray, np.ndarray]], lighting: Lighting) -> np.ndarray:
        acc = np.zeros_like(img)
        for start, axis in poses:
            layer = img.copy()
            layer = self._composite(layer, self._dart_polys(dart, np.asarray(start, float),
                                                             np.asarray(axis, float), lighting),
                                    lighting.gain)
            acc += layer
        return acc / len(poses)

    def _shadow_mask(self, darts: list[DartInstance], occluders: list[Occluder],
                     lighting: Lighting) -> np.ndarray | None:
        L = lighting.direction
        if L[2] <= 0.05 or lighting.shadow_strength <= 0:
            return None
        segments: list[tuple[np.ndarray, np.ndarray, float]] = []
        for dart in darts:
            if dart.tip_position is not None:
                continue
            s = dart.style
            start = dart.surface_point()
            a = dart.axis
            body_end = dart.visible_point_length() + s.barrel_length + s.shaft_length
            segments.append((start, start + a * dart.visible_point_length(), s.point_radius))
            segments.append((start + a * dart.visible_point_length(),
                             start + a * (dart.visible_point_length() + s.barrel_length), s.barrel_radius))
            segments.append((start + a * (dart.visible_point_length() + s.barrel_length),
                             start + a * body_end, s.shaft_radius))
            fstart = body_end - s.flight_overlap
            segments.append((start + a * fstart, start + a * (fstart + s.flight_length), s.flight_span * 0.6))
        for occ in occluders:
            for cap in occ.capsules:
                segments.append((np.asarray(cap.p0, float), np.asarray(cap.p1, float), cap.radius))
            for sph in occ.spheres:
                c = np.asarray(sph.center, float)
                segments.append((c, c + 1e-3, sph.radius))
        if not segments:
            return None
        w, h = self.size
        mask = np.zeros((h, w), dtype=np.float32)
        for p0, p1, radius in segments:
            q0 = p0 - (p0[2] / L[2]) * L
            q1 = p1 - (p1[2] / L[2]) * L
            d = q1[:2] - q0[:2]
            n = np.linalg.norm(d)
            perp = np.array([-d[1], d[0]]) / n if n > 1e-6 else np.array([1.0, 0.0])
            quad = np.array([q0[:2] + perp * radius, q1[:2] + perp * radius,
                             q1[:2] - perp * radius, q0[:2] - perp * radius])
            quad3 = np.concatenate([quad, np.zeros((4, 1))], axis=1)
            cam_pts = self.camera.to_camera(quad3)
            if np.any(cam_pts[:, 2] <= 1.0):
                continue
            uv = cam_pts[:, :2] / cam_pts[:, 2:3]
            px = uv @ self.camera.K[:2, :2].T + self.camera.K[:2, 2]
            cv2.fillConvexPoly(mask, np.round(px * 16).astype(np.int32), 1.0, cv2.LINE_AA, 4)
        # Soft shadow edge: blur width in pixels from mm at the board centre.
        mm_per_px = self._mm_per_pixel()
        sigma = max(0.6, lighting.shadow_blur_mm / mm_per_px)
        return cv2.GaussianBlur(mask, (0, 0), sigma)

    def _mm_per_pixel(self) -> float:
        J = self.camera.board_jacobian((self.camera.K[0, 2], self.camera.K[1, 2]))
        if J is None:
            return 1.0
        return float(math.sqrt(abs(np.linalg.det(J))))


def _barrel_profile(t: float) -> float:
    """Relative barrel radius along its length (tapered at both ends)."""
    if t < 0.12:
        return 0.72 + 0.28 * t / 0.12
    if t > 0.88:
        return 0.75 + 0.25 * (1 - t) / 0.12
    return 1.0

# Geometry Engine

The internal unit is the millimeter. XML units are converted on read and converted back
with controlled rounding on write. The public MCP API does not expose backend-specific
types.

## Implemented

- `Point`, `Vector`, `BBox`, affine `Transform`, inverse transforms, and composition;
- translation, rotation, top/bottom mirroring, and component-local transforms;
- bounding-box union, intersection, overlap, distance, and containment;
- segment and polyline distance and intersection, plus point-in-polygon tests;
- exact circular-arc length through three DipTrace points;
- normalized `GeometryShape` values for circle, ellipse, rectangle, obround, polygon, and line;
- exact local-to-board pad transforms, including rotation and Bottom-side mirroring;
- circular via geometry, documented custom mask/paste swell, shrink, and segments, and
  line/polygon courtyard geometry;
- deterministic uniform-grid `SpatialIndex` with bounding-box and nearest-neighbor queries;
- SVG/JSON before-and-after previews and DRC markers.

## Backend

The core uses pure Python. The `geometry` extra installs `Shapely>=2,<3` and enables GEOS
predicates for rotated pads, ellipses, obrounds, polygons, and swept-trace distance.
Shapely types do not appear in the MCP API. Spatial query results are always sorted by
stable ID. Without the extra, complex geometry uses a conservative bounding box or the
check is explicitly skipped.

## Limitations

- There is no public general-purpose polygon Boolean, offset, or clipping API.
- Rounded-rectangle corner contours are currently represented conservatively by the full rectangle.
- Numeric mask, paste, and courtyard contours are available only when verified XML fields are present.
- The `Common` mask/paste policy is preserved as metadata and is not converted into a fabricated expansion value.
- Copper refill, thermal reliefs, and isolated islands are not reconstructed.
- Return-path analysis uses boundaries and reports explicitly low confidence.

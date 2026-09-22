"""TCX download + analysis tools.

Downloads the full trackpoint-level TCX file for an activity (finer-grained
than Garmin's 1km lap splits) and returns a summarized time-series analysis
instead of the raw XML, so the response stays a reasonable size.
"""

import statistics
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

TCX_NS = "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"
TPX_NS = "http://www.garmin.com/xmlschemas/ActivityExtension/v2"
NS = {"tcx": TCX_NS, "tpx": TPX_NS}


def _format_pace(seconds_per_km: float | None) -> str | None:
    if seconds_per_km is None or seconds_per_km <= 0 or seconds_per_km == float("inf"):
        return None
    minutes = int(seconds_per_km // 60)
    secs = int(seconds_per_km % 60)
    return f"{minutes}:{secs:02d}"


def _pace_to_seconds(pace: str) -> int:
    m, s = pace.split(":")
    return int(m) * 60 + int(s)


def _parse_time(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_trackpoints(tcx_bytes: bytes, include_gps: bool = False) -> list[dict[str, Any]]:
    """Parse every <Trackpoint> in the TCX file into a flat dict.

    GPS coordinates (<Position>) are only included when include_gps=True —
    this is the user's own activity data, so it's opt-in rather than the
    hard PII strip used for other tools (which guards against exposing
    other people embedded in shared/group API responses).
    """
    root = ET.fromstring(tcx_bytes)
    points: list[dict[str, Any]] = []

    for tp in root.iter(f"{{{TCX_NS}}}Trackpoint"):
        time_el = tp.find("tcx:Time", NS)
        dist_el = tp.find("tcx:DistanceMeters", NS)
        alt_el = tp.find("tcx:AltitudeMeters", NS)
        hr_el = tp.find("tcx:HeartRateBpm/tcx:Value", NS)
        cad_el = tp.find(".//tpx:RunCadence", NS)
        speed_el = tp.find(".//tpx:Speed", NS)

        point: dict[str, Any] = {
            "time": _parse_time(time_el.text if time_el is not None else None),
            "distance_m": float(dist_el.text) if dist_el is not None and dist_el.text else None,
            "altitude_m": float(alt_el.text) if alt_el is not None and alt_el.text else None,
            "heart_rate": int(float(hr_el.text)) if hr_el is not None and hr_el.text else None,
            "cadence": int(float(cad_el.text)) if cad_el is not None and cad_el.text else None,
            "speed_ms": float(speed_el.text) if speed_el is not None and speed_el.text else None,
        }

        if include_gps:
            lat_el = tp.find("tcx:Position/tcx:LatitudeDegrees", NS)
            lon_el = tp.find("tcx:Position/tcx:LongitudeDegrees", NS)
            point["lat"] = float(lat_el.text) if lat_el is not None and lat_el.text else None
            point["lon"] = float(lon_el.text) if lon_el is not None and lon_el.text else None

        points.append(point)

    return [p for p in points if p["time"] is not None]


def _summarize_points(pts: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate HR/cadence/elevation for a group of trackpoints."""
    hrs = [p["heart_rate"] for p in pts if p["heart_rate"] is not None]
    cads = [p["cadence"] for p in pts if p["cadence"] is not None]
    alts = [p["altitude_m"] for p in pts if p["altitude_m"] is not None]
    return {
        "avg_heart_rate": round(statistics.mean(hrs)) if hrs else None,
        "avg_cadence": round(statistics.mean(cads)) if cads else None,
        "avg_elevation_m": round(statistics.mean(alts), 1) if alts else None,
    }


def _build_distance_segments(points: list[dict[str, Any]], interval_meters: int) -> list[dict[str, Any]]:
    """Bucket trackpoints into fixed-distance segments (e.g. every 500m),
    aligned to the start of the run — like laps, but at any distance."""
    dist_points = [p for p in points if p["distance_m"] is not None]
    if not dist_points:
        return []

    start_dist = dist_points[0]["distance_m"]
    buckets: dict[int, list[dict[str, Any]]] = {}
    for p in dist_points:
        bucket_idx = int((p["distance_m"] - start_dist) // interval_meters)
        buckets.setdefault(bucket_idx, []).append(p)

    segments = []
    for idx in sorted(buckets):
        pts = buckets[idx]
        distance_delta_m = pts[-1]["distance_m"] - pts[0]["distance_m"]
        time_delta_s = (pts[-1]["time"] - pts[0]["time"]).total_seconds()
        pace_s_per_km = (time_delta_s / (distance_delta_m / 1000)) if distance_delta_m > 0 else None

        segment = {
            "segment_start_m": idx * interval_meters,
            "distance_m": round(distance_delta_m, 1),
            "duration_s": round(time_delta_s, 1),
            "pace": _format_pace(pace_s_per_km),
            **_summarize_points(pts),
        }

        if "lat" in pts[0] and pts[0].get("lat") is not None:
            segment["start_lat"] = pts[0]["lat"]
            segment["start_lon"] = pts[0]["lon"]

        segments.append(segment)

    return segments


def _sliding_fastest_window(points: list[dict[str, Any]], target_m: float) -> dict[str, Any] | None:
    """Find the true fastest `target_m`-long window anywhere in the run,
    using a sliding two-pointer scan (not bound to fixed segment boundaries
    like _build_distance_segments — this catches a fast burst that straddles
    two laps)."""
    pts = [p for p in points if p["distance_m"] is not None]
    n = len(pts)
    if n < 2:
        return None

    best = None
    j = 0
    for i in range(n):
        if j < i:
            j = i
        while j < n and pts[j]["distance_m"] - pts[i]["distance_m"] < target_m:
            j += 1
        if j >= n:
            break
        dur = (pts[j]["time"] - pts[i]["time"]).total_seconds()
        if dur <= 0:
            continue
        if best is None or dur < best["duration_s"]:
            actual_distance = pts[j]["distance_m"] - pts[i]["distance_m"]
            pace_s_per_km = dur / (actual_distance / 1000)
            best = {
                "duration_s": round(dur, 1),
                "distance_m": round(actual_distance, 1),
                "pace": _format_pace(pace_s_per_km),
                "start_time": pts[i]["time"].isoformat(),
                "end_time": pts[j]["time"].isoformat(),
                **_summarize_points(pts[i : j + 1]),
            }

    return best


def _analyze(points: list[dict[str, Any]], interval_meters: int) -> dict[str, Any]:
    segments = _build_distance_segments(points, interval_meters)

    total_distance_m = max((p["distance_m"] for p in points if p["distance_m"] is not None), default=0)
    duration_s = (points[-1]["time"] - points[0]["time"]).total_seconds()

    # Pacing consistency: stddev of per-segment pace (seconds/km), lower = more even effort.
    paced_segments = [s for s in segments if s["pace"]]
    pace_seconds = [_pace_to_seconds(s["pace"]) for s in paced_segments]
    pace_std_dev_s = round(statistics.pstdev(pace_seconds), 1) if len(pace_seconds) >= 2 else None

    # HR drift: second-half average HR vs first-half (cardiac drift indicator).
    hrs_with_time = [(p["time"], p["heart_rate"]) for p in points if p["heart_rate"] is not None]
    hr_drift_pct = None
    if len(hrs_with_time) >= 10:
        mid = len(hrs_with_time) // 2
        first_half = [h for _, h in hrs_with_time[:mid]]
        second_half = [h for _, h in hrs_with_time[mid:]]
        if first_half and second_half and statistics.mean(first_half) > 0:
            hr_drift_pct = round(
                (statistics.mean(second_half) - statistics.mean(first_half)) / statistics.mean(first_half) * 100, 1
            )

    # Best/worst full-length segment (bucket-aligned) and the true sliding-window
    # fastest of the same distance (not bound to segment boundaries).
    fastest_segment = min(paced_segments, key=lambda s: _pace_to_seconds(s["pace"]), default=None)
    slowest_segment = max(paced_segments, key=lambda s: _pace_to_seconds(s["pace"]), default=None)
    true_fastest_window = _sliding_fastest_window(points, interval_meters)

    result = {
        "point_count": len(points),
        "start_time": points[0]["time"].isoformat(),
        "duration_seconds": round(duration_s, 1),
        "distance_km": round(total_distance_m / 1000, 3),
        "pace_std_dev_seconds": pace_std_dev_s,
        "hr_drift_pct": hr_drift_pct,
        "fastest_segment": fastest_segment,
        "slowest_segment": slowest_segment,
        "true_fastest_window": true_fastest_window,
        "segments": segments,
    }

    lats = [p["lat"] for p in points if p.get("lat") is not None]
    lons = [p["lon"] for p in points if p.get("lon") is not None]
    if lats and lons:
        result["route_bounds"] = {
            "min_lat": min(lats), "max_lat": max(lats),
            "min_lon": min(lons), "max_lon": max(lons),
        }
        gps_points = [p for p in points if p.get("lat") is not None and p.get("lon") is not None]
        result["start_point"] = {"lat": gps_points[0]["lat"], "lon": gps_points[0]["lon"]}
        result["end_point"] = {"lat": gps_points[-1]["lat"], "lon": gps_points[-1]["lon"]}

    return result


def register(mcp: FastMCP):
    @mcp.tool()
    def analyze_activity_tcx(
        activity_id: int,
        interval_meters: int = 500,
        save_file: bool = True,
        include_gps: bool = True,
    ) -> dict[str, Any]:
        """Download the full-resolution TCX trackpoint data for an activity and
        return a detailed distance-based analysis — much finer-grained than the
        1km lap splits from get_activity_splits.

        Breaks the run into fixed-distance segments (default every 500m, lap-
        style) with pace/HR/cadence/elevation per segment, plus:
        - pacing consistency (pace std deviation across segments)
        - cardiac drift (HR trend from first half of the run to second half)
        - true_fastest_window: the single fastest `interval_meters`-long
          stretch anywhere in the run via a sliding-window scan — this can
          beat fastest_segment because it isn't locked to segment boundaries
          (e.g. a fast burst spanning the tail of one 500m block and the
          start of the next).

        Args:
            activity_id: The Garmin activity ID
            interval_meters: Segment length in meters for the breakdown and
                for true_fastest_window (default 500, min 100)
            save_file: If True, also save the raw TCX XML file locally and
                return its path for further offline analysis (always has full
                GPS precision regardless of include_gps)
            include_gps: If True (default), include per-segment start
                coordinates plus the route's overall lat/lon bounds and
                start/end point.
        """
        from garmin_mcp import get_client
        from garmin_mcp.auth import get_token_dir

        interval_meters = max(interval_meters, 100)

        client = get_client()
        tcx_bytes = client.download_activity_tcx(activity_id)

        points = _parse_trackpoints(tcx_bytes, include_gps=include_gps)
        if not points:
            return {"activity_id": activity_id, "error": "No trackpoints found in TCX file"}

        result: dict[str, Any] = {"activity_id": activity_id}
        result.update(_analyze(points, interval_meters))

        if save_file:
            out_dir = Path(get_token_dir()) / "tcx_cache"
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"{activity_id}.tcx"
            out_path.write_bytes(tcx_bytes)
            result["tcx_file_path"] = str(out_path)

        return result

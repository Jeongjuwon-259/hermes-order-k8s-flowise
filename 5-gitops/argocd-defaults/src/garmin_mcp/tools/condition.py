"""Daily body condition / readiness summary.

Combines Body Battery, stress, sleep, HRV, respiration, resting HR, and
training readiness into one digestible "how is my body today" report —
richer than what the Garmin Connect app surfaces in a single screen.
"""

from typing import Any

from mcp.server.fastmcp import FastMCP

from garmin_mcp.client import today_str
from garmin_mcp.sanitize import strip_pii


def _stress_label(level: int | None) -> str | None:
    """Garmin's own stress scale buckets."""
    if level is None or level < 0:
        return None
    if level <= 25:
        return "Rest"
    if level <= 50:
        return "Low"
    if level <= 75:
        return "Medium"
    return "High"


def _summarize_body_battery(bb_days: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    if not bb_days:
        return None
    day = bb_days[0]
    values_array = day.get("bodyBatteryValuesArray") or []
    levels = [v[1] for v in values_array if len(v) > 1 and v[1] is not None]

    event = day.get("bodyBatteryDynamicFeedbackEvent") or {}

    return {
        "current_level": levels[-1] if levels else None,
        "day_high": max(levels) if levels else None,
        "day_low": min(levels) if levels else None,
        "charged": day.get("charged"),
        "drained": day.get("drained"),
        "feedback": event.get("feedbackShortType"),
        "level_category": event.get("bodyBatteryLevel"),
    }


def _summarize_sleep(sleep: dict[str, Any] | None) -> dict[str, Any] | None:
    if not sleep:
        return None
    daily = sleep.get("dailySleepDTO") or {}
    if not daily.get("sleepTimeSeconds"):
        return None
    return {
        "duration_hours": round(daily["sleepTimeSeconds"] / 3600, 1),
        "deep_minutes": round(daily["deepSleepSeconds"] / 60, 1) if daily.get("deepSleepSeconds") else None,
        "light_minutes": round(daily["lightSleepSeconds"] / 60, 1) if daily.get("lightSleepSeconds") else None,
        "rem_minutes": round(daily["remSleepSeconds"] / 60, 1) if daily.get("remSleepSeconds") else None,
        "awake_minutes": round(daily["awakeSleepSeconds"] / 60, 1) if daily.get("awakeSleepSeconds") else None,
        "sleep_score": (sleep.get("dailySleepDTO", {}).get("sleepScores") or {}).get("overall", {}).get("value"),
    }


def _running_recommendation(
    readiness_score: int | None,
    body_battery_level: int | None,
    sleep_score: int | None,
) -> str:
    """Simple heuristic combining the three strongest readiness signals into
    a plain-language running recommendation."""
    red_flags = 0
    if readiness_score is not None and readiness_score < 50:
        red_flags += 1
    if body_battery_level is not None and body_battery_level < 40:
        red_flags += 1
    if sleep_score is not None and sleep_score < 60:
        red_flags += 1

    if red_flags >= 2:
        return "휴식 또는 매우 가벼운 조깅 권장 — 회복 신호가 여러 개 겹침"
    if red_flags == 1:
        return "가벼운 러닝은 괜찮으나 고강도 훈련은 피할 것"
    return "정상 강도 훈련 가능"


def register(mcp: FastMCP):
    @mcp.tool()
    def get_daily_condition_summary(date: str = "") -> dict[str, Any]:
        """Get a combined daily body-condition report: Body Battery (current
        level, day high/low, charged/drained), stress (avg/max + category),
        sleep (duration, stages, score), HRV, respiration, resting heart
        rate, training readiness, and a plain-language running
        recommendation. Pulls from multiple Garmin endpoints in one call —
        more comprehensive than a single screen in the Garmin Connect app.

        Args:
            date: Date (YYYY-MM-DD), defaults to today
        """
        from garmin_mcp import get_client

        client = get_client()
        d = date or today_str()

        result: dict[str, Any] = {"date": d}

        try:
            stats = client.get_stats(d)
            result["resting_heart_rate"] = stats.get("restingHeartRate")
            result["total_steps"] = stats.get("totalSteps")
            result["total_calories"] = stats.get("totalKilocalories")
        except Exception as e:
            result["stats_error"] = str(e)

        try:
            bb = client.get_body_battery(d)
            result["body_battery"] = _summarize_body_battery(bb)
        except Exception as e:
            result["body_battery"] = {"error": str(e)}

        try:
            stress = client.get_stress_data(d)
            result["stress"] = {
                "avg": stress.get("avgStressLevel"),
                "max": stress.get("maxStressLevel"),
                "category": _stress_label(stress.get("avgStressLevel")),
            }
        except Exception as e:
            result["stress"] = {"error": str(e)}

        try:
            sleep = client.get_sleep_data(d)
            result["sleep"] = _summarize_sleep(sleep)
        except Exception as e:
            result["sleep"] = {"error": str(e)}

        try:
            hrv = client.get_hrv_data(d)
            hrv_summary = hrv.get("hrvSummary") if isinstance(hrv, dict) else None
            result["hrv"] = {
                "last_night_avg": hrv_summary.get("lastNightAvg") if hrv_summary else None,
                "weekly_avg": hrv_summary.get("weeklyAvg") if hrv_summary else None,
                "status": hrv_summary.get("status") if hrv_summary else None,
            } if hrv else None
        except Exception as e:
            result["hrv"] = {"error": str(e)}

        try:
            resp = client.get_respiration_data(d)
            result["respiration"] = {
                "avg_waking": resp.get("avgWakingRespirationValue"),
                "lowest": resp.get("lowestRespirationValue"),
                "highest": resp.get("highestRespirationValue"),
            }
        except Exception as e:
            result["respiration"] = {"error": str(e)}

        try:
            spo2 = client.get_spo2_data(d)
            result["spo2"] = {
                "average": spo2.get("averageSpO2"),
                "lowest": spo2.get("lowestSpO2"),
            }
        except Exception as e:
            result["spo2"] = {"error": str(e)}

        try:
            readiness = client.get_training_readiness(d)
            latest = readiness[0] if readiness else {}
            result["training_readiness"] = {
                "score": latest.get("score"),
                "level": latest.get("level"),
                "feedback": latest.get("feedbackShort"),
                "recovery_time_hours": round(latest["recoveryTime"] / 60, 1) if latest.get("recoveryTime") else None,
            }
        except Exception as e:
            result["training_readiness"] = {"error": str(e)}

        bb_level = (result.get("body_battery") or {}).get("current_level") if isinstance(result.get("body_battery"), dict) else None
        sleep_score = (result.get("sleep") or {}).get("sleep_score") if isinstance(result.get("sleep"), dict) else None
        readiness_score = (result.get("training_readiness") or {}).get("score") if isinstance(result.get("training_readiness"), dict) else None

        result["running_recommendation"] = _running_recommendation(readiness_score, bb_level, sleep_score)

        return strip_pii(result)

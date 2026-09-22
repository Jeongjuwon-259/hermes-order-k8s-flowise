"""Training metrics tools (VO2max, training status, race predictions, etc.)."""

from datetime import date, timedelta
from typing import Any

from mcp.server.fastmcp import FastMCP

from garmin_mcp.client import today_str
from garmin_mcp.sanitize import strip_pii


def _classify_endurance(score: int, data: dict[str, Any]) -> str:
    """Map a raw endurance score to Garmin's own tier labels, using the
    classification thresholds Garmin returns alongside the score (rather
    than guessing at the undocumented `classification` id)."""
    tiers = [
        ("Elite", data.get("classificationLowerLimitElite")),
        ("Superior", data.get("classificationLowerLimitSuperior")),
        ("Expert", data.get("classificationLowerLimitExpert")),
        ("Well Trained", data.get("classificationLowerLimitWellTrained")),
        ("Trained", data.get("classificationLowerLimitTrained")),
        ("Intermediate", data.get("classificationLowerLimitIntermediate")),
    ]
    for label, threshold in tiers:
        if threshold is not None and score >= threshold:
            return label
    return "Beginner"


def register(mcp: FastMCP):
    @mcp.tool()
    def get_training_status(date: str = "") -> dict[str, Any]:
        """Get current training status (Productive, Maintaining, Overreaching,
        Detraining, Recovery, Peaking, Unproductive).

        Args:
            date: Date (YYYY-MM-DD), defaults to today
        """
        from garmin_mcp import get_client

        client = get_client()
        d = date or today_str()
        return strip_pii(client.get_training_status(d))

    @mcp.tool()
    def get_training_readiness(date: str = "") -> list[dict[str, Any]]:
        """Get training readiness score indicating how prepared you are
        for training today. Considers sleep, recovery, training load, and HRV.

        Args:
            date: Date (YYYY-MM-DD), defaults to today
        """
        from garmin_mcp import get_client

        client = get_client()
        d = date or today_str()
        return strip_pii(client.get_training_readiness(d))

    @mcp.tool()
    def get_vo2max_and_fitness(date: str = "") -> dict[str, Any]:
        """Get VO2max estimate and fitness age data. Essential for
        Jack Daniels VDOT calculation and training pace zones.

        Args:
            date: Date (YYYY-MM-DD), defaults to today
        """
        from garmin_mcp import get_client

        client = get_client()
        d = date or today_str()

        max_metrics = client.get_max_metrics(d)

        try:
            fitness_age = client.get_fitnessage_data(d)
        except Exception:
            fitness_age = None

        return strip_pii({
            "max_metrics": max_metrics,
            "fitness_age": fitness_age,
        })

    @mcp.tool()
    def get_race_predictions() -> dict[str, Any]:
        """Get predicted race times for 5K, 10K, half marathon, and marathon
        based on current fitness level.
        """
        from garmin_mcp import get_client

        client = get_client()
        return strip_pii(client.get_race_predictions())

    @mcp.tool()
    def get_lactate_threshold(
        start_date: str = "",
        end_date: str = "",
    ) -> dict[str, Any]:
        """Get lactate threshold data. Critical for Norwegian double threshold
        training and zone-based training methods.

        Args:
            start_date: Start date (YYYY-MM-DD), optional
            end_date: End date (YYYY-MM-DD), optional
        """
        from garmin_mcp import get_client

        client = get_client()
        return strip_pii(client.get_lactate_threshold(
            start_date=start_date or None,
            end_date=end_date or None,
        ))

    @mcp.tool()
    def get_training_load_summary(weeks: int = 4) -> dict[str, Any]:
        """Get a summarized view of running-specific training load metrics:
        endurance score (aerobic capacity for sustained effort), hill score
        (climbing strength/endurance), and running tolerance (weekly impact
        load vs. your body's adapted tolerance — a signal for injury risk
        when load consistently exceeds tolerance).

        Args:
            weeks: How many past weeks of running tolerance data to include
                (default 4, each entry is one week)
        """
        from garmin_mcp import get_client

        client = get_client()
        today = today_str()
        start_date = (date.today() - timedelta(weeks=weeks)).isoformat()

        result: dict[str, Any] = {"date": today}

        try:
            endurance = strip_pii(client.get_endurance_score(today))
            result["endurance_score"] = {
                "score": endurance.get("overallScore"),
                "level": _classify_endurance(endurance.get("overallScore", 0), endurance),
                "gauge_range": [endurance.get("gaugeLowerLimit"), endurance.get("gaugeUpperLimit")],
            }
        except Exception as e:
            result["endurance_score"] = {"error": str(e)}

        try:
            hill = strip_pii(client.get_hill_score(today))
            result["hill_score"] = {
                "overall_score": hill.get("overallScore"),
                "strength_score": hill.get("strengthScore"),
                "endurance_score": hill.get("enduranceScore"),
                "vo2max": hill.get("vo2MaxPreciseValue") or hill.get("vo2Max"),
            }
        except Exception as e:
            result["hill_score"] = {"error": str(e)}

        try:
            tolerance_weeks = strip_pii(client.get_running_tolerance(start_date, today, "weekly"))
            result["running_tolerance_weeks"] = [
                {
                    "week_start": w.get("startOfWeek"),
                    "week_end": w.get("endOfWeek"),
                    "distance_km": round(w["totalDistance"] / 1000, 1) if w.get("totalDistance") else 0,
                    "impact_load": w.get("totalImpactLoad"),
                    "tolerance": w.get("tolerance"),
                    "load_used_pct": (
                        round(w["totalImpactLoad"] / w["tolerance"] * 100, 1)
                        if w.get("totalImpactLoad") and w.get("tolerance")
                        else None
                    ),
                }
                for w in tolerance_weeks
            ]
        except Exception as e:
            result["running_tolerance_weeks"] = {"error": str(e)}

        return result

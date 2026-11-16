"""Freshness checks shared by detection and its preview."""

from dataclasses import dataclass
import math


def is_fresh(stamp: float, now: float, timeout: float) -> bool:
    """Reject expired samples and stamps in the future (including clock resets)."""

    age = now - stamp
    return math.isfinite(age) and 0.0 <= age <= timeout


@dataclass
class DetectionHealth:
    """Detector state; levels follow diagnostic_msgs/DiagnosticStatus."""

    model_ready: bool = False
    error: str | None = None
    result_stamp: float | None = None
    count: int = 0

    def status(self, now: float, timeout: float) -> tuple[int, str]:
        if not self.model_ready:
            return 2, self.error or "Model is unavailable."
        if self.error is not None:
            return 2, self.error
        if self.result_stamp is None:
            return 1, "Waiting for the first inference result."
        if not is_fresh(self.result_stamp, now, timeout):
            return 1, "Detection result is stale or its timestamp is invalid."
        return 0, "Fresh inference result; %s objects." % self.count

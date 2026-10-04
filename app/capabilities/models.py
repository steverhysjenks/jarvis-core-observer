from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CapabilityResult:
    """
    Standard result returned by a Jarvis capability.

    claimed:
        The capability recognises this request as belonging
        to its domain.

    handled:
        The capability successfully performed the request.

    domain:
        Stable capability/domain name.

    path:
        Execution path used inside the capability.
    """

    claimed: bool
    handled: bool
    domain: str | None
    path: str
    result: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict:
        payload = {
            "handled": self.handled,
            "domain": self.domain,
            "path": self.path,
        }

        payload.update(self.metadata)

        if self.result is not None:
            payload["result"] = self.result

        return payload

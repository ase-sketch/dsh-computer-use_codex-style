class DesktopUnavailable(RuntimeError):
    """Raised when the live Windows desktop cannot be observed or driven."""


class TurnInterrupted(RuntimeError):
    """Physical Escape / interrupt file stopped Computer Use for this turn."""


class ApprovalDenied(RuntimeError):
    """Elicitation rejected an app approval request."""


class ApprovalNeeded(RuntimeError):
    """Helper-style pause: return approvalRequest and retry with x-oai-cua-approved-app."""

    def __init__(self, request: dict) -> None:
        super().__init__(f"Allow DeepSeek Harness to use {request.get('displayName') or request.get('app')}?")
        self.request = request

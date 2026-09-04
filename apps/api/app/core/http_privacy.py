from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class PrivateApiResponseMiddleware:
    """Prevent storage of owner-bearing API responses without buffering bodies."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        private = scope["type"] == "http" and (path == "/api/v1" or path.startswith("/api/v1/"))

        async def send_private(message: Message) -> None:
            if private and message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                streaming = "text/event-stream" in headers.get("content-type", "").lower()
                no_transform = "no-transform" in headers.get("cache-control", "").lower()
                headers["Cache-Control"] = "private, no-store" + (
                    ", no-transform" if streaming or no_transform else ""
                )
                headers["Pragma"] = "no-cache"
                headers["Expires"] = "0"
            await send(message)

        await self.app(scope, receive, send_private)

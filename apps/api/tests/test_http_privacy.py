import asyncio

from app.core.http_privacy import PrivateApiResponseMiddleware


def test_stream_headers_preserve_cookies_and_forward_chunks_immediately():
    messages = []

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": [
            (b"cache-control", b"public, max-age=3600"),
            (b"content-type", b"text/event-stream"),
            (b"set-cookie", b"one=synthetic; HttpOnly"),
            (b"set-cookie", b"two=synthetic; HttpOnly"),
            (b"vary", b"Origin"),
        ]})
        chunk = {"type": "http.response.body", "body": b"data: first\n\n", "more_body": True}
        await send(chunk)
        assert messages[-1] is chunk  # forwarded before upstream completion
        await send({"type": "http.response.body", "body": b"data: last\n\n", "more_body": False})

    async def send(message):
        messages.append(message)

    asyncio.run(PrivateApiResponseMiddleware(app)({"type": "http", "path": "/api/v1/stream"}, None, send))
    headers = messages[0]["headers"]
    assert (b"cache-control", b"private, no-store, no-transform") in headers
    assert len([h for h in headers if h[0] == b"set-cookie"]) == 2
    assert (b"vary", b"Origin") in headers
    assert len(messages) == 3


def test_non_api_path_is_not_modified():
    original = {"type": "http.response.start", "status": 200, "headers": [(b"cache-control", b"max-age=60")]}
    messages = []

    async def app(scope, receive, send):
        await send(original)

    async def send(message):
        messages.append(message)

    for path in ("/health", "/ready", "/api/v10/other"):
        asyncio.run(PrivateApiResponseMiddleware(app)({"type": "http", "path": path}, None, send))
    assert all(message["headers"] == [(b"cache-control", b"max-age=60")] for message in messages)

"""Bound request bodies before multipart parsing or JSON validation consumes them."""

from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


class RequestBodyLimitMiddleware:
    def __init__(self, app: ASGIApp, max_body_bytes: int):
        if max_body_bytes <= 0:
            raise ValueError('Request body limit must be positive.')
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return
        lengths = [value for name, value in scope['headers'] if name.lower() == b'content-length']
        if lengths:
            try:
                if len(lengths) != 1 or not lengths[0].isdigit():
                    raise ValueError
                declared = int(lengths[0])
            except ValueError:
                await JSONResponse({'detail': 'Invalid Content-Length header.'}, status_code=400)(scope, receive, send)
                return
            if declared > self.max_body_bytes:
                await JSONResponse({'detail': 'Request body exceeds the upload limit.'}, status_code=413)(scope, receive, send)
                return
        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message['type'] == 'http.request':
                received += len(message.get('body', b''))
                if received > self.max_body_bytes:
                    # FastAPI handles this response, and Starlette closes multipart
                    # temporary files when its input stream raises an exception.
                    raise HTTPException(413, 'Request body exceeds the upload limit.')
            return message

        await self.app(scope, limited_receive, send)

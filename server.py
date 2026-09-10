#!/usr/bin/env python3
"""Local OpenAI-compatible transcription API backed by transcribe.cpp."""

from __future__ import annotations

import array
import io
import json
import os
import signal
import sys
import threading
import wave
from email import policy
from email.parser import BytesParser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import transcribe_cpp


def load_wav_mono16k(data: bytes) -> array.array:
    """Decode a 16 kHz mono PCM WAV into float32 samples."""
    try:
        with wave.open(io.BytesIO(data), "rb") as wav_file:
            channels = wav_file.getnchannels()
            sample_width = wav_file.getsampwidth()
            sample_rate = wav_file.getframerate()
            compression = wav_file.getcomptype()
            frames = wav_file.readframes(wav_file.getnframes())
    except (EOFError, wave.Error) as exc:
        raise ValueError(f"invalid WAV file: {exc}") from exc

    if compression != "NONE":
        raise ValueError(f"expected uncompressed PCM, got {compression}")
    if channels != 1:
        raise ValueError(f"expected mono audio, got {channels} channels")
    if sample_width != 2:
        raise ValueError(f"expected 16-bit PCM, got {sample_width * 8}-bit")
    if sample_rate != 16000:
        raise ValueError(f"expected 16 kHz audio, got {sample_rate} Hz")

    pcm16 = array.array("h")
    pcm16.frombytes(frames)
    if sys.byteorder == "big":
        pcm16.byteswap()
    return array.array("f", (sample / 32768.0 for sample in pcm16))


def parse_multipart(content_type: str, body: bytes) -> dict[str, bytes]:
    """Parse multipart form fields using only the Python standard library."""
    header = (
        f"Content-Type: {content_type}\r\n"
        "MIME-Version: 1.0\r\n\r\n"
    ).encode("ascii", errors="replace")
    message = BytesParser(policy=policy.default).parsebytes(header + body)
    if not message.is_multipart():
        raise ValueError("expected multipart/form-data")

    fields: dict[str, bytes] = {}
    for part in message.iter_parts():
        if part.get_content_disposition() != "form-data":
            continue
        name = part.get_param("name", header="content-disposition")
        if name:
            fields[name] = part.get_payload(decode=True) or b""
    return fields


def text_field(fields: dict[str, bytes], name: str) -> str | None:
    value = fields.get(name, b"").decode("utf-8", errors="replace").strip()
    return value or None


class BridgeServer(ThreadingHTTPServer):
    daemon_threads = True

    model: transcribe_cpp.Model
    inference_lock: threading.Lock
    api_key: str
    max_upload_bytes: int


class RequestHandler(BaseHTTPRequestHandler):
    server: BridgeServer

    def send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:
        if urlsplit(self.path).path.rstrip("/") != "/health":
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        self.send_json(
            HTTPStatus.OK,
            {
                "status": "ok",
                "model": self.server.model.variant,
                "architecture": self.server.model.arch,
                "backend": self.server.model.backend,
            },
        )

    def do_POST(self) -> None:
        if urlsplit(self.path).path.rstrip("/") not in {
            "/v1/audio/transcriptions",
            "/inference",
        }:
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return

        if self.server.api_key:
            expected = f"Bearer {self.server.api_key}"
            if self.headers.get("Authorization") != expected:
                self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
                return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "invalid Content-Length"})
            return
        if content_length <= 0:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "empty request"})
            return
        if content_length > self.server.max_upload_bytes:
            self.send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "request too large"})
            return

        try:
            body = self.rfile.read(content_length)
            fields = parse_multipart(self.headers.get("Content-Type", ""), body)
            if "file" not in fields:
                raise ValueError("multipart field 'file' is required")
            pcm = load_wav_mono16k(fields["file"])
            if not pcm:
                raise ValueError("audio is empty")

            capabilities = self.server.model.capabilities
            duration_ms = len(pcm) * 1000 // capabilities.native_sample_rate
            if capabilities.max_audio_ms > 0 and duration_ms > capabilities.max_audio_ms:
                raise ValueError(
                    f"audio is {duration_ms / 1000:.1f}s; model limit is "
                    f"{capabilities.max_audio_ms / 1000:.1f}s"
                )

            requested_language = text_field(fields, "language")
            language = requested_language
            if capabilities.languages and requested_language:
                supported = {item.lower() for item in capabilities.languages}
                if requested_language.lower() not in supported:
                    language = None

            with self.server.inference_lock:
                with self.server.model.session() as session:
                    result = session.run(pcm, timestamps="none", language=language)
            self.send_json(HTTPStatus.OK, {"text": result.text.strip()})
        except ValueError as exc:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception as exc:
            self.log_error("transcription failed: %s", exc)
            self.send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": "transcription failed"},
            )


def required_path(variable: str) -> Path:
    value = os.environ.get(variable, "").strip()
    if not value:
        raise SystemExit(f"{variable} must point to a GGUF model")
    path = Path(value).expanduser()
    if not path.is_file():
        raise SystemExit(f"model not found: {path}")
    return path


def main() -> int:
    host = os.environ.get("BRIDGE_HOST", "127.0.0.1")
    port = int(os.environ.get("BRIDGE_PORT", "8765"))
    backend = os.environ.get("TRANSCRIBE_BACKEND", "auto")
    model_path = required_path("TRANSCRIBE_MODEL")
    api_key = os.environ.get("BRIDGE_API_KEY", "")
    max_upload_bytes = int(os.environ.get("BRIDGE_MAX_UPLOAD_BYTES", str(2 * 1024 * 1024)))

    model = transcribe_cpp.Model(model_path, backend=backend)
    server = BridgeServer((host, port), RequestHandler)
    server.model = model
    server.inference_lock = threading.Lock()
    server.api_key = api_key
    server.max_upload_bytes = max_upload_bytes

    def stop_server(_signum: int, _frame: Any) -> None:
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, stop_server)
    signal.signal(signal.SIGINT, stop_server)

    print(
        f"Bridge listening on http://{host}:{port} | "
        f"{model.arch}/{model.variant} | {model.backend}",
        flush=True,
    )
    try:
        server.serve_forever()
    finally:
        server.server_close()
        model.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

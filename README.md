# Vocalinux transcribe.cpp bridge

An unofficial, local OpenAI-compatible transcription API that connects
[Vocalinux](https://github.com/VocaHQ/vocalinux) to
[transcribe.cpp](https://github.com/handy-computer/transcribe.cpp).

The bridge keeps one GGUF model loaded between requests and can use the CPU or
an accelerator supported by transcribe.cpp, including Vulkan. It was tested
with GigaAM v3 E2E RNN-T Q8 on Intel Iris Xe.

This project is not affiliated with or endorsed by VocaHQ, the transcribe.cpp
authors, Handy, or the GigaAM authors.

## Features

- OpenAI-compatible `POST /v1/audio/transcriptions`
- whisper.cpp-style `POST /inference`
- `GET /health`
- no Python web-framework dependencies
- optional bearer-token authentication
- serialized inference for the transcribe.cpp 0.x model-sharing contract
- listens on `127.0.0.1` by default

## Requirements

- Python 3.9 or newer
- [uv](https://docs.astral.sh/uv/)
- a shared build of transcribe.cpp
- a GGUF model supported by transcribe.cpp

For a Vulkan build on Debian or Ubuntu:

```bash
sudo apt install build-essential cmake git libvulkan-dev glslc spirv-headers libopenblas-dev
git clone --depth 1 https://github.com/handy-computer/transcribe.cpp.git
cd transcribe.cpp
cmake -S . -B build-vulkan \
  -DCMAKE_BUILD_TYPE=Release \
  -DTRANSCRIBE_VULKAN=ON \
  -DTRANSCRIBE_BUILD_SHARED=ON
cmake --build build-vulkan --target transcribe --parallel
```

See the upstream [build documentation](https://github.com/handy-computer/transcribe.cpp#build)
for other platforms and accelerators.

## Run

Set paths for your checkout, shared library, Python bindings, and model:

```bash
export TRANSCRIBE_LIBRARY=/absolute/path/to/transcribe.cpp/build-vulkan/src/libtranscribe.so
export PYTHONPATH=/absolute/path/to/transcribe.cpp/bindings/python/src
export TRANSCRIBE_MODEL=/absolute/path/to/model.gguf
export TRANSCRIBE_BACKEND=vulkan

uv run --no-project python server.py
```

The service starts at `http://127.0.0.1:8765`. Check it with:

```bash
curl --fail http://127.0.0.1:8765/health
```

Test a transcription with a 16 kHz mono 16-bit PCM WAV:

```bash
curl --fail \
  -F file=@audio.wav \
  -F model=local-model \
  -F language=ru \
  http://127.0.0.1:8765/v1/audio/transcriptions
```

Only one model is loaded per bridge process. The OpenAI `model` form field is
accepted for compatibility but does not select a different model.

## Vocalinux settings

In Vocalinux, select **Remote API** and configure:

| Setting | Value |
| --- | --- |
| Server URL | `http://127.0.0.1:8765` |
| Endpoint | `/v1/audio/transcriptions` |
| Model | any descriptive name |
| API key | empty unless `BRIDGE_API_KEY` is set |

Vocalinux sends 16 kHz mono PCM WAV audio, which is the input expected by the
bridge.

## systemd user service

1. Copy `bridge.env.example` to
   `~/.config/vocalinux-transcribe-cpp-bridge.env` and replace every example
   path with an absolute path on your machine.
2. Copy or link `vocalinux-transcribe-cpp-bridge.service.example` to
   `~/.config/systemd/user/vocalinux-transcribe-cpp-bridge.service`.
3. Reload user units and enable the service:

```bash
systemctl --user daemon-reload
systemctl --user enable --now vocalinux-transcribe-cpp-bridge.service
```

Inspect its status with:

```bash
systemctl --user status vocalinux-transcribe-cpp-bridge.service
```

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `TRANSCRIBE_MODEL` | required | Absolute path to a supported GGUF model |
| `TRANSCRIBE_LIBRARY` | required by bindings | Path to `libtranscribe.so` |
| `PYTHONPATH` | required for source checkout | Path to `bindings/python/src` |
| `TRANSCRIBE_BACKEND` | `auto` | `auto`, `cpu`, `vulkan`, `cuda`, and others supported upstream |
| `BRIDGE_HOST` | `127.0.0.1` | Listening address |
| `BRIDGE_PORT` | `8765` | Listening port |
| `BRIDGE_API_KEY` | empty | Optional bearer token |
| `BRIDGE_MAX_UPLOAD_BYTES` | `2097152` | Maximum request size |

Do not bind the bridge to a non-loopback address without setting an API key
and applying appropriate network controls.

## License

The bridge is available under the MIT License. Model weights and external
projects keep their own licenses; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

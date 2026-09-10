# Third-party notices

This repository does not include Vocalinux, transcribe.cpp, or model weights.
They are separate projects installed by the user.

## transcribe.cpp

The bridge uses the Python bindings from
[handy-computer/transcribe.cpp](https://github.com/handy-computer/transcribe.cpp),
which is available under the MIT License.

Copyright (c) 2026 The transcribe.cpp authors.

The WAV decoding approach in `server.py` is adapted from the transcribe.cpp
Python binding example. The upstream MIT license and third-party notices are
available in the transcribe.cpp repository:

- [LICENSE](https://github.com/handy-computer/transcribe.cpp/blob/main/LICENSE)
- [THIRD-PARTY-LICENSES.md](https://github.com/handy-computer/transcribe.cpp/blob/main/THIRD-PARTY-LICENSES.md)

## Models

Model weights are not distributed by this project. Users must review and
accept the license of each model they download. The tested
`gigaam-v3-e2e-rnnt` GGUF inherits the MIT License from the GigaAM v3 base
model:

- [GigaAM v3](https://huggingface.co/ai-sage/GigaAM-v3)
- [transcribe.cpp GigaAM documentation](https://github.com/handy-computer/transcribe.cpp/blob/main/docs/models/gigaam.md)

## Vocalinux

[Vocalinux](https://github.com/VocaHQ/vocalinux) is an independent AGPL-3.0
project. No Vocalinux source code is included here. This bridge interoperates
with Vocalinux through its optional Remote API interface.

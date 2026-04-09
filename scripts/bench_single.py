"""
Single-chunk manual benchmark — one config at a time.
Usage:
    python scripts/bench_single.py A
    python scripts/bench_single.py B
    ... etc.

Configs: A B C D E F G H
"""
import sys, time

CONFIG = sys.argv[1].upper() if len(sys.argv) > 1 else "A"

TEXT = (
    "KiCad is a free and open-source electronics design automation (EDA) suite. "
    "It features a schematic editor, PCB layout editor, and 3D viewer. "
    "KiCad supports a wide range of file formats and is used by hobbyists "
    "and professionals alike for designing printed circuit boards."
)
TEXTS = [TEXT]

print(f"Config: {CONFIG}")
print(f"Text length: {len(TEXT)} chars")
print()

import torch
print(f"PyTorch:  {torch.__version__}")
try:
    import onnxruntime as ort
    print(f"ORT:      {ort.__version__}")
    ONNX_OK = True
except ImportError:
    print("ORT:      NOT INSTALLED")
    ONNX_OK = False
print()

from sentence_transformers import SentenceTransformer

BATCH_MAP = {
    "A": (None,   "pytorch", None),
    "B": (8,      "pytorch", None),
    "C": (64,     "pytorch", None),
    "D": (128,    "pytorch", None),
    "E": (None,   "onnx",    None),
    "F": (8,      "onnx",    None),
    "G": (64,     "onnx",    None),
    "H": (128,    "onnx",    None),
}

batch_size, backend, _ = BATCH_MAP[CONFIG]

if backend == "onnx" and not ONNX_OK:
    print("SKIP — onnxruntime not installed")
    sys.exit(1)

# Load model
print(f"Loading model (backend={backend})...")
t0 = time.perf_counter()
kwargs = {"trust_remote_code": True}
if backend == "onnx":
    kwargs["backend"] = "onnx"

try:
    model = SentenceTransformer("Qwen/Qwen3-Embedding-0.6B", **kwargs)
    load_s = time.perf_counter() - t0
    print(f"  Load time: {load_s:.3f}s")
except Exception as e:
    print(f"  LOAD FAILED: {e}")
    sys.exit(1)

# Encode
print(f"Encoding 1 chunk (batch_size={batch_size})...")
enc_kwargs = {"normalize_embeddings": True, "show_progress_bar": False}
if batch_size is not None:
    enc_kwargs["batch_size"] = batch_size

t0 = time.perf_counter()
try:
    vecs = model.encode(TEXTS, **enc_kwargs)
    encode_s = time.perf_counter() - t0
    print(f"  Encode time: {encode_s:.3f}s")
    print(f"  Vector shape: {vecs.shape}")
    chunks_per_sec = 1.0 / encode_s if encode_s > 0 else 0
    print(f"  Chunks/sec:  {chunks_per_sec:.1f}")
except Exception as e:
    encode_s = time.perf_counter() - t0
    print(f"  ENCODE FAILED after {encode_s:.3f}s: {e}")
    sys.exit(1)

print()
print("DONE")

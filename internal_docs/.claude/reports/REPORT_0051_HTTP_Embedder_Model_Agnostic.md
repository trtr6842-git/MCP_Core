# REPORT 0051 — HTTP Embedder Model-Agnostic Refactor

**STATUS:** COMPLETE
**Instruction file:** *(none — chat-prompted session)*
**Date:** 2026-04-10

## Summary

Three related problems were fixed in the HTTP embedding probe and embedder in a single chat
session. The `HttpEmbedder` was hardcoded to the Qwen3 instruction-prefix format and the
probe hardcoded the Qwen3 model name, causing failures when connecting to non-Qwen3 servers
or servers (vLLM) that use a different model ID string. The probe also failed to detect
context length from vLLM's `max_model_len` field. The probe was redesigned to query
`/v1/models` *before* sending an embed request, auto-discovering both the model ID and
context length, eliminating wrong-model 404s entirely.

---

## Problems Addressed

### P1: Qwen3-specific instruction prefix applied to all models

`HttpEmbedder.embed_query()` unconditionally prepended:

```
Instruct: {instruction}\nQuery:{query}
```

This format is specific to Qwen3-Embedding and causes incorrect embeddings on other models
(e.g. BGE, E5, OpenAI-compatible endpoints). No way to disable it.

### P2: Probe hardcoded `_DEFAULT_MODEL` in the embed payload

`probe_embedding_endpoints()` always sent `"Qwen/Qwen3-Embedding-0.6B"` as the model name
regardless of what was configured in `embedding_endpoints.toml`. vLLM (and other strict
servers) reject unknown model names with a hard 404, producing ERROR-level stack traces in
the server logs.

### P3: vLLM context length not detected

The probe checked `max_context_length` (LM Studio) and `meta.n_ctx_train` (llama.cpp) but
not `max_model_len` (vLLM). vLLM's `/v1/models` response only contains `max_model_len`,
so context length always fell back to the conservative 8192-token default.

---

## Changes

### `src/kicad_mcp/semantic/http_embedder.py`

**`HttpEmbedder.__init__`** — added `use_instruction_prefix: bool = False` parameter.
Defaults to `False` so any model works without configuration. Stored as
`self._use_instruction_prefix`.

**`HttpEmbedder.embed_query`** — instruction prefix is now conditional:
```python
if self._use_instruction_prefix:
    text = f"Instruct: {effective_instruction}\nQuery:{query}"
else:
    text = query
```

**`probe_embedding_endpoints`** — redesigned to query `/v1/models` *first*, before sending
the embed probe. This provides the actual model ID and context length from the server,
avoiding a round-trip with the wrong model name. Priority chains:

| | model name | context length |
|---|---|---|
| 1st | explicit `model` in config | explicit `context_length` in config |
| 2nd | `id` field from `/v1/models` | `max_context_length` / `max_model_len` / `meta.n_ctx_train` |
| 3rd | `_DEFAULT_MODEL` | `_DEFAULT_CONTEXT_LENGTH` |

The probe now also writes the resolved `model` back into the returned config dict so
`server.py` can pass it to `HttpEmbedder` without re-discovering it.

Added `max_model_len` (vLLM) to the context length field lookup alongside the existing
`max_context_length` and `meta.n_ctx_train`.

### `src/kicad_mcp/server.py`

Both `HttpEmbedder` instantiation sites (query embedder and cache-rebuild embedder) updated
to pass:
- `model_name=http_config.get("model", "")`
- `use_instruction_prefix=http_config.get("instruction_prefix", False)`

### `config/embedding_endpoints.toml`

- Removed duplicate `http://192.168.0.153:8082` entry that existed only to work around the
  wrong model name. Auto-discovery makes it unnecessary.
- Dropped explicit `model` keys from the two llama.cpp-served endpoints (localhost and LAN)
  so the probe auto-discovers the serving model's actual ID.
- Added `instruction_prefix = true` to all Qwen3-serving endpoints.
- Added a field documentation block at the top of the file explaining all supported keys.

### `tests/test_http_embedder.py`

- Renamed `test_embed_query_applies_instruction_prefix` →
  `test_embed_query_applies_instruction_prefix_when_enabled` (requires
  `use_instruction_prefix=True` explicitly).
- Added `test_embed_query_no_prefix_by_default` — verifies raw query is sent without prefix.
- Added `test_embed_query_custom_instruction_ignored_without_prefix`.
- Added `test_probe_discovers_model_from_v1_models_when_not_configured`.
- Added `test_probe_config_model_takes_priority_over_discovered`.
- Added `test_context_length_from_vllm_max_model_len`.

Total: 50 tests, all passing.

---

## Observed Trigger

vLLM server logs from `http://192.168.0.153:8082` showed a 404 with:
```
VLLMNotFoundError: The model `Qwen3-Embedding-0.6B-Q8_0.gguf` does not exist.
```
The vLLM instance serves the model as `qwen3-embedding-0.6b`. The workaround at the time
was two duplicate TOML entries for the same URL with different model strings. The redesigned
probe eliminates the need for that workaround entirely.

Context length detection for the same endpoint was returning 8192 (default) because vLLM
reports `max_model_len: 32768` — a field name the old probe did not check.

---

## Notes

- `_DEFAULT_MODEL` is retained as a last-resort fallback but will rarely be reached now that
  `/v1/models` is queried first.
- The `use_instruction_prefix` flag is not auto-detected from the model name — it remains an
  explicit opt-in in the TOML config. This keeps the probe model-agnostic without requiring
  a model-name allowlist.
- `embed()` (batch document embedding for cache rebuilds) is unaffected — the instruction
  prefix only applies to `embed_query()`.

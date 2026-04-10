# Maintainer Guide — KiCad MCP Server

## Updating documentation caches

When KiCad releases a new version or the docs are updated:

1. Update the pinned ref in `config/doc_pins.toml`
2. Delete the stale `docs_cache/{version}/` directory
3. Start the server with an HTTP embedding endpoint configured
   (see `config/embedding_endpoints.toml`)
4. The server will:
   - Clone the docs from GitLab at the pinned ref
   - Embed all chunks via the HTTP endpoint
   - Save the new cache
5. Commit the updated `docs_cache/` and `embedding_cache/` files:
   ```
   git add docs_cache/ embedding_cache/
   git commit -m "Update docs + embeddings for vX.Y"
   git push
   ```

**Note:** Before committing `docs_cache/`, strip the embedded `.git` directory
from the clone so git does not treat it as a submodule:

```bash
rm -rf docs_cache/{version}/.git
git add docs_cache/{version}/
```

## LFS setup (first-time per machine)

```bash
git lfs install
```

LFS tracking is configured in `.gitattributes`. Any `.npy`, `.json` under
`embedding_cache/`, and all files under `docs_cache/` are tracked via LFS.

## Adding a new KiCad version

1. Add the new version to `config/doc_pins.toml`
2. Follow the cache rebuild steps above for the new version
3. Keep old version caches committed — end users may query either version

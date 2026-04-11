# Multi-Source Framework — Pluggable Documentation Sources

> Design document for extending the KiCad MCP Server to support multiple
> documentation sources through a unified virtual filesystem.

## Motivation

The server currently indexes one documentation source: the official kicad-doc
repository. Engineers also need access to the KiCad Library Conventions (KLC),
the KiCad Libraries GitLab Wiki, and potentially other sources (Markdown docs,
PDFs, scraped reference pages). Each source has a different format, structure,
and URL scheme.

Rather than building a separate integration for each source, this document
defines a framework where adding a new source requires only the format-specific
parsing logic. Everything else — git cloning, embedding, caching, search,
CLI navigation — is shared infrastructure.

## Design principle: unified virtual filesystem

Following the Manus post design philosophy (see DESIGN_INFLUENCES.md), the
server exposes a CLI interface where paths work like a filesystem. Adding a
doc source adds a **mount point**, not a command group. All sources are
navigated through the existing `docs` command group with `search`, `read`,
and `list` subcommands.

### Why unified paths, not separate command groups

The rejected alternative was separate command groups per source:
```
kicad docs search "pad"        # searches kicad-doc only
kicad klc search "pad"         # searches KLC only
```

This was rejected because:

1. **It breaks the Unix CLI metaphor.** The Manus principle says: one
   namespace, composable via pipes. Separate command groups create N
   parallel filesystems with different syntax and no cross-source
   composition.

2. **Pipes can't compose across groups.** You can't do
   `kicad search "pad" | grep silkscreen` across both sources.

3. **It's the "catalog of typed function calls" anti-pattern** from the
   Manus post — just hidden behind subcommand names instead of tool names.
   Each new source would add cognitive load for Claude (which syntax? which
   path format?).

4. **Search results can't be mixed.** If Claude searches for "silkscreen
   requirements," it should get the KLC rule F5.1 alongside the pcbnew
   docs section, each with a copy-pasteable `read` command in the same
   path syntax.

### The virtual filesystem

All doc sources mount into a single path tree:

```
/                               # root
├── pcbnew/                     # guide (from kicad-doc, mounted at root)
│   ├── Board Setup
│   ├── Constraints
│   └── ...
├── eeschema/                   # guide (from kicad-doc, mounted at root)
│   └── ...
├── klc/                        # source (from KLC repo, mounted at klc/)
│   ├── general/
│   │   ├── G1/
│   │   │   ├── G1.1
│   │   │   └── ...
│   │   └── G2/
│   ├── symbol/
│   │   └── S1/ ... S7/
│   ├── footprint/
│   │   └── F1/ ... F9/
│   └── model/
│       └── M1/ ... M2/
├── wiki/                       # future: KiCad libraries wiki
│   └── ...
└── ...
```

### Commands — unchanged interface, larger tree

```
kicad docs list                              # all top-level entries (guides + sources)
kicad docs list klc                          # KLC categories
kicad docs list klc/symbol                   # KLC symbol rules
kicad docs read klc/footprint/F5/F5.1        # read a KLC rule
kicad docs read pcbnew/Board Setup           # unchanged — kicad-doc section
kicad docs search "silkscreen"               # searches EVERYTHING
kicad docs search "silkscreen" --guide klc   # scoped to KLC
kicad docs search "pad" --guide pcbnew       # scoped to pcbnew (unchanged)
```

### Backward compatibility

Existing kicad-doc guides mount directly at root — no prefix. Every existing
path (`pcbnew/Board Setup`, `eeschema/Symbols`, etc.) continues to work
unchanged. New sources mount at named prefixes (`klc/`, `wiki/`, etc.).

This is analogous to how Linux mounts the root filesystem at `/` and additional
filesystems at `/mnt/whatever`.

### Alias resolution

KLC rules are universally known by their ID (`G1.1`, `S4.3`, `F5.1`). The
full path `klc/footprint/F5/F5.1` is verbose for CLI usage. The system
supports shorthand:

```
kicad docs read klc/F5.1        # shorthand — expands to klc/footprint/F5/F5.1
kicad docs read klc/S4.3        # shorthand — expands to klc/symbol/S4/S4.3
```

Alias resolution is per-source. When a path starts with `klc/` and the
second segment matches a rule ID pattern (`[GSFM]\d+\.\d+`), the system
expands it to the full path. Other sources define their own aliases (or none).

## Framework components

### 1. `Section` dataclass — universal representation

Every loader produces the same normalized output:

```python
@dataclass
class Section:
    id: str              # unique within the source, e.g. "G1.1", "Board Setup"
    title: str           # display title
    content: str         # raw text content (stripped of format-specific markup)
    level: int           # hierarchy depth (for tree display)
    parent_id: str | None  # parent section ID (for tree construction)
    source_file: str     # relative path within source repo
    metadata: dict       # source-specific extras (anchor, rule_id, weight, etc.)
```

Everything downstream of the loader operates on `Section` lists. No code
outside the loader knows about AsciiDoc headings, Hugo front matter, or
Markdown syntax.

### 2. `Loader` protocol — format-specific parsing

```python
class Loader(Protocol):
    def load(self, source_root: Path) -> list[Section]:
        """Parse all content files and return normalized sections."""
        ...
```

Concrete implementations:

- **`AsciiDocHeadingLoader`** — current kicad-doc logic. Parses `==`/`===`/`====`
  heading hierarchy, follows `include::` directives, extracts `[[anchor-id]]`
  patterns. Strips `image::` and `//` comment lines.

- **`HugoAsciiDocLoader`** — KLC logic. Walks `content/` directory structure.
  Parses Hugo TOML front matter (`+++...+++`) to extract title and weight.
  Derives hierarchy from directory nesting. Each non-`_index` `.adoc` file
  becomes one Section. The rule ID is extracted from the filename.

- **Future:** `MarkdownLoader`, `RstLoader`, `HtmlLoader`, `PdfExtractLoader`

### 3. `UrlBuilder` protocol — canonical web URLs

```python
class UrlBuilder(Protocol):
    def build_url(self, section: Section, version: str | None = None) -> str:
        """Return the canonical web URL for a section."""
        ...
```

Concrete implementations:

- **`KicadDocUrlBuilder`** — deterministic formula:
  `https://docs.kicad.org/{version}/en/{guide}/{guide}.html#{anchor}`

- **`KlcUrlBuilder`** — deterministic formula:
  `https://klc.kicad.org/{category}/{group}/{rule_id}.html`
  (e.g., `https://klc.kicad.org/footprint/f5/f5.1.html`)

For simple sources, the URL builder may just be a template string with
section metadata interpolation.

### 4. `DocSource` descriptor — declarative config

```python
@dataclass
class DocSource:
    name: str                    # mount point name, e.g. "klc"
    display_name: str            # "Library Conventions (KLC)"
    clone_url: str               # git repo URL
    default_ref: str             # branch/tag to clone, e.g. "master"

    loader: Loader               # parse files → Section list
    chunker: Chunker             # sections → Chunk list
    url_builder: UrlBuilder      # section → canonical web URL

    versioned: bool = False      # does this source have version branches?
    versions: dict[str, str] | None = None  # version → git ref mapping
    content_root: str = ""       # subdirectory within repo (e.g. "content" for KLC, "src" for kicad-doc)
    aliases: dict[str, str] | None = None   # shorthand → full path mappings (or a resolver callable)
```

### 5. `Chunker` protocol — unchanged

The existing `Chunker` protocol already supports this diversity:

```python
class Chunker(Protocol):
    def chunk(self, sections: list[dict], guide: str) -> list[Chunk]:
        ...
```

For kicad-doc: `AsciiDocChunker` with D2 prose-flush (handles large sections).
For KLC: A simple "one section = one chunk" chunker (rules are 100–500 words,
already ideal embedding size). The breadcrumb prefix format adapts per source.

### 6. `DocIndex` as virtual filesystem

The current `DocIndex` loads guides from one source. Refactored to mount
multiple sources:

```python
class DocIndex:
    def mount(self, mount_point: str, sections: list[Section],
              url_builder: UrlBuilder):
        """Mount a source's sections at the given path prefix.

        mount_point="" means sections are mounted at root (kicad-doc guides).
        mount_point="klc" means sections are accessible under klc/.
        """
        ...

    # list_sections, get_section, search — operate on the merged tree
    # --guide filter matches against mount_point or first path segment
```

kicad-doc guides mount with `mount_point=""` — their paths remain `pcbnew/...`,
`eeschema/...` without any prefix.

New sources mount with a named prefix — KLC sections accessible as `klc/...`.

### 7. Semantic search across the merged tree

All sources' chunks feed into one `VectorIndex`. The `guide` field on each
`Chunk` carries the mount point prefix. Search is cross-source by default;
`--guide` narrows to a subtree.

Embedding happens per-source (different chunkers produce different chunks),
but the resulting vectors merge into one index. Cache namespacing by source
name ensures independent rebuilds.

Cross-source reranking works naturally — the cross-encoder scores
`(query, document)` pairs on relevance regardless of writing style.

### 8. Configuration — `sources.toml`

```toml
[sources.kicad-doc]
display_name = "KiCad Documentation"
clone_url = "https://gitlab.com/kicad/services/kicad-doc.git"
loader = "asciidoc_heading"
chunker = "asciidoc"
content_root = "src"
versioned = true

[sources.kicad-doc.versions]
"10.0" = { ref = "10.0", default = true }
"9.0"  = { ref = "9.0" }

[sources.klc]
display_name = "Library Conventions (KLC)"
clone_url = "https://gitlab.com/kicad/libraries/klc.git"
loader = "hugo_asciidoc"
chunker = "one_per_section"
content_root = "content"
ref = "master"
versioned = false
```

## KLC source: specifics

### Source repository

- **Repo:** `https://gitlab.com/kicad/libraries/klc`
- **License:** Creative Commons Attribution 3.0 Unported
- **Format:** Hugo static site with AsciiDoc (`.adoc`) content files
- **Build:** Hugo + AsciiDoctor → `https://klc.kicad.org`

### Content structure

```
content/
├── _index.adoc                          # KLC home / intro
├── history.adoc                         # revision history
├── general/
│   ├── _index.adoc                      # "Generals" category page (mostly empty)
│   ├── G1/
│   │   ├── _index.adoc                  # "G1 General Guidelines" group page
│   │   ├── G1.1.adoc                    # individual rule
│   │   ├── G1.2.adoc
│   │   └── ...G1.11.adoc
│   ├── G2/
│   │   └── G2.1.adoc
│   └── G3/
│       ├── G3.1.adoc
│       └── G3.2.adoc
├── symbol/
│   ├── S1/ ... S7/                      # same nested pattern
├── footprint/
│   ├── F1/ ... F9/
└── model/
    ├── M1/ ... M2/
```

### Key differences from kicad-doc

| Aspect | kicad-doc | KLC |
|--------|-----------|-----|
| Structure | Deep nested `.adoc` with `include::` directives | Flat: one `.adoc` per rule, ~70 files |
| Sections per file | Dozens of headings per file | 1 heading (rule title), body is rule text |
| Total content | ~775 sections across 9 guides | ~70 rules across 4 categories |
| Anchors | `[[anchor-id]]` patterns | Hugo front matter + filename-based URLs |
| URL pattern | `docs.kicad.org/{ver}/en/{guide}/{guide}.html#{anchor}` | `klc.kicad.org/{category}/{group}/{rule}.html` |
| Versioning | Branches per KiCad version | Single `master` branch (KLC v3.0.64) |
| Format quirks | Standard AsciiDoc heading hierarchy | Hugo TOML front matter (`+++...+++`) |

### Chunking strategy for KLC

Each rule IS the chunk. Most rules are 100–500 words — already ideal for
embedding. The chunker emits one chunk per rule file with a breadcrumb:
`[klc > Footprints > F5 Layer Requirements > F5.1 Silkscreen layer requirements]`

For rare long rules, split on sub-headings or list boundaries, but keep
the rule ID in every chunk.

### URL builder for KLC

```python
def make_klc_url(category: str, group: str, rule_id: str) -> str:
    return f"https://klc.kicad.org/{category}/{group.lower()}/{rule_id.lower()}.html"
```

### Alias table for KLC

Rule IDs map deterministically to full paths:
- `G1.1` → `klc/general/G1/G1.1`
- `S4.3` → `klc/symbol/S4/S4.3`
- `F5.1` → `klc/footprint/F5/F5.1`
- `M1.1` → `klc/model/M1/M1.1`

Pattern: first letter determines category (`G`=general, `S`=symbol,
`F`=footprint, `M`=model). The group is the part before the dot
(e.g., `S4`). The full rule ID is the filename.

## What's plug-and-play vs. custom per source

### Must write (source-specific):
- A `Loader` implementation (the format-specific parsing logic)
- A `UrlBuilder` (often just a template string)
- Possibly a `Chunker` if the default "one section = one chunk" doesn't fit

### Gets for free (framework infrastructure):
- Git clone/cache management
- Embedding pipeline (batching, caching, HTTP/local fallback)
- VectorIndex construction and cross-source search
- CLI navigation (`search`/`read`/`list`) with filters (grep/head/tail)
- Embedding cache with content-hash invalidation
- Startup wiring and logging
- Error-as-navigation on all commands
- Metadata footer with source attribution

### Lightweight config (no code):
- Alias definitions (pattern-based or static mapping)
- `sources.toml` entry

## Migration path

1. Define `Section` dataclass and `Loader` protocol
2. Refactor `doc_loader.py` → `AsciiDocHeadingLoader` satisfying protocol
3. Refactor `DocIndex` to accept mounted sources instead of raw guide dirs
4. Verify all existing tests pass (paths unchanged, kicad-doc at root)
5. Build `HugoAsciiDocLoader` for KLC
6. Build `KlcUrlBuilder`
7. Mount KLC at `klc/` prefix — `kicad docs list klc` works
8. Add KLC alias resolution for rule IDs
9. Add `sources.toml` config
10. Build KLC embedding cache

**Steps 1–4 are pure refactors with zero user-visible changes.** Existing
tests are the regression safety net. Step 7 is where the framework proves
itself.

## Future sources (no work now, no architecture blockers)

- **KiCad Libraries GitLab Wiki** — Markdown or AsciiDoc pages with practical
  guidance beyond the KLC formal rules
- **Datasheets / app notes** — PDF extraction for component-specific reference
- **KiCad file format specification** — developer documentation
- **User-contributed guides** — Markdown documentation from the community

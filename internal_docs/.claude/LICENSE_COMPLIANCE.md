# License Compliance — Corpus Sources

> Status: **Open — action required.** This document tracks what the source
> licenses require and what this project currently does or does not do to
> satisfy those requirements.

---

## Source corpus

| Source | Repository | Versions used |
|--------|-----------|---------------|
| KiCad Documentation | `https://gitlab.com/kicad/services/kicad-doc.git` | `10.0` (default), `9.0` (legacy) |

There is currently one corpus source. All documentation content originates
from the official KiCad project.

---

## Source license

The KiCad documentation is **dual-licensed**. The licensee may choose either:

1. **GNU General Public License v3 or later (GPLv3+)**
   Full text: `docs_cache/{version}/LICENSE.GPLv3`
   Reference: http://www.gnu.org/licenses/gpl.html

2. **Creative Commons Attribution 3.0 Unported (CC-BY 3.0) or later**
   Full text: `docs_cache/{version}/LICENSE.CC-BY`
   Reference: http://creativecommons.org/licenses/by/3.0/

Official license page: http://kicad.org/about/licenses/

This project has **not yet made an explicit license election**. The choice
must be recorded before any public distribution.

---

## How this project uses the source

This project uses the KiCad documentation in three distinct ways, each
of which has different license implications:

### 1. Verbatim distribution (git submodules / Git LFS)

The full documentation source trees are committed as git submodules under
`docs_cache/10.0/` and `docs_cache/9.0/` and distributed via Git LFS to
all users who clone the repository.

This is **reproduction and distribution** of the Work under both CC-BY
and GPLv3. The upstream license files (`LICENSE.adoc`, `LICENSE.CC-BY`,
`LICENSE.GPLv3`) are present in those directories, so the verbatim copy
requirement is met at the submodule level — but the project root provides
no attribution or license notice pointing to them.

### 2. Derived embedding caches (Git LFS)

The embedding pipeline chunks the AsciiDoc source into prose segments,
stores the chunk text in metadata JSON files, and saves pre-computed
embedding vectors as `.npy` files. These are committed to Git LFS under
`embedding_cache/` and distributed with the repository.

The chunked text in the metadata JSON files is recognizably derived from
the original Work. Whether the `.npy` vector arrays constitute an
"Adaptation" under CC-BY is legally uncertain — mathematical
transformations do not produce text recognizable as the original — but
the JSON metadata clearly does.

Under CC-BY, an Adaptation must: (a) carry a notice that changes were
made, (b) keep intact all copyright notices, and (c) include attribution
(see requirements below).

### 3. Runtime serving via MCP (public performance)

The MCP server reads and returns documentation content to connected
clients. When deployed on a shared LAN (Stage 2 and beyond), this
constitutes **public performance** under CC-BY §1(h): making works
available "in such a way that members of the public may access these
Works from a place and at a place individually chosen by them."

Public performance requires attribution to be provided "reasonable to
the medium" (CC-BY §4b). The server's tool results currently include a
metadata footer with the source URL (`[kicad-docs 10.0 | … |
https://docs.kicad.org/…]`) but do not include a copyright notice or
explicit attribution to the KiCad project.

---

## Requirements by license path

### Path A — CC-BY 3.0

These requirements apply when distributing, reproducing, or publicly
performing the Work (§4):

| Requirement | Where it applies | Current status |
|-------------|-----------------|----------------|
| Attribute the original author (KiCad project) | Every distribution and public performance | **Missing from project root and tool responses** |
| Include the title of the Work | Every distribution | **Missing from project root** |
| Include URI/copy of the CC-BY license | Every distribution | Fulfilled inside submodule dirs; **missing from project root** |
| Keep all copyright notices intact | Adaptations and Collections | Fulfilled inside submodule dirs |
| Mark Adaptations as changed | Embedding cache JSON (chunked text) | **Missing** |
| No sublicensing | All uses | OK — no sublicense attempted |
| No derogatory modification | All uses | OK |

### Path B — GPLv3+

| Requirement | Where it applies | Current status |
|-------------|-----------------|----------------|
| Include the full GPLv3 license text | Every distribution | Fulfilled inside submodule dirs; **missing from project root** |
| Preserve copyright notices | Every distribution | Fulfilled inside submodule dirs |
| Corresponding source available | If distributing binaries/object code | N/A — source-only distribution |
| Downstream recipients receive GPLv3 rights | Every distribution | Not communicated at project root level |

---

## Specific items that need to be addressed

The following are the concrete gaps, ordered by scope of impact:

### 1. Elect a license

Decide whether this project uses the corpus under **CC-BY 3.0** or
**GPLv3+** and record that decision in this document and in the project's
own `LICENSE` file (or `NOTICE` file). CC-BY 3.0 is the simpler path for
a server that serves content at runtime; GPLv3+ adds source-availability
obligations that are already met (the server is open source).

Recommendation: elect **CC-BY 3.0** for simplicity. Document the election.

### 2. Add attribution to the project root

Create a `NOTICE` file (or equivalent section in `README.md`) at the
repository root containing:

- The name of the original work: *KiCad Documentation*
- The copyright holder: *The KiCad Project*
- The license elected (CC-BY 3.0 or GPLv3+) with its URI
- A pointer to where the full license text can be found

Example for CC-BY path:

```
This repository includes content from the KiCad Documentation,
copyright The KiCad Project (https://www.kicad.org/).
Licensed under the Creative Commons Attribution 3.0 Unported License.
License text: docs_cache/{version}/LICENSE.CC-BY
https://creativecommons.org/licenses/by/3.0/
```

### 3. Add attribution to tool responses

When the MCP server returns documentation content to users it is publicly
performing the Work. The attribution must be "reasonable to the medium."
The existing metadata footer (`[kicad-docs 10.0 | N results |
https://docs.kicad.org/…]`) satisfies the URI requirement but not the
author/copyright credit requirement.

The footer should be updated to include something like:

```
[kicad-docs 10.0 | © The KiCad Project | CC-BY 3.0 | https://docs.kicad.org/…]
```

This is a one-line change in the presentation layer.

### 4. Mark embedding cache as an Adaptation

The metadata JSON files in `embedding_cache/` contain chunked text
derived from the original AsciiDoc source. Under CC-BY §3(b), Adaptations
must "take reasonable steps to clearly label, demarcate or otherwise
identify that changes were made."

Add a `LICENSE` or `attribution.json` file to each
`embedding_cache/{version}/` directory stating that the chunk text is
derived from the KiCad Documentation under CC-BY 3.0, that the text has
been chunked and that original content is unmodified within each chunk.

### 5. Update README

Add a "Documentation Source" section to `README.md` that names the
upstream corpus, its license, and where to find the license texts. This
is good practice independent of legal obligation and makes the
attribution visible to anyone who clones the repo.

---

## What is already satisfied

- License files are present inside the submodule directories
  (`docs_cache/{version}/LICENSE.*`), so verbatim copies of the Work
  carry their licenses.
- Tool results include a source URL linking back to the official KiCad
  documentation site.
- The AsciiDoc source is served without modification (no derogatory
  alteration).
- Embedding caches link each chunk back to its source section via
  `section_path`.

---

## References

- KiCad license page: http://kicad.org/about/licenses/
- CC-BY 3.0 full text: `docs_cache/10.0/LICENSE.CC-BY`
- GPLv3 full text: `docs_cache/10.0/LICENSE.GPLv3`
- Dual-license statement: `docs_cache/10.0/LICENSE.adoc`

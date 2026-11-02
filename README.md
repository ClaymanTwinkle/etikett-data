# etikett-data

Offline product database for the Klarblik app (ingredient scanner for Sweden, Denmark and Finland).

Every Monday a GitHub Action filters the [Open Food Facts](https://world.openfoodfacts.org) export down to products sold in Sweden, Denmark or Finland that have an ingredient list, and publishes the result to the release [`products-latest`](../../releases/tag/products-latest):

- `products.json.zlib` – JSON compressed with raw deflate (no zlib header)
- `manifest.json` – version (build date), product count, byte size and SHA-256 of `products.json.zlib`

Format:

```json
{"version": "2026-11-02", "license": "...", "products": {"<barcode>": ["name", "quantity", "brand", "front image path", {"sv": "ingredients", "da": "...", "fi": "...", "en": "...", "main": "..."}]}}
```

- Ingredient texts are kept in Swedish, Danish, Finnish and English; `main` is the product's main-language text, stored only when it differs from those.
- Allergen markup from Open Food Facts (`<span class="allergen">`, `_word_`) is removed.
- The image path is relative to `https://images.openfoodfacts.org/images/products/`.

Build it yourself: see the docstring in [`tools/build_products.py`](tools/build_products.py).

## License

**Data** (the published `products.json.zlib`): contains information from Open Food Facts, made available under the [Open Database License (ODbL) 1.0](https://opendatacommons.org/licenses/odbl/1-0/) (full text in [`LICENSE`](LICENSE)); individual contents are under the [Database Contents License (DbCL) 1.0](https://opendatacommons.org/licenses/dbcl/1-0/). This filtered database is published under the same ODbL 1.0.

**Code** (everything in [`tools/`](tools/) and [`.github/`](.github/)): [PolyForm Noncommercial License 1.0.0](tools/LICENSE). Free for personal, research and other noncommercial use; commercial use is not permitted.

Required Notice: Copyright kesar (https://github.com/ClaymanTwinkle)

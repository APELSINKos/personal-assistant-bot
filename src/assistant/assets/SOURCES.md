# Card assets

The pictures (`assistant/core/services/cards.py` and `money_cards.py`) draw with these files only. They are copied
unchanged from their upstream repositories at the commits below; `SHA256SUMS` lists every file.

| Files | Upstream | License |
|---|---|---|
| `fonts/Manrope.ttf` | `google/fonts` @ `9710da1e`, `ofl/manrope/Manrope[wght].ttf` | SIL Open Font License 1.1, `fonts/Manrope-OFL.txt` |
| `fonts/Unbounded.ttf` | `google/fonts` @ `9710da1e`, `ofl/unbounded/Unbounded[wght].ttf` | SIL Open Font License 1.1, `fonts/Unbounded-OFL.txt` |
| `fonts/Onest.ttf` | `google/fonts` @ `9710da1e`, `ofl/onest/Onest[wght].ttf` | SIL Open Font License 1.1, `fonts/Onest-OFL.txt` |
| `emoji/emoji_u*.png` (63: habits and money categories) | `googlefonts/noto-emoji` @ `e20cbc2b`, `2D/png/128/` | SIL Open Font License 1.1 (the repository's `LICENSE`), `emoji/LICENSE.txt`; Apache 2.0 (its README), `emoji/LICENSE-APACHE-2.0.txt` |

Onest (version 2.001, 193,056 bytes) is the fallback font: it draws, in the same line, the letters of a name that
Manrope lacks — the Kazakh Ә Ғ Қ Ң Ұ, the other Cyrillic letters of the CIS countries, ʼ and ʻ.

The emoji images follow the repository's `LICENSE`, which upstream changed from Apache 2.0 to the
OFL in `254596e5` (2024-07-29); the License section of its README still names Apache 2.0 for most
images, so both texts are kept: `emoji/LICENSE-APACHE-2.0.txt` is that `LICENSE` as it was before
the change (`41e31b11`).

Check them with `sha256sum -c SHA256SUMS` from this folder.

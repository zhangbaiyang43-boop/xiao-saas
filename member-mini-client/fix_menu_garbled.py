# -*- coding: utf-8 -*-
"""One-time fix for garbled static Chinese in menu.vue template."""
import re
from pathlib import Path

path = Path(__file__).parent / "src/subpkg-order/pages/menu.vue"
content = path.read_text(encoding="utf-8")
original = content

# Exact replacements: (old, new) — user-visible static text only
REPLACEMENTS = [
    ('<text class="shop-meta-dot">闂?</text>', '<text class="shop-meta-dot">·</text>'),
    ('<text class="shop-meta-arrow">闂?</text>', '<text class="shop-meta-arrow">›</text>'),
    ('<text class="reorder-label">濠电姷鏁搁崑鐐哄垂閸\u033c洖绠伴柟闂寸劍閺呮繈鏌曟径鍡樻珦闁轰礁鍟\u0082埞鎴﹀磼濮橆厼鏆堥梺绋匡功閸忔ê顫忓ú顏嶆晝闁挎繂娲㈤埀顒佸浮閺?</text>', '<text class="reorder-label">上次点过</text>'),
]

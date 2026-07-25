"""A small hand-built pictogram set for the HTML report - trailhead-sign
style monoline glyphs instead of emoji, so the report renders identically
everywhere and doesn't lean on a platform's emoji font.

Each symbol is defined once in an SVG sprite sheet (`sprite_defs()`) and
referenced by `<use>` wherever it appears (`use(name)`), the standard
"icon sprite" pattern - keeps the HTML light regardless of how many times
an icon repeats.

Weather/stat glyphs (sun, cloud, rain, storm, thermometer, wind, wave,
whale, bluebottle) carry their own fixed colour baked into the symbol,
rather than inheriting `currentColor` - they read as "the sun", "a
thermometer", etc, not as generic outline marks, and stay legible in both
themes without per-instance overrides. Activity pictograms stay
currentColor so they still pick up the accent tint from their surroundings.
"""

from __future__ import annotations

SYMBOLS: dict[str, str] = {
    # --- activities (currentColor - tinted by their wrapper) -----------
    "climbing": """
        <polyline points="3,19 9,9 12,13 16,6 21,19" />
        <circle cx="13" cy="10.5" r="1.1" fill="currentColor" stroke="none"/>
    """,
    "hiking": """
        <circle cx="8.5" cy="5" r="1.6" fill="currentColor" stroke="none"/>
        <line x1="8.5" y1="7" x2="10" y2="13"/>
        <line x1="10" y1="13" x2="7" y2="20"/>
        <line x1="10" y1="13" x2="14" y2="19"/>
        <line x1="9" y1="9" x2="15" y2="12"/>
        <line x1="15" y1="12" x2="17" y2="20"/>
    """,
    "swimming": """
        <circle cx="7" cy="9" r="1.4" fill="currentColor" stroke="none"/>
        <path d="M8 10c2 1 3 3 6 2"/>
        <path d="M2 18c2-2 4-2 6 0s4 2 6 0 4-2 6 0"/>
    """,
    "snorkelling": """
        <ellipse cx="11" cy="12" rx="5" ry="4"/>
        <path d="M6 11c-2-1-3 0-3 2"/>
        <path d="M16 8c1-2 3-2 3 0v3"/>
    """,
    "scuba": """
        <ellipse cx="10" cy="11" rx="4.5" ry="4"/>
        <path d="M15 9c1.5-1 3 0 3 2s-1.5 2-1.5 2"/>
        <rect x="9" y="18" width="6" height="3" rx="1"/>
        <circle cx="16" cy="4" r="1.6" fill="currentColor" stroke="none"/>
        <path d="M15 5.4c-1 1-1.5 2.4-1.5 4"/>
    """,
    "surfing": """
        <ellipse cx="13" cy="9" rx="7" ry="2" transform="rotate(-28 13 9)"/>
        <path d="M2 18c2-2 4-2 6 0s4 2 6 0 4-2 6 0"/>
    """,
    "kayaking": """
        <path d="M2 15c3 3 17 3 20 0-3 4-17 4-20 0Z"/>
        <line x1="5" y1="6" x2="17" y2="16"/>
        <ellipse cx="5" cy="6" rx="1.6" ry="0.9" transform="rotate(-40 5 6)"/>
        <ellipse cx="17" cy="16" rx="1.6" ry="0.9" transform="rotate(-40 17 16)"/>
    """,
    "kitesurfing": """
        <path d="M12 2 L17 8 L12 12 L7 8 Z"/>
        <line x1="12" y1="12" x2="9" y2="20"/>
        <ellipse cx="8" cy="21" rx="3" ry="1"/>
    """,
    "sailing": """
        <line x1="12" y1="3" x2="12" y2="17"/>
        <path d="M12 4 L12 13 L5 13Z"/>
        <path d="M4 17c2 2 14 2 16 0-2 3-14 3-16 0Z"/>
    """,
    "city_touring": """
        <rect x="3" y="12" width="4" height="9"/>
        <rect x="9" y="6" width="4" height="15"/>
        <rect x="15" y="9" width="4" height="12"/>
        <line x1="2" y1="21" x2="22" y2="21"/>
    """,
    "beach_day": """
        <line x1="12" y1="10" x2="12" y2="21"/>
        <path d="M4 10a8 8 0 0 1 16 0Z"/>
        <line x1="4" y1="10" x2="20" y2="10"/>
        <path d="M5 21c2-2 4-2 6 0s4 2 6 0"/>
    """,
    # --- sky / condition (fixed colour) ---------------------------------
    "sky-clear": """
        <circle cx="12" cy="12" r="4.4" fill="#eaa227" stroke="none"/>
        <g stroke="#eaa227" stroke-width="1.8">
        <line x1="12" y1="2.5" x2="12" y2="5"/>
        <line x1="12" y1="19" x2="12" y2="21.5"/>
        <line x1="2.5" y1="12" x2="5" y2="12"/>
        <line x1="19" y1="12" x2="21.5" y2="12"/>
        <line x1="5.2" y1="5.2" x2="7" y2="7"/>
        <line x1="17" y1="17" x2="18.8" y2="18.8"/>
        <line x1="5.2" y1="18.8" x2="7" y2="17"/>
        <line x1="17" y1="7" x2="18.8" y2="5.2"/>
        </g>
    """,
    "sky-partly": """
        <circle cx="16.5" cy="6.5" r="3.2" fill="#eaa227" stroke="none"/>
        <g stroke="#eaa227" stroke-width="1.6">
        <line x1="16.5" y1="1.3" x2="16.5" y2="2.6"/>
        <line x1="21.7" y1="6.5" x2="20.4" y2="6.5"/>
        <line x1="20.1" y1="2.9" x2="19.2" y2="3.8"/>
        </g>
        <path d="M4 18a4 4 0 0 1 1-7.9 5 5 0 0 1 9.6-1.6A4.5 4.5 0 0 1 15 18Z" fill="#8894a1" fill-opacity="0.9" stroke="#8894a1"/>
    """,
    "sky-cloudy": """
        <path d="M6 17a4 4 0 0 1 .6-8 5.5 5.5 0 0 1 10.6-1.2A4.5 4.5 0 0 1 17 17Z" fill="#8894a1" fill-opacity="0.9" stroke="#8894a1"/>
    """,
    "sky-rain": """
        <path d="M6 14a4 4 0 0 1 .6-8 5.5 5.5 0 0 1 10.6-1.2A4.5 4.5 0 0 1 17 14Z" fill="#8894a1" fill-opacity="0.9" stroke="#8894a1"/>
        <g stroke="#4a86c9" stroke-width="1.8">
        <line x1="8" y1="17" x2="7" y2="20.5"/>
        <line x1="12" y1="17" x2="11" y2="20.5"/>
        <line x1="16" y1="17" x2="15" y2="20.5"/>
        </g>
    """,
    "sky-storm": """
        <path d="M6 13a4 4 0 0 1 .6-8 5.5 5.5 0 0 1 10.6-1.2A4.5 4.5 0 0 1 17 13Z" fill="#7c7690" fill-opacity="0.9" stroke="#7c7690"/>
        <polyline points="12.5,12.5 9.5,17.5 12.5,17.5 10.5,22" fill="#7a63c9" stroke="#7a63c9" stroke-width="1.8"/>
    """,
    # --- stat chips (fixed colour) ---------------------------------------
    "temp": """
        <rect x="10" y="3" width="4" height="11" rx="2" stroke="#d85c3f"/>
        <circle cx="12" cy="17" r="3.4" fill="#d85c3f" stroke="#d85c3f"/>
        <line x1="12" y1="6" x2="12" y2="15" stroke="#d85c3f" stroke-width="2"/>
    """,
    "wind": """
        <g stroke="#2f9a92">
        <path d="M3 9h9a2.5 2.5 0 1 0-2.2-3.7"/>
        <path d="M3 13h13a2.5 2.5 0 1 1-2.2 3.7"/>
        <path d="M3 17h7"/>
        </g>
    """,
    "wave": """
        <g stroke="#2f8fbf">
        <path d="M2 14c2-2 4-2 6 0s4 2 6 0 4-2 6 0"/>
        <path d="M2 18c2-2 4-2 6 0s4 2 6 0 4-2 6 0" opacity="0.55"/>
        </g>
    """,
    "sea-temp": """
        <rect x="10" y="2" width="4" height="9" rx="2" stroke="#1f6f96"/>
        <circle cx="12" cy="14.5" r="3.2" fill="#1f6f96" stroke="#1f6f96"/>
        <line x1="12" y1="5" x2="12" y2="12.5" stroke="#1f6f96" stroke-width="2"/>
        <path d="M3 19.5c2-1.5 4-1.5 6 0s4 1.5 6 0 4-1.5 6 0" stroke="#1f6f96"/>
    """,
    "chart": """
        <line x1="3" y1="21" x2="21" y2="21"/>
        <rect x="5" y="14" width="3.5" height="7"/>
        <rect x="10.3" y="9" width="3.5" height="12"/>
        <rect x="15.6" y="4" width="3.5" height="17"/>
    """,
    "uv": """
        <circle cx="12" cy="12" r="3.4" fill="currentColor" stroke="none"/>
        <line x1="12" y1="4" x2="12" y2="6"/>
        <line x1="12" y1="18" x2="12" y2="20"/>
        <line x1="4" y1="12" x2="6" y2="12"/>
        <line x1="18" y1="12" x2="20" y2="12"/>
        <line x1="6.3" y1="6.3" x2="7.7" y2="7.7"/>
        <line x1="16.3" y1="16.3" x2="17.7" y2="17.7"/>
        <line x1="6.3" y1="17.7" x2="7.7" y2="16.3"/>
        <line x1="16.3" y1="7.7" x2="17.7" y2="6.3"/>
    """,
    # --- misc -----------------------------------------------------------
    "warning": """
        <path d="M12 3 L22 20 L2 20 Z"/>
        <line x1="12" y1="9" x2="12" y2="14"/>
        <circle cx="12" cy="17" r="0.9" fill="currentColor" stroke="none"/>
    """,
    "sparkle": """
        <path d="M12 3c0 4-1 5-5 5 4 0 5 1 5 5 0-4 1-5 5-5-4 0-5-1-5-5Z" fill="currentColor" stroke="none"/>
    """,
    "whale": """
        <path d="M2 13c3-5 9-7 15-5 2 .7 4 2 5 4-2 1-4 1.3-6 1-1.5 3-5 4.5-9 4-4-.5-6-2-5-4Z" fill="#3d5a80" fill-opacity="0.85" stroke="#3d5a80"/>
        <path d="M15 8v-4" stroke="#3d5a80"/>
        <circle cx="7" cy="12" r="0.8" fill="#eef1ea" stroke="none"/>
    """,
    "bluebottle": """
        <path d="M6 6c2-2 10-2 12 0 1.5 1.5 1 4-1 5-3 1.5-7 1.5-10 0-2-1-2.5-3.5-1-5Z" fill="#5064c9" fill-opacity="0.75" stroke="#5064c9"/>
        <g stroke="#5064c9">
        <path d="M8 12c0 3-1 4-1 7"/>
        <path d="M12 12.5c0 3.2 1 4.3 1 7.5"/>
        <path d="M16 12c0 3-1 4-1 7"/>
        </g>
    """,
    "refresh": """
        <path d="M20 11A8 8 0 1 0 19.5 16"/>
        <polyline points="20,5 20,11 14,11"/>
    """,
    "car": """
        <path d="M4 16 5 10a2 2 0 0 1 2-1h10a2 2 0 0 1 2 1l1 6"/>
        <rect x="3" y="16" width="18" height="4" rx="1.5"/>
        <circle cx="7.5" cy="20" r="1.4" fill="currentColor" stroke="none"/>
        <circle cx="16.5" cy="20" r="1.4" fill="currentColor" stroke="none"/>
    """,
    "alert-park": """
        <path d="M3 20 L11 5 L14 5 L21 20 Z"/>
        <path d="M8 20 L11.5 12 L16 20"/>
        <line x1="12.5" y1="9" x2="12.5" y2="9"/>
    """,
}


def sprite_defs() -> str:
    """One hidden <svg> holding every symbol - referenced elsewhere via `use()`."""
    symbols = "\n".join(
        f'<symbol id="i-{name}" viewBox="0 0 24 24">{markup}</symbol>' for name, markup in SYMBOLS.items()
    )
    return f'<svg aria-hidden="true" style="position:absolute;width:0;height:0;overflow:hidden" xmlns="http://www.w3.org/2000/svg"><defs>{symbols}</defs></svg>'


def use(name: str, css_class: str = "", style: str = "") -> str:
    classes = f"icon-glyph {css_class}".strip()
    style_attr = f' style="{style}"' if style else ""
    return f'<svg class="{classes}" aria-hidden="true"{style_attr}><use href="#i-{name}"></use></svg>'

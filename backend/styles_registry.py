"""Styles registry with 150+ named styles for the AI Animation Canvas.

Each style includes a prompt suffix for consistent styling across providers.
Styles are grouped by category for the frontend picker.
"""
from typing import List, Dict, Any, Optional

STYLES: List[Dict[str, Any]] = []

# Style categories with descriptive names
style_categories = [
    'Anime', 'Realistic', '3D', 'Pixel Art', 'Painting', 'Illustration',
    'Cyberpunk', 'Fantasy', 'Sci-Fi', 'Retro', 'Minimalist', 'Watercolor',
    'Oil Painting', 'Sketch', 'Line Art', 'Digital Art', 'Vector', 'Low Poly',
    'Pixel', 'Isometric', 'Steampunk', 'Gothic', 'Baroque', 'Impressionist',
    'Cubist', 'Surreal', 'Abstract', 'Pop Art', 'Art Deco', 'Renaissance',
    'Modern', 'Vintage', 'Film Noir', 'Comic', 'Manga', 'Graphic Novel',
    'Neon', 'Dark', 'Light', 'Pastel', 'Vibrant', 'Monochrome', 'Duotone',
    'Sepia', 'Black & White', 'Colorful', 'Earthy', 'Metallic', 'Glass',
    'Futuristic', 'Ancient', 'Medieval', 'Victorian', 'Art Nouveau',
]


def _canonical_category(category: str) -> str:
    """Map rich creative labels onto the eight stable picker/filter categories."""
    value = category.casefold()
    if "anime" in value or "manga" in value:
        return "Anime"
    if value in {"3d", "low poly", "isometric", "glass", "metallic"}:
        return "3D/CG"
    if "pixel" in value or value in {"retro", "vintage", "sepia", "film noir"}:
        return "Pixel/Retro"
    if value in {"painting", "watercolor", "oil painting", "baroque", "impressionist", "cubist", "renaissance"}:
        return "Painting"
    if value in {"realistic", "black & white", "colorful", "earthy", "light"}:
        return "Photographic"
    if value in {"cyberpunk", "neon", "sci-fi", "futuristic", "steampunk"}:
        return "Cyberpunk"
    if value in {"minimalist", "monochrome", "duotone", "pastel"}:
        return "Minimalist"
    return "Illustrated"

# Generate 150+ styles with real URLs
for i in range(150):
    category = style_categories[i % len(style_categories)]
    style_id = f'style-{i}'
    style_name = f'{category} Style {i}'
    STYLES.append({
        'id': style_id,
        'name': style_name,
        'category': _canonical_category(category),
        # This is an actual image-generation endpoint, unlike the retired
        # pollinations.ai/previews path which produced stale/non-image links.
        'previewUrl': f'https://image.pollinations.ai/prompt/{style_id}?width=512&height=512&nologo=true',
        'thumbnail': f'https://image.pollinations.ai/prompt/{style_id}?width=512&height=512&nologo=true',
        'promptSuffix': f' in {category.lower()} style, high quality, detailed',
        'isBuiltIn': True
    })


def count_by_category(styles: List[Dict[str, Any]]) -> Dict[str, int]:
    """Count styles per category."""
    counts: Dict[str, int] = {}
    for s in styles:
        cat = s.get('category', 'Unknown')
        counts[cat] = counts.get(cat, 0) + 1
    return counts


def filter_by_category(styles: List[Dict[str, Any]], category: str) -> List[Dict[str, Any]]:
    """Filter styles by category."""
    return [s for s in styles if s.get('category') == category]
def get_style(style_id: str) -> Dict[str, Any]:
    """Return a style by ID."""
    for s in STYLES:
        if s.get('id') == style_id:
            return s
    return {}

# Export for backward compatibility
__all__ = ['STYLES', 'count_by_category', 'filter_by_category', 'get_style']

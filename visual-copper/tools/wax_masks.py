"""Portable gold masks for Visual Waxed Copper Items Faithful editions.

Only Pillow and the adjacent mask_patterns.json are required. No file is written.
The old 32x gold border pixels are recorded as text in that JSON; no old copper
texture is reused. The supplied image must be the final-resolution Faithful
surface or assembled UV atlas. UV coordinates themselves remain unchanged.

mask_for_texture(name, original_image, scale, band_width) returns (mask, gold):
  mask: Pillow L image, 0 or 255, at the supplied image's exact dimensions.
  gold: Pillow RGBA image at those dimensions, transparent outside the mask.
        Selected RGB is the gold color and alpha equals the source alpha.
The caller should replace only RGB at mask positions and retain source alpha.
"""

from functools import lru_cache
import json
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps


@lru_cache(maxsize=1)
def _patterns():
    return json.loads(Path(__file__).with_name("mask_patterns.json").read_text(encoding="utf-8"))


def canonical_texture_name(name):
    """Normalize any of the 72 active names and the retained unused helper."""
    stem = str(name).replace("\\", "/").rsplit("/", 1)[-1]
    if stem.endswith(".png"):
        stem = stem[:-4]
    if not stem.startswith("waxed_"):
        raise ValueError("Expected a waxed texture name: " + str(name))
    for stage in ("exposed_", "weathered_", "oxidized_"):
        if stem.startswith("waxed_" + stage):
            stem = "waxed_" + stem[len("waxed_" + stage):]
            break
    return "waxed_copper_block" if stem == "waxed_copper" else stem


def additional_face_coverage(name):
    """Return newly marked native UV faces, expressed in vanilla atlas pixels."""
    entries = _patterns()["additional_faces"].get(canonical_texture_name(name), [])
    # Copies prevent caller changes from mutating the cached shared design data.
    return [dict(entry, rect_native=list(entry["rect_native"])) for entry in entries]


def _seed_mask(template):
    width, height = template["size"]
    result = Image.new("L", (width, height))
    result.putdata([0 if value == "." else 255 for row in template["rows"] for value in row])
    return result


def _generated_icon_mask(source, band_width):
    """Outline the actual Faithful sprite, retaining copper in thin pieces.

    The sprites moved and changed width relative to the historical examples.
    An outer row envelope preserves the marker's frame shape without adding
    gold to internal holes. Connected-component coverage is capped at one half
    so a chain link only one/two source pixels thick still retains copper.
    """
    foreground = source.getchannel("A").point(lambda alpha: 255 if alpha else 0)
    envelope = Image.new("L", source.size)
    hull = ImageDraw.Draw(envelope)
    foreground_pixels = foreground.load()
    for y in range(source.height):
        opaque_x = [x for x in range(source.width) if foreground_pixels[x, y]]
        if opaque_x:
            hull.line((min(opaque_x), y, max(opaque_x), y), fill=255)
    # Padding makes image-edge metal an actual outer edge as well.
    padded = ImageOps.expand(envelope, border=band_width, fill=0)
    interior = padded.filter(ImageFilter.MinFilter(2 * band_width + 1)).crop(
        (band_width, band_width, source.width + band_width, source.height + band_width))
    candidate = ImageChops.multiply(ImageChops.subtract(envelope, interior), foreground)
    candidate_pixels = candidate.load()
    result = Image.new("L", source.size)
    selected = result.load()
    visited = set()
    for y in range(source.height):
        for x in range(source.width):
            if not foreground_pixels[x, y] or (x, y) in visited:
                continue
            pending, component = [(x, y)], []
            visited.add((x, y))
            while pending:
                px, py = pending.pop()
                component.append((px, py))
                for nx, ny in ((px - 1, py), (px + 1, py), (px, py - 1), (px, py + 1)):
                    if (0 <= nx < source.width and 0 <= ny < source.height and
                            foreground_pixels[nx, ny] and (nx, ny) not in visited):
                        visited.add((nx, ny))
                        pending.append((nx, ny))
            edge = sorted(point for point in component if candidate_pixels[point])
            budget = len(component) // 2
            # Stable left-to-right priority gives a continuous gold accent on
            # extremely thin links, with the opposing metal edge retained.
            for point in edge[:budget]:
                selected[point] = 255
    return result


def _resize_old_border(seed, final_size, ratio, band_width):
    if band_width == ratio:
        # Normal 32x/64x policy: retain old 32x topology exactly, using native
        # gold pixels at 32x and two gold pixels at 64x.
        return seed.resize(final_size, Image.Resampling.NEAREST)
    # A thinner comparison (64x / 1px) traces the old one-pixel paths through
    # their expanded cell centers. Joining adjacent points avoids dashed lines.
    result = Image.new("L", final_size)
    draw = ImageDraw.Draw(result)
    center = ratio // 2
    for y in range(seed.height):
        for x in range(seed.width):
            if not seed.getpixel((x, y)):
                continue
            point = (x * ratio + center, y * ratio + center)
            draw.point(point, fill=255)
            for nx, ny in ((x + 1, y), (x, y + 1)):
                if nx < seed.width and ny < seed.height and seed.getpixel((nx, ny)):
                    draw.line((point, (nx * ratio + center, ny * ratio + center)), fill=255, width=band_width)
    return result


def _add_native_face(mask, face, scale, band_width):
    x0, y0, x1, y1 = [coordinate * scale for coordinate in face["rect_native"]]
    width, height = x1 - x0, y1 - y0
    draw = ImageDraw.Draw(mask)
    if face.get("replace_existing_wax"):
        # Restore the source copper interior before drawing a complete ring.
        # The old antenna stem used an asymmetric stripe on its side faces.
        draw.rectangle((x0, y0, x1 - 1, y1 - 1), fill=0)
    ring_width = min(band_width, (min(width, height) - 1) // 2)
    if ring_width:
        draw.rectangle((x0, y0, x1 - 1, y1 - 1), outline=255, width=ring_width)
    elif width <= height:
        # A 1-native-pixel chest latch side is 2 pixels wide at 32x; a complete
        # 1px ring would turn it entirely gold. A single long edge leaves metal.
        draw.rectangle((x0, y0, x0, y1 - 1), fill=255)
    else:
        draw.rectangle((x0, y0, x1 - 1, y0), fill=255)


def _added_gold_color(x, y, ratio, palette):
    # Repeat native 32x shading cells at 64x, preserving the same marker style
    # while the underlying Faithful copper retains its independently drawn 64x
    # detail. Integer arithmetic makes new island shading fully deterministic.
    sx, sy = x // ratio, y // ratio
    value = (sx * 37 + sy * 19 + (sx * sy) % 23) % 16
    index = (0, 4, 4, 3, 4, 5, 3, 4, 5, 1, 4, 3, 5, 0, 4, 2)[value]
    return tuple(palette[index])


def mask_for_texture(name, original_image, scale, band_width):
    """Return (L mask, RGBA gold overlay), clipped to final Faithful alpha.

    scale is the ratio to vanilla textures: 2 means the 32x edition and 4 the
    64x edition. band_width is in final texture pixels. Defaults chosen by the
    builder should be 1 at 32x and 2 at 64x; 1 at 64x supports the comparison.
    Unknown names and incorrectly sized images fail explicitly.
    """
    if scale not in (2, 4):
        raise ValueError("scale must be 2 (32x) or 4 (64x); accepted 16x textures are immutable")
    if band_width not in (1, 2) or (scale == 2 and band_width != 1):
        raise ValueError("Use 1px at 32x and 1px or 2px at 64x")
    source = original_image.convert("RGBA")
    key = canonical_texture_name(name)
    patterns = _patterns()
    if key == "waxed_copper_door_outline":
        if source.size != (48 * scale, 32 * scale):
            raise ValueError("Unexpected unused door-outline sheet size")
        return Image.new("L", source.size), Image.new("RGBA", source.size)
    if key not in patterns["templates"]:
        raise ValueError("Unknown wax texture: " + str(name))
    template = patterns["templates"][key]
    ratio = scale // 2
    expected_size = tuple(dimension * ratio for dimension in template["size"])
    if source.size != expected_size:
        raise ValueError(f"{name}: expected final Faithful image {expected_size}, got {source.size}")
    if key in {"waxed_copper_bars", "waxed_copper_chain", "waxed_copper_door", "waxed_copper_lantern"}:
        mask = _generated_icon_mask(source, band_width)
    else:
        mask = _resize_old_border(_seed_mask(template), source.size, ratio, band_width)
    for face in additional_face_coverage(key):
        _add_native_face(mask, face, scale, band_width)

    gold = Image.new("RGBA", source.size)
    palette = patterns["palette"]
    source_pixels, mask_pixels, gold_pixels = source.load(), mask.load(), gold.load()
    for y in range(source.height):
        for x in range(source.width):
            alpha = source_pixels[x, y][3]
            if not mask_pixels[x, y] or not alpha:
                mask_pixels[x, y] = 0
                continue
            old_value = template["rows"][y // ratio][x // ratio]
            rgb = tuple(palette[int(old_value)]) if old_value != "." else _added_gold_color(x, y, ratio, palette)
            gold_pixels[x, y] = (*rgb, alpha)
    return mask, gold

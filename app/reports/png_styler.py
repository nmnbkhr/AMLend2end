"""
PNG Styler - Bloomberg Terminal Style Post-Processing

Applies a Bloomberg-terminal inspired visual style to plot PNGs without
modifying the original notebook outputs.

Features:
- Dark background margin/padding
- Top header bar with terminal info
- Subtle grid overlay on background
- Watermark in bottom-right
- Slight contrast enhancement
"""

import logging
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter

from ..utils.paths import get_run_dir, get_plots_dir

logger = logging.getLogger(__name__)

# Bloomberg-inspired color palette (matching UI theme spec)
# bg: #0B0F14, panel: #121821, panel2: #0F141C, border: #273142
# text: #E6EEF8, muted: #A7B1C2, accent: #FFB000, cyan: #22D3EE, green: #00C853, red: #FF5252
THEMES = {
    "bloomberg": {
        "bg_color": (11, 15, 20),             # #0B0F14 - near-black
        "header_bg": (15, 20, 28),             # #0F141C - panel2
        "header_text": (255, 176, 0),          # #FFB000 - terminal amber/orange
        "header_text_secondary": (167, 177, 194),  # #A7B1C2 - muted gray
        "grid_color": (39, 49, 66),            # #273142 - border color
        "watermark_color": (70, 80, 100),      # Slightly visible on dark
        "border_color": (255, 176, 0),         # #FFB000 - accent orange
        "text_color": (230, 238, 248),         # #E6EEF8 - main text
        "header_height": 44,
        "padding": 20,
        "grid_spacing": 40,
        "contrast_factor": 1.1,
    },
    "dark": {
        "bg_color": (18, 24, 33),             # #121821 - panel
        "header_bg": (11, 15, 20),             # #0B0F14 - bg
        "header_text": (34, 211, 238),         # #22D3EE - cyan
        "header_text_secondary": (167, 177, 194),
        "grid_color": (39, 49, 66),
        "watermark_color": (70, 80, 100),
        "border_color": (34, 211, 238),        # cyan
        "text_color": (230, 238, 248),
        "header_height": 44,
        "padding": 20,
        "grid_spacing": 40,
        "contrast_factor": 1.1,
    },
}


def _get_font(size: int = 14, bold: bool = False) -> ImageFont.FreeTypeFont:
    """
    Get a font for text rendering.

    Falls back to default font if system fonts not available.
    """
    # Try common monospace fonts
    font_names = [
        "DejaVuSansMono-Bold.ttf" if bold else "DejaVuSansMono.ttf",
        "LiberationMono-Bold.ttf" if bold else "LiberationMono-Regular.ttf",
        "UbuntuMono-Bold.ttf" if bold else "UbuntuMono-Regular.ttf",
        "Consolas-Bold.ttf" if bold else "Consolas.ttf",
        "Monaco.ttf",
    ]

    # Common font paths on Linux
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/",
        "/usr/share/fonts/truetype/liberation/",
        "/usr/share/fonts/truetype/ubuntu/",
        "/usr/share/fonts/TTF/",
        "/usr/share/fonts/",
    ]

    for font_path in font_paths:
        for font_name in font_names:
            try:
                full_path = Path(font_path) / font_name
                if full_path.exists():
                    return ImageFont.truetype(str(full_path), size)
            except Exception:
                continue

    # Try loading by name (works on some systems)
    for font_name in font_names:
        try:
            return ImageFont.truetype(font_name, size)
        except Exception:
            continue

    # Fallback to default
    try:
        return ImageFont.load_default()
    except Exception:
        return None


def _draw_grid(
    draw: ImageDraw.Draw,
    width: int,
    height: int,
    theme: dict,
    header_height: int,
    padding: int,
    orig_width: int,
    orig_height: int,
) -> None:
    """Draw subtle grid lines on the background (not over the original plot)."""
    grid_color = theme["grid_color"]
    spacing = theme["grid_spacing"]

    # Calculate the area where the original image sits
    img_left = padding
    img_top = header_height + padding
    img_right = img_left + orig_width
    img_bottom = img_top + orig_height

    # Draw vertical lines (outside image area)
    for x in range(0, width, spacing):
        if x < img_left or x > img_right:
            draw.line([(x, header_height), (x, height)], fill=grid_color, width=1)
        else:
            # Draw only above and below the image
            draw.line([(x, header_height), (x, img_top)], fill=grid_color, width=1)
            draw.line([(x, img_bottom), (x, height)], fill=grid_color, width=1)

    # Draw horizontal lines (outside image area)
    for y in range(header_height, height, spacing):
        if y < img_top or y > img_bottom:
            draw.line([(0, y), (width, y)], fill=grid_color, width=1)
        else:
            # Draw only to the left and right of the image
            draw.line([(0, y), (img_left, y)], fill=grid_color, width=1)
            draw.line([(img_right, y), (width, y)], fill=grid_color, width=1)


def _draw_header(
    draw: ImageDraw.Draw,
    width: int,
    theme: dict,
    run_id: str,
    timestamp: str,
) -> None:
    """Draw the terminal-style header bar."""
    header_height = theme["header_height"]

    # Draw header background
    draw.rectangle([(0, 0), (width, header_height)], fill=theme["header_bg"])

    # Draw accent line at bottom of header
    draw.line([(0, header_height - 1), (width, header_height - 1)],
              fill=theme["border_color"], width=2)

    # Get fonts
    title_font = _get_font(16, bold=True)
    info_font = _get_font(12, bold=False)

    # Draw "AML TERMINAL" on left
    title_text = "AML TERMINAL"
    draw.text((15, 10), title_text, fill=theme["header_text"], font=title_font)

    # Draw run info on right
    short_run_id = run_id[:8] if len(run_id) > 8 else run_id
    info_text = f"RUN {short_run_id} | {timestamp}"

    # Calculate text width for right alignment
    if info_font:
        try:
            bbox = draw.textbbox((0, 0), info_text, font=info_font)
            text_width = bbox[2] - bbox[0]
        except AttributeError:
            # Older Pillow versions
            text_width = len(info_text) * 7
    else:
        text_width = len(info_text) * 7

    draw.text((width - text_width - 15, 13), info_text,
              fill=theme["header_text_secondary"], font=info_font)


def _draw_watermark(
    draw: ImageDraw.Draw,
    width: int,
    height: int,
    theme: dict,
) -> None:
    """Draw subtle watermark in bottom-right corner."""
    watermark_text = "AML TERMINAL"
    watermark_font = _get_font(10, bold=False)

    # Calculate position (bottom-right with padding)
    if watermark_font:
        try:
            bbox = draw.textbbox((0, 0), watermark_text, font=watermark_font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
        except AttributeError:
            text_width = len(watermark_text) * 6
            text_height = 10
    else:
        text_width = len(watermark_text) * 6
        text_height = 10

    x = width - text_width - 10
    y = height - text_height - 8

    draw.text((x, y), watermark_text, fill=theme["watermark_color"], font=watermark_font)


def style_single_png(
    input_path: Path,
    output_path: Path,
    run_id: str,
    theme_name: str = "bloomberg",
    timestamp: Optional[str] = None,
) -> Optional[Path]:
    """
    Apply Bloomberg-terminal style to a single PNG file.

    Args:
        input_path: Path to original PNG file
        output_path: Path to save styled PNG
        run_id: Run identifier for header display
        theme_name: Theme to apply ("bloomberg" or "dark")
        timestamp: Optional timestamp string (defaults to current time)

    Returns:
        Path to styled PNG if successful, None otherwise
    """
    try:
        theme = THEMES.get(theme_name, THEMES["bloomberg"])

        # Load original image
        original = Image.open(input_path)
        orig_width, orig_height = original.size

        # Convert to RGB if necessary (handle RGBA, palette modes)
        if original.mode in ("RGBA", "LA"):
            # Create white background for transparent images
            background = Image.new("RGB", original.size, (255, 255, 255))
            if original.mode == "RGBA":
                background.paste(original, mask=original.split()[3])
            else:
                background.paste(original, mask=original.split()[1])
            original = background
        elif original.mode != "RGB":
            original = original.convert("RGB")

        # Enhance contrast slightly
        enhancer = ImageEnhance.Contrast(original)
        original = enhancer.enhance(theme["contrast_factor"])

        # Calculate new dimensions
        padding = theme["padding"]
        header_height = theme["header_height"]
        new_width = orig_width + (padding * 2)
        new_height = orig_height + header_height + (padding * 2)

        # Create new image with dark background
        styled = Image.new("RGB", (new_width, new_height), theme["bg_color"])
        draw = ImageDraw.Draw(styled)

        # Draw grid on background
        _draw_grid(draw, new_width, new_height, theme, header_height, padding,
                   orig_width, orig_height)

        # Paste original image
        styled.paste(original, (padding, header_height + padding))

        # Draw header
        if timestamp is None:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        _draw_header(draw, new_width, theme, run_id, timestamp)

        # Draw watermark
        _draw_watermark(draw, new_width, new_height, theme)

        # Draw subtle border around original image
        img_left = padding - 1
        img_top = header_height + padding - 1
        img_right = padding + orig_width
        img_bottom = header_height + padding + orig_height
        draw.rectangle(
            [(img_left, img_top), (img_right, img_bottom)],
            outline=theme["border_color"],
            width=1
        )

        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Save styled image
        styled.save(output_path, "PNG", optimize=True)

        logger.debug(f"Styled: {input_path.name} -> {output_path.name}")
        return output_path

    except Exception as e:
        logger.error(f"Failed to style {input_path}: {e}")
        return None


def style_pngs(
    run_id: str,
    theme: str = "bloomberg",
    timestamp: Optional[str] = None,
) -> List[Path]:
    """
    Apply Bloomberg-terminal style to all PNG plots for a run.

    Reads PNGs from artifacts/runs/<run_id>/plots/ and creates styled
    versions in artifacts/runs/<run_id>/plots/styled/

    Args:
        run_id: The run identifier
        theme: Theme name ("bloomberg" or "dark")
        timestamp: Optional timestamp for header (defaults to current time)

    Returns:
        List of paths to newly created styled PNG files
    """
    styled_files = []

    try:
        plots_dir = get_plots_dir(run_id)
    except ValueError as e:
        logger.error(f"Invalid run_id for styling: {e}")
        return styled_files

    if not plots_dir.exists():
        logger.warning(f"Plots directory not found: {plots_dir}")
        return styled_files

    # Output directory for styled plots
    styled_dir = plots_dir / "styled"
    styled_dir.mkdir(parents=True, exist_ok=True)

    # Get timestamp for consistent header across all plots
    if timestamp is None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Process each PNG in plots directory
    png_files = list(plots_dir.glob("*.png"))

    if not png_files:
        logger.info(f"No PNG files found in {plots_dir}")
        return styled_files

    logger.info(f"Styling {len(png_files)} PNG files with '{theme}' theme...")

    for png_file in png_files:
        output_path = styled_dir / png_file.name
        result = style_single_png(png_file, output_path, run_id, theme, timestamp)
        if result:
            styled_files.append(result)

    logger.info(f"Created {len(styled_files)} styled plots in {styled_dir}")
    return styled_files


def get_styled_plots_dir(run_id: str) -> Optional[Path]:
    """
    Get the styled plots directory for a run if it exists.

    Args:
        run_id: The run identifier

    Returns:
        Path to styled plots directory if exists, None otherwise
    """
    try:
        styled_dir = get_plots_dir(run_id) / "styled"
        return styled_dir if styled_dir.exists() else None
    except ValueError:
        return None


def has_styled_plots(run_id: str) -> bool:
    """
    Check if styled plots exist for a run.

    Args:
        run_id: The run identifier

    Returns:
        True if styled plots directory exists and contains files
    """
    styled_dir = get_styled_plots_dir(run_id)
    if styled_dir is None:
        return False
    return any(styled_dir.glob("*.png"))


def panelize_png(
    input_path: Path,
    output_path: Path,
    header_left: str,
    header_right: str,
    theme_name: str = "bloomberg",
) -> Optional[Path]:
    """
    Apply Bloomberg-terminal style panelization to a single PNG file.

    This is the primary entry point for styling individual PNGs with
    customizable header text.

    Args:
        input_path: Path to original PNG file
        output_path: Path to save styled PNG
        header_left: Text to display on left side of header (e.g., "AML TERMINAL")
        header_right: Text to display on right side of header (e.g., "RUN abc123 | 2024-01-15")
        theme_name: Theme to apply ("bloomberg" or "dark")

    Returns:
        Path to styled PNG if successful, None otherwise
    """
    try:
        theme = THEMES.get(theme_name, THEMES["bloomberg"])

        # Load original image
        original = Image.open(input_path)
        orig_width, orig_height = original.size

        # Convert to RGB if necessary (handle RGBA, palette modes)
        if original.mode in ("RGBA", "LA"):
            background = Image.new("RGB", original.size, (255, 255, 255))
            if original.mode == "RGBA":
                background.paste(original, mask=original.split()[3])
            else:
                background.paste(original, mask=original.split()[1])
            original = background
        elif original.mode != "RGB":
            original = original.convert("RGB")

        # Enhance contrast slightly
        enhancer = ImageEnhance.Contrast(original)
        original = enhancer.enhance(theme["contrast_factor"])

        # Calculate new dimensions
        padding = theme["padding"]
        header_height = theme["header_height"]
        new_width = orig_width + (padding * 2)
        new_height = orig_height + header_height + (padding * 2)

        # Create new image with dark background
        styled = Image.new("RGB", (new_width, new_height), theme["bg_color"])
        draw = ImageDraw.Draw(styled)

        # Draw grid on background
        _draw_grid(draw, new_width, new_height, theme, header_height, padding,
                   orig_width, orig_height)

        # Paste original image
        styled.paste(original, (padding, header_height + padding))

        # Draw custom header with provided text
        _draw_custom_header(draw, new_width, theme, header_left, header_right)

        # Draw watermark
        _draw_watermark(draw, new_width, new_height, theme)

        # Draw subtle border around original image
        img_left = padding - 1
        img_top = header_height + padding - 1
        img_right = padding + orig_width
        img_bottom = header_height + padding + orig_height
        draw.rectangle(
            [(img_left, img_top), (img_right, img_bottom)],
            outline=theme["border_color"],
            width=1
        )

        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Save styled image
        styled.save(output_path, "PNG", optimize=True)

        logger.debug(f"Panelized: {input_path.name} -> {output_path.name}")
        return output_path

    except Exception as e:
        logger.error(f"Failed to panelize {input_path}: {e}")
        return None


def _draw_custom_header(
    draw: ImageDraw.Draw,
    width: int,
    theme: dict,
    header_left: str,
    header_right: str,
) -> None:
    """Draw the terminal-style header bar with custom text."""
    header_height = theme["header_height"]

    # Draw header background
    draw.rectangle([(0, 0), (width, header_height)], fill=theme["header_bg"])

    # Draw accent line at bottom of header
    draw.line([(0, header_height - 1), (width, header_height - 1)],
              fill=theme["border_color"], width=2)

    # Get fonts
    title_font = _get_font(16, bold=True)
    info_font = _get_font(12, bold=False)

    # Draw left header text
    draw.text((15, 12), header_left, fill=theme["header_text"], font=title_font)

    # Draw right header text
    if info_font:
        try:
            bbox = draw.textbbox((0, 0), header_right, font=info_font)
            text_width = bbox[2] - bbox[0]
        except AttributeError:
            text_width = len(header_right) * 7
    else:
        text_width = len(header_right) * 7

    draw.text((width - text_width - 15, 15), header_right,
              fill=theme["header_text_secondary"], font=info_font)


def panelize_run_plots(
    run_id: str,
    theme: str = "bloomberg",
    timestamp: Optional[str] = None,
) -> List[Path]:
    """
    Apply Bloomberg-terminal style panelization to all PNG plots for a run.

    This is an alias for style_pngs() that uses the panelizer terminology.

    Args:
        run_id: The run identifier
        theme: Theme name ("bloomberg" or "dark")
        timestamp: Optional timestamp for header (defaults to current time)

    Returns:
        List of paths to newly created styled PNG files
    """
    return style_pngs(run_id, theme=theme, timestamp=timestamp)

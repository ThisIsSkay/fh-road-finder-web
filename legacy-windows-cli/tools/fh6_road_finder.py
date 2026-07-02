#!/usr/bin/env python
"""FH6 Road Finder: detect possible undiscovered-road pixels in map screenshots."""

from __future__ import annotations

import argparse
import html
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


PRESET_TOLERANCE_NAMES = {
    0: "ultra_strict",
    1: "strict",
    2: "normal",
    5: "loose",
    8: "very_loose",
}

SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}
JPEG_EXTENSIONS = {".jpg", ".jpeg"}

@dataclass
class Region:
    name: str
    image: Image.Image
    x_offset: int
    y_offset: int
    width: int
    height: int


@dataclass
class OutputRecord:
    source_file: str
    display_name: str
    tolerance: int
    mode_name: str
    region_name: str | None
    total_matching_pixels: int
    cluster_count: int
    overlay_file: Path | None
    black_file: Path
    transparent_file: Path | None


def parse_rgb(value: str, option_name: str) -> tuple[int, int, int]:
    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 3:
        raise argparse.ArgumentTypeError(f"{option_name} must look like 128,128,128")
    try:
        rgb = tuple(int(part) for part in parts)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{option_name} must contain whole numbers") from exc
    if any(channel < 0 or channel > 255 for channel in rgb):
        raise argparse.ArgumentTypeError(f"{option_name} values must be between 0 and 255")
    return rgb  # type: ignore[return-value]


def parse_tolerances(value: str) -> list[int]:
    name_to_value = {name: tolerance for tolerance, name in PRESET_TOLERANCE_NAMES.items()}
    tolerances: list[int] = []
    for part in value.split(","):
        token = part.strip().lower()
        if not token:
            continue
        if token in name_to_value:
            tolerance = name_to_value[token]
        else:
            try:
                tolerance = int(token)
            except ValueError as exc:
                raise argparse.ArgumentTypeError(
                    "tolerances must be comma-separated numbers or preset names"
                ) from exc
        if tolerance < 0:
            raise argparse.ArgumentTypeError("tolerances must be 0 or higher")
        if tolerance not in tolerances:
            tolerances.append(tolerance)
    if not tolerances:
        raise argparse.ArgumentTypeError("at least one tolerance is required")
    return tolerances


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Detect possible undiscovered Forza Horizon road pixels in map screenshots."
    )
    parser.add_argument("--input", required=True, type=Path, help="Folder containing map screenshots.")
    parser.add_argument("--output", required=True, type=Path, help="Folder for generated outputs.")
    parser.add_argument(
        "--target-rgb",
        default="128,128,128",
        type=lambda value: parse_rgb(value, "--target-rgb"),
        help="Target RGB value. Default: 128,128,128",
    )
    parser.add_argument(
        "--tolerances",
        default="0,1,2",
        type=parse_tolerances,
        help="Comma-separated tolerances or preset names. Default: 0,1,2",
    )
    parser.add_argument(
        "--min-cluster-size",
        default=8,
        type=int,
        help="Minimum connected matching pixels to keep. Default: 8",
    )
    parser.add_argument(
        "--highlight-color",
        default="255,0,0",
        type=lambda value: parse_rgb(value, "--highlight-color"),
        help="Highlight RGB color. Default: 255,0,0",
    )
    parser.add_argument(
        "--overlay-alpha",
        default=0.85,
        type=float,
        help="Highlight strength on overlay, from 0.0 to 1.0. Default: 0.85",
    )
    parser.add_argument("--no-overlay", action="store_true", help="Do not write overlay PNGs.")
    parser.add_argument("--no-transparent", action="store_true", help="Do not write transparent mask PNGs.")
    parser.add_argument("--no-csv", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument(
        "--distance-mode",
        default="channel",
        choices=["channel", "euclidean"],
        help="Distance mode. Default: channel",
    )
    return parser


def find_input_images(input_dir: Path) -> list[Path]:
    if not input_dir.exists() or not input_dir.is_dir():
        raise FileNotFoundError(f"Input folder does not exist: {input_dir}")
    return sorted(path for path in input_dir.iterdir() if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS)


def find_ignored_input_files(input_dir: Path) -> list[Path]:
    return sorted(path for path in input_dir.iterdir() if path.is_file() and path.suffix.lower() not in SUPPORTED_EXTENSIONS)


def remove_old_generated_outputs(output_dir: Path) -> None:
    patterns = ("*.png", "*.csv", "report.html")
    removed = 0
    for pattern in patterns:
        for output_path in output_dir.glob(pattern):
            if output_path.is_file():
                try:
                    output_path.unlink()
                    removed += 1
                except OSError:
                    print(f"WARNING: Could not remove old output file: {output_path.name}")
    if removed:
        print(f"Cleared {removed} old output file(s).")


def safe_stem(path: Path) -> str:
    chars = []
    for char in path.stem:
        chars.append(char if char.isalnum() or char in ("-", "_") else "_")
    return "".join(chars).strip("_") or "map"


def split_regions(image: Image.Image) -> list[Region]:
    return [Region("full", image, 0, 0, image.width, image.height)]


def make_detection_mask(
    image: Image.Image,
    target_rgb: tuple[int, int, int],
    tolerance: int,
    distance_mode: str,
) -> np.ndarray:
    rgb_array = np.asarray(image.convert("RGB"), dtype=np.int16)
    target = np.asarray(target_rgb, dtype=np.int16)
    difference = np.abs(rgb_array - target)

    if distance_mode == "channel":
        mask = np.all(difference <= tolerance, axis=2)
    else:
        distance = np.sqrt(np.sum(np.square(difference.astype(np.float32)), axis=2))
        mask = distance <= float(tolerance) * math.sqrt(3.0)

    return mask.astype(np.uint8)


def detect_clusters(
    mask: np.ndarray,
    min_cluster_size: int,
    x_offset: int,
    y_offset: int,
    source_name: str,
    tolerance: int,
    grid_region: str,
    total_matching_pixels: int,
) -> tuple[np.ndarray, list[dict[str, object]]]:
    if min_cluster_size < 1:
        min_cluster_size = 1

    component_count, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, 8)
    kept_component_ids: list[int] = []
    clusters: list[dict[str, object]] = []

    for component_id in range(1, component_count):
        pixel_count = int(stats[component_id, cv2.CC_STAT_AREA])
        if pixel_count < min_cluster_size:
            continue

        x = int(stats[component_id, cv2.CC_STAT_LEFT])
        y = int(stats[component_id, cv2.CC_STAT_TOP])
        width = int(stats[component_id, cv2.CC_STAT_WIDTH])
        height = int(stats[component_id, cv2.CC_STAT_HEIGHT])
        center_x, center_y = centroids[component_id]
        kept_component_ids.append(component_id)
        clusters.append(
            {
                "source_file": source_name,
                "tolerance": tolerance,
                "cluster_id": 0,
                "pixel_count": pixel_count,
                "bounding_box_x1": x + x_offset,
                "bounding_box_y1": y + y_offset,
                "bounding_box_x2": x + x_offset + width - 1,
                "bounding_box_y2": y + y_offset + height - 1,
                "center_x": round(float(center_x + x_offset), 2),
                "center_y": round(float(center_y + y_offset), 2),
                "width": width,
                "height": height,
                "grid_region": grid_region,
                "total_matching_pixels_before_cluster_filter": total_matching_pixels,
            }
        )

    clusters.sort(key=lambda row: int(row["pixel_count"]), reverse=True)
    for index, cluster in enumerate(clusters, start=1):
        cluster["cluster_id"] = index

    kept_mask = np.isin(labels, kept_component_ids).astype(np.uint8)
    return kept_mask, clusters


def save_black_highlight(path: Path, mask: np.ndarray, highlight_rgb: tuple[int, int, int]) -> None:
    output = np.zeros((mask.shape[0], mask.shape[1], 3), dtype=np.uint8)
    output[mask > 0] = np.asarray(highlight_rgb, dtype=np.uint8)
    Image.fromarray(output, "RGB").save(path, compress_level=3)


def save_overlay(
    path: Path,
    image: Image.Image,
    mask: np.ndarray,
    highlight_rgb: tuple[int, int, int],
    overlay_alpha: float,
) -> None:
    alpha = max(0.0, min(1.0, overlay_alpha))
    rgb = np.asarray(image.convert("RGB"), dtype=np.float32)
    highlight = np.asarray(highlight_rgb, dtype=np.float32)
    rgb[mask > 0] = rgb[mask > 0] * (1.0 - alpha) + highlight * alpha
    Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), "RGB").save(path, compress_level=3)


def save_transparent(path: Path, mask: np.ndarray, highlight_rgb: tuple[int, int, int]) -> None:
    output = np.zeros((mask.shape[0], mask.shape[1], 4), dtype=np.uint8)
    output[mask > 0, 0:3] = np.asarray(highlight_rgb, dtype=np.uint8)
    output[mask > 0, 3] = 255
    Image.fromarray(output, "RGBA").save(path, compress_level=3)


def relative_link(path: Path, output_dir: Path) -> str:
    try:
        return path.relative_to(output_dir).as_posix()
    except ValueError:
        return path.as_posix()


def write_html_report(path: Path, records: list[OutputRecord], output_dir: Path, settings: dict[str, object]) -> None:
    rows: list[str] = [
        "<!doctype html>",
        "<html lang=\"en\">",
        "<head>",
        "<meta charset=\"utf-8\">",
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">",
        "<title>FH6 Road Finder Report</title>",
        "<style>",
        "body{font-family:Segoe UI,Arial,sans-serif;margin:24px;background:#111;color:#eee;}",
        "a{color:#ff6b6b;} h1{margin-bottom:6px;} h2{margin-top:32px;border-top:1px solid #333;padding-top:18px;}",
        ".meta{color:#bbb;margin-bottom:18px;} .record{margin:18px 0 28px;padding:14px;border:1px solid #333;background:#1a1a1a;}",
        ".thumb{max-width:420px;width:100%;height:auto;border:1px solid #444;background:#000;}",
        ".links{margin-top:10px;} .empty{color:#aaa;}",
        "</style>",
        "</head><body>",
        "<h1>FH6 Road Finder Report</h1>",
        "<div class=\"meta\">"
        f"Generated: {html.escape(str(settings['generated_at']))} | "
        f"Target RGB: {html.escape(str(settings['target_rgb']))} | "
        f"Distance mode: {html.escape(str(settings['distance_mode']))} | "
        "Tiny red hits are kept in the images"
        "</div>",
    ]

    if settings.get("jpeg_count"):
        rows.append(
            "<p><strong>JPEG warning:</strong> JPEG compression changes exact pixel colors. "
            "Use tolerance 5 or higher if PNG screenshots are not available.</p>"
        )

    if not records:
        rows.append("<p>No supported image files were processed.</p>")

    for record in records:
        region_text = f" | Region: {record.region_name}" if record.region_name else ""
        rows.append("<div class=\"record\">")
        rows.append(
            f"<h2>{html.escape(record.display_name)} | Tolerance {record.tolerance} "
            f"({html.escape(record.mode_name)}){html.escape(region_text)}</h2>"
        )
        rows.append(
            f"<p>Matching red pixels: <strong>{record.total_matching_pixels:,}</strong>. "
            "Even tiny hits are shown in the generated images.</p>"
        )
        rows.append("<div class=\"links\">")
        if record.overlay_file:
            overlay_href = html.escape(relative_link(record.overlay_file, output_dir))
            rows.append(f"<p><a href=\"{overlay_href}\">Open overlay image</a></p>")
            rows.append(f"<a href=\"{overlay_href}\"><img class=\"thumb\" src=\"{overlay_href}\" alt=\"overlay\"></a>")
        black_href = html.escape(relative_link(record.black_file, output_dir))
        rows.append(f"<p><a href=\"{black_href}\">Open black highlight image</a></p>")
        if record.transparent_file:
            transparent_href = html.escape(relative_link(record.transparent_file, output_dir))
            rows.append(f"<p><a href=\"{transparent_href}\">Open transparent mask</a></p>")
        rows.append("</div>")
        rows.append("</div>")

    rows.append("</body></html>")
    path.write_text("\n".join(rows), encoding="utf-8")


def output_prefix(stem: str, region: Region, tolerance: int) -> str:
    return f"{stem}_tol{tolerance}"


def process_image(
    image_path: Path,
    output_dir: Path,
    tolerances: list[int],
    target_rgb: tuple[int, int, int],
    highlight_rgb: tuple[int, int, int],
    min_cluster_size: int,
    overlay_alpha: float,
    distance_mode: str,
    write_overlay_files: bool,
    write_transparent_files: bool,
) -> list[OutputRecord]:
    print(f"  Processing {image_path.name}...")
    image = Image.open(image_path)
    image.load()
    image = image.convert("RGBA")

    stem = safe_stem(image_path)
    records: list[OutputRecord] = []
    for region in split_regions(image):
        source_name = image_path.name
        for tolerance in tolerances:
            mode_name = PRESET_TOLERANCE_NAMES.get(tolerance, "custom")
            prefix = output_prefix(stem, region, tolerance)

            raw_mask = make_detection_mask(region.image, target_rgb, tolerance, distance_mode)
            total_matching_pixels = int(np.count_nonzero(raw_mask))
            _, clusters = detect_clusters(
                raw_mask,
                min_cluster_size,
                region.x_offset,
                region.y_offset,
                source_name,
                tolerance,
                "",
                total_matching_pixels,
            )

            black_file = output_dir / f"{prefix}_black_highlight.png"
            save_black_highlight(black_file, raw_mask, highlight_rgb)

            overlay_file: Path | None = None
            if write_overlay_files:
                overlay_file = output_dir / f"{prefix}_overlay.png"
                save_overlay(overlay_file, region.image, raw_mask, highlight_rgb, overlay_alpha)

            transparent_file: Path | None = None
            if write_transparent_files:
                transparent_file = output_dir / f"{prefix}_transparent.png"
                save_transparent(transparent_file, raw_mask, highlight_rgb)

            print(f"    full tol={tolerance}: {total_matching_pixels:,} px, {len(clusters)} clusters")
            records.append(
                OutputRecord(
                    source_file=image_path.name,
                    display_name=image_path.name,
                    tolerance=tolerance,
                    mode_name=mode_name,
                    region_name=None,
                    total_matching_pixels=total_matching_pixels,
                    cluster_count=len(clusters),
                    overlay_file=overlay_file,
                    black_file=black_file,
                    transparent_file=transparent_file,
                )
            )
    return records


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.min_cluster_size < 1:
        parser.error("--min-cluster-size must be 1 or higher")
    if not math.isfinite(args.overlay_alpha):
        parser.error("--overlay-alpha must be a number")

    input_dir = args.input.resolve()
    output_dir = args.output.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    remove_old_generated_outputs(output_dir)

    try:
        image_files = find_input_images(input_dir)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    ignored_files = find_ignored_input_files(input_dir)
    jpeg_files = [path for path in image_files if path.suffix.lower() in JPEG_EXTENSIONS]

    print("FH6 Road Finder")
    print("-----------------------------------------")
    print(f"Input: {input_dir}")
    print(f"Output: {output_dir}")
    print(f"Target RGB: {args.target_rgb}")
    print(f"Tolerances: {', '.join(str(tolerance) for tolerance in args.tolerances)}")
    print(f"Distance mode: {args.distance_mode}")
    print(f"Minimum cluster size: {args.min_cluster_size}")
    print("")

    if ignored_files:
        print(f"WARNING: Ignoring {len(ignored_files)} unsupported file(s):")
        for ignored_file in ignored_files[:20]:
            print(f"  {ignored_file.name}")
        if len(ignored_files) > 20:
            print(f"  ...and {len(ignored_files) - 20} more")
        print("")

    if jpeg_files:
        print(f"WARNING: {len(jpeg_files)} JPEG file(s) detected.")
        print("JPEG compression shifts pixel colors. PNG screenshots are recommended.")
        print("If using JPEG input, tolerance 5 or 8 may be more useful than 0, 1, or 2.")
        print("")

    if not image_files:
        print("No supported image files found in the input folder. Nothing to process.")
        print("Supported: PNG - best, JPG/JPEG, BMP, TIF/TIFF")
        write_html_report(
            output_dir / "report.html",
            [],
            output_dir,
            {
                "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "target_rgb": args.target_rgb,
                "distance_mode": args.distance_mode,
                "min_cluster_size": args.min_cluster_size,
                "jpeg_count": 0,
            },
        )
        return 0

    all_records: list[OutputRecord] = []

    for index, image_file in enumerate(image_files, start=1):
        print(f"[{index}/{len(image_files)}]")
        try:
            records = process_image(
                image_file,
                output_dir,
                args.tolerances,
                args.target_rgb,
                args.highlight_color,
                args.min_cluster_size,
                args.overlay_alpha,
                args.distance_mode,
                not args.no_overlay,
                not args.no_transparent,
            )
        except Exception as exc:  # noqa: BLE001 - keep batch-friendly errors clear.
            print(f"ERROR while processing {image_file.name}: {exc}", file=sys.stderr)
            return 1
        all_records.extend(records)

    write_html_report(
        output_dir / "report.html",
        all_records,
        output_dir,
        {
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "target_rgb": args.target_rgb,
            "distance_mode": args.distance_mode,
            "min_cluster_size": args.min_cluster_size,
            "jpeg_count": len(jpeg_files),
        },
    )

    print("")
    print(f"Done. Processed {len(image_files)} image file(s).")
    print("CSV files were not created. Check the overlay images in the HTML report.")
    print(f"Open this report first: {output_dir / 'report.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

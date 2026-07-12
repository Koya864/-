#!/usr/bin/env python3
"""VectorPack — AI生成画像(PNG/JPG)をプロ向け納品データ一式に変換する.

使い方:
    python3 tools/vectorpack/vectorize.py <画像ファイル> [--out 出力先ディレクトリ]

出力(納品パック):
    <名前>.svg  — ベクターデータ(Figma/ブラウザでそのまま開ける)
    <名前>.pdf  — ベクターPDF(印刷・入稿用)
    <名前>.ai   — Illustrator互換ファイル(中身はPDF互換。Illustrator/After Effectsで開ける)
    <名前>-original.png — 元画像
    <名前>-vectorpack.zip — 上記一式

必要ライブラリ: pip install vtracer svglib reportlab pillow
"""

import argparse
import shutil
import sys
import zipfile
from pathlib import Path

from PIL import Image


def analyze_suitability(img: Image.Image) -> tuple[str, bool]:
    """ベクター化に向く画像かを色数から判定する(正直に伝えるのが機能)。"""
    small = img.convert("RGBA").resize((128, 128))
    colors = small.getcolors(maxcolors=128 * 128)
    n = len(colors) if colors else 128 * 128
    if n <= 512:
        return f"色数 {n}: ロゴ・フラットイラスト向きの画像です。高品質なベクター化が期待できます。", True
    if n <= 4096:
        return f"色数 {n}: グラデーションを含む画像です。ベクター化で色の段差が出ることがあります。", True
    return (f"色数 {n}: 写真的な画像です。ベクター化には原理的に不向きで、"
            "ファイルが巨大化し品質も落ちます(ロゴ・イラスト用途を推奨)。"), False


def png_to_svg(src: Path, dst: Path):
    import vtracer
    vtracer.convert_image_to_svg_py(
        str(src), str(dst),
        colormode="color",
        hierarchical="stacked",
        mode="spline",          # 曲線で近似(ロゴ向き)
        filter_speckle=4,       # ごみ除去
        color_precision=6,
        layer_difference=16,
        corner_threshold=60,
        length_threshold=4.0,
        splice_threshold=45,
        path_precision=3,
    )


def svg_to_pdf(svg: Path, pdf: Path):
    from reportlab.graphics import renderPDF
    from svglib.svglib import svg2rlg
    drawing = svg2rlg(str(svg))
    if drawing is None:
        raise RuntimeError("SVGの読み込みに失敗しました")
    renderPDF.drawToFile(drawing, str(pdf))


def make_pack(input_path: Path, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    name = input_path.stem

    img = Image.open(input_path)
    note, _suitable = analyze_suitability(img)
    print(f"[判定] {note}")

    # 入力をPNGに正規化(JPG等にも対応)
    normalized = out_dir / f"{name}-original.png"
    img.convert("RGBA").save(normalized)

    svg = out_dir / f"{name}.svg"
    pdf = out_dir / f"{name}.pdf"
    ai = out_dir / f"{name}.ai"

    print("[1/3] ベクター化(PNG → SVG)…")
    png_to_svg(normalized, svg)

    print("[2/3] ベクターPDFを生成(SVG → PDF)…")
    svg_to_pdf(svg, pdf)

    print("[3/3] Illustrator互換ファイルを生成(.ai)…")
    # 現代の .ai はPDFベース。PDF互換の .ai として書き出す
    shutil.copyfile(pdf, ai)

    pack = out_dir / f"{name}-vectorpack.zip"
    with zipfile.ZipFile(pack, "w", zipfile.ZIP_DEFLATED) as z:
        for f in (svg, pdf, ai, normalized):
            z.write(f, f.name)

    print("\n=== 納品パック完成 ===")
    for f in (svg, pdf, ai, normalized, pack):
        print(f"  {f}  ({f.stat().st_size:,} bytes)")
    return pack


def main():
    ap = argparse.ArgumentParser(description="VectorPack — 画像をベクター納品データ一式に変換")
    ap.add_argument("input", help="入力画像(PNG/JPG)")
    ap.add_argument("--out", default=None, help="出力先ディレクトリ(既定: 入力と同じ場所の <名前>-pack/)")
    args = ap.parse_args()

    src = Path(args.input).resolve()
    if not src.is_file():
        sys.exit(f"エラー: ファイルが見つかりません: {src}")
    out_dir = Path(args.out).resolve() if args.out else src.parent / f"{src.stem}-pack"
    make_pack(src, out_dir)


if __name__ == "__main__":
    main()

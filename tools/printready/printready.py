#!/usr/bin/env python3
"""PrintReady — AI生成PDFを「印刷して大丈夫か」診断し、入稿品質に変換する.

使い方:
    # 診断のみ
    python3 tools/printready/printready.py check チラシ.pdf

    # 診断 + 入稿用PDFに変換(高解像度化 + CMYK変換)
    python3 tools/printready/printready.py fix チラシ.pdf [--out 入稿用.pdf]

必要ライブラリ: pip install pikepdf img2pdf pillow

背景:
    ChatGPT等が出力するPDFは、中身が72〜150dpi程度のラスター画像(画面用)。
    商業印刷には300〜350dpiが必要で、色もRGBではなくCMYKが求められる。
    「画面では綺麗なのに印刷すると荒い」の原因はここにある。
"""

import argparse
import io
import sys
import zlib
from pathlib import Path

import pikepdf
from PIL import Image

PT_PER_INCH = 72.0
PRINT_DPI = 300          # 商業印刷の標準
OK_DPI = 280             # これ以上なら合格とみなす
SCREEN_DPI_HINT = 150    # これ未満は明確に「画面用」


def extract_images(page) -> list:
    """ページ内の画像XObjectを (名前, PILイメージ) で返す。"""
    out = []
    resources = page.get("/Resources", {})
    xobjects = resources.get("/XObject", {})
    for name, obj in xobjects.items():
        if obj.get("/Subtype") == "/Image":
            try:
                pdfimg = pikepdf.PdfImage(obj)
                out.append((str(name), pdfimg.as_pil_image()))
            except Exception as e:  # 特殊なエンコードはスキップして報告
                out.append((str(name), None))
    return out


def check_pdf(path: Path, quiet: bool = False) -> dict:
    """診断して結果dictを返す。"""
    pdf = pikepdf.open(path)
    report = {"path": str(path), "pages": [], "verdict_ok": True,
              "low_dpi": False, "rgb_only": False}

    for i, page in enumerate(pdf.pages, 1):
        box = [float(x) for x in page.mediabox]
        w_pt, h_pt = box[2] - box[0], box[3] - box[1]
        w_mm, h_mm = w_pt / PT_PER_INCH * 25.4, h_pt / PT_PER_INCH * 25.4
        is_a4 = abs(w_mm - 210) < 3 and abs(h_mm - 297) < 3

        page_info = {"page": i, "size_mm": (round(w_mm, 1), round(h_mm, 1)),
                     "is_a4": is_a4, "images": []}

        for name, img in extract_images(page):
            if img is None:
                page_info["images"].append({"name": name, "error": "未対応エンコード"})
                continue
            # 実効dpi = 画像のピクセル数 ÷ 紙面に置かれたサイズ(インチ)
            eff_dpi_x = img.width / (w_pt / PT_PER_INCH)
            eff_dpi_y = img.height / (h_pt / PT_PER_INCH)
            eff_dpi = round(min(eff_dpi_x, eff_dpi_y))
            page_info["images"].append({
                "name": name, "px": (img.width, img.height),
                "mode": img.mode, "effective_dpi": eff_dpi,
            })
            if eff_dpi < OK_DPI:
                report["low_dpi"] = True
                report["verdict_ok"] = False
            if img.mode != "CMYK":
                report["rgb_only"] = True
                report["verdict_ok"] = False
        if not page_info["images"]:
            page_info["note"] = "ラスター画像なし(テキスト/ベクターのみ。解像度の心配は不要)"
        report["pages"].append(page_info)

    if not quiet:
        print_report(report)
    return report


def print_report(report: dict):
    print(f"\n=== PrintReady 診断: {Path(report['path']).name} ===")
    for p in report["pages"]:
        w, h = p["size_mm"]
        size_note = "A4" if p["is_a4"] else f"{w}×{h}mm(A4ではありません)"
        print(f"\n[ページ {p['page']}] 用紙サイズ: {size_note}")
        if "note" in p:
            print(f"  {p['note']}")
        for im in p["images"]:
            if "error" in im:
                print(f"  画像 {im['name']}: {im['error']}")
                continue
            dpi = im["effective_dpi"]
            if dpi >= OK_DPI:
                grade = "OK — 印刷品質です"
            elif dpi >= SCREEN_DPI_HINT:
                grade = "注意 — 少し甘くなります(近距離で見るチラシには不足)"
            else:
                grade = "NG — 画面用の解像度です。印刷するとはっきり荒れます"
            color = "CMYK(印刷用)" if im["mode"] == "CMYK" else f"{im['mode']}(画面用の色。印刷でくすむことがあります)"
            print(f"  画像 {im['name']}: {im['px'][0]}×{im['px'][1]}px → 実効 {dpi}dpi: {grade}")
            print(f"    色モード: {color}")
    if report["verdict_ok"]:
        verdict = "このまま入稿できます"
    elif report["low_dpi"]:
        verdict = "このまま印刷すると荒れます → `fix` で入稿用に変換できます"
    else:  # 解像度は足りていて色だけRGB
        verdict = ("解像度は印刷品質です。ただし色がRGBのため、印刷所によっては"
                   "色味が変わる(鮮やかな色がくすむ)ことがあります → `fix` でCMYK化できます")
    print("\n判定:", verdict)


def fix_pdf(path: Path, out: Path):
    """低解像度ページ画像を高解像度化し、CMYK化してA4の入稿用PDFを再生成する。

    プロトタイプでは Lanczos 補間で拡大する(製品版はAI超解像に差し替え予定)。
    """
    import img2pdf

    pdf = pikepdf.open(path)
    page_jpegs = []
    for i, page in enumerate(pdf.pages, 1):
        images = [im for im in extract_images(page) if im[1] is not None]
        if not images:
            print(f"[ページ {i}] ラスター画像なし — このページはそのままの品質で保持されます")
            continue
        # AI生成チラシはページ全面が1枚画像のことがほとんど。最大の画像を採用
        img = max((im for _, im in images), key=lambda x: x.width * x.height)

        target_w = int(210 / 25.4 * PRINT_DPI)   # A4 @300dpi = 2480px
        target_h = int(297 / 25.4 * PRINT_DPI)   # 3508px
        if img.width < target_w:
            print(f"[ページ {i}] {img.width}px → {target_w}px に高解像度化(Lanczos)…")
            img = img.resize((target_w, target_h), Image.LANCZOS)
        print(f"[ページ {i}] RGB → CMYK に変換…")
        cmyk = img.convert("CMYK")
        buf = io.BytesIO()
        cmyk.save(buf, format="JPEG", quality=95, dpi=(PRINT_DPI, PRINT_DPI))
        page_jpegs.append(buf.getvalue())

    if not page_jpegs:
        sys.exit("変換対象の画像ページがありませんでした")

    a4 = (img2pdf.mm_to_pt(210), img2pdf.mm_to_pt(297))
    out.write_bytes(img2pdf.convert(page_jpegs, layout_fun=img2pdf.get_layout_fun(a4)))
    print(f"\n入稿用PDFを書き出しました: {out}")
    print("再診断:")
    check_pdf(out)


def main():
    ap = argparse.ArgumentParser(description="PrintReady — AI生成PDFの印刷品質診断・変換")
    ap.add_argument("command", choices=["check", "fix"], help="check=診断のみ / fix=入稿用に変換")
    ap.add_argument("input", help="対象のPDF")
    ap.add_argument("--out", default=None, help="fix時の出力先(既定: <名前>-print.pdf)")
    args = ap.parse_args()

    src = Path(args.input).resolve()
    if not src.is_file():
        sys.exit(f"エラー: ファイルが見つかりません: {src}")

    if args.command == "check":
        check_pdf(src)
    else:
        out = Path(args.out).resolve() if args.out else src.with_name(src.stem + "-print.pdf")
        check_pdf(src)
        print("\n--- 変換を開始します ---")
        fix_pdf(src, out)


if __name__ == "__main__":
    main()

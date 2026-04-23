
# """
# TypoPDF - Production Transparent Handwriting System
# UPDATED: Support for all 13 handwriting styles (0-12)
# ✅ Subject/Date feature REMOVED
# """

# import os
# import subprocess
# import base64
# import xml.etree.ElementTree as ET
# from io import BytesIO
# from flask import Flask, request, jsonify, send_file, render_template
# from reportlab.pdfgen import canvas
# from reportlab.lib.pagesizes import A4
# from reportlab.lib.units import cm
# from PIL import Image, ImageDraw, ImageFont
# import numpy as np
# from reportlab.lib.utils import ImageReader
# import io

# import cv2
# from demo import generate_handwriting

# # ===============================================
# # CONFIGURATION
# # ===============================================
# app = Flask(__name__)
# app.secret_key = "typopdf-production-2026"

# BASE_DIR = os.path.abspath(os.path.dirname(__file__))
# OUTPUT_DIR = os.path.join(BASE_DIR, "output")
# TEMP_DIR = os.path.join(BASE_DIR, "temp")

# for directory in [OUTPUT_DIR, TEMP_DIR]:
#     os.makedirs(directory, exist_ok=True)

# # File paths
# SVG_ORIGINAL = os.path.join(OUTPUT_DIR, "handwriting.svg")
# SVG_TRANSPARENT = os.path.join(OUTPUT_DIR, "handwriting_transparent.svg")
# PNG_ORIGINAL = os.path.join(OUTPUT_DIR, "handwriting.png")
# PNG_TRANSPARENT = os.path.join(OUTPUT_DIR, "handwriting_transparent.png")
# COMPOSITE_PREVIEW = os.path.join(OUTPUT_DIR, "preview.png")
# PDF_OUTPUT = os.path.join(OUTPUT_DIR, "document.pdf")

# # Constants
# PAGE_WIDTH, PAGE_HEIGHT = A4
# A4_300DPI = (2480, 3508)  # Width x Height at 300 DPI
# INKSCAPE = r"C:\Program Files\Inkscape\bin\inkscape.exe"

# STYLES = {
#     # 🟤 Group A: Rough / Human (Readable, not exam)
#     "style0": {"style": 0, "bias": 0.25, "name": "Style 0 - Rough Human"},
#     "style1": {"style": 1, "bias": 0.35, "name": "Style 1 - Casual Human"},
#     "style2": {"style": 2, "bias": 0.40, "name": "Style 2 - Natural Human"},

#     # 🔵 Group B: Clear / Exam Style (BEST RANGE)
#     "style3": {"style": 3, "bias": 0.55, "name": "Style 3 - Clean Exam"},
#     "style4": {"style": 4, "bias": 0.65, "name": "Style 4 - Standard Exam"},
#     "style5": {"style": 5, "bias": 0.70, "name": "Style 5 - Neat Exam"},
#     "style6": {"style": 6, "bias": 0.75, "name": "Style 6 - Very Neat"},
#     "style7": {"style": 7, "bias": 0.80, "name": "Style 7 - Formal Exam"},

#     # 🟣 Group C: Stylized (ONLY ONE)
#     "style8": {"style": 12, "bias": 0.75, "name": "Style 8 - Stylized Display"},
# }

# # Margins (cm to pixels at 300 DPI: 1cm = 118px)
# MARGINS = {
#     'left': int(2.0 * 118),    # 236px
#     'right': int(1.5 * 118),   # 177px
#     'top': int(2.5 * 118),     # 295px
#     'bottom': int(2.0 * 118),  # 236px
#     'header': int(1.0 * 118),  # 118px (no longer used for subject/date)
# }

# # ===============================================
# # CORE EXTRACTION FUNCTIONS
# # ===============================================

# def extract_svg_transparent(input_svg, output_svg):
#     """Remove SVG background"""
#     try:
#         tree = ET.parse(input_svg)
#         root = tree.getroot()
        
#         ns = {'svg': 'http://www.w3.org/2000/svg'}
#         ET.register_namespace('', ns['svg'])
        
#         removed = 0
        
#         for rect in root.findall('.//{http://www.w3.org/2000/svg}rect'):
#             parent = list(root.iter())
#             for p in parent:
#                 try:
#                     p.remove(rect)
#                     removed += 1
#                     break
#                 except ValueError:
#                     continue
        
#         for rect in root.findall('.//rect'):
#             try:
#                 root.remove(rect)
#                 removed += 1
#             except ValueError:
#                 pass
        
#         if 'viewBox' not in root.attrib:
#             width = root.get('width', '1000').replace('px', '')
#             height = root.get('height', '1000').replace('px', '')
#             root.set('viewBox', f'0 0 {width} {height}')
        
#         tree.write(output_svg, encoding='utf-8', xml_declaration=True)
        
#         print(f"✓ SVG: removed {removed} backgrounds")
#         return True
        
#     except Exception as e:
#         print(f"✗ SVG extraction failed: {e}")
#         return False


# def extract_png_transparent(input_png, output_png, threshold=240):
#     """Remove PNG background using adaptive thresholding"""
#     try:
#         img = cv2.imread(input_png)
#         if img is None:
#             raise ValueError(f"Cannot read: {input_png}")
        
#         gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
#         mask = cv2.adaptiveThreshold(
#             gray, 255,
#             cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
#             cv2.THRESH_BINARY_INV,
#             blockSize=11,
#             C=2
#         )
        
#         if mask is None or np.all(mask == 0):
#             _, mask = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY_INV)
        
#         kernel = np.ones((2, 2), np.uint8)
#         mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)
#         mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
#         mask = cv2.GaussianBlur(mask, (3, 3), 0)
        
#         img_pil = Image.open(input_png).convert('RGB')
#         alpha_channel = Image.fromarray(mask).convert('L')
#         img_pil.putalpha(alpha_channel)
        
#         img_pil.save(output_png, 'PNG', compress_level=6)
        
#         transparent_px = np.sum(mask == 0)
#         total_px = mask.size
#         ratio = (transparent_px / total_px) * 100
        
#         print(f"✓ PNG: {ratio:.1f}% background removed")
#         return True
        
#     except Exception as e:
#         print(f"✗ PNG extraction failed: {e}")
#         return False


# def overlay_on_paper(paper_path, handwriting_path, scale=1.0):
#     """
#     Overlay handwriting on paper background
#     ✅ NO subject/date parameters
#     """
#     print(f"\n🎨 OVERLAY FUNCTION CALLED")
#     print(f"   Paper: {paper_path}")
#     print(f"   Handwriting: {handwriting_path}")
#     print(f"   Scale: {scale}")
    
#     # Load paper
#     paper = Image.open(paper_path).convert('RGB')
#     original_paper_size = paper.size
#     print(f"   Original paper size: {original_paper_size[0]}x{original_paper_size[1]}px")
    
#     paper = paper.resize(A4_300DPI, Image.Resampling.LANCZOS)
#     print(f"   Resized paper to: {A4_300DPI[0]}x{A4_300DPI[1]}px (A4 @ 300 DPI)")
    
#     # Load handwriting
#     handwriting = Image.open(handwriting_path).convert('RGBA')
#     hw_w, hw_h = handwriting.size
#     print(f"   Handwriting size: {hw_w}x{hw_h}px")
    
#     # Calculate usable area (no header space needed anymore)
#     usable_w = A4_300DPI[0] - MARGINS['left'] - MARGINS['right']
#     usable_h = A4_300DPI[1] - MARGINS['top'] - MARGINS['bottom']
#     print(f"   Usable area: {usable_w}x{usable_h}px")
    
#     # Scale handwriting
#     scale_factor = min(usable_w / hw_w, usable_h / hw_h) * scale
#     new_w = int(hw_w * scale_factor)
#     new_h = int(hw_h * scale_factor)
    
#     if new_h > usable_h:
#         scale_factor = usable_h / hw_h
#         new_w = int(hw_w * scale_factor)
#         new_h = int(hw_h * scale_factor)
    
#     print(f"   Scaling handwriting to: {new_w}x{new_h}px (factor: {scale_factor:.3f})")
    
#     handwriting_scaled = handwriting.resize((new_w, new_h), Image.Resampling.LANCZOS)
    
#     # Position (directly at top margin, no header offset)
#     x = MARGINS['left']
#     y = MARGINS['top']
#     print(f"   Position: ({x}, {y})")
    
#     # Alpha composite
#     paper.paste(handwriting_scaled, (x, y), handwriting_scaled)
#     print(f"✅ Overlay complete!")
    
#     return paper


# def sanitize_text(text):
#     """Clean text for handwriting generation"""
#     replacements = {
#         '"': '"', '"': '"', ''': "'", ''': "'",
#         '–': '-', '—': '-', '…': '...',
#     }
    
#     for old, new in replacements.items():
#         text = text.replace(old, new)
    
#     text = text.encode('ascii', 'ignore').decode('ascii')
#     text = text.replace('\r\n', '\n').replace('\r', '\n')
#     text = '\n'.join([line.strip() for line in text.split('\n') if line.strip()])
    
#     return text


# # ===============================================
# # FLASK ROUTES
# # ===============================================

# @app.route("/")
# def index():
#     return render_template("index.html")


# @app.route("/generate", methods=["POST"])
# def api_generate():
#     """
#     Main API endpoint for handwriting generation
#     ✅ Subject and date parameters REMOVED
#     """
#     try:
#         data = request.get_json()
        
#         text = data.get("text", "")
#         style_id = data.get("style", "style3")
#         font_size = int(data.get("fontSize", 100))
#         ink_color = data.get("inkColor", "#000000")
        
#         print("\n" + "=" * 60)
#         print("📝 HANDWRITING GENERATION REQUEST")
#         print("=" * 60)
#         print(f"Text: {text[:50]}...")
#         print(f"Style: {style_id}")
#         print(f"Font Size: {font_size}%")
#         print(f"Ink Color: {ink_color}")
#         # ✅ Subject and date NOT logged
        
#         if not text.strip():
#             return jsonify({
#                 "status": "error",
#                 "message": "Text cannot be empty!"
#             }), 400
        
#         # Clean text
#         clean_text = sanitize_text(text)
        
#         # Get style config
#         style_config = STYLES.get(style_id, STYLES["style3"])
#         style_num = style_config["style"]
#         bias = style_config["bias"]
        
#         print(f"\n🎨 STYLE DETAILS")
#         print(f"   Style ID: {style_id}")
#         print(f"   Style Number: {style_num}")
#         print(f"   Bias: {bias}")
#         print(f"   Name: {style_config['name']}")
        
#         # Generate SVG
#         print(f"\n✍️  GENERATING HANDWRITING")
#         generate_handwriting(
#             text=clean_text,
#             output_path=SVG_ORIGINAL,
#             style=style_num,
#             bias=bias,
#             ink_color=ink_color
#         )
#         print(f"✅ SVG generated: {SVG_ORIGINAL}")
        
#         # Extract transparent SVG
#         print(f"\n🎨 EXTRACTING TRANSPARENT SVG")
#         if not extract_svg_transparent(SVG_ORIGINAL, SVG_TRANSPARENT):
#             raise Exception("Failed to extract transparent SVG")
        
#         # Convert to PNG
#         print(f"\n🖼️  CONVERTING TO PNG")
#         dpi = int(300 * (font_size / 100))
#         cmd = [
#             INKSCAPE,
#             SVG_TRANSPARENT,
#             "--export-type=png",
#             f"--export-filename={PNG_ORIGINAL}",
#             f"--export-dpi={dpi}"
#         ]
        
#         print(f"   DPI: {dpi}")
#         print(f"   Command: {' '.join(cmd)}")
        
#         result = subprocess.run(cmd, capture_output=True, text=True)
        
#         if not os.path.exists(PNG_ORIGINAL):
#             raise Exception(f"Inkscape conversion failed: {result.stderr}")
        
#         print(f"✅ PNG created: {PNG_ORIGINAL}")
        
#         # Extract transparent PNG
#         print(f"\n🎨 EXTRACTING TRANSPARENT PNG")
#         if not extract_png_transparent(PNG_ORIGINAL, PNG_TRANSPARENT):
#             raise Exception("Failed to extract transparent PNG")
        
#         # Handle background
#         bg_data = data.get("backgroundImage", "")
#         if bg_data:
#             print(f"\n🖼️  PROCESSING BACKGROUND IMAGE")
#             bg_bytes = base64.b64decode(bg_data.split(',')[1])
#             background_path = os.path.join(OUTPUT_DIR, "background.png")
            
#             with open(background_path, 'wb') as f:
#                 f.write(bg_bytes)
            
#             print(f"✅ Background saved: {background_path}")
#         else:
#             print(f"\n🖼️  CREATING DEFAULT WHITE BACKGROUND")
#             background_path = os.path.join(OUTPUT_DIR, "white_bg.png")
#             white_bg = Image.new('RGB', A4_300DPI, (255, 255, 255))
#             white_bg.save(background_path, 'PNG')
#             print(f"✅ White background created: {background_path}")
        
#         # Overlay
#         print(f"\n🎨 OVERLAYING HANDWRITING ON PAPER")
#         composite = overlay_on_paper(
#             paper_path=background_path,
#             handwriting_path=PNG_TRANSPARENT,
#             scale=1.0
#         )
        
#         composite.save(COMPOSITE_PREVIEW, 'PNG')
#         print(f"✅ Composite saved: {COMPOSITE_PREVIEW}")
        
#         # Convert to base64
#         with open(COMPOSITE_PREVIEW, 'rb') as f:
#             preview_data = base64.b64encode(f.read()).decode('utf-8')
        
#         print(f"\n✅ SUCCESS!")
#         print("=" * 60 + "\n")
        
#         return jsonify({
#             "status": "success",
#             "preview": f"data:image/png;base64,{preview_data}"
#         })
        
#     except Exception as e:
#         import traceback
#         print(f"\n{'='*60}")
#         print(f"❌ ERROR OCCURRED")
#         print(f"{'='*60}")
#         traceback.print_exc()
#         print(f"{'='*60}\n")
        
#         return jsonify({
#             "status": "error",
#             "message": str(e)
#         }), 500


# @app.route("/download-pdf", methods=["POST"])
# def download_pdf():
#     """
#     Generate and download PDF
#     ✅ Subject/date removed from PDF generation
#     """
#     try:
#         if not os.path.exists(COMPOSITE_PREVIEW):
#             return jsonify({
#                 "status": "error",
#                 "message": "Please generate a preview first!"
#             }), 400
        
#         print("\n" + "=" * 60)
#         print("📄 PDF GENERATION")
#         print("=" * 60)
        
#         # Load composite image
#         img = Image.open(COMPOSITE_PREVIEW).convert('RGB')
#         img_width, img_height = img.size
#         print(f"✓ Image loaded: {img_width}x{img_height}px")
        
#         # Margins
#         left_margin = MARGINS['left'] / 118 * cm
#         right_margin = MARGINS['right'] / 118 * cm
#         top_margin = MARGINS['top'] / 118 * cm
#         bottom_margin = MARGINS['bottom'] / 118 * cm
        
#         # Usable area (no header space)
#         usable_width = PAGE_WIDTH - left_margin - right_margin
#         usable_height = PAGE_HEIGHT - top_margin - bottom_margin
        
#         # Convert to points
#         img_width_pts = img_width * 72 / 300
#         img_height_pts = img_height * 72 / 300
        
#         # Scale
#         scale = usable_width / img_width_pts
#         scaled_width = img_width_pts * scale
#         scaled_height = img_height_pts * scale
        
#         # Multi-page calculation
#         pages_needed = max(1, int(scaled_height / usable_height) + (1 if scaled_height % usable_height > 50 else 0))
        
#         print(f"✓ Scaled: {scaled_width:.1f}x{scaled_height:.1f} pts")
#         print(f"✓ Pages needed: {pages_needed}")
        
#         # Create PDF
#         c = canvas.Canvas(PDF_OUTPUT, pagesize=A4)
        
#         for page_num in range(1, pages_needed + 1):
#             print(f"   Drawing page {page_num}/{pages_needed}...")
            
#             # Position
#             y_offset = (page_num - 1) * usable_height
#             remaining_height = scaled_height - y_offset
#             page_draw_height = min(remaining_height, usable_height)
            
#             x_position = left_margin
#             y_position = PAGE_HEIGHT - top_margin - page_draw_height
            
#             if pages_needed > 1:
#                 crop_scale = img_height / scaled_height
#                 crop_top = int(y_offset * crop_scale)
#                 crop_bottom = int((y_offset + page_draw_height) * crop_scale)
#                 crop_bottom = min(crop_bottom, img_height)
#                 cropped = img.crop((0, crop_top, img_width, crop_bottom))
#                 img_buffer = io.BytesIO()
#                 cropped.save(img_buffer, format="PNG")
#                 img_buffer.seek(0)
#                 c.drawImage(
#         ImageReader(img_buffer),
#         0,
#         0,
#         width=PAGE_WIDTH,
#         height=PAGE_HEIGHT,
#         mask='auto'
#     )

#         else:
#             img_buffer = io.BytesIO()
#             img.save(img_buffer, format="PNG")
#             img_buffer.seek(0)
#             c.drawImage(
#         ImageReader(img_buffer),
#         0,
#         0,
#         width=PAGE_WIDTH,
#         height=PAGE_HEIGHT,
#         mask='auto'
#     )
        
#             # Page number (bottom center)
#             c.saveState()
#             c.setFont("Times-Roman", 10)
#             c.setFillColorRGB(0.4, 0.4, 0.4)
#             c.drawCentredString(PAGE_WIDTH / 2, bottom_margin - 0.5 * cm, str(page_num))
#             c.restoreState()
            
#             if page_num < pages_needed:
#                 c.showPage()
        
#         c.save()
        
#         print(f"✅ PDF saved: {PDF_OUTPUT}")
        
#         # Verify PDF exists and has content
#         if not os.path.exists(PDF_OUTPUT):
#             raise Exception("PDF file was not created")
        
#         pdf_size = os.path.getsize(PDF_OUTPUT)
#         if pdf_size == 0:
#             raise Exception("PDF file is empty")
        
#         print(f"📤 Sending PDF to browser ({pdf_size} bytes)...")
        
#         # Send file with proper headers
#         filename = f'handwritten_{int(os.path.getmtime(PDF_OUTPUT))}.pdf'
#         response = send_file(
#             PDF_OUTPUT,
#             mimetype='application/pdf',
#             as_attachment=True,
#             download_name=filename
#         )
        
#         # Add CORS headers to ensure browser can download
#         response.headers['Access-Control-Allow-Origin'] = '*'
#         response.headers['Access-Control-Expose-Headers'] = 'Content-Disposition'
        
#         print(f"✅ PDF sent successfully to browser")
#         print(f"{'='*60}\n")
        
#         return response
        
#     except Exception as e:
#         import traceback
#         print(f"\n{'='*60}")
#         print(f"❌ PDF ERROR")
#         print(f"{'='*60}")
#         traceback.print_exc()
#         print(f"{'='*60}\n")
#         return jsonify({
#             "status": "error",
#             "message": f"PDF generation failed: {str(e)}"
#         }), 500


# if __name__ == "__main__":
#     print("=" * 60)
    
#     print("=" * 60)
#     print(f"✓ Server: http://127.0.0.1:5000")
#     print("=" * 60)
#     app.run(debug=True, host='0.0.0.0', port=5000)
"""
TypoPDF - Production Transparent Handwriting System
UPDATED: Support for all 13 handwriting styles (0-12)
✅ Subject/Date feature REMOVED
"""

import os
import subprocess
import base64
import xml.etree.ElementTree as ET
from io import BytesIO
from flask import Flask, request, jsonify, send_file, render_template
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from PIL import Image, ImageDraw, ImageFont
import numpy as np
from reportlab.lib.utils import ImageReader
import io

import cv2
from demo import generate_handwriting

# ===============================================
# CONFIGURATION
# ===============================================
app = Flask(__name__)
app.secret_key = "typopdf-production-2026"

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
TEMP_DIR = os.path.join(BASE_DIR, "temp")

for directory in [OUTPUT_DIR, TEMP_DIR]:
    os.makedirs(directory, exist_ok=True)

# File paths
SVG_ORIGINAL = os.path.join(OUTPUT_DIR, "handwriting.svg")
SVG_TRANSPARENT = os.path.join(OUTPUT_DIR, "handwriting_transparent.svg")
PNG_ORIGINAL = os.path.join(OUTPUT_DIR, "handwriting.png")
PNG_TRANSPARENT = os.path.join(OUTPUT_DIR, "handwriting_transparent.png")
COMPOSITE_PREVIEW = os.path.join(OUTPUT_DIR, "preview.png")

# Constants
PAGE_WIDTH, PAGE_HEIGHT = A4
A4_300DPI = (2480, 3508)  # Width x Height at 300 DPI
INKSCAPE = r"C:\Program Files\Inkscape\bin\inkscape.exe"

STYLES = {
    # 🟤 Group A: Rough / Human (Readable, not exam)
    "style0": {"style": 0, "bias": 0.25, "name": "Style 0 - Rough Human"},
    "style1": {"style": 1, "bias": 0.35, "name": "Style 1 - Casual Human"},
    "style2": {"style": 2, "bias": 0.40, "name": "Style 2 - Natural Human"},

    # 🔵 Group B: Clear / Exam Style (BEST RANGE)
    "style3": {"style": 3, "bias": 0.55, "name": "Style 3 - Clean Exam"},
    "style4": {"style": 4, "bias": 0.65, "name": "Style 4 - Standard Exam"},
    "style5": {"style": 5, "bias": 0.70, "name": "Style 5 - Neat Exam"},
    "style6": {"style": 6, "bias": 0.75, "name": "Style 6 - Very Neat"},
    "style7": {"style": 7, "bias": 0.80, "name": "Style 7 - Formal Exam"},

    # 🟣 Group C: Stylized (ONLY ONE)
    "style8": {"style": 12, "bias": 0.75, "name": "Style 8 - Stylized Display"},
}

# Margins (cm to pixels at 300 DPI: 1cm = 118px)
MARGINS = {
    'left': int(2.0 * 118),    # 236px
    'right': int(1.5 * 118),   # 177px
    'top': int(2.5 * 118),     # 295px
    'bottom': int(2.0 * 118),  # 236px
    'header': int(1.0 * 118),  # 118px (no longer used for subject/date)
}

# Shared state: last background path set by api_generate, read by download_pdf
_last_background_path = None


# ===============================================
# SVG MULTI-PAGE HELPERS
# ===============================================

def parse_svg_viewbox(svg_path):
    """
    Return (vb_x, vb_y, vb_w, vb_h) from the SVG's viewBox attribute.
    Falls back to width/height attributes when viewBox is absent.
    All values are floats in SVG user-units.
    """
    tree = ET.parse(svg_path)
    root = tree.getroot()

    # Strip XML namespace prefix so attribute lookups work with or without ns
    vb = root.get('viewBox', '').strip()
    if vb:
        parts = vb.replace(',', ' ').split()
        return tuple(float(p) for p in parts)   # (x, y, w, h)

    # Fall back to width / height
    w = float(root.get('width',  '1000').replace('px', ''))
    h = float(root.get('height', '1000').replace('px', ''))
    return (0.0, 0.0, w, h)


def render_svg_segment_to_transparent_png(
    src_svg,
    out_png,
    vb_x, vb_y, vb_w,
    seg_y,          # top of this segment in SVG user-units
    seg_h_svg,      # height of this segment in SVG user-units
    out_w_px,       # desired PNG width in pixels (= USABLE_W_PX)
    out_h_px,       # desired PNG height in pixels (= actual seg height)
    inkscape_exe,
    threshold=240
):
    """
    1. Clone src_svg and set its viewBox to show only the requested segment.
    2. Export to PNG via Inkscape at the exact pixel dimensions given.
    3. Remove the white background to leave only the ink strokes.
    Returns True on success.
    """
    import copy, tempfile

    # ── Clone SVG and patch viewBox + explicit size ─────────────────────────
    tree = ET.parse(src_svg)
    root = tree.getroot()

    # Register the SVG namespace so we don't get ns0: prefixes
    ET.register_namespace('', 'http://www.w3.org/2000/svg')

    new_vb = f"{vb_x} {seg_y} {vb_w} {seg_h_svg}"
    root.set('viewBox', new_vb)
    # Tell Inkscape the exact pixel size to export
    root.set('width',  f"{out_w_px}px")
    root.set('height', f"{out_h_px}px")

    # Write patched SVG to a temp file
    tmp_svg = out_png.replace('.png', '_seg.svg')
    tree.write(tmp_svg, encoding='utf-8', xml_declaration=True)

    # ── Render via Inkscape ──────────────────────────────────────────────────
    cmd = [
        inkscape_exe,
        tmp_svg,
        '--export-type=png',
        f'--export-filename={out_png}',
        '--export-dpi=300',
        f'--export-width={out_w_px}',
        f'--export-height={out_h_px}',
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if not os.path.exists(out_png):
        raise RuntimeError(
            f"Inkscape failed for segment SVG {tmp_svg}:\n{result.stderr}"
        )

    # ── Remove white background ──────────────────────────────────────────────
    img = cv2.imread(out_png)
    if img is None:
        raise RuntimeError(f"Cannot read Inkscape output: {out_png}")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    mask = cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        blockSize=11, C=2
    )
    if np.all(mask == 0):
        _, mask = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY_INV)

    kernel = np.ones((2, 2), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN,  kernel, iterations=1)
    mask = cv2.GaussianBlur(mask, (3, 3), 0)

    img_pil = Image.open(out_png).convert('RGB')
    img_pil.putalpha(Image.fromarray(mask).convert('L'))
    img_pil.save(out_png, 'PNG', compress_level=6)

    # Clean up temp SVG
    try:
        os.remove(tmp_svg)
    except OSError:
        pass

    return True

# ===============================================
# CORE EXTRACTION FUNCTIONS
# ===============================================

def extract_svg_transparent(input_svg, output_svg):
    """Remove SVG background"""
    try:
        tree = ET.parse(input_svg)
        root = tree.getroot()
        
        ns = {'svg': 'http://www.w3.org/2000/svg'}
        ET.register_namespace('', ns['svg'])
        
        removed = 0
        
        for rect in root.findall('.//{http://www.w3.org/2000/svg}rect'):
            parent = list(root.iter())
            for p in parent:
                try:
                    p.remove(rect)
                    removed += 1
                    break
                except ValueError:
                    continue
        
        for rect in root.findall('.//rect'):
            try:
                root.remove(rect)
                removed += 1
            except ValueError:
                pass
        
        if 'viewBox' not in root.attrib:
            width = root.get('width', '1000').replace('px', '')
            height = root.get('height', '1000').replace('px', '')
            root.set('viewBox', f'0 0 {width} {height}')
        
        tree.write(output_svg, encoding='utf-8', xml_declaration=True)
        
        print(f"✓ SVG: removed {removed} backgrounds")
        return True
        
    except Exception as e:
        print(f"✗ SVG extraction failed: {e}")
        return False


def extract_png_transparent(input_png, output_png, threshold=240):
    """Remove PNG background using adaptive thresholding"""
    try:
        img = cv2.imread(input_png)
        if img is None:
            raise ValueError(f"Cannot read: {input_png}")
        
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        mask = cv2.adaptiveThreshold(
            gray, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            blockSize=11,
            C=2
        )
        
        if mask is None or np.all(mask == 0):
            _, mask = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY_INV)
        
        kernel = np.ones((2, 2), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
        mask = cv2.GaussianBlur(mask, (3, 3), 0)
        
        img_pil = Image.open(input_png).convert('RGB')
        alpha_channel = Image.fromarray(mask).convert('L')
        img_pil.putalpha(alpha_channel)
        
        img_pil.save(output_png, 'PNG', compress_level=6)
        
        transparent_px = np.sum(mask == 0)
        total_px = mask.size
        ratio = (transparent_px / total_px) * 100
        
        print(f"✓ PNG: {ratio:.1f}% background removed")
        return True
        
    except Exception as e:
        print(f"✗ PNG extraction failed: {e}")
        return False


def overlay_on_paper(paper_path, handwriting_path, scale=1.0):
    """
    Overlay handwriting on paper background for PREVIEW.
    Scales by WIDTH only (same as PDF export) so long text is never squished.
    Only the first-page segment is shown in the preview image.
    Returns (composite_image, total_pages_int).
    """
    print(f"\n🎨 OVERLAY FUNCTION CALLED (width-scale preview)")
    print(f"   Paper: {paper_path}")
    print(f"   Handwriting: {handwriting_path}")

    # Load paper and resize to A4 @ 300 DPI
    paper_template = Image.open(paper_path).convert('RGB')
    paper_template = paper_template.resize(A4_300DPI, Image.Resampling.LANCZOS)
    print(f"   Paper resized to: {A4_300DPI[0]}x{A4_300DPI[1]}px (A4 @ 300 DPI)")

    # Load handwriting
    handwriting = Image.open(handwriting_path).convert('RGBA')
    hw_w, hw_h = handwriting.size
    print(f"   Handwriting size: {hw_w}x{hw_h}px")

    # Usable area on one A4 page
    usable_w = A4_300DPI[0] - MARGINS['left'] - MARGINS['right']
    usable_h = A4_300DPI[1] - MARGINS['top'] - MARGINS['bottom']
    print(f"   Usable area per page: {usable_w}x{usable_h}px")

    # ── Scale by WIDTH only (identical to the PDF export path) ──────────────
    width_scale = (usable_w / hw_w) * scale
    scaled_w = int(hw_w * width_scale)
    scaled_h = int(hw_h * width_scale)   # height grows naturally – may span many pages
    print(f"   Width-scaled handwriting: {scaled_w}x{scaled_h}px (factor: {width_scale:.3f})")

    # Total pages (ceiling division)
    total_pages = max(1, -(-scaled_h // usable_h))
    print(f"   Total pages: {total_pages}")

    handwriting_scaled = handwriting.resize((scaled_w, scaled_h), Image.Resampling.LANCZOS)

    # ── For the preview, show only the FIRST page segment ───────────────────
    first_page_h = min(scaled_h, usable_h)
    hw_segment = handwriting_scaled.crop((0, 0, scaled_w, first_page_h))

    # Compose onto fresh paper copy
    page_bg = paper_template.copy()
    paste_x = MARGINS['left']
    paste_y = MARGINS['top']
    page_bg.paste(hw_segment, (paste_x, paste_y), hw_segment)
    print(f"✅ Preview overlay complete! (page 1 of {total_pages})")

    return page_bg, total_pages


def sanitize_text(text):
    """Clean text for handwriting generation"""
    replacements = {
        '"': '"', '"': '"', ''': "'", ''': "'",
        '–': '-', '—': '-', '…': '...',
    }
    
    for old, new in replacements.items():
        text = text.replace(old, new)
    
    text = text.encode('ascii', 'ignore').decode('ascii')
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = '\n'.join([line.strip() for line in text.split('\n') if line.strip()])
    
    return text


# ===============================================
# FLASK ROUTES
# ===============================================

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/generate", methods=["POST"])
def api_generate():
    """
    Main API endpoint for handwriting generation
    ✅ Subject and date parameters REMOVED
    """
    try:
        data = request.get_json()
        
        text = data.get("text", "")
        style_id = data.get("style", "style3")
        font_size = int(data.get("fontSize", 100))
        ink_color = data.get("inkColor", "#000000")
        
        print("\n" + "=" * 60)
        print("📝 HANDWRITING GENERATION REQUEST")
        print("=" * 60)
        print(f"Text: {text[:50]}...")
        print(f"Style: {style_id}")
        print(f"Font Size: {font_size}%")
        print(f"Ink Color: {ink_color}")
        # ✅ Subject and date NOT logged
        
        if not text.strip():
            return jsonify({
                "status": "error",
                "message": "Text cannot be empty!"
            }), 400
        
        # Clean text
        clean_text = sanitize_text(text)
        
        # Get style config
        style_config = STYLES.get(style_id, STYLES["style3"])
        style_num = style_config["style"]
        bias = style_config["bias"]
        
        print(f"\n🎨 STYLE DETAILS")
        print(f"   Style ID: {style_id}")
        print(f"   Style Number: {style_num}")
        print(f"   Bias: {bias}")
        print(f"   Name: {style_config['name']}")
        
        # Generate SVG
        print(f"\n✍️  GENERATING HANDWRITING")
        generate_handwriting(
            text=clean_text,
            output_path=SVG_ORIGINAL,
            style=style_num,
            bias=bias,
            ink_color=ink_color
        )
        print(f"✅ SVG generated: {SVG_ORIGINAL}")
        
        # Extract transparent SVG
        print(f"\n🎨 EXTRACTING TRANSPARENT SVG")
        if not extract_svg_transparent(SVG_ORIGINAL, SVG_TRANSPARENT):
            raise Exception("Failed to extract transparent SVG")
        
        # Convert to PNG
        print(f"\n🖼️  CONVERTING TO PNG")
        dpi = int(300 * (font_size / 100))
        cmd = [
            INKSCAPE,
            SVG_TRANSPARENT,
            "--export-type=png",
            f"--export-filename={PNG_ORIGINAL}",
            f"--export-dpi={dpi}"
        ]
        
        print(f"   DPI: {dpi}")
        print(f"   Command: {' '.join(cmd)}")
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if not os.path.exists(PNG_ORIGINAL):
            raise Exception(f"Inkscape conversion failed: {result.stderr}")
        
        print(f"✅ PNG created: {PNG_ORIGINAL}")
        
        # Extract transparent PNG
        print(f"\n🎨 EXTRACTING TRANSPARENT PNG")
        if not extract_png_transparent(PNG_ORIGINAL, PNG_TRANSPARENT):
            raise Exception("Failed to extract transparent PNG")
        
        # Handle background
        bg_data = data.get("backgroundImage", "")
        if bg_data:
            print(f"\n🖼️  PROCESSING BACKGROUND IMAGE")
            bg_bytes = base64.b64decode(bg_data.split(',')[1])
            background_path = os.path.join(OUTPUT_DIR, "background.png")
            
            with open(background_path, 'wb') as f:
                f.write(bg_bytes)
            
            print(f"✅ Background saved: {background_path}")
        else:
            print(f"\n🖼️  CREATING DEFAULT WHITE BACKGROUND")
            background_path = os.path.join(OUTPUT_DIR, "white_bg.png")
            white_bg = Image.new('RGB', A4_300DPI, (255, 255, 255))
            white_bg.save(background_path, 'PNG')
            print(f"✅ White background created: {background_path}")
        
        # Share background path with download_pdf
        global _last_background_path
        _last_background_path = background_path
        
        # Overlay – returns (image, total_pages)
        print(f"\n🎨 OVERLAYING HANDWRITING ON PAPER")
        composite, total_pages = overlay_on_paper(
            paper_path=background_path,
            handwriting_path=PNG_TRANSPARENT,
            scale=1.0
        )
        
        composite.save(COMPOSITE_PREVIEW, 'PNG')
        print(f"✅ Composite saved: {COMPOSITE_PREVIEW} ({total_pages} page(s) total)")
        
        # Convert to base64
        with open(COMPOSITE_PREVIEW, 'rb') as f:
            preview_data = base64.b64encode(f.read()).decode('utf-8')
        
        print(f"\n✅ SUCCESS! ({total_pages} page(s))")
        print("=" * 60 + "\n")
        
        return jsonify({
            "status": "success",
            "preview": f"data:image/png;base64,{preview_data}",
            "pages": total_pages
        })
        
    except Exception as e:
        import traceback
        print(f"\n{'='*60}")
        print(f"❌ ERROR OCCURRED")
        print(f"{'='*60}")
        traceback.print_exc()
        print(f"{'='*60}\n")
        
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@app.route("/download-pdf", methods=["POST"])
def download_pdf():
    """
    SVG-native multi-page vertical PDF export.

    Pipeline per page:
      1. Clip SVG via viewBox offset  → render segment PNG via Inkscape
      2. Remove white background      → transparent handwriting PNG
      3. Draw background paper (full A4) on PDF canvas  ← every page
      4. Draw transparent handwriting PNG on top         ← at margin
      5. showPage()                                      ← every page

    Splitting at SVG level = Inkscape renders each page at native 300 DPI
    → no resampling, crisp text, consistent margins across all pages.
    """
    try:
        # ── Guards ──────────────────────────────────────────────────────────────
        if not os.path.exists(SVG_TRANSPARENT):
            return jsonify({
                "status": "error",
                "message": "Please generate a preview first!"
            }), 400

        global _last_background_path
        if not _last_background_path or not os.path.exists(_last_background_path):
            return jsonify({
                "status": "error",
                "message": "Background not found – please generate a preview first!"
            }), 400

        print("\n" + "=" * 60)
        print("📄 PDF GENERATION – SVG-native multi-page vertical flow")
        print("=" * 60)

        # ── A4 pixel constants (300 DPI) ────────────────────────────────────────
        PAGE_W_PX, PAGE_H_PX = A4_300DPI          # 2480 × 3508 px
        MARGIN_L = MARGINS['left']                 # 236 px
        MARGIN_R = MARGINS['right']                # 177 px
        MARGIN_T = MARGINS['top']                  # 295 px
        MARGIN_B = MARGINS['bottom']               # 236 px

        # Usable pixel area per page
        USABLE_W_PX = PAGE_W_PX - MARGIN_L - MARGIN_R   # 2067 px
        USABLE_H_PX = PAGE_H_PX - MARGIN_T - MARGIN_B   # 2977 px
        print(f"✓ A4 page:    {PAGE_W_PX}×{PAGE_H_PX} px")
        print(f"✓ Usable area: {USABLE_W_PX}×{USABLE_H_PX} px per page")

        # ── Parse SVG viewBox ────────────────────────────────────────────────────
        vb_x, vb_y, vb_w, vb_h = parse_svg_viewbox(SVG_TRANSPARENT)
        print(f"✓ SVG viewBox: x={vb_x} y={vb_y} w={vb_w} h={vb_h} (SVG units)")

        # ── Map SVG units → pixels via width-only scale ──────────────────────────
        # Inkscape will render vb_w SVG units as USABLE_W_PX pixels.
        px_per_svg_unit = USABLE_W_PX / vb_w

        # Total SVG height in pixels at this scale
        full_h_px = vb_h * px_per_svg_unit
        print(f"✓ Full SVG height at scale: {full_h_px:.0f} px")

        # One A4 page height in SVG user-units
        page_h_svg = USABLE_H_PX / px_per_svg_unit
        print(f"✓ One A4 page height in SVG units: {page_h_svg:.2f}")

        # ── Number of pages (ceiling division) ──────────────────────────────────
        import math
        pages_needed = max(1, math.ceil(vb_h / page_h_svg))
        print(f"✓ Pages needed: {pages_needed}")

        # ── Prepare background template (RGB PIL, loaded once) ───────────────────
        bg_pil = Image.open(_last_background_path).convert('RGB')
        bg_pil = bg_pil.resize(A4_300DPI, Image.Resampling.LANCZOS)
        # Pre-encode background to PNG bytes for ReportLab
        bg_buf = io.BytesIO()
        bg_pil.save(bg_buf, format='PNG', compress_level=3)
        bg_buf.seek(0)
        bg_reader = ImageReader(bg_buf)

        # ReportLab coordinate helpers
        pts_per_px   = 72.0 / 300.0             # 0.24 pt per pixel
        margin_l_pts = MARGIN_L * pts_per_px
        margin_t_pts = MARGIN_T * pts_per_px
        usable_w_pts = USABLE_W_PX * pts_per_px

        # ── Build PDF in RAM ─────────────────────────────────────────────────────
        pdf_buffer = io.BytesIO()
        c = canvas.Canvas(pdf_buffer, pagesize=A4)

        for page_num in range(pages_needed):
            print(f"   Rendering page {page_num + 1}/{pages_needed} via Inkscape ...")

            # ── 1.  Calculate this page's SVG viewport ───────────────────────────
            seg_y_svg   = vb_y + page_num * page_h_svg
            remaining_h = (vb_y + vb_h) - seg_y_svg
            seg_h_svg_actual = min(page_h_svg, remaining_h)  # last page may be shorter

            # Pixel height of this segment (may be < USABLE_H_PX on last page)
            seg_h_px = int(round(seg_h_svg_actual * px_per_svg_unit))

            # ── 2.  Render SVG segment → transparent PNG ─────────────────────────
            seg_png = os.path.join(TEMP_DIR, f"page_{page_num + 1}_hw.png")
            render_svg_segment_to_transparent_png(
                src_svg     = SVG_TRANSPARENT,
                out_png     = seg_png,
                vb_x        = vb_x,
                vb_y        = vb_y,
                vb_w        = vb_w,
                seg_y       = seg_y_svg,
                seg_h_svg   = seg_h_svg_actual,
                out_w_px    = USABLE_W_PX,
                out_h_px    = seg_h_px,
                inkscape_exe= INKSCAPE,
            )
            print(f"   ✓ Segment PNG: {USABLE_W_PX}×{seg_h_px} px")

            # ── 3.  Draw background paper (full A4, every page) ──────────────────
            c.drawImage(
                bg_reader,
                0, 0,
                width=PAGE_WIDTH,
                height=PAGE_HEIGHT,
                preserveAspectRatio=False
            )

            # ── 4.  Draw transparent handwriting segment at margin position ───────
            #    ReportLab: y=0 at BOTTOM of page
            seg_h_pts = seg_h_px * pts_per_px
            draw_x    = margin_l_pts
            draw_y    = PAGE_HEIGHT - margin_t_pts - seg_h_pts

            c.drawImage(
                ImageReader(seg_png),
                draw_x, draw_y,
                width  = usable_w_pts,
                height = seg_h_pts,
                mask   = 'auto'         # honours PNG alpha transparency
            )

            # ── 5.  Subtle page number at bottom centre ──────────────────────────
            c.saveState()
            c.setFont("Times-Roman", 10)
            c.setFillColorRGB(0.45, 0.45, 0.45)
            c.drawCentredString(PAGE_WIDTH / 2, 0.4 * cm, str(page_num + 1))
            c.restoreState()

            # ── 6.  Commit page to PDF (every page, including last) ──────────────
            c.showPage()

        c.save()

        # Clean up temp segment PNGs
        for page_num in range(pages_needed):
            tmp = os.path.join(TEMP_DIR, f"page_{page_num + 1}_hw.png")
            try:
                os.remove(tmp)
            except OSError:
                pass

        pdf_size = pdf_buffer.tell()
        pdf_buffer.seek(0)
        print(f"📤 Streaming {pages_needed}-page PDF ({pdf_size:,} bytes) ...")

        import time
        filename = f"handwritten_{int(time.time())}.pdf"

        response = send_file(
            pdf_buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )
        response.headers['Access-Control-Allow-Origin']   = '*'
        response.headers['Access-Control-Expose-Headers'] = 'Content-Disposition'

        print(f"✅ PDF streamed successfully ({pages_needed} pages)")
        print(f"{'='*60}\n")
        return response

    except Exception as e:
        import traceback
        print(f"\n{'='*60}")
        print(f"❌ PDF ERROR")
        print(f"{'='*60}")
        traceback.print_exc()
        print(f"{'='*60}\n")
        return jsonify({
            "status": "error",
            "message": f"PDF generation failed: {str(e)}"
        }), 500


if __name__ == "__main__":
    print("=" * 60)
    print("=" * 60)
    print(f"✓ Server: http://127.0.0.1:5000")
    print("=" * 60)
    app.run(debug=True, host='0.0.0.0', port=5000)
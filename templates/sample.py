"""
TypoPDF - Production Transparent Handwriting System
UPDATED: Support for all 13 handwriting styles (0-12)
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
PDF_OUTPUT = os.path.join(OUTPUT_DIR, "document.pdf")

# Constants
PAGE_WIDTH, PAGE_HEIGHT = A4
A4_300DPI = (2480, 3508)  # Width x Height at 300 DPI
INKSCAPE = r"C:\Program Files\Inkscape\bin\inkscape.exe"

# ALL 13 HANDWRITING STYLES (0-12)

STYLES = {
    "style0":  {"style": 0,  "bias": 0.25, "name": "Style 0 - Rough"},
    "style1":  {"style": 1,  "bias": 0.35, "name": "Style 1 - Casual"},
    "style2":  {"style": 2,  "bias": 0.45, "name": "Style 2 - Natural"},
    "style3":  {"style": 3,  "bias": 0.55, "name": "Style 3 - Flowing"},
    "style4":  {"style": 4,  "bias": 0.65, "name": "Style 4 - Exam"},
    "style5":  {"style": 5,  "bias": 0.75, "name": "Style 5 - Neat"},
    "style6":  {"style": 6,  "bias": 0.85, "name": "Style 6 - Rounded"},
    "style7":  {"style": 7,  "bias": 0.95, "name": "Style 7 - Formal"},
    "style8":  {"style": 8,  "bias": 1.05, "name": "Style 8 - Elegant"},
    "style9":  {"style": 9,  "bias": 1.15, "name": "Style 9 - Bold"},
    "style10": {"style": 10, "bias": 1.25, "name": "Style 10 - Artistic"},
    "style11": {"style": 11, "bias": 1.35, "name": "Style 11 - Decorative"},
    "style12": {"style": 12, "bias": 0.75, "name": "Style 12 - Stylized"},
}

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
#     "style7": {"style": 8, "bias": 0.80, "name": "Style 7 - Formal Exam"},

#     # 🟣 Group C: Stylized (ONLY ONE)
#     "style8": {"style": 12, "bias": 0.75, "name": "Style 8 - Stylized Display"},
    
# }

# Margins (cm to pixels at 300 DPI: 1cm = 118px)
MARGINS = {
    'left': int(2.0 * 118),    # 236px
    'right': int(1.5 * 118),   # 177px
    'top': int(2.5 * 118),     # 295px
    'bottom': int(2.0 * 118),  # 236px
    'header': int(1.0 * 118),  # 118px
}

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
        
        # Remove rectangles
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
        
        # Ensure viewBox
        if 'viewBox' not in root.attrib:
            width = root.get('width', '1000').replace('px', '')
            height = root.get('height', '1000').replace('px', '')
            root.set('viewBox', f'0 0 {width} {height}')
        
        tree.write(output_svg, encoding='utf-8', xml_declaration=True)
        
        print(f"✓ SVG extraction: removed {removed} background elements")
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
        
        img_pil.save(output_png, 'PNG', optimize=True, compress_level=9)
        
        transparent_px = np.sum(mask == 0)
        total_px = mask.size
        ratio = (transparent_px / total_px) * 100
        
        print(f"✓ PNG extraction: {ratio:.1f}% background removed")
        return True
        
    except Exception as e:
        print(f"✗ PNG extraction failed: {e}")
        return False


def overlay_on_paper(paper_path, handwriting_path, subject="", date="", scale=1.0):
    """Overlay handwriting on paper background"""
    print(f"\n🎨 OVERLAY FUNCTION CALLED")
    print(f"   Paper: {paper_path}")
    print(f"   Handwriting: {handwriting_path}")
    print(f"   Scale: {scale}")
    
    # Load paper
    paper = Image.open(paper_path).convert('RGB')
    original_paper_size = paper.size
    print(f"   Original paper size: {original_paper_size[0]}x{original_paper_size[1]}px")
    
    paper = paper.resize(A4_300DPI, Image.Resampling.LANCZOS)
    print(f"   Resized paper to: {A4_300DPI[0]}x{A4_300DPI[1]}px (A4 @ 300 DPI)")
    
    # Load handwriting
    handwriting = Image.open(handwriting_path).convert('RGBA')
    hw_w, hw_h = handwriting.size
    print(f"   Handwriting size: {hw_w}x{hw_h}px")
    
    # Calculate usable area
    usable_w = A4_300DPI[0] - MARGINS['left'] - MARGINS['right']
    usable_h = A4_300DPI[1] - MARGINS['top'] - MARGINS['bottom'] - MARGINS['header']
    print(f"   Usable area: {usable_w}x{usable_h}px")
    
    # Scale handwriting
    scale_factor = min(usable_w / hw_w, usable_h / hw_h) * scale
    new_w = int(hw_w * scale_factor)
    new_h = int(hw_h * scale_factor)
    
    if new_h > usable_h:
        scale_factor = usable_h / hw_h
        new_w = int(hw_w * scale_factor)
        new_h = int(hw_h * scale_factor)
    
    print(f"   Scaling handwriting to: {new_w}x{new_h}px (factor: {scale_factor:.3f})")
    
    handwriting_scaled = handwriting.resize((new_w, new_h), Image.Resampling.LANCZOS)
    
    # Position
    x = MARGINS['left']
    y = MARGINS['top'] + MARGINS['header']
    print(f"   Position: ({x}, {y})")
    
    # Alpha composite
    paper.paste(handwriting_scaled, (x, y), handwriting_scaled)
    print(f"✅ Overlay complete!")
    
    # Add header text if provided
    if subject or date:
        draw = ImageDraw.Draw(paper)
        try:
            font = ImageFont.truetype("arial.ttf", 32)
        except:
            font = ImageFont.load_default()
        
        header_y = MARGINS['top'] + 30
        text_color = (50, 50, 50)
        
        if subject:
            draw.text((MARGINS['left'], header_y), f"Subject: {subject}", fill=text_color, font=font)
        
        if date:
            date_text = f"Date: {date}"
            bbox = draw.textbbox((0, 0), date_text, font=font)
            date_width = bbox[2] - bbox[0]
            date_x = A4_300DPI[0] - MARGINS['right'] - date_width
            draw.text((date_x, header_y), date_text, fill=text_color, font=font)
    
    return paper


def sanitize_text(text):
    """Clean text for handwriting generation"""
    replacements = {
        '"': '"', '"': '"', ''': "'", ''': "'",
        '–': '-', '—': '-', '…': '...',
    }
    
    for old, new in replacements.items():
        text = text.replace(old, new)
    
    text = text.encode('ascii', 'ignore').decode('ascii')
    return text


# ===============================================
# ROUTES
# ===============================================

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/generate", methods=["POST"])
def generate():
    """Generate handwriting preview with paper overlay"""
    try:
        data = request.json
        
        raw_text = data.get("text", "").strip()
        style_key = data.get("style", "style5")
        ink_color = data.get("ink_color", "#000000")
        font_size = float(data.get("font_size", 1.0))
        transparent = data.get("transparent", True)
        paper_image = data.get("paper_image", None)
        
        print(f"\n{'='*70}")
        print(f"📝 NEW GENERATION REQUEST")
        print(f"{'='*70}")
        print(f"Text length: {len(raw_text)} chars")
        print(f"Style: {style_key}")
        print(f"Ink color: {ink_color}")
        print(f"Font size: {font_size}x")
        print(f"Transparent: {transparent}")
        
        if paper_image:
            paper_size = len(paper_image)
            print(f"Paper image: YES ({paper_size:,} bytes = {paper_size/1024:.1f} KB)")
        else:
            print(f"Paper image: NO")
        
        print(f"{'='*70}\n")
        
        if not raw_text:
            return jsonify({
                "status": "error",
                "message": "Please enter some text"
            }), 400
        
        text = sanitize_text(raw_text)
        style_config = STYLES.get(style_key, STYLES["style5"])
        
        print(f"📊 Using {style_config['name']}")
        print(f"   Style index: {style_config['style']}")
        print(f"   Bias: {style_config['bias']}")
        
        # Step 1: Generate SVG
        print(f"\n🔄 Step 1: Generating handwriting SVG...")
        generate_handwriting(
            text=text,
            output_path=SVG_ORIGINAL,
            style=style_config["style"],
            bias=style_config["bias"],
            ink_color=ink_color
        )
        print(f"✅ SVG saved: {SVG_ORIGINAL}")
        
        # Step 2: Extract transparent SVG
        if transparent:
            print(f"\n🔄 Step 2: Extracting transparent SVG...")
            success = extract_svg_transparent(SVG_ORIGINAL, SVG_TRANSPARENT)
            svg_to_use = SVG_TRANSPARENT if success else SVG_ORIGINAL
        else:
            svg_to_use = SVG_ORIGINAL
        
        # Step 3: Convert to PNG
        print(f"\n🔄 Step 3: Converting SVG → PNG (300 DPI)...")
        if not os.path.exists(INKSCAPE):
            return jsonify({
                "status": "error",
                "message": f"Inkscape not found at: {INKSCAPE}"
            }), 500
        
        png_output = PNG_TRANSPARENT if transparent else PNG_ORIGINAL
        
        result = subprocess.run([
            INKSCAPE,
            svg_to_use,
            "--export-type=png",
            f"--export-filename={png_output}",
            "--export-dpi=300"
        ], check=True, capture_output=True, text=True)
        
        if not os.path.exists(png_output):
            print(f"❌ PNG not created!")
            raise Exception("PNG conversion failed")
        
        print(f"✅ PNG saved: {png_output}")
        
        # Step 4: PNG transparency
        if transparent:
            print(f"\n🔄 Step 4: Applying PNG alpha masking...")
            extract_png_transparent(png_output, png_output)
        
        # Step 5: Overlay on paper
        preview_url = None
        
        if paper_image and transparent:
            print(f"\n🔄 Step 5: Creating paper overlay...")
            print(f"   Paper image size: {len(paper_image):,} bytes")
            
            try:
                # Decode base64
                if 'base64,' in paper_image:
                    paper_data = paper_image.split('base64,')[1]
                else:
                    paper_data = paper_image
                
                paper_bytes = base64.b64decode(paper_data)
                print(f"   Decoded: {len(paper_bytes):,} bytes")
                
                # Save temp
                temp_paper = os.path.join(TEMP_DIR, "uploaded_paper.png")
                with open(temp_paper, 'wb') as f:
                    f.write(paper_bytes)
                print(f"   Saved temp: {temp_paper}")
                
                # Verify
                paper_check = Image.open(temp_paper)
                print(f"   Verified: {paper_check.size[0]}x{paper_check.size[1]}px, mode={paper_check.mode}")
                
                # Create overlay
                composite = overlay_on_paper(
                    paper_path=temp_paper,
                    handwriting_path=png_output,
                    subject="",
                    date="",
                    scale=font_size
                )
                
                # Save
                composite.save(COMPOSITE_PREVIEW, 'PNG', optimize=True)
                print(f"\n✅ COMPOSITE SAVED: {COMPOSITE_PREVIEW}")
                print(f"   Size: {composite.size[0]}x{composite.size[1]}px")
                
                preview_url = f"/output/preview.png?t={int(os.path.getmtime(COMPOSITE_PREVIEW))}"
                
                # Cleanup
                if os.path.exists(temp_paper):
                    os.remove(temp_paper)
                    print(f"   Cleaned temp file")
                
            except Exception as e:
                print(f"\n⚠️  OVERLAY FAILED: {e}")
                import traceback
                traceback.print_exc()
                preview_url = f"/output/{os.path.basename(png_output)}?t={int(os.path.getmtime(png_output))}"
        else:
            reason = "no paper" if not paper_image else "not transparent"
            print(f"\nℹ️  Skipping overlay ({reason})")
            preview_url = f"/output/{os.path.basename(png_output)}?t={int(os.path.getmtime(png_output))}"
        
        print(f"\n{'='*70}")
        print(f"✅ SUCCESS")
        print(f"Preview URL: {preview_url}")
        print(f"{'='*70}\n")
        
        return jsonify({
            "status": "success",
            "image_url": preview_url,
            "message": f"Generated with {style_config['name']}"
        })
        
    except Exception as e:
        import traceback
        print(f"\n{'='*70}")
        print(f"❌ ERROR:")
        print(f"{'='*70}")
        traceback.print_exc()
        print(f"{'='*70}\n")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@app.route("/output/<path:filename>")
def output_file(filename):
    """Serve generated files"""
    filepath = os.path.join(OUTPUT_DIR, filename)
    if os.path.exists(filepath):
        return send_file(filepath)
    else:
        return jsonify({"error": "File not found"}), 404


@app.route("/download-pdf", methods=["POST"])
def download_pdf():
    """Generate PDF with paper background"""
    try:
        data = request.json
        
        text = data.get("text", "").strip()
        subject = data.get("subject", "")
        date = data.get("date", "")
        paper_image = data.get("paper_image", None)
        
        print(f"\n{'='*70}")
        print(f"📄 PDF GENERATION")
        print(f"{'='*70}")
        print(f"Subject: {subject or '(none)'}")
        print(f"Date: {date or '(none)'}")
        print(f"Paper: {'YES' if paper_image else 'NO'}")
        print(f"{'='*70}\n")
        
        # Check prerequisites
        if not os.path.exists(PNG_TRANSPARENT):
            return jsonify({
                "status": "error",
                "message": "Generate preview first!"
            }), 400
        
        # Choose source
        if paper_image and os.path.exists(COMPOSITE_PREVIEW):
            pdf_source = COMPOSITE_PREVIEW
            print(f"📄 Using: COMPOSITE (paper + handwriting)")
        else:
            pdf_source = PNG_TRANSPARENT
            print(f"📄 Using: TRANSPARENT PNG (handwriting only)")
        
        print(f"   Source: {pdf_source}")
        
        # Load image
        img = Image.open(pdf_source)
        img_width, img_height = img.size
        print(f"   Size: {img_width}x{img_height}px")
        
        # Margins
        left_margin = MARGINS['left'] / 118 * cm
        right_margin = MARGINS['right'] / 118 * cm
        top_margin = MARGINS['top'] / 118 * cm
        bottom_margin = MARGINS['bottom'] / 118 * cm
        header_height = MARGINS['header'] / 118 * cm
        
        # Usable area
        usable_width = PAGE_WIDTH - left_margin - right_margin
        usable_height = PAGE_HEIGHT - top_margin - bottom_margin - header_height
        
        # Convert to points
        img_width_pts = img_width * 72 / 300
        img_height_pts = img_height * 72 / 300
        
        # Scale
        scale = usable_width / img_width_pts
        scaled_width = img_width_pts * scale
        scaled_height = img_height_pts * scale
        
        # Pages
        pages_needed = max(1, int(scaled_height / usable_height) + (1 if scaled_height % usable_height > 50 else 0))
        
        print(f"   Scaled: {scaled_width:.1f}x{scaled_height:.1f} pts")
        print(f"   Pages: {pages_needed}")
        
        # Create PDF
        c = canvas.Canvas(PDF_OUTPUT, pagesize=A4)
        
        for page_num in range(1, pages_needed + 1):
            print(f"   Page {page_num}/{pages_needed}...")
            
            # Header
            if subject or date:
                c.saveState()
                c.setFont("Times-Roman", 11)
                c.setFillColorRGB(0.2, 0.2, 0.2)
                header_y = PAGE_HEIGHT - top_margin + 0.5 * cm
                if subject:
                    c.drawString(left_margin, header_y, f"Subject: {subject}")
                if date:
                    c.drawRightString(PAGE_WIDTH - right_margin, header_y, f"Date: {date}")
                c.restoreState()
            
            # Position
            y_offset = (page_num - 1) * usable_height
            remaining_height = scaled_height - y_offset
            page_draw_height = min(remaining_height, usable_height)
            
            x_position = left_margin
            y_position = PAGE_HEIGHT - top_margin - header_height - page_draw_height
            
            # Draw
            if pages_needed > 1:
                crop_scale = img_height / scaled_height
                crop_top = int(y_offset * crop_scale)
                crop_bottom = int((y_offset + page_draw_height) * crop_scale)
                crop_bottom = min(crop_bottom, img_height)
                
                cropped = img.crop((0, crop_top, img_width, crop_bottom))
                temp_path = os.path.join(OUTPUT_DIR, f"temp_page_{page_num}.png")
                cropped.save(temp_path, 'PNG')
                c.drawImage(
                temp_path,
                0,
                0,
                width=PAGE_WIDTH,
                height=PAGE_HEIGHT,
                mask='auto'
                )


                
                # c.drawImage(
                #     temp_path,
                #     x_position,
                #     y_position,
                #     width=scaled_width,
                #     height=page_draw_height,
                #     mask='auto'
                # )
                
                os.remove(temp_path)
            else:
                # c.drawImage(
                #     pdf_source,
                #     x_position,
                #     y_position,
                #     width=scaled_width,
                #     height=page_draw_height,
                #     mask='auto'
                # )
                
                c.drawImage(
                pdf_source,
                 0,
                 0,
                width=PAGE_WIDTH,
                height=PAGE_HEIGHT,
                mask='auto'
                )

            
            # Page number
            c.saveState()
            c.setFont("Times-Roman", 10)
            c.setFillColorRGB(0.4, 0.4, 0.4)
            c.drawCentredString(PAGE_WIDTH / 2, bottom_margin - 0.5 * cm, str(page_num))
            c.restoreState()
            
            if page_num < pages_needed:
                c.showPage()
        
        c.save()
        
        print(f"\n✅ PDF CREATED: {PDF_OUTPUT}")
        print(f"{'='*70}\n")
        
        filename = f'handwritten_{subject or "document"}.pdf'
        return send_file(
            PDF_OUTPUT,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        import traceback
        print(f"\n{'='*70}")
        print(f"❌ PDF ERROR:")
        print(f"{'='*70}")
        traceback.print_exc()
        print(f"{'='*70}\n")
        return jsonify({
            "status": "error",
            "message": f"PDF failed: {str(e)}"
        }), 500


if __name__ == "__main__":
    print("=" * 70)
    print("TypoPDF Server - ALL 13 STYLES (0-12)")
    print("=" * 70)
    print(f"✓ Output: {OUTPUT_DIR}")
    print(f"✓ Temp: {TEMP_DIR}")
    print(f"✓ Styles: 13 (style0-style12)")
    print(f"✓ Paper overlay: ENABLED")
    print(f"✓ Server: http://127.0.0.1:5000")
    print("=" * 70)
    app.run(debug=True, host='0.0.0.0', port=5000)

    
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
PDF_OUTPUT = os.path.join(OUTPUT_DIR, "document.pdf")

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
    Overlay handwriting on paper background
    ✅ NO subject/date parameters
    """
    print(f"\n🎨 OVERLAY FUNCTION CALLED")
    print(f"   Paper: {paper_path}")
    print(f"   Handwriting: {handwriting_path}")
    print(f"   Scale: {scale}")
    
    # Load paper
    paper = Image.open(paper_path).convert('RGB')
    original_paper_size = paper.size
    print(f"   Original paper size: {original_paper_size[0]}x{original_paper_size[1]}px")
    
    paper = paper.resize(A4_300DPI, Image.Resampling.LANCZOS)
    print(f"   Resized paper to: {A4_300DPI[0]}x{A4_300DPI[1]}px (A4 @ 300 DPI)")
    
    # Load handwriting
    handwriting = Image.open(handwriting_path).convert('RGBA')
    hw_w, hw_h = handwriting.size
    print(f"   Handwriting size: {hw_w}x{hw_h}px")
    
    # Calculate usable area (no header space needed anymore)
    usable_w = A4_300DPI[0] - MARGINS['left'] - MARGINS['right']
    usable_h = A4_300DPI[1] - MARGINS['top'] - MARGINS['bottom']
    print(f"   Usable area: {usable_w}x{usable_h}px")
    
    # Scale handwriting
    scale_factor = min(usable_w / hw_w, usable_h / hw_h) * scale
    new_w = int(hw_w * scale_factor)
    new_h = int(hw_h * scale_factor)
    
    if new_h > usable_h:
        scale_factor = usable_h / hw_h
        new_w = int(hw_w * scale_factor)
        new_h = int(hw_h * scale_factor)
    
    print(f"   Scaling handwriting to: {new_w}x{new_h}px (factor: {scale_factor:.3f})")
    
    handwriting_scaled = handwriting.resize((new_w, new_h), Image.Resampling.LANCZOS)
    
    # Position (directly at top margin, no header offset)
    x = MARGINS['left']
    y = MARGINS['top']
    print(f"   Position: ({x}, {y})")
    
    # Alpha composite
    paper.paste(handwriting_scaled, (x, y), handwriting_scaled)
    print(f"✅ Overlay complete!")
    
    return paper


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
            # backgroung image
            background_path = os.path.join(TEMP_DIR, "background.png")
            
            with open(background_path, 'wb') as f:
                f.write(bg_bytes)
            
            print(f"✅ Background saved: {background_path}")
        else:
            print(f"\n🖼️  CREATING DEFAULT WHITE BACKGROUND")
            background_path = os.path.join(OUTPUT_DIR, "white_bg.png")
            white_bg = Image.new('RGB', A4_300DPI, (255, 255, 255))
            white_bg.save(background_path, 'PNG')
            print(f"✅ White background created: {background_path}")
        
        # Overlay
        print(f"\n🎨 OVERLAYING HANDWRITING ON PAPER")
        composite = overlay_on_paper(
            paper_path=background_path,
            handwriting_path=PNG_TRANSPARENT,
            scale=1.0
        )
        
        composite.save(COMPOSITE_PREVIEW, 'PNG')
        print(f"✅ Composite saved: {COMPOSITE_PREVIEW}")
        
        # Convert to base64
        with open(COMPOSITE_PREVIEW, 'rb') as f:
            preview_data = base64.b64encode(f.read()).decode('utf-8')
        
        print(f"\n✅ SUCCESS!")
        print("=" * 60 + "\n")
        
        return jsonify({
            "status": "success",
            "preview": f"data:image/png;base64,{preview_data}"
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
    Generate and download PDF
    ✅ Subject/date removed from PDF generation
    """
    try:
        if not os.path.exists(COMPOSITE_PREVIEW):
            return jsonify({
                "status": "error",
                "message": "Please generate a preview first!"
            }), 400
        
        print("\n" + "=" * 60)
        print("📄 PDF GENERATION")
        print("=" * 60)
        
        # Load composite image
        img = Image.open(COMPOSITE_PREVIEW).convert('RGB')
        img_width, img_height = img.size
        print(f"✓ Image loaded: {img_width}x{img_height}px")
        
        # Margins
        left_margin = MARGINS['left'] / 118 * cm
        right_margin = MARGINS['right'] / 118 * cm
        top_margin = MARGINS['top'] / 118 * cm
        bottom_margin = MARGINS['bottom'] / 118 * cm
        
        # Usable area (no header space)
        usable_width = PAGE_WIDTH - left_margin - right_margin
        usable_height = PAGE_HEIGHT - top_margin - bottom_margin
        
        # Convert to points
        img_width_pts = img_width * 72 / 300
        img_height_pts = img_height * 72 / 300
        
        # Scale
        scale = usable_width / img_width_pts
        scaled_width = img_width_pts * scale
        scaled_height = img_height_pts * scale
        
        # Multi-page calculation
        pages_needed = max(1, int(scaled_height / usable_height) + (1 if scaled_height % usable_height > 50 else 0))
        
        print(f"✓ Scaled: {scaled_width:.1f}x{scaled_height:.1f} pts")
        print(f"✓ Pages needed: {pages_needed}")
        
        # Create PDF
        c = canvas.Canvas(PDF_OUTPUT, pagesize=A4)
        
        for page_num in range(1, pages_needed + 1):
            print(f"   Drawing page {page_num}/{pages_needed}...")
            
            # Position
            y_offset = (page_num - 1) * usable_height
            remaining_height = scaled_height - y_offset
            page_draw_height = min(remaining_height, usable_height)
            
            x_position = left_margin
            y_position = PAGE_HEIGHT - top_margin - page_draw_height
            
            # Draw image
            if pages_needed > 1:
                crop_scale = img_height / scaled_height
                crop_top = int(y_offset * crop_scale)
                crop_bottom = int((y_offset + page_draw_height) * crop_scale)
                crop_bottom = min(crop_bottom, img_height)
                
                cropped = img.crop((0, crop_top, img_width, crop_bottom))
                temp_path = os.path.join(OUTPUT_DIR, f"temp_page_{page_num}.png")
                cropped.save(temp_path, 'PNG')
                
                c.drawImage(
                    temp_path,
                    # x_position,
                    # y_position,
                    width=PAGE_WIDTH,
                    height=PAGE_HEIGHT,
                    preserveAspectRatio=True,
                    mask='auto'
                )
                
                os.remove(temp_path)
            else:
                temp_path = os.path.join(OUTPUT_DIR, "temp_single.png")
                img.save(temp_path, 'PNG')
                
                c.drawImage(
                    temp_path,
                    # x_position,
                    # y_position,
                    width=PAGE_WIDTH,
                    height=PAGE_HEIGHT,
                    preserveAspectRatio=True,
                    mask='auto'
                )
                
                os.remove(temp_path)
            
            # Page number (bottom center)
            c.saveState()
            c.setFont("Times-Roman", 10)
            c.setFillColorRGB(0.4, 0.4, 0.4)
            c.drawCentredString(PAGE_WIDTH / 2, bottom_margin - 0.5 * cm, str(page_num))
            c.restoreState()
            
            if page_num < pages_needed:
                c.showPage()
        
        c.save()
        
        print(f"✅ PDF saved: {PDF_OUTPUT}")
        print(f"{'='*60}\n")
        
        # Send file
        filename = f'handwritten_{int(os.path.getmtime(PDF_OUTPUT))}.pdf'
        return send_file(
            PDF_OUTPUT,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )
        
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
    print("TypoPDF Server - NO SUBJECT/DATE")
    print("=" * 60)
    print(f"✓ Styles: 9 (optimized)")
    print(f"✓ Multi-page: AUTO")
    print(f"✓ Subject/Date: REMOVED")
    print(f"✓ Server: http://127.0.0.1:5000")
    print("=" * 60)
    app.run(debug=True, host='0.0.0.0', port=5000)

    # """
# TypoPDF - Production Transparent Handwriting System
# UPDATED: Support for all 13 handwriting styles (0-12)
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

# # ALL 13 HANDWRITING STYLES (0-12)

# STYLES = {
#     "style0":  {"style": 0,  "bias": 0.25, "name": "Style 0 - Rough"},
#     "style1":  {"style": 1,  "bias": 0.35, "name": "Style 1 - Casual"},
#     "style2":  {"style": 2,  "bias": 0.45, "name": "Style 2 - Natural"},
#     "style3":  {"style": 3,  "bias": 0.55, "name": "Style 3 - Flowing"},
#     "style4":  {"style": 4,  "bias": 0.65, "name": "Style 4 - Exam"},
#     "style5":  {"style": 5,  "bias": 0.75, "name": "Style 5 - Neat"},
#     "style6":  {"style": 6,  "bias": 0.85, "name": "Style 6 - Rounded"},
#     "style7":  {"style": 7,  "bias": 0.95, "name": "Style 7 - Formal"},
#     "style8":  {"style": 8,  "bias": 1.05, "name": "Style 8 - Elegant"},
#     "style9":  {"style": 9,  "bias": 1.15, "name": "Style 9 - Bold"},
#     "style10": {"style": 10, "bias": 1.25, "name": "Style 10 - Artistic"},
#     "style11": {"style": 11, "bias": 1.35, "name": "Style 11 - Decorative"},
#     "style12": {"style": 12, "bias": 0.75, "name": "Style 12 - Stylized"},
# }

# # STYLES = {
# #     # 🟤 Group A: Rough / Human (Readable, not exam)
# #     "style0": {"style": 0, "bias": 0.25, "name": "Style 0 - Rough Human"},
# #     "style1": {"style": 1, "bias": 0.35, "name": "Style 1 - Casual Human"},
# #     "style2": {"style": 2, "bias": 0.40, "name": "Style 2 - Natural Human"},

# #     # 🔵 Group B: Clear / Exam Style (BEST RANGE)
# #     "style3": {"style": 3, "bias": 0.55, "name": "Style 3 - Clean Exam"},
# #     "style4": {"style": 4, "bias": 0.65, "name": "Style 4 - Standard Exam"},
# #     "style5": {"style": 5, "bias": 0.70, "name": "Style 5 - Neat Exam"},
# #     "style6": {"style": 6, "bias": 0.75, "name": "Style 6 - Very Neat"},
# #     "style7": {"style": 8, "bias": 0.80, "name": "Style 7 - Formal Exam"},

# #     # 🟣 Group C: Stylized (ONLY ONE)
# #     "style8": {"style": 12, "bias": 0.75, "name": "Style 8 - Stylized Display"},
    
# # }

# # Margins (cm to pixels at 300 DPI: 1cm = 118px)
# MARGINS = {
#     'left': int(2.0 * 118),    # 236px
#     'right': int(1.5 * 118),   # 177px
#     'top': int(2.5 * 118),     # 295px
#     'bottom': int(2.0 * 118),  # 236px
#     'header': int(1.0 * 118),  # 118px
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
        
#         # Remove rectangles
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
        
#         # Ensure viewBox
#         if 'viewBox' not in root.attrib:
#             width = root.get('width', '1000').replace('px', '')
#             height = root.get('height', '1000').replace('px', '')
#             root.set('viewBox', f'0 0 {width} {height}')
        
#         tree.write(output_svg, encoding='utf-8', xml_declaration=True)
        
#         print(f"✓ SVG extraction: removed {removed} background elements")
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
        
#         img_pil.save(output_png, 'PNG', optimize=True, compress_level=9)
        
#         transparent_px = np.sum(mask == 0)
#         total_px = mask.size
#         ratio = (transparent_px / total_px) * 100
        
#         print(f"✓ PNG extraction: {ratio:.1f}% background removed")
#         return True
        
#     except Exception as e:
#         print(f"✗ PNG extraction failed: {e}")
#         return False


# def overlay_on_paper(paper_path, handwriting_path, subject="", date="", scale=1.0):
#     """Overlay handwriting on paper background"""
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
    
#     # Calculate usable area
#     usable_w = A4_300DPI[0] - MARGINS['left'] - MARGINS['right']
#     usable_h = A4_300DPI[1] - MARGINS['top'] - MARGINS['bottom'] - MARGINS['header']
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
    
#     # Position
#     x = MARGINS['left']
#     y = MARGINS['top'] + MARGINS['header']
#     print(f"   Position: ({x}, {y})")
    
#     # Alpha composite
#     paper.paste(handwriting_scaled, (x, y), handwriting_scaled)
#     print(f"✅ Overlay complete!")
    
#     # Add header text if provided
#     if subject or date:
#         draw = ImageDraw.Draw(paper)
#         try:
#             font = ImageFont.truetype("arial.ttf", 32)
#         except:
#             font = ImageFont.load_default()
        
#         header_y = MARGINS['top'] + 30
#         text_color = (50, 50, 50)
        
#         if subject:
#             draw.text((MARGINS['left'], header_y), f"Subject: {subject}", fill=text_color, font=font)
        
#         if date:
#             date_text = f"Date: {date}"
#             bbox = draw.textbbox((0, 0), date_text, font=font)
#             date_width = bbox[2] - bbox[0]
#             date_x = A4_300DPI[0] - MARGINS['right'] - date_width
#             draw.text((date_x, header_y), date_text, fill=text_color, font=font)
    
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
#     return text


# # ===============================================
# # ROUTES
# # ===============================================

# @app.route("/")
# def index():
#     return render_template("index.html")


# @app.route("/generate", methods=["POST"])
# def generate():
#     """Generate handwriting preview with paper overlay"""
#     try:
#         data = request.json
        
#         raw_text = data.get("text", "").strip()
#         style_key = data.get("style", "style5")
#         ink_color = data.get("ink_color", "#000000")
#         font_size = float(data.get("font_size", 1.0))
#         transparent = data.get("transparent", True)
#         paper_image = data.get("paper_image", None)
        
#         print(f"\n{'='*70}")
#         print(f"📝 NEW GENERATION REQUEST")
#         print(f"{'='*70}")
#         print(f"Text length: {len(raw_text)} chars")
#         print(f"Style: {style_key}")
#         print(f"Ink color: {ink_color}")
#         print(f"Font size: {font_size}x")
#         print(f"Transparent: {transparent}")
        
#         if paper_image:
#             paper_size = len(paper_image)
#             print(f"Paper image: YES ({paper_size:,} bytes = {paper_size/1024:.1f} KB)")
#         else:
#             print(f"Paper image: NO")
        
#         print(f"{'='*70}\n")
        
#         if not raw_text:
#             return jsonify({
#                 "status": "error",
#                 "message": "Please enter some text"
#             }), 400
        
#         text = sanitize_text(raw_text)
#         style_config = STYLES.get(style_key, STYLES["style5"])
        
#         print(f"📊 Using {style_config['name']}")
#         print(f"   Style index: {style_config['style']}")
#         print(f"   Bias: {style_config['bias']}")
        
#         # Step 1: Generate SVG
#         print(f"\n🔄 Step 1: Generating handwriting SVG...")
#         generate_handwriting(
#             text=text,
#             output_path=SVG_ORIGINAL,
#             style=style_config["style"],
#             bias=style_config["bias"],
#             ink_color=ink_color
#         )
#         print(f"✅ SVG saved: {SVG_ORIGINAL}")
        
#         # Step 2: Extract transparent SVG
#         if transparent:
#             print(f"\n🔄 Step 2: Extracting transparent SVG...")
#             success = extract_svg_transparent(SVG_ORIGINAL, SVG_TRANSPARENT)
#             svg_to_use = SVG_TRANSPARENT if success else SVG_ORIGINAL
#         else:
#             svg_to_use = SVG_ORIGINAL
        
#         # Step 3: Convert to PNG
#         print(f"\n🔄 Step 3: Converting SVG → PNG (300 DPI)...")
#         if not os.path.exists(INKSCAPE):
#             return jsonify({
#                 "status": "error",
#                 "message": f"Inkscape not found at: {INKSCAPE}"
#             }), 500
        
#         png_output = PNG_TRANSPARENT if transparent else PNG_ORIGINAL
        
#         result = subprocess.run([
#             INKSCAPE,
#             svg_to_use,
#             "--export-type=png",
#             f"--export-filename={png_output}",
#             "--export-dpi=300"
#         ], check=True, capture_output=True, text=True)
        
#         if not os.path.exists(png_output):
#             print(f"❌ PNG not created!")
#             raise Exception("PNG conversion failed")
        
#         print(f"✅ PNG saved: {png_output}")
        
#         # Step 4: PNG transparency
#         if transparent:
#             print(f"\n🔄 Step 4: Applying PNG alpha masking...")
#             extract_png_transparent(png_output, png_output)
        
#         # Step 5: Overlay on paper
#         preview_url = None
        
#         if paper_image and transparent:
#             print(f"\n🔄 Step 5: Creating paper overlay...")
#             print(f"   Paper image size: {len(paper_image):,} bytes")
            
#             try:
#                 # Decode base64
#                 if 'base64,' in paper_image:
#                     paper_data = paper_image.split('base64,')[1]
#                 else:
#                     paper_data = paper_image
                
#                 paper_bytes = base64.b64decode(paper_data)
#                 print(f"   Decoded: {len(paper_bytes):,} bytes")
                
#                 # Save temp
#                 temp_paper = os.path.join(TEMP_DIR, "uploaded_paper.png")
#                 with open(temp_paper, 'wb') as f:
#                     f.write(paper_bytes)
#                 print(f"   Saved temp: {temp_paper}")
                
#                 # Verify
#                 paper_check = Image.open(temp_paper)
#                 print(f"   Verified: {paper_check.size[0]}x{paper_check.size[1]}px, mode={paper_check.mode}")
                
#                 # Create overlay
#                 composite = overlay_on_paper(
#                     paper_path=temp_paper,
#                     handwriting_path=png_output,
#                     subject="",
#                     date="",
#                     scale=font_size
#                 )
                
#                 # Save
#                 composite.save(COMPOSITE_PREVIEW, 'PNG', optimize=True)
#                 print(f"\n✅ COMPOSITE SAVED: {COMPOSITE_PREVIEW}")
#                 print(f"   Size: {composite.size[0]}x{composite.size[1]}px")
                
#                 preview_url = f"/output/preview.png?t={int(os.path.getmtime(COMPOSITE_PREVIEW))}"
                
#                 # Cleanup
#                 if os.path.exists(temp_paper):
#                     os.remove(temp_paper)
#                     print(f"   Cleaned temp file")
                
#             except Exception as e:
#                 print(f"\n⚠️  OVERLAY FAILED: {e}")
#                 import traceback
#                 traceback.print_exc()
#                 preview_url = f"/output/{os.path.basename(png_output)}?t={int(os.path.getmtime(png_output))}"
#         else:
#             reason = "no paper" if not paper_image else "not transparent"
#             print(f"\nℹ️  Skipping overlay ({reason})")
#             preview_url = f"/output/{os.path.basename(png_output)}?t={int(os.path.getmtime(png_output))}"
        
#         print(f"\n{'='*70}")
#         print(f"✅ SUCCESS")
#         print(f"Preview URL: {preview_url}")
#         print(f"{'='*70}\n")
        
#         return jsonify({
#             "status": "success",
#             "image_url": preview_url,
#             "message": f"Generated with {style_config['name']}"
#         })
        
#     except Exception as e:
#         import traceback
#         print(f"\n{'='*70}")
#         print(f"❌ ERROR:")
#         print(f"{'='*70}")
#         traceback.print_exc()
#         print(f"{'='*70}\n")
#         return jsonify({
#             "status": "error",
#             "message": str(e)
#         }), 500


# @app.route("/output/<path:filename>")
# def output_file(filename):
#     """Serve generated files"""
#     filepath = os.path.join(OUTPUT_DIR, filename)
#     if os.path.exists(filepath):
#         return send_file(filepath)
#     else:
#         return jsonify({"error": "File not found"}), 404


# @app.route("/download-pdf", methods=["POST"])
# def download_pdf():
#     """Generate PDF with paper background"""
#     try:
#         data = request.json
        
#         text = data.get("text", "").strip()
#         subject = data.get("subject", "")
#         date = data.get("date", "")
#         paper_image = data.get("paper_image", None)
        
#         print(f"\n{'='*70}")
#         print(f"📄 PDF GENERATION")
#         print(f"{'='*70}")
#         print(f"Subject: {subject or '(none)'}")
#         print(f"Date: {date or '(none)'}")
#         print(f"Paper: {'YES' if paper_image else 'NO'}")
#         print(f"{'='*70}\n")
        
#         # Check prerequisites
#         if not os.path.exists(PNG_TRANSPARENT):
#             return jsonify({
#                 "status": "error",
#                 "message": "Generate preview first!"
#             }), 400
        
#         # Choose source
#         if paper_image and os.path.exists(COMPOSITE_PREVIEW):
#             pdf_source = COMPOSITE_PREVIEW
#             print(f"📄 Using: COMPOSITE (paper + handwriting)")
#         else:
#             pdf_source = PNG_TRANSPARENT
#             print(f"📄 Using: TRANSPARENT PNG (handwriting only)")
        
#         print(f"   Source: {pdf_source}")
        
#         # Load image
#         img = Image.open(pdf_source)
#         img_width, img_height = img.size
#         print(f"   Size: {img_width}x{img_height}px")
        
#         # Margins
#         left_margin = MARGINS['left'] / 118 * cm
#         right_margin = MARGINS['right'] / 118 * cm
#         top_margin = MARGINS['top'] / 118 * cm
#         bottom_margin = MARGINS['bottom'] / 118 * cm
#         header_height = MARGINS['header'] / 118 * cm
        
#         # Usable area
#         usable_width = PAGE_WIDTH - left_margin - right_margin
#         usable_height = PAGE_HEIGHT - top_margin - bottom_margin - header_height
        
#         # Convert to points
#         img_width_pts = img_width * 72 / 300
#         img_height_pts = img_height * 72 / 300
        
#         # Scale
#         scale = usable_width / img_width_pts
#         scaled_width = img_width_pts * scale
#         scaled_height = img_height_pts * scale
        
#         # Pages
#         pages_needed = max(1, int(scaled_height / usable_height) + (1 if scaled_height % usable_height > 50 else 0))
        
#         print(f"   Scaled: {scaled_width:.1f}x{scaled_height:.1f} pts")
#         print(f"   Pages: {pages_needed}")
        
#         # Create PDF
#         c = canvas.Canvas(PDF_OUTPUT, pagesize=A4)
        
#         for page_num in range(1, pages_needed + 1):
#             print(f"   Page {page_num}/{pages_needed}...")
            
#             # Header
#             if subject or date:
#                 c.saveState()
#                 c.setFont("Times-Roman", 11)
#                 c.setFillColorRGB(0.2, 0.2, 0.2)
#                 header_y = PAGE_HEIGHT - top_margin + 0.5 * cm
#                 if subject:
#                     c.drawString(left_margin, header_y, f"Subject: {subject}")
#                 if date:
#                     c.drawRightString(PAGE_WIDTH - right_margin, header_y, f"Date: {date}")
#                 c.restoreState()
            
#             # Position
#             y_offset = (page_num - 1) * usable_height
#             remaining_height = scaled_height - y_offset
#             page_draw_height = min(remaining_height, usable_height)
            
#             x_position = left_margin
#             y_position = PAGE_HEIGHT - top_margin - header_height - page_draw_height
            
#             # Draw
#             if pages_needed > 1:
#                 crop_scale = img_height / scaled_height
#                 crop_top = int(y_offset * crop_scale)
#                 crop_bottom = int((y_offset + page_draw_height) * crop_scale)
#                 crop_bottom = min(crop_bottom, img_height)
                
#                 cropped = img.crop((0, crop_top, img_width, crop_bottom))
#                 temp_path = os.path.join(OUTPUT_DIR, f"temp_page_{page_num}.png")
#                 cropped.save(temp_path, 'PNG')
#                 c.drawImage(
#                 temp_path,
#                 0,
#                 0,
#                 width=PAGE_WIDTH,
#                 height=PAGE_HEIGHT,
#                 mask='auto'
#                 )


                
#                 # c.drawImage(
#                 #     temp_path,
#                 #     x_position,
#                 #     y_position,
#                 #     width=scaled_width,
#                 #     height=page_draw_height,
#                 #     mask='auto'
#                 # )
                
#                 os.remove(temp_path)
#             else:
#                 # c.drawImage(
#                 #     pdf_source,
#                 #     x_position,
#                 #     y_position,
#                 #     width=scaled_width,
#                 #     height=page_draw_height,
#                 #     mask='auto'
#                 # )
                
#                 c.drawImage(
#                 pdf_source,
#                  0,
#                  0,
#                 width=PAGE_WIDTH,
#                 height=PAGE_HEIGHT,
#                 mask='auto'
#                 )

            
#             # Page number
#             c.saveState()
#             c.setFont("Times-Roman", 10)
#             c.setFillColorRGB(0.4, 0.4, 0.4)
#             c.drawCentredString(PAGE_WIDTH / 2, bottom_margin - 0.5 * cm, str(page_num))
#             c.restoreState()
            
#             if page_num < pages_needed:
#                 c.showPage()
        
#         c.save()
        
#         print(f"\n✅ PDF CREATED: {PDF_OUTPUT}")
#         print(f"{'='*70}\n")
        
#         filename = f'handwritten_{subject or "document"}.pdf'
#         return send_file(
#             PDF_OUTPUT,
#             mimetype='application/pdf',
#             as_attachment=True,
#             download_name=filename
#         )
        
#     except Exception as e:
#         import traceback
#         print(f"\n{'='*70}")
#         print(f"❌ PDF ERROR:")
#         print(f"{'='*70}")
#         traceback.print_exc()
#         print(f"{'='*70}\n")
#         return jsonify({
#             "status": "error",
#             "message": f"PDF failed: {str(e)}"
#         }), 500


# if __name__ == "__main__":
#     print("=" * 70)
#     print("TypoPDF Server - ALL 13 STYLES (0-12)")
#     print("=" * 70)
#     print(f"✓ Output: {OUTPUT_DIR}")
#     print(f"✓ Temp: {TEMP_DIR}")
#     print(f"✓ Styles: 13 (style0-style12)")
#     print(f"✓ Paper overlay: ENABLED")
#     print(f"✓ Server: http://127.0.0.1:5000")
#     print("=" * 70)
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
PDF_OUTPUT = os.path.join(OUTPUT_DIR, "document.pdf")

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
    Overlay handwriting on paper background
    ✅ NO subject/date parameters
    """
    print(f"\n🎨 OVERLAY FUNCTION CALLED")
    print(f"   Paper: {paper_path}")
    print(f"   Handwriting: {handwriting_path}")
    print(f"   Scale: {scale}")
    
    # Load paper
    paper = Image.open(paper_path).convert('RGB')
    original_paper_size = paper.size
    print(f"   Original paper size: {original_paper_size[0]}x{original_paper_size[1]}px")
    
    paper = paper.resize(A4_300DPI, Image.Resampling.LANCZOS)
    print(f"   Resized paper to: {A4_300DPI[0]}x{A4_300DPI[1]}px (A4 @ 300 DPI)")
    
    # Load handwriting
    handwriting = Image.open(handwriting_path).convert('RGBA')
    hw_w, hw_h = handwriting.size
    print(f"   Handwriting size: {hw_w}x{hw_h}px")
    
    # Calculate usable area (no header space needed anymore)
    usable_w = A4_300DPI[0] - MARGINS['left'] - MARGINS['right']
    usable_h = A4_300DPI[1] - MARGINS['top'] - MARGINS['bottom']
    print(f"   Usable area: {usable_w}x{usable_h}px")
    
    # Scale handwriting
    scale_factor = min(usable_w / hw_w, usable_h / hw_h) * scale
    new_w = int(hw_w * scale_factor)
    new_h = int(hw_h * scale_factor)
    
    if new_h > usable_h:
        scale_factor = usable_h / hw_h
        new_w = int(hw_w * scale_factor)
        new_h = int(hw_h * scale_factor)
    
    print(f"   Scaling handwriting to: {new_w}x{new_h}px (factor: {scale_factor:.3f})")
    
    handwriting_scaled = handwriting.resize((new_w, new_h), Image.Resampling.LANCZOS)
    
    # Position (directly at top margin, no header offset)
    x = MARGINS['left']
    y = MARGINS['top']
    print(f"   Position: ({x}, {y})")
    
    # Alpha composite
    paper.paste(handwriting_scaled, (x, y), handwriting_scaled)
    print(f"✅ Overlay complete!")
    
    return paper


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
        
        # Overlay
        print(f"\n🎨 OVERLAYING HANDWRITING ON PAPER")
        composite = overlay_on_paper(
            paper_path=background_path,
            handwriting_path=PNG_TRANSPARENT,
            scale=1.0
        )
        
        composite.save(COMPOSITE_PREVIEW, 'PNG')
        print(f"✅ Composite saved: {COMPOSITE_PREVIEW}")
        
        # Convert to base64
        with open(COMPOSITE_PREVIEW, 'rb') as f:
            preview_data = base64.b64encode(f.read()).decode('utf-8')
        
        print(f"\n✅ SUCCESS!")
        print("=" * 60 + "\n")
        
        return jsonify({
            "status": "success",
            "preview": f"data:image/png;base64,{preview_data}"
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
    Generate and download PDF
    ✅ Subject/date removed from PDF generation
    """
    try:
        if not os.path.exists(COMPOSITE_PREVIEW):
            return jsonify({
                "status": "error",
                "message": "Please generate a preview first!"
            }), 400
        
        print("\n" + "=" * 60)
        print("📄 PDF GENERATION")
        print("=" * 60)
        
        # Load composite image
        img = Image.open(COMPOSITE_PREVIEW).convert('RGB')
        img_width, img_height = img.size
        print(f"✓ Image loaded: {img_width}x{img_height}px")
        
        # Margins
        left_margin = MARGINS['left'] / 118 * cm
        right_margin = MARGINS['right'] / 118 * cm
        top_margin = MARGINS['top'] / 118 * cm
        bottom_margin = MARGINS['bottom'] / 118 * cm
        
        # Usable area (no header space)
        usable_width = PAGE_WIDTH - left_margin - right_margin
        usable_height = PAGE_HEIGHT - top_margin - bottom_margin
        
        # Convert to points
        img_width_pts = img_width * 72 / 300
        img_height_pts = img_height * 72 / 300
        
        # Scale
        scale = usable_width / img_width_pts
        scaled_width = img_width_pts * scale
        scaled_height = img_height_pts * scale
        
        # Multi-page calculation
        pages_needed = max(1, int(scaled_height / usable_height) + (1 if scaled_height % usable_height > 50 else 0))
        
        print(f"✓ Scaled: {scaled_width:.1f}x{scaled_height:.1f} pts")
        print(f"✓ Pages needed: {pages_needed}")
        
        # Create PDF
        c = canvas.Canvas(PDF_OUTPUT, pagesize=A4)
        
        for page_num in range(1, pages_needed + 1):
            print(f"   Drawing page {page_num}/{pages_needed}...")
            
            # Position
            y_offset = (page_num - 1) * usable_height
            remaining_height = scaled_height - y_offset
            page_draw_height = min(remaining_height, usable_height)
            
            x_position = left_margin
            y_position = PAGE_HEIGHT - top_margin - page_draw_height
            
            # Draw image
            # if pages_needed > 1:
            #     crop_scale = img_height / scaled_height
            #     crop_top = int(y_offset * crop_scale)
            #     crop_bottom = int((y_offset + page_draw_height) * crop_scale)
            #     crop_bottom = min(crop_bottom, img_height)
                
            #     cropped = img.crop((0, crop_top, img_width, crop_bottom))
            #     temp_path = os.path.join(OUTPUT_DIR, f"temp_page_{page_num}.png")
            #     cropped.save(temp_path, 'PNG')
                
            #     c.drawImage(
            #         temp_path,
            #         # x_position,
            #         # y_position,
            #         width=PAGE_WIDTH,
            #         height=PAGE_HEIGHT,
            #         preserveAspectRatio=True,
            #         mask='auto'
            #     )
                
            #     os.remove(temp_path)
            # else:
            #     temp_path = os.path.join(OUTPUT_DIR, "temp_single.png")
            #     img.save(temp_path, 'PNG')
                
            #     c.drawImage(
            #         temp_path,
            #         # x_position,
            #         # y_position,
            #         0,
            #         0,
            #         width=PAGE_WIDTH,
            #         height=PAGE_HEIGHT,
            #         preserveAspectRatio=True,
            #         mask='auto'
            #     )
                
            #     os.remove(temp_path)
            if pages_needed > 1:
                crop_scale = img_height / scaled_height
                crop_top = int(y_offset * crop_scale)
                crop_bottom = int((y_offset + page_draw_height) * crop_scale)
                crop_bottom = min(crop_bottom, img_height)
                cropped = img.crop((0, crop_top, img_width, crop_bottom))
                img_buffer = io.BytesIO()
                cropped.save(img_buffer, format="PNG")
                img_buffer.seek(0)
                c.drawImage(
        ImageReader(img_buffer),
        0,
        0,
        width=PAGE_WIDTH,
        height=PAGE_HEIGHT,
        mask='auto'
    )

        else:
            img_buffer = io.BytesIO()
            img.save(img_buffer, format="PNG")
            img_buffer.seek(0)
            c.drawImage(
        ImageReader(img_buffer),
        0,
        0,
        width=PAGE_WIDTH,
        height=PAGE_HEIGHT,
        mask='auto'
    )
        
            # Page number (bottom center)
            c.saveState()
            c.setFont("Times-Roman", 10)
            c.setFillColorRGB(0.4, 0.4, 0.4)
            c.drawCentredString(PAGE_WIDTH / 2, bottom_margin - 0.5 * cm, str(page_num))
            c.restoreState()
            
            if page_num < pages_needed:
                c.showPage()
        
        c.save()
        
        print(f"✅ PDF saved: {PDF_OUTPUT}")
        print(f"{'='*60}\n")
        
        # Send file
        filename = f'handwritten_{int(os.path.getmtime(PDF_OUTPUT))}.pdf'
        return send_file(
            PDF_OUTPUT,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )
        
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
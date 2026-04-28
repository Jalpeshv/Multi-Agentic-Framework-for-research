# pdf/pdf_generator.py
from pathlib import Path
import markdown2
from xhtml2pdf import pisa
import sys
import re
import base64

CSS_FILE = Path(__file__).resolve().parents[1] / "app" / "templates" / "css_print.css"


def convert_markdown_to_pdf(md_path: str, output_pdf_path: str):
    """
    Reads markdown file, converts to HTML with embedded CSS, writes PDF.
    Sanitizes tables and strips mermaid blocks to prevent xhtml2pdf crashes.
    """
    md_text = Path(md_path).read_text(encoding="utf-8")
    
    # 0. Pre-sanitize markdown tables — xhtml2pdf crashes on complex/wide tables
    lines = md_text.split("\n")
    sanitized_lines = []
    for line in lines:
        if line.strip().startswith("|") and "|" in line:
            cells = line.split("|")
            # Limit to 5 columns (including empty leading/trailing)
            if len(cells) > 6:
                cells = cells[:6] + [""]
            # Truncate long cells
            cells = [c[:80] if len(c) > 80 else c for c in cells]
            line = "|".join(cells)
        sanitized_lines.append(line)
    md_text = "\n".join(sanitized_lines)
    
    # 1. Strip mermaid blocks entirely (xhtml2pdf can't render them)
    md_text = re.sub(r'```mermaid\s+.*?\s+```', '\n*[Diagram: see rendered report]*\n', md_text, flags=re.DOTALL)
    
    # 2. Convert to HTML
    extras = ["fenced-code-blocks", "tables", "code-friendly", "cuddled-lists"]
    html_body = markdown2.markdown(md_text, extras=extras)

    # 3. Get CSS & Build Full HTML
    css_content = ""
    if CSS_FILE.exists():
        css_content = CSS_FILE.read_text(encoding="utf-8")
    
    full_html = f"""
    <!doctype html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            @page {{
                size: a4 portrait;
                margin: 2cm 2cm 2.5cm 2cm;
                @frame footer {{
                    -pdf-frame-content: footerContent;
                    bottom: 1cm;
                    margin-left: 2cm;
                    margin-right: 2cm;
                    height: 1cm;
                }}
            }}
            
            body {{
                font-family: "Times New Roman", Times, serif;
                text-align: justify;
                line-height: 1.6;
                font-size: 11pt;
                color: #2b2b2b;
                background-color: #FFFFFF;
            }}
            
            h1 {{
                 color: #1a365d;
                 font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
                 font-size: 24pt;
                 border-bottom: 2px solid #2c5282;
                 padding-bottom: 8px;
                 margin-bottom: 20px;
            }}
            
            h2 {{
                 color: #2c5282;
                 font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
                 font-size: 18pt;
                 border-bottom: 1px solid #e2e8f0;
                 margin-top: 25px;
                 padding-bottom: 5px;
            }}
            
            h3 {{
                 color: #2d3748;
                 font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
                 font-size: 14pt;
                 margin-top: 20px;
            }}
            
            p {{
                margin-bottom: 12px;
            }}

            pre {{
                background-color: #f8f9fa;
                border: 1px solid #e9ecef;
                border-radius: 4px;
                padding: 10px;
                font-family: "Courier New", Courier, monospace;
                font-size: 9.5pt;
                white-space: pre-wrap;
            }}

            code {{
                background-color: #f8f9fa;
                color: #c53030;
                font-family: "Courier New", Courier, monospace;
                padding: 2px 4px;
                border-radius: 3px;
                font-size: 10pt;
            }}
            
            blockquote {{
                border-left: 4px solid #4299e1;
                margin: 15px 0 15px 15px;
                padding: 5px 10px;
                background-color: #ebf8ff;
                font-style: italic;
                color: #2c5282;
            }}
            
            table {{
                border-collapse: collapse;
                width: 100%;
                margin: 20px 0;
                color: #2d3748;
                font-size: 10pt;
                font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
            }}
            th {{
                border-bottom: 2px solid #cbd5e0;
                border-top: 2px solid #cbd5e0;
                text-align: left;
                padding: 8px 10px;
                background-color: #f7fafc;
                font-weight: bold;
                color: #4a5568;
            }}
            td {{
                border-bottom: 1px solid #e2e8f0;
                padding: 8px 10px;
                word-wrap: break-word;
            }}
            tr:nth-child(even) {{
                background-color: #f8fafc;
            }}

            {css_content}
        </style>
    </head>
    <body>
    {html_body}
    </body>
    </html>
    """
    
    # 4. Write PDF with fallback
    try:
        with open(output_pdf_path, "wb") as result_file:
            pisa_status = pisa.CreatePDF(
                src=full_html,
                dest=result_file
            )
        if pisa_status.err:
            print(f"Warning: PDF generated with {pisa_status.err} errors", file=sys.stderr)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"WARNING: PDF first attempt failed: {e}, retrying without tables...", file=sys.stderr)
        # Fallback: strip HTML tables entirely
        simple_html = re.sub(r'<table.*?</table>', '<p><em>[Table: see markdown report for full data]</em></p>', full_html, flags=re.DOTALL)
        try:
            with open(output_pdf_path, "wb") as result_file:
                pisa.CreatePDF(src=simple_html, dest=result_file)
        except Exception as e2:
            traceback.print_exc()
            raise RuntimeError(f"PDF generation failed: {e2}")

    return output_pdf_path

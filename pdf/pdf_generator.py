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
                margin: 2.5cm;
                @top-center {{
                    content: "Research Report";
                    font-family: serif;
                    font-size: 9pt;
                    color: #666;
                }}
                @bottom-center {{
                    content: "Page " counter(page);
                    font-family: serif;
                    font-size: 9pt;
                    color: #666;
                }}
            }}
            
            body {{
                font-family: serif;
                text-align: justify;
                line-height: 1.5;
                font-size: 11pt;
                color: #000000;
                background-color: #FFFFFF;
            }}
            
            h1 {{
                 color: #000000;
                 font-family: sans-serif;
                 border-bottom: 2px solid #000;
                 padding-bottom: 5px;
            }}
            
            h2, h3 {{
                 color: #2c3e50;
                 font-family: sans-serif;
                 border-bottom: 1px solid #ddd;
                 margin-top: 15px;
            }}
            
            p {{
                margin-bottom: 10px;
            }}

            code {{
                background-color: #f5f5f5;
                color: #c7254e;
                font-family: monospace;
            }}
            
            table {{
                border-collapse: collapse;
                width: 100%;
                margin: 15px 0;
                color: #000;
                font-size: 9pt;
            }}
            th {{
                border-bottom: 2px solid #000;
                text-align: left;
                padding: 5px;
                background-color: #eee;
                font-size: 9pt;
            }}
            td {{
                border-bottom: 1px solid #ddd;
                padding: 4px;
                font-size: 9pt;
                word-wrap: break-word;
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
        print(f"WARNING: PDF first attempt failed: {e}, retrying without tables...", file=sys.stderr)
        # Fallback: strip HTML tables entirely
        simple_html = re.sub(r'<table.*?</table>', '<p><em>[Table: see markdown report for full data]</em></p>', full_html, flags=re.DOTALL)
        try:
            with open(output_pdf_path, "wb") as result_file:
                pisa.CreatePDF(src=simple_html, dest=result_file)
        except Exception as e2:
            raise RuntimeError(f"PDF generation failed: {e2}")

    return output_pdf_path

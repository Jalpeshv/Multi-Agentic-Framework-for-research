"""Fix ALL longtable column specs - remove X, fix widths"""
import re

with open('report_full.tex', 'r', encoding='utf-8') as f:
    content = f.read()

# Find ALL longtable column specs and fix them
def fix_longtable_cols(content):
    """Fix every longtable{...} column spec"""
    # Find all \begin{longtable}{...}
    pattern = r'\\begin\{longtable\}\{([^}]*)\}'
    
    def fix_cols(m):
        cols = m.group(1)
        original = cols
        
        # Replace X with p{4cm}
        if 'X' in cols:
            # Count columns to distribute width
            pipe_count = cols.count('|')
            col_parts = [c for c in re.split(r'\|', cols) if c.strip()]
            
            # Calculate fixed width already used
            fixed = 0
            x_count = 0
            for part in col_parts:
                pw = re.search(r'p\{([\d.]+)cm\}', part)
                if pw:
                    fixed += float(pw.group(1))
                elif 'X' in part:
                    x_count += 1
                elif part.strip() in ('c', 'l', 'r'):
                    fixed += 2.0  # approximate
            
            remaining = max(2.0, (14.0 - fixed) / max(1, x_count))
            cols = cols.replace('X', f'p{{{remaining:.1f}cm}}')
        
        # Check total width doesn't exceed ~14.5cm
        widths = [float(x) for x in re.findall(r'p\{([\d.]+)cm\}', cols)]
        total = sum(widths)
        if total > 15.0 and len(widths) > 0:
            # Scale down proportionally
            scale = 14.0 / total
            for w in widths:
                new_w = round(w * scale, 1)
                cols = cols.replace(f'p{{{w}cm}}', f'p{{{new_w}cm}}', 1)
        
        if cols != original:
            print(f'  Fixed: {original} -> {cols}')
        
        return f'\\begin{{longtable}}{{{cols}}}'
    
    return re.sub(pattern, fix_cols, content)

content = fix_longtable_cols(content)

# Also fix endfirsthead/endhead sections that might have wrong cols
# The header rows should match the column count

# Count remaining issues
x_in_longtable = len(re.findall(r'\\begin\{longtable\}\{[^}]*X', content))
print(f'Remaining X in longtable: {x_in_longtable}')

# List all longtable column specs for verification
for m in re.finditer(r'\\begin\{longtable\}\{([^}]*)\}', content):
    cols = m.group(1)
    widths = [float(x) for x in re.findall(r'([\d.]+)cm', cols)]
    total = sum(widths) if widths else 0
    pos = content[:m.start()].count('\n') + 1
    print(f'  Line {pos}: {cols}  (total={total:.1f}cm)')

with open('report_full.tex', 'w', encoding='utf-8') as f:
    f.write(content)

print(f'\nDone: {len(content):,} chars')

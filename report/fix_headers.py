#!/usr/bin/env python3
"""Remove all remaining duplicate third header blocks after \\endfoot."""
import re

filepath = r'c:\Users\viken hadavani\ai-research-assistant\report\report_full.tex'

with open(filepath, 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
i = 0
removed = 0
while i < len(lines):
    new_lines.append(lines[i])
    if lines[i].strip() == r'\endfoot':
        # Look ahead: skip optional blank + \hline + any header row + \hline
        j = i + 1
        # Skip blank lines
        blank_start = j
        while j < len(lines) and lines[j].strip() == '':
            j += 1
        # Check for \hline
        if j < len(lines) and lines[j].strip() == r'\hline':
            k = j + 1
            # Check for a header row (contains \textbf or starts with \textbf or \texttt)
            if k < len(lines) and (r'\textbf{' in lines[k] or r'\texttt{' in lines[k]):
                m = k + 1
                # Check for closing \hline
                if m < len(lines) and lines[m].strip() == r'\hline':
                    # Found duplicate header block! Skip lines from blank_start to m+1
                    i = m + 1
                    removed += 1
                    continue
    i += 1

with open(filepath, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print(f"Removed {removed} duplicate header blocks")

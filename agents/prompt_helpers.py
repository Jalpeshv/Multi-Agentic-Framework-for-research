# agents/prompt_helpers.py
def simple_render(template_text: str, mapping: dict):
    out = template_text
    for k, v in mapping.items():
        token = "{{" + k + "}}"
        out = out.replace(token, str(v))
    return out

# orchestrator/pipeline_validator.py
"""
Pipeline Supervisor / Validator
Ensures the pipeline does not fail silently by verifying phase outputs.
"""
import os
import sys

class PipelineValidator:
    @staticmethod
    def validate_phase1_research(research_outputs, expected_count=3):
        """Phase 1: Verify exactly N outputs and no rate limit failures."""
        if not research_outputs:
            return False, "Research Phase returned zero outputs."
        if len(research_outputs) != expected_count:
            return False, f"Expected {expected_count} research outputs, but got {len(research_outputs)}."
            
        for idx, out in enumerate(research_outputs):
            if out.get("status") == "failed":
                return False, f"Research Agent [{out.get('role', idx)}] explicitly failed: {out.get('error', 'Unknown Error')}"
            
            # Additional check: Did it get truncated or stringify an error?
            summary = out.get("summary", "")
            if not summary or len(summary) < 50:
                return False, f"Research Agent [{out.get('role', idx)}] generated an invalid/empty summary."
                
            if "429" in summary or "rate limit" in summary.lower():
                return False, f"Research Agent [{out.get('role', idx)}] summary contains rate limit error trace."
                
        return True, "Research validation passed."

    @staticmethod
    def validate_phase2_methodology(methodology_output):
        """Phase 2: Verify exactly ONE master methodology with valid length."""
        if not methodology_output:
            return False, "Methodology Phase returned empty result."
            
        if methodology_output.get("error"):
            return False, f"Methodology Generation failed: {methodology_output.get('error')}"
            
        methodology_text = methodology_output.get("proposed_methodology", "")
        if len(methodology_text) < 300:
            return False, f"Methodology appears truncated or empty (length: {len(methodology_text)}). Expected detailed methodology >300 chars."
            
        return True, "Methodology validation passed."

    @staticmethod
    def validate_phase3_visuals(master_visual):
        """Phase 3: Verify paperbanana images exist on disk."""
        if not master_visual:
            return False, "Visualizer Phase generated no output."
            
        if isinstance(master_visual, dict):
            status = master_visual.get("status")
            if status == "error":
                 return False, f"Visualizer Agent returned error: {master_visual.get('error', 'Unknown')}"
                 
            all_diagrams = master_visual.get("all_diagrams", {})
            paths_to_check = []
            for k, v in all_diagrams.items():
                if isinstance(v, str) and v.endswith(('.png', '.svg', '.jpg')):
                    paths_to_check.append(v)
        else:
            return False, "Validation expected a dictionary from Visualizer Agent."
            
        if not paths_to_check:
            return False, "No valid image links found in visualizer output."
            
        for path in paths_to_check:
            # Clean possible file:// prefix
            clean_path = path.replace("file://", "")
            if not os.path.exists(clean_path):
                return False, f"Diagram image missing from disk: {clean_path}"
                
        return True, "Visuals validation passed."

    @staticmethod
    def validate_phase4_report(invoice_output):
        """Phase 4: Scan the final synthesized Markdown strictly for necessary structures."""
        if not invoice_output or invoice_output.get("status") == "failed":
            return False, "Report Synthesis failed to generate a valid object."
            
        sections = invoice_output.get("sections_markdown", [])
        if not sections:
            return False, "Report contains NO sections."
            
        # Combine all titles for easy checking
        all_titles = [sec.get("title", "").lower() for sec in sections]
        
        required_keywords = ["literature", "methodology", "reference"]
        for req in required_keywords:
            if not any(req in title for title in all_titles):
                return False, f"Final report is missing required section: '{req.title()}'"
                
        return True, "Report synthesis validation passed."

    @staticmethod
    def validate_phase5_pdf(pdf_path):
        """Phase 5: Check PDF exists and is >10KB."""
        if not pdf_path or not os.path.exists(pdf_path):
            return False, f"PDF file not found at {pdf_path}"
            
        size = os.path.getsize(pdf_path)
        if size < 10240:  # 10 KB
            return False, f"PDF generation resulted in a blank or corrupted file (Size: {size/1024:.2f} KB). Required > 10 KB."
            
        return True, "PDF generation validation passed."

import re
import uuid
from typing import Dict, Any, Tuple

try:
    from presidio_analyzer import AnalyzerEngine
    presidio_analyzer = AnalyzerEngine()
except Exception:
    presidio_analyzer = None

try:
    import spacy
    nlp_spacy = spacy.load("en_core_web_sm")
except Exception:
    nlp_spacy = None


class PIIDetector:
    """
    Bi-directional PII Handler:
    1. Microsoft Presidio (Primary PII detector for 40+ standard entities)
    2. SpaCy NER (Supporting contextual entity detection: PERSON, ORG, GPE)
    3. Custom Regex Patterns (Internal Employee IDs, API keys, custom account numbers)
    4. Multi-engine Span Deduplication (All engines run on original text; overlapping sub-spans are merged)
    5. Bi-directional token masking & restoration map
    """

    PATTERNS = {
        "EMAIL": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        "PHONE": r'\b(?:\+?1[-. ]?)?\(?([0-9]{3})\)?[-. ]?([0-9]{3})[-. ]?([0-9]{4})\b',
        "SSN": r'\b\d{3}-\d{2}-\d{4}\b',
        "CREDIT_CARD": r'\b(?:\d[ -]*?){13,16}\b',
        "EMPLOYEE_ID": r'\bEMP-\d{5}\b',
        "API_KEY": r'\bsk-[A-Za-z0-9]{32,}\b'
    }

    def _remove_overlapping_spans(self, spans: list) -> list:
        """
        Sorts spans by score desc, then span length desc.
        Filters out any sub-span that overlaps with a higher-priority or longer span.
        Span structure: (start, end, entity_type, score, val)
        """
        sorted_spans = sorted(spans, key=lambda s: (s[3], s[1] - s[0]), reverse=True)
        accepted = []
        for span in sorted_spans:
            start, end, etype, score, val = span
            # Reject if overlaps with any accepted span
            overlap = False
            for a_start, a_end, _, _, _ in accepted:
                if not (end <= a_start or start >= a_end):
                    overlap = True
                    break
            if not overlap:
                accepted.append(span)
        # Return sorted right-to-left for clean string offset replacement
        return sorted(accepted, key=lambda s: s[0], reverse=True)

    def mask_pii(self, text: str) -> Tuple[str, Dict[str, str], int]:
        pii_map = {}
        candidate_spans = []

        # Engine 1: Presidio Analysis on original text (score threshold >= 0.5)
        if presidio_analyzer is not None:
            try:
                results = presidio_analyzer.analyze(text=text, entities=[], language='en', score_threshold=0.5)
                for res in results:
                    val = text[res.start:res.end]
                    candidate_spans.append((res.start, res.end, res.entity_type, res.score, val))
            except Exception:
                pass

        # Engine 2: SpaCy NER on original text (for PERSON, ORG, GPE)
        if nlp_spacy is not None:
            try:
                doc = nlp_spacy(text)
                for ent in doc.ents:
                    if ent.label_ in ["PERSON", "ORG", "GPE"]:
                        val = ent.text
                        if len(val.strip()) > 2:
                            candidate_spans.append((ent.start_char, ent.end_char, ent.label_, 0.85, val))
            except Exception:
                pass

        # Engine 3: Custom Regex Patterns on original text
        for entity_type, pattern in self.PATTERNS.items():
            for m in re.finditer(pattern, text):
                val = m.group(0)
                candidate_spans.append((m.start(), m.end(), entity_type, 0.95, val))

        # Deduplicate & filter overlapping spans across all 3 engines
        final_spans = self._remove_overlapping_spans(candidate_spans)

        # Perform right-to-left replacement on original text
        masked_text = text
        count = 0
        for start, end, entity_type, score, val in final_spans:
            placeholder = f"<PII_{entity_type}_{uuid.uuid4().hex[:6].upper()}>"
            pii_map[placeholder] = val
            masked_text = masked_text[:start] + placeholder + masked_text[end:]
            count += 1

        return masked_text, pii_map, count

    def unmask_pii(self, text: str, pii_map: Dict[str, str]) -> str:
        unmasked_text = text
        for placeholder, original in pii_map.items():
            unmasked_text = unmasked_text.replace(placeholder, original)
        return unmasked_text


pii_detector = PIIDetector()

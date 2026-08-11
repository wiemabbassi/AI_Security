import re
import uuid
from typing import Dict, Any, Tuple

try:
    from presidio_analyzer import AnalyzerEngine
    from presidio_anonymizer import AnonymizerEngine
    presidio_analyzer = AnalyzerEngine()
    presidio_anonymizer = AnonymizerEngine()
except Exception:
    presidio_analyzer = None
    presidio_anonymizer = None

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
    4. Bi-directional token masking & restoration map
    """

    PATTERNS = {
        "EMAIL": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        "PHONE": r'\b(?:\+?1[-. ]?)?\(?([0-9]{3})\)?[-. ]?([0-9]{3})[-. ]?([0-9]{4})\b',
        "SSN": r'\b\d{3}-\d{2}-\d{4}\b',
        "CREDIT_CARD": r'\b(?:\d[ -]*?){13,16}\b',
        "EMPLOYEE_ID": r'\bEMP-\d{5}\b',
        "API_KEY": r'\bsk-[A-Za-z0-9]{32,}\b'
    }

    def mask_pii(self, text: str) -> Tuple[str, Dict[str, str], int]:
        pii_map = {}
        masked_text = text
        count = 0

        # 1. Microsoft Presidio Analysis if available
        if presidio_analyzer is not None:
            try:
                results = presidio_analyzer.analyze(text=text, entities=[], language='en')
                for res in sorted(results, key=lambda x: x.start, reverse=True):
                    val = text[res.start:res.end]
                    entity_type = res.entity_type
                    placeholder = f"<PII_{entity_type}_{uuid.uuid4().hex[:6].upper()}>"
                    if val not in pii_map.values():
                        pii_map[placeholder] = val
                        masked_text = masked_text[:res.start] + placeholder + masked_text[res.end:]
                        count += 1
            except Exception:
                pass

        # 2. SpaCy NER Analysis if available
        if nlp_spacy is not None:
            try:
                doc = nlp_spacy(masked_text)
                for ent in reversed(doc.ents):
                    if ent.label_ in ["PERSON", "ORG", "GPE"]:
                        val = ent.text
                        if not val.startswith("<PII_") and val not in pii_map.values():
                            placeholder = f"<PII_{ent.label_}_{uuid.uuid4().hex[:6].upper()}>"
                            pii_map[placeholder] = val
                            masked_text = masked_text[:ent.start_char] + placeholder + masked_text[ent.end_char:]
                            count += 1
            except Exception:
                pass

        # 3. Custom Regex Patterns
        for entity_type, pattern in self.PATTERNS.items():
            matches = list(set(re.findall(pattern, masked_text)))
            for match in matches:
                if isinstance(match, tuple):
                    match = "-".join(match)
                if match not in pii_map.values() and not match.startswith("<PII_"):
                    placeholder = f"<PII_{entity_type}_{uuid.uuid4().hex[:6].upper()}>"
                    pii_map[placeholder] = match
                    masked_text = masked_text.replace(match, placeholder)
                    count += 1

        return masked_text, pii_map, count

    def unmask_pii(self, text: str, pii_map: Dict[str, str]) -> str:
        unmasked_text = text
        for placeholder, original in pii_map.items():
            unmasked_text = unmasked_text.replace(placeholder, original)
        return unmasked_text

pii_detector = PIIDetector()

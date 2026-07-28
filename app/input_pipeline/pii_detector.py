import re
import uuid
from typing import Dict, Any, Tuple

class PIIDetector:
    """
    Bi-directional PII Handler:
    1. Detects Email, Phone, SSN, Credit Card, Employee ID, API Keys.
    2. Masks sensitive entities before sending prompt to downstream LLM.
    3. Stores exact token mapping securely for restoration.
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

        for entity_type, pattern in self.PATTERNS.items():
            matches = list(set(re.findall(pattern, masked_text)))
            for match in matches:
                if isinstance(match, tuple):
                    match = "-".join(match)
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

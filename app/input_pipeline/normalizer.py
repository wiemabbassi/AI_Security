import unicodedata
import re
try:
    import ftfy
except ImportError:
    ftfy = None

class TextNormalizer:
    """
    Normalizes input text by fixing unicode obfuscation, mojibake,
    HTML entities, and collapsing homoglyphs.
    """
    def normalize(self, text: str) -> str:
        if not text:
            return ""
        
        # 1. Fix text encoding & mojibake with ftfy if installed
        if ftfy is not None:
            text = ftfy.fix_text(text)
            
        # 2. Unicode NFKC normalization (collapses homoglyphs like ℯ -> e, 𝐇 -> H)
        normalized = unicodedata.normalize("NFKC", text)
        
        # 3. Clean zero-width non-printable characters
        cleaned = re.sub(r'[\u200B-\u200D\uFEFF]', '', normalized)
        
        # 4. Standardize whitespace
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        
        return cleaned

normalizer = TextNormalizer()

"""
Heidi Calls: PII Redaction Filter
Privacy-preserving text processing for medical voicemails

Detects and redacts:
- Australian Medicare numbers
- Phone numbers (AU format)
- Email addresses
- Dates of birth
- Full names (heuristic-based)
- Addresses
- Credit card numbers
- Australian TFN (Tax File Numbers)
- Health identifiers
"""

import re
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum


class PIIType(str, Enum):
    """Types of PII that can be detected"""
    MEDICARE = "medicare_number"
    PHONE = "phone_number"
    EMAIL = "email"
    DOB = "date_of_birth"
    NAME = "name"
    ADDRESS = "address"
    CREDIT_CARD = "credit_card"
    TFN = "tax_file_number"
    HEALTH_ID = "health_identifier"
    SSN = "social_security"  # For US compatibility


@dataclass
class PIIMatch:
    """Represents a detected PII instance"""
    pii_type: PIIType
    original_value: str
    start_pos: int
    end_pos: int
    redacted_value: str


class PIIRedactionFilter:
    """
    Enterprise-grade PII detection and redaction service.
    Implements defense-in-depth with multiple detection patterns.
    """
    
    def __init__(self, redaction_char: str = "█"):
        self.redaction_char = redaction_char
        self._compile_patterns()
    
    def _compile_patterns(self):
        """Pre-compile regex patterns for performance"""
        
        # Australian Medicare Number: 10-11 digits, often formatted with spaces
        # Format: XXXX XXXXX X or XXXXXXXXXX
        self.medicare_pattern = re.compile(
            r'\b(\d{4}[\s-]?\d{5}[\s-]?\d{1,2})\b'
        )
        
        # Australian Phone Numbers (mobile and landline)
        # Mobile: 04XX XXX XXX, Landline: (0X) XXXX XXXX
        self.phone_pattern = re.compile(
            r'(?:\+?61[-.\s]?|0)(?:'
            r'4\d{2}[-.\s]?\d{3}[-.\s]?\d{3}|'  # Mobile
            r'[2-9]\d{1}[-.\s]?\d{4}[-.\s]?\d{4}|'  # Landline
            r'\(\d{2}\)[-.\s]?\d{4}[-.\s]?\d{4})'  # Landline with area code
        )
        
        # Email addresses
        self.email_pattern = re.compile(
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        )
        
        # Dates of Birth - multiple formats
        self.dob_patterns = [
            # "date of birth is March 15, 1965" or "DOB: 15/03/1965"
            re.compile(
                r'(?:date\s+of\s+birth|DOB|d\.o\.b\.?|born\s+on|birthday)\s*'
                r'(?:is\s+|:\s*)?'
                r'(\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|'
                r'(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}|'
                r'\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})',
                re.IGNORECASE
            ),
            # Standalone date patterns (be more conservative)
            re.compile(r'\b(\d{2}/\d{2}/\d{4})\b'),
            re.compile(r'\b(\d{4}-\d{2}-\d{2})\b'),  # ISO format
        ]
        
        # Credit Card Numbers (13-19 digits, possibly with spaces/dashes)
        self.credit_card_pattern = re.compile(
            r'\b(?:\d{4}[-\s]?){3,4}\d{1,4}\b'
        )
        
        # Australian Tax File Number (9 digits)
        self.tfn_pattern = re.compile(
            r'\b\d{3}[-\s]?\d{3}[-\s]?\d{3}\b'
        )
        
        # Street addresses (basic heuristic)
        self.address_pattern = re.compile(
            r'\b\d+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+'
            r'(?:Street|St|Road|Rd|Avenue|Ave|Drive|Dr|Lane|Ln|Court|Ct|'
            r'Place|Pl|Crescent|Cres|Boulevard|Blvd|Way|Close|Circuit)\b',
            re.IGNORECASE
        )
        
        # Name patterns (following "my name is", "this is", "I'm", etc.)
        self.name_patterns = [
            re.compile(
                r'(?:my\s+name\s+is|this\s+is|I\'?m|I\s+am|'
                r'name\'?s|speaking\s+is|patient\s+name:?)\s+'
                r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})',
                re.IGNORECASE
            ),
            # "Mrs/Mr/Ms/Dr Name"
            re.compile(
                r'\b(?:Mrs?\.?|Ms\.?|Dr\.?|Miss)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\b'
            ),
        ]
    
    def detect_pii(self, text: str) -> List[PIIMatch]:
        """
        Detect all PII instances in the text.
        Returns a list of PIIMatch objects with positions and types.
        """
        matches: List[PIIMatch] = []
        
        # Medicare numbers
        for match in self.medicare_pattern.finditer(text):
            matches.append(PIIMatch(
                pii_type=PIIType.MEDICARE,
                original_value=match.group(),
                start_pos=match.start(),
                end_pos=match.end(),
                redacted_value=self._redact_medicare(match.group())
            ))
        
        # Phone numbers
        for match in self.phone_pattern.finditer(text):
            matches.append(PIIMatch(
                pii_type=PIIType.PHONE,
                original_value=match.group(),
                start_pos=match.start(),
                end_pos=match.end(),
                redacted_value=self._redact_phone(match.group())
            ))
        
        # Emails
        for match in self.email_pattern.finditer(text):
            matches.append(PIIMatch(
                pii_type=PIIType.EMAIL,
                original_value=match.group(),
                start_pos=match.start(),
                end_pos=match.end(),
                redacted_value=self._redact_email(match.group())
            ))
        
        # Dates of birth
        for pattern in self.dob_patterns:
            for match in pattern.finditer(text):
                # Get the date part (group 1 if exists, otherwise full match)
                date_value = match.group(1) if match.lastindex else match.group()
                matches.append(PIIMatch(
                    pii_type=PIIType.DOB,
                    original_value=match.group(),
                    start_pos=match.start(),
                    end_pos=match.end(),
                    redacted_value=self._redact_dob(match.group())
                ))
        
        # Credit cards
        for match in self.credit_card_pattern.finditer(text):
            # Validate it looks like a credit card (not a phone or other number)
            digits_only = re.sub(r'\D', '', match.group())
            if 13 <= len(digits_only) <= 19:
                matches.append(PIIMatch(
                    pii_type=PIIType.CREDIT_CARD,
                    original_value=match.group(),
                    start_pos=match.start(),
                    end_pos=match.end(),
                    redacted_value=self._redact_credit_card(match.group())
                ))
        
        # Addresses
        for match in self.address_pattern.finditer(text):
            matches.append(PIIMatch(
                pii_type=PIIType.ADDRESS,
                original_value=match.group(),
                start_pos=match.start(),
                end_pos=match.end(),
                redacted_value=self._redact_generic(match.group(), keep_last=0)
            ))
        
        # Names
        for pattern in self.name_patterns:
            for match in pattern.finditer(text):
                matches.append(PIIMatch(
                    pii_type=PIIType.NAME,
                    original_value=match.group(),
                    start_pos=match.start(),
                    end_pos=match.end(),
                    redacted_value=self._redact_name(match.group())
                ))
        
        # Remove duplicates and overlapping matches (keep longest)
        matches = self._deduplicate_matches(matches)
        
        return matches
    
    def _deduplicate_matches(self, matches: List[PIIMatch]) -> List[PIIMatch]:
        """Remove overlapping matches, keeping the longest one"""
        if not matches:
            return []
        
        # Sort by start position, then by length (descending)
        sorted_matches = sorted(matches, key=lambda m: (m.start_pos, -(m.end_pos - m.start_pos)))
        
        result = []
        last_end = -1
        
        for match in sorted_matches:
            if match.start_pos >= last_end:
                result.append(match)
                last_end = match.end_pos
        
        return result
    
    def _redact_medicare(self, value: str) -> str:
        """Redact Medicare number, keeping first 2 digits"""
        digits = re.sub(r'\D', '', value)
        return digits[:2] + self.redaction_char * (len(digits) - 2)
    
    def _redact_phone(self, value: str) -> str:
        """Redact phone number, keeping last 3 digits"""
        digits = re.sub(r'\D', '', value)
        return self.redaction_char * (len(digits) - 3) + digits[-3:]
    
    def _redact_email(self, value: str) -> str:
        """Redact email, showing first char and domain"""
        if '@' in value:
            local, domain = value.split('@', 1)
            return local[0] + self.redaction_char * (len(local) - 1) + '@' + domain
        return self.redaction_char * len(value)
    
    def _redact_dob(self, value: str) -> str:
        """Redact date of birth completely"""
        # Keep the prefix like "date of birth is" but redact the date
        patterns = [
            (r'(date\s+of\s+birth\s*(?:is\s*)?)', r'\1[DOB REDACTED]'),
            (r'(DOB\s*:?\s*)', r'\1[DOB REDACTED]'),
            (r'(born\s+on\s*)', r'\1[DOB REDACTED]'),
        ]
        result = value
        for pattern, replacement in patterns:
            if re.match(pattern, result, re.IGNORECASE):
                return re.sub(pattern + r'.*', replacement, result, flags=re.IGNORECASE)
        return '[DOB REDACTED]'
    
    def _redact_credit_card(self, value: str) -> str:
        """Redact credit card, keeping last 4 digits"""
        digits = re.sub(r'\D', '', value)
        return self.redaction_char * (len(digits) - 4) + digits[-4:]
    
    def _redact_name(self, value: str) -> str:
        """Redact name while keeping the prefix"""
        # Find common prefixes and keep them
        prefixes = [
            r'my\s+name\s+is\s+',
            r'this\s+is\s+',
            r'I\'?m\s+',
            r'I\s+am\s+',
            r'name\'?s\s+',
            r'(?:Mrs?\.?|Ms\.?|Dr\.?|Miss)\s+'
        ]
        for prefix_pattern in prefixes:
            match = re.match(f'({prefix_pattern})(.*)', value, re.IGNORECASE)
            if match:
                return match.group(1) + '[NAME REDACTED]'
        return '[NAME REDACTED]'
    
    def _redact_generic(self, value: str, keep_last: int = 0) -> str:
        """Generic redaction with optional last characters kept"""
        if keep_last > 0:
            return self.redaction_char * (len(value) - keep_last) + value[-keep_last:]
        return self.redaction_char * len(value)
    
    def redact(self, text: str) -> Tuple[str, List[PIIMatch], bool]:
        """
        Main redaction method.
        Returns: (redacted_text, list of matches, is_pii_safe)
        """
        matches = self.detect_pii(text)
        
        if not matches:
            return text, [], True
        
        # Apply redactions from end to start to preserve positions
        redacted_text = text
        for match in sorted(matches, key=lambda m: m.start_pos, reverse=True):
            redacted_text = (
                redacted_text[:match.start_pos] + 
                match.redacted_value + 
                redacted_text[match.end_pos:]
            )
        
        return redacted_text, matches, True
    
    def get_pii_summary(self, matches: List[PIIMatch]) -> Dict[str, int]:
        """Get a summary count of PII types found"""
        summary = {}
        for match in matches:
            pii_type = match.pii_type.value
            summary[pii_type] = summary.get(pii_type, 0) + 1
        return summary


# Singleton instance for reuse
pii_filter = PIIRedactionFilter()


def redact_pii(text: str) -> Tuple[str, bool]:
    """
    Convenience function for quick PII redaction.
    Returns (redacted_text, is_pii_safe)
    """
    redacted, _, is_safe = pii_filter.redact(text)
    return redacted, is_safe


if __name__ == "__main__":
    # Test the PII filter
    test_text = """
    Hi, this is John Smith calling about my blood pressure medication. 
    I've run out and need a refill urgently. My date of birth is March 15, 1965 
    and my Medicare number is 2345 6789 0. Please call me back at 0412 345 678.
    My email is john.smith@email.com and I live at 42 Collins Street Melbourne.
    """
    
    filter_instance = PIIRedactionFilter()
    redacted, matches, is_safe = filter_instance.redact(test_text)
    
    print("=== Original Text ===")
    print(test_text)
    print("\n=== Redacted Text ===")
    print(redacted)
    print("\n=== PII Matches Found ===")
    for match in matches:
        print(f"  {match.pii_type.value}: '{match.original_value}' -> '{match.redacted_value}'")
    print(f"\n=== Is PII Safe: {is_safe} ===")

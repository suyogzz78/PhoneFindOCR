"""Pure text -> phone numbers. No AI, no I/O, easy to test."""
import re

# Optional +91 / +977 or a leading 0, then 10 digits (spaces/dashes allowed between digits).
# \d also matches Devanagari digits, which the OCR may emit.
PHONE = re.compile(r"(?<!\d)(?:\+?(?:91|977)[\s-]?|0)?(\d(?:[\s-]?\d){9})(?!\d)")


def extract_phones(text: str) -> list[str]:
    """Return unique mobile numbers (10 digits, starting 6-9) in order of appearance."""
    found: list[str] = []
    seen: set[str] = set()
    for m in PHONE.finditer(text):
        # int(c) converts Devanagari digits (९८४...) to ASCII
        num = "".join(str(int(c)) for c in m.group(1) if c.isdigit())
        if num[0] in "6789" and num not in seen:
            seen.add(num)
            found.append(num)
    return found

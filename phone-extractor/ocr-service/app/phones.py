"""Pure text -> phone numbers. No AI, no I/O, easy to test."""
import re

# Optional +91 / +977 or a leading 0, then 10 digits (spaces/dashes allowed between digits).
# \d also matches Devanagari digits, which the OCR may emit.
PHONE = re.compile(r"(?<!\d)(?<!\+91)(?<!\+91[\s-])(?:\+?977[\s-]?|0)?([9९][6-8६-८](?:[\s-]?\d){8})(?!\d)")


def extract_phones(text: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for m in PHONE.finditer(text):
        # int(c) converts Devanagari digits to ASCII character by character
        num = "".join(str(int(c)) for c in m.group(1) if c.isdigit())
        if num not in seen:
            seen.add(num)
            found.append(num)
    return found


#limit is 50 mb
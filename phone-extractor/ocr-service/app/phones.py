"""Pure text -> phone numbers. No AI, no I/O, easy to test."""
import re

# Optional +91 / +977 or a leading 0, then 10 digits (spaces/dashes allowed between digits).
# \d also matches Devanagari digits, which the OCR may emit.
PHONE = re.compile(r"(?<!\d)(?<!\+91)(?<!\+91[\s-])(?:\+?977[\s-]?|0)?([9९][6-8६-८](?:[\s-]?\d){8})(?!\d)")


# Incomplete/partial mobile numbers (7 to 9 digits starting with 9, e.g. 92212748 or 98412345)
INCOMPLETE_PHONE = re.compile(
    r"(?<!\d)(?<!\+91)(?<!\+91[\s-])(?:\+?977[\s-]?|0)?([9९](?:[\s-]?\d){6,8})(?!\d)"
)


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


def extract_incomplete_phones(text: str, valid_phones: list[str] | None = None) -> list[str]:
    found: list[str] = []
    seen = set(valid_phones or [])
    for m in INCOMPLETE_PHONE.finditer(text):
        num = "".join(str(int(c)) for c in m.group(1) if c.isdigit())
        if num not in seen:
            seen.add(num)
            found.append(num)
    return found
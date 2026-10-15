"""Remove personal details from OCR text before it is sent to OpenAI or stored.

Data minimization under Jordan's Personal Data Protection Law: the app needs the
store, date, total and items of a receipt, not the phone numbers or the name of
the customer printed on it.

- Jordanian phone numbers become [PHONE]: mobiles (077, 078, 079 + 7 digits),
  landlines (02, 03, 05, 06 + 7 digits), and both with +962 or 00962 instead of
  the leading 0. Spaces or hyphens between digits are allowed, and Arabic-Indic
  digits are matched too.
- The value of a "Customer name" / "اسم العميل" field becomes [NAME]. OCR often
  puts the label and its value on separate lines, so when the label's line has
  no value, the next non-empty line is taken as the value.
"""
import re

PHONE = "[PHONE]"
NAME = "[NAME]"


def _d(digits: str) -> str:
    """A character class matching any of `digits` in Western, Arabic-Indic or Persian form."""
    chars = "".join(f"{d}{chr(0x0660 + int(d))}{chr(0x06F0 + int(d))}" for d in digits)
    return f"[{chars}]"


_SEP = "[ -]?"  # one optional space or hyphen between digits
_ANY = _d("0123456789")


def _then(pattern: str) -> str:
    return f"{_SEP}{pattern}"


_SEVEN_DIGITS = _then(_ANY) * 7
_SUBSCRIBER = f"(?:{_d('7')}{_then(_d('789'))}{_SEVEN_DIGITS}|{_d('2356')}{_SEVEN_DIGITS})"
_COUNTRY_CODE = f"(?:\\+|{_d('0')}{_then(_d('0'))}){_then(_d('9'))}{_then(_d('6'))}{_then(_d('2'))}"
# +962 79..., +962 (0)79..., 00962 6..., or a leading 0 as in 079... and 06...
_PREFIX = f"(?:{_COUNTRY_CODE}{_SEP}(?:\\({_d('0')}\\){_SEP})?|{_d('0')}{_SEP})"

PHONE_PATTERN = re.compile(
    f"(?<![\\w+])"  # not the end of a longer number or word
    f"{_PREFIX}{_SUBSCRIBER}"
    f"(?!{_SEP}{_ANY})"  # and not followed by more digits
)

CUSTOMER_LABELS = ("customer name", "اسم العميل")
_LABEL_PATTERN = re.compile(
    "|".join(r"\s*".join(map(re.escape, label.split())) for label in CUSTOMER_LABELS), re.IGNORECASE,
)
# What may separate a label from its value: colons (Latin, Arabic and full-width), dashes, spaces.
_SEPARATORS = " \t:：-–—|"


def redact_phones(text: str) -> str:
    return PHONE_PATTERN.sub(PHONE, text)


def redact_customer_names(text: str) -> str:
    lines = text.split("\n")
    redact_next = False
    for index, line in enumerate(lines):
        if redact_next and line.strip():
            lines[index] = NAME
            redact_next = False
            continue
        match = _LABEL_PATTERN.search(line)
        if not match:
            continue
        # Text on either side of the label is its value: OCR can read a right-to-left line in either order.
        before = line[:match.start()].strip(_SEPARATORS)
        after = line[match.end():].strip(_SEPARATORS)
        if before or after:
            lines[index] = f"{match.group(0)}: {NAME}"
        else:
            redact_next = True
    return "\n".join(lines)


def redact(text: str) -> str:
    """Replace phone numbers with [PHONE] and the customer's name with [NAME]."""
    if not text:
        return text
    return redact_customer_names(redact_phones(text))

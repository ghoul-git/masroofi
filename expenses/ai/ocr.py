import easyocr

_reader = None


def get_reader():
    """Load the OCR model once and reuse it, since loading is slow."""
    global _reader
    if _reader is None:
        _reader = easyocr.Reader(["ar", "en"], gpu=False)
    return _reader


def read_text(image) -> tuple[str, float]:
    """Return the recognized text and the average confidence (0 to 1)."""
    results = get_reader().readtext(image)
    if not results:
        return "", 0.0
    text = "\n".join(line for _, line, _ in results)
    confidence = sum(conf for _, _, conf in results) / len(results)
    return text, confidence

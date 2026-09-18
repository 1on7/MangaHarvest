from datetime import datetime
import re
import unicodedata

ARABIC_MONTHS = {
    "يناير": "January", "فبراير": "February", "مارس": "March",
    "أبريل": "April", "ابريل": "April", "مايو": "May",
    "يونيو": "June", "يونيو": "June", "يوليو": "July",
    "أغسطس": "August", "اغسطس": "August", "سبتمبر": "September",
    "أكتوبر": "October", "اكتوبر": "October", "نوفمبر": "November",
    "ديسمبر": "December",
}

ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def convert_arabic_date_to_numeric(date_str):
    if not date_str:
        return ""

    value = unicodedata.normalize("NFKC", str(date_str)).translate(ARABIC_DIGITS)
    value = value.replace("،", ",").strip()
    value = re.sub(r"\s+", " ", value)

    for arabic_month, english_month in ARABIC_MONTHS.items():
        value = value.replace(arabic_month, english_month)

    for fmt in ("%B %d, %Y", "%d %B %Y", "%B %d %Y", "%d %B, %Y"):
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue

    return ""

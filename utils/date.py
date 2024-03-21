from datetime import datetime

def convert_arabic_date_to_numeric(date_str):
    # Mapping of Arabic month names to English
    arabic_months = {
        'يناير': 'January',
        'فبراير': 'February',
        'مارس': 'March',
        'أبريل': 'April',
        'مايو': 'May',
        'يونيو': 'June',
        'يوليو': 'July',
        'أغسطس': 'August',
        'سبتمبر': 'September',
        'أكتوبر': 'October',
        'نوفمبر': 'November',
        'ديسمبر': 'December'
    }

    # Replace Arabic month names with English
    for arabic_month, english_month in arabic_months.items():
        date_str = date_str.replace(arabic_month, english_month)
    try:
        # Parse the date string into a datetime object
        date_obj = datetime.strptime(date_str, '%B %d, %Y').strftime('%Y-%m-%d')
        return date_obj
    except:
        date_obj = datetime.strptime(date_str, '%d %B %Y').strftime('%Y-%m-%d')
        return date_obj
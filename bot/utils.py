def check_red_flags(text: str) -> list:
    RED_FLAGS = [
        "боль в груди", "боль в сердце", "сердце", "инфаркт",
        "кровотечение", "обильное кровотечение", "кровь",
        "потеря сознания", "обморок", "упал в обморок",
        "судороги", "конвульсии", "припадок",
        "отек горла", "не могу дышать", "удушье", "затрудненное дыхание",
        "отравление", "яды", "токсины",
        "травма головы", "удар по голове", "потеря памяти",
        "высокая температура", "жар", "лихорадка",
        "боль в животе острая", "острая боль", "режущая боль"
    ]
    
    text_lower = text.lower()
    found_flags = []
    
    for flag in RED_FLAGS:
        if flag.lower() in text_lower:
            found_flags.append(flag)
    
    return found_flags

def format_medical_report(data: dict, analysis: dict) -> str:
    report = f"""
╔══════════════════════════════════════╗
║     МЕДИЦИНСКИЙ АССИСТЕНТ           ║
║     (Не является диагнозом)         ║
╚══════════════════════════════════════╝

📋 ДАННЫЕ ПАЦИЕНТА:
• Возраст: {data.get('age', 'не указан')}
• Пол: {data.get('gender', 'не указан')}
• Жалоба: {data.get('main_complaint', 'не указана')}
• Длительность: {data.get('duration', 'не указана')}
• Тяжесть: {data.get('severity', 'не указана')}/5

🔍 АНАЛИЗ:
{analysis.get('analysis', 'Требуется осмотр врача')}

⚠️ УРОВЕНЬ СРОЧНОСТИ: {analysis.get('urgency', 'medium').upper()}

👨‍⚕️ РЕКОМЕНДУЕМЫЙ СПЕЦИАЛИСТ:
{analysis.get('recommended_specialist', 'Терапевт')}

📌 РЕКОМЕНДАЦИИ:
"""
    
    for i, rec in enumerate(analysis.get('recommendations', ['Обратитесь к врачу']), 1):
        report += f"{i}. {rec}\n"
    
    if analysis.get('warnings'):
        report += "\n⚡ ВНИМАНИЕ:\n"
        for warning in analysis['warnings']:
            report += f"• {warning}\n"
    
    report += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{analysis.get('disclaimer', 'Это не медицинская консультация. Обратитесь к врачу.')}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    
    return report

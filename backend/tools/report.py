"""
Report Generator Tool
=====================
Structures analysis results into a formatted narrative report.
Supports bilingual output (Indonesian & English).
"""

import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


def format_report(
    title: str,
    analysis_text: str,
    statistics: dict | None = None,
    chart_count: int = 0,
    language: str = "id",
) -> str:
    """
    Format a complete analysis report with title, body, and conclusion.

    Args:
        title: Report title.
        analysis_text: Main analysis narrative from LLM.
        statistics: Statistics dict for summary section.
        chart_count: Number of charts generated.
        language: "id" or "en".

    Returns:
        Formatted Markdown report string.
    """
    timestamp = datetime.now().strftime("%d %B %Y, %H:%M")

    if language == "id":
        report = f"""# 📊 {title}

*Laporan dibuat secara otomatis pada {timestamp}*

---

{analysis_text}

---

**Ringkasan Teknis:**
- Jumlah visualisasi yang dihasilkan: {chart_count}
- Status analisis: ✅ Selesai
- Pemrosesan: 100% lokal (tidak ada data yang dikirim ke cloud)
"""
    else:
        report = f"""# 📊 {title}

*Report automatically generated on {timestamp}*

---

{analysis_text}

---

**Technical Summary:**
- Visualizations generated: {chart_count}
- Analysis status: ✅ Complete
- Processing: 100% local (no data sent to cloud)
"""

    return report


def extract_report_title(narrative: str, language: str = "id") -> str:
    """
    Extract or generate a title from the narrative text.
    Looks for markdown H1 headers first, then generates a default.
    """
    for line in narrative.split("\n"):
        line = line.strip()
        if line.startswith("# "):
            return line.replace("# ", "").strip()

    if language == "id":
        return "Laporan Analisis Data"
    return "Data Analysis Report"

# DEMO SCOPE — whole file.
PROTOTYPE_LABEL_FA = "نمونهٔ اولیهٔ تحلیل ریسک قاعده‌محور — نیازمند بازبینی انسانی"
PROTOTYPE_LABEL_EN = "Rule-Based Risk Analysis Prototype — human review required"


def demo(request):
    return {
        "DEMO_MODE": True,
        "PROTOTYPE_LABEL_FA": PROTOTYPE_LABEL_FA,
        "PROTOTYPE_LABEL_EN": PROTOTYPE_LABEL_EN,
    }

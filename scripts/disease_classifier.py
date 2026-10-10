"""
疾病分类器：用关键词把条目归到具体传染病。

用法：
    from disease_classifier import classify_disease
    classify_disease(title + summary)  # -> "鼠疫" / "新冠" / ... / "未明确"

注意顺序：靠前的优先（如"禽流感"要在"流感"前，"新冠"要在"SARS"前，
因为 "SARS-CoV-2" 里含有 "SARS"；"鼠疫"要在"肺炎"前）。
"""

# (疾病中文名, [关键词...])，按优先级从高到低排列
DISEASE_KEYWORDS = [
    ("鼠疫", ["鼠疫", "plague", "yersinia pestis", "耶尔森菌", "чума"]),
    ("禽流感", ["禽流感", "H5N1", "H7N9", "H5N6", "bird flu", "avian influenza", "птичий грипп"]),
    ("流感", ["流感", "influenza", "грипп"]),
    ("新冠", ["新冠", "COVID", "SARS-CoV-2", "2019-nCoV", "coronavirus", "ковид"]),
    ("非典", ["非典", "SARS"]),
    ("中东呼吸综合征", ["中东呼吸", "MERS"]),
    ("猴痘", ["猴痘", "mpox", "monkeypox"]),
    ("登革热", ["登革热", "dengue", "денге"]),
    ("埃博拉", ["埃博拉", "ebola", "эбола"]),
    ("马尔堡病", ["马尔堡", "marburg"]),
    ("霍乱", ["霍乱", "cholera", "холера"]),
    ("麻疹", ["麻疹", "measles", "корь"]),
    ("肺炎", ["肺炎", "pneumonia", "пневмония"]),
    ("结核", ["结核", "tuberculosis", "туберкулез"]),
    ("炭疽", ["炭疽", "anthrax", "сибирская язва"]),
    ("寨卡", ["寨卡", "zika"]),
    ("基孔肯雅热", ["基孔肯雅", "chikungunya"]),
    ("尼帕病毒病", ["尼帕", "nipah"]),
    ("拉沙热", ["拉沙热", "lassa"]),
    ("天花", ["天花", "smallpox", "оспа"]),
    ("脊髓灰质炎", ["脊髓灰质炎", "polio", "小儿麻痹"]),
    ("狂犬病", ["狂犬病", "rabies", "бешенство"]),
    ("疟疾", ["疟疾", "malaria", "малярия"]),
    ("肝炎", ["肝炎", "hepatitis", "甲肝", "乙肝", "丙肝", "гепатит"]),
    ("艾滋病", ["艾滋", "HIV", "AIDS"]),
    ("诺如病毒病", ["诺如", "norovirus"]),
    ("手足口病", ["手足口", "EV71", "柯萨奇"]),
    ("布鲁氏菌病", ["布鲁氏", "brucella", "布病"]),
    ("钩端螺旋体病", ["钩端", "leptospira", "钩体病"]),
    ("鹦鹉热", ["鹦鹉热", "psittacosis"]),
    ("军团菌病", ["军团菌", "legionella"]),
    ("伤寒", ["伤寒", "typhoid"]),
    ("白喉", ["白喉", "diphtheria"]),
    ("百日咳", ["百日咳", "pertussis"]),
    ("破伤风", ["破伤风", "tetanus"]),
    ("流行性腮腺炎", ["腮腺炎", "mumps"]),
    ("风疹", ["风疹", "rubella"]),
    ("水痘", ["水痘", "chickenpox", "varicella"]),
    ("带状疱疹", ["带状疱疹", "shingles"]),
]

UNKNOWN = "未明确"


def classify_disease(text: str) -> str:
    """给一段文本定疾病分类，命中返回疾病中文名，否则返回"未明确"。"""
    t = (text or "").lower()
    for name, keywords in DISEASE_KEYWORDS:
        for kw in keywords:
            if kw.lower() in t:
                return name
    return UNKNOWN


def disease_list() -> list:
    """返回所有疾病名（按优先级顺序）。"""
    return [name for name, _ in DISEASE_KEYWORDS]

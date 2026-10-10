"""
疾病分类器：用关键词把条目归到具体传染病。

用法：
    from disease_classifier import classify_disease, disease_list
    classify_disease(title + summary)  # -> "鼠疫" / "新冠" / ... / "未明确"

注意顺序：靠前的优先（如"禽流感"要在"流感"前，"新冠"要在"非典"前，
因为 "SARS-CoV-2" 里含有 "SARS"；"斑疹伤寒"要在"伤寒"前；
"克里米亚-刚果出血热"要在"肾综合征出血热"前，因为都含"出血热"）。
"""

# (疾病中文名, [关键词...])，按优先级从高到低排列
DISEASE_KEYWORDS = [
    ("鼠疫", ["鼠疫", "plague", "yersinia pestis", "耶尔森菌", "чум"]),
    ("禽流感", ["禽流感", "H5N1", "H7N9", "H5N6", "bird flu", "avian influenza", "птичий грипп"]),
    ("流感", ["流感", "influenza", "грипп", "swine flu", "猪流感"]),
    ("新冠", ["新冠", "COVID", "SARS-CoV-2", "2019-nCoV", "coronavirus", "ковид"]),
    ("非典", ["非典", "SARS"]),
    ("中东呼吸综合征", ["中东呼吸", "MERS"]),
    ("人偏肺病毒病", ["偏肺病毒", "hMPV", "metapneumovirus"]),
    ("呼吸道合胞病毒病", ["合胞病毒", "RSV", "respiratory syncytial"]),
    ("猴痘", ["猴痘", "mpox", "monkeypox"]),
    ("天花", ["天花", "smallpox", "осп"]),
    ("水痘", ["水痘", "chickenpox", "varicella"]),
    ("带状疱疹", ["带状疱疹", "shingles", "herpes zoster"]),
    ("麻疹", ["麻疹", "measles", "кори"]),
    ("风疹", ["风疹", "rubella"]),
    ("流行性腮腺炎", ["腮腺炎", "mumps"]),
    ("脊髓灰质炎", ["脊髓灰质炎", "polio", "小儿麻痹"]),
    ("白喉", ["白喉", "diphtheria"]),
    ("百日咳", ["百日咳", "pertussis"]),
    ("破伤风", ["破伤风", "tetanus"]),
    ("猩红热", ["猩红热", "scarlet fever"]),
    ("流行性脑脊髓膜炎", ["流行性脑脊髓膜炎", "流脑", "meningococcal", "менингококк"]),
    ("流行性乙型脑炎", ["乙型脑炎", "乙脑", "Japanese encephalitis"]),
    ("蜱传脑炎", ["蜱传脑炎", "森林脑炎", "tick-borne encephalitis"]),
    ("肺炎", ["肺炎", "pneumonia", "пневмони", "肺炎支原体", "肺炎链球菌"]),
    ("军团菌病", ["军团菌", "legionella"]),
    ("鹦鹉热", ["鹦鹉热", "psittacosis"]),
    ("Q热", ["Q热", "贝纳柯克斯体", "Q fever"]),
    ("结核", ["结核", "tuberculosis", "туберкулез"]),
    ("麻风", ["麻风", "leprosy", "проказ", "汉森病"]),
    ("霍乱", ["霍乱", "cholera", "холер"]),
    ("斑疹伤寒", ["斑疹伤寒", "斑疹", "typhus"]),
    ("伤寒", ["伤寒", "typhoid", "副伤寒", "paratyphoid"]),
    ("细菌性痢疾", ["痢疾", "志贺菌", "shigella", "shigellosis"]),
    ("诺如病毒病", ["诺如", "norovirus"]),
    ("轮状病毒病", ["轮状", "rotavirus"]),
    ("手足口病", ["手足口", "EV71", "柯萨奇"]),
    ("肝炎", ["肝炎", "hepatitis", "甲肝", "乙肝", "丙肝", "丁肝", "戊肝", "гепатит"]),
    ("艾滋病", ["艾滋", "HIV", "AIDS"]),
    ("梅毒", ["梅毒", "syphilis"]),
    ("淋病", ["淋病", "gonorrhea", "gonorrhoea"]),
    ("埃博拉", ["埃博拉", "ebola", "эбол"]),
    ("马尔堡病", ["马尔堡", "marburg"]),
    ("拉沙热", ["拉沙热", "lassa"]),
    ("克里米亚-刚果出血热", ["克里米亚-刚果出血热", "克里米亚刚果出血热", "CCHF", "Crimean-Congo"]),
    ("裂谷热", ["裂谷热", "Rift Valley"]),
    ("肾综合征出血热", ["肾综合征出血热", "流行性出血热", "汉坦", "hantavirus", "出血热"]),
    ("黄热病", ["黄热病", "yellow fever"]),
    ("登革热", ["登革热", "dengue", "денге"]),
    ("寨卡", ["寨卡", "zika"]),
    ("基孔肯雅热", ["基孔肯雅", "chikungunya"]),
    ("西尼罗河热", ["西尼罗", "West Nile"]),
    ("尼帕病毒病", ["尼帕", "nipah"]),
    ("亨德拉病毒病", ["亨德拉", "hendra"]),
    ("发热伴血小板减少综合征", ["发热伴血小板减少", "SFTS", "新布尼亚病毒"]),
    ("炭疽", ["炭疽", "anthrax", "сибирск"]),
    ("鼻疽", ["鼻疽", "glanders"]),
    ("兔热病", ["兔热病", "土拉菌", "tularemia"]),
    ("布鲁氏菌病", ["布鲁氏", "brucella", "布病"]),
    ("钩端螺旋体病", ["钩端", "leptospira", "钩体病"]),
    ("莱姆病", ["莱姆病", "莱姆", "Lyme", "伯氏疏螺旋体", "borrelia"]),
    ("恙虫病", ["恙虫病", "恙虫", "scrub typhus", "orientia"]),
    ("回归热", ["回归热", "relapsing fever"]),
    ("疟疾", ["疟疾", "malaria", "маляри"]),
    ("血吸虫病", ["血吸虫", "schistosoma", "schistosomiasis"]),
    ("利什曼病", ["利什曼", "黑热病", "leishmania", "kala-azar"]),
    ("丝虫病", ["丝虫病", "丝虫", "filaria", "象皮病"]),
    ("包虫病", ["包虫病", "棘球蚴", "echinococcus"]),
    ("弓形虫病", ["弓形虫", "toxoplasma"]),
    ("狂犬病", ["狂犬病", "rabies", "бешенств", "恐水症"]),
    ("李斯特菌病", ["李斯特菌", "listeria"]),
    ("沙门氏菌病", ["沙门氏菌", "salmonella"]),
    ("空肠弯曲菌病", ["弯曲菌", "campylobacter"]),
    ("大肠杆菌病", ["大肠杆菌", "O157", "E. coli"]),
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

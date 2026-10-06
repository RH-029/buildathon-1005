"""Conservative English/Chinese phrase interpretation; no model or extra key.

Recognizes explicit preferences, never executes memory instructions or infers
numeric budgets/deadlines. Unsupported statements remain raw evidence.
"""

import re

TAG_WORDS = {
    "nature": r"\bnature\b|\bgardens?\b|自然|花园|花園",
    "gardens": r"\bgardens?\b|花园|花園",
    "photography": r"\bphotograph\w*\b|\bphotos?\b|摄影|攝影|拍照",
    "scenic": r"\bscenic\b|\bviews?\b|\bphotograph\w*\b|风景|風景",
    "quiet": r"\bquiet\b|\bpeaceful\b|安静|安靜",
    "walking": r"\bwalk\w*\b|散步|步行",
    "hiking": r"\bhik\w*\b|徒步|爬山",
    "social": r"\bfriends\b|\bsocial\b|朋友|社交",
    "art": r"\bart\b|\bmuseums?\b|艺术|藝術|博物馆",
    "food": r"\bfood\b|美食",
}


def interpret_text(text):
    text = text.casefold().replace("’", "'")
    likes, avoids = set(), set()
    clauses = r"[.!?。！？;；,，]|\bbut\b|但是|\band\s+(?=(?:i\s+)?(?:dislike|hate|avoid|like|love|enjoy|prefer|want|don't|do not)\b)"
    for clause in re.split(clauses, text):
        negative = bool(re.search(r"\bdislike\b|\bhate\b|\bavoid\b|\bdon't (?:like|enjoy|want)\b|\bdo not (?:like|enjoy|want)\b|不喜欢|不喜歡|讨厌|討厭|避免", clause))
        positive = bool(re.search(r"\blike\b|\blove\b|\benjoy\b|\bprefer\b|\bwant\b|喜欢|喜歡|想要|偏好", clause))
        if not (negative or positive):
            continue
        for tag, words in TAG_WORDS.items():
            if re.search(words, clause):
                (avoids if negative else likes).add(tag)
    slower = bool(re.search(
        r"(?:felt|was|were|too)\s+rushed|dislike\s+(?:packed|tight|rushed)\s+(?:schedules?|itineraries)|"
        r"(?:one|single|just one|only one)\s+(?:main\s+)?activit\w*|fewer\s+(?:stops|activities)|"
        r"more\s+breathing\s+room|prefer\s+(?:a\s+)?(?:slow|relaxed)|太赶|太趕|只安排一个|只安排一個|"
        r"一个主要活动|一個主要活動|不喜欢紧凑|不喜歡緊湊|放慢|更多休息", text))
    if re.search(r"\b(?:not|never)\s+(?:felt\s+)?rushed\b|\b(?:don't|do not) want (?:a )?(?:slow|relaxed)|不觉得赶|不覺得趕", text):
        slower = False
    short_drives = bool(re.search(r"(?:prefer|like|want)\s+(?:a\s+)?short(?:er)?\s+drives?|"
                                 r"(?:dislike|avoid|hate)\s+long\s+drives?|短途驾驶|短途駕駛|不喜欢长途|不喜歡長途", text))
    if re.search(r"(?:don't|do not)\s+(?:prefer|like|want)\s+short\s+drives?|不喜欢短途|不喜歡短途", text):
        short_drives = False
    vegetarian = bool(re.search(r"\b(?:i am|i'm|i require|i need)\s+(?:a\s+)?vegetarian\b|"
                               r"\b(?:require|need)\s+vegetarian\s+(?:food|meals)|我是素食|吃素|需要素食", text))
    if re.search(r"\b(?:not|no longer)\s+(?:a\s+)?vegetarian\b|不吃素|不再吃素", text):
        vegetarian = False
    step_free = bool(re.search(r"\b(?:need|require)\s+(?:a\s+)?step.free|\b(?:cannot|can't)\s+(?:use|climb)\s+stairs|需要无台阶|需要無台階|不能爬楼梯|不能爬樓梯", text))
    if re.search(r"(?:don't|do not)\s+(?:need|require)\s+(?:a\s+)?step.free|不需要无台阶|不需要無台階", text):
        step_free = False
    low_energy = bool(re.search(r"\btired\b|\bexhausted\b|疲惫|疲憊|很累", text))
    if re.search(r"\bnot\s+(?:tired|exhausted)\b|不累|不疲惫|不疲憊", text):
        low_energy = False
    return {"liked_tags": sorted(likes), "avoided_tags": sorted(avoids),
            "slower_pace": slower, "short_drives": short_drives,
            "requires_vegetarian": vegetarian, "requires_step_free": step_free,
            "low_energy": low_energy}


def completed_place_id(text, metadata):
    """No visit inferred from a suggestion or an ambiguous mention of a place."""
    if not metadata.get("trip_id"):
        return None
    if not re.search(r"\bi (?:completed|visited)\b|我完成了|我去过|我去過", text.casefold()):
        return None
    marker = re.search(r"\bplace_id:\s*([a-z0-9-]+)\b", text)
    return marker.group(1) if marker else None

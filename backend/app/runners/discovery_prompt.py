"""Parse natural-language discovery prompts — credentials, login intent, exploration goals."""

from __future__ import annotations

import re
from dataclasses import dataclass, field


_LOGIN_SKIP = re.compile(
    r"\b(?:no\s+login|without\s+login|skip\s+login|public\s+(?:site|access)|"
    r"no\s+auth(?:entication)?|anonymous|unauthenticated)\b",
    re.I,
)

_LOGIN_HINT = re.compile(
    r"\b(?:login|log\s+in|sign\s+in|signin|authenticate|credentials?|username|password)\b",
    re.I,
)

_BROAD_EXPLORE = re.compile(
    r"\b(?:explore\s+all|all\s+(?:main\s+)?(?:menus?|modules?|pages?|screens?|workflows?)|"
    r"full\s+(?:site|app|application|exploration|scan)|entire\s+(?:app|application|site)|"
    r"discover\s+everything|scan\s+(?:all|the)\s|walk\s+through\s+all|"
    r"comprehensive\s+(?:exploration|discovery)|explore\s+the\s+(?:whole|entire)\s|"
    r"crawl\s+(?:all|the\s+whole|everything)|map\s+(?:all|the\s+entire)\s)\b",
    re.I,
)

_STRICT_HINT = re.compile(
    r"\b(?:only|just|strictly|limited\s+to|focus\s+on|do\s+not\s+explore|don't\s+explore|"
    r"no\s+other|specifically|must\s+follow|follow\s+only|instructions?\s+only)\b",
    re.I,
)

_MULTIPLE_CASES_HINT = re.compile(
    r"\b(?:create\s+(?:all\s+)?(?:possible\s+)?(?:separate\s+)?test\s+cases?|"
    r"generate\s+(?:all\s+)?(?:possible\s+)?test\s+cases?|"
    r"individual\s+test\s+cases?|one\s+test\s+(?:case\s+)?per|"
    r"separate\s+(?:test\s+)?cases?\s+(?:for|per)\s+each|multiple\s+test\s+cases?|"
    r"propose\s+(?:all\s+)?(?:possible\s+)?test\s+cases?)\b",
    re.I,
)

_SINGLE_CASE_HINT = re.compile(
    r"\b(?:one\s+combined\s+test\s+case|single\s+(?:end-to-end\s+)?(?:test\s+)?case|"
    r"one\s+end-to-end|entire\s+(?:automation\s+)?(?:test\s+)?case|"
    r"full\s+(?:automation\s+)?(?:test\s+)?(?:case|flow|journey)|"
    r"as\s+(?:a\s+)?single\s+(?:test\s+)?(?:case|flow)|follow\s+(?:these|the)\s+steps)\b",
    re.I,
)

_STEPS_SECTION_HEADER = re.compile(
    r"^(?:automation\s+)?(?:test\s+)?steps?\s*(?:to\s+(?:reproduce|automate|execute))?\s*:?\s*$|"
    r"^(?:scenario|journey|flow|procedure|test\s+case)\s*(?:steps?)?\s*:?\s*$|"
    r"^(?:steps?\s+to\s+follow|detailed\s+steps|manual\s+steps)\s*:?\s*$",
    re.I,
)

# Multi-flow markers in a single prompt (Flow 1 / Scenario A / Test Case: Checkout)
_FLOW_HEADER = re.compile(
    r"^(?:#{1,3}\s*)?(?:flow|scenario|journey|test\s*case|use\s*case)\s*"
    r"(?:(?:#|no\.?|number)\s*)?"
    r"([A-Za-z0-9][\w\s\-']{0,80})?\s*:?\s*(.*)$",
    re.I,
)

_MULTI_FLOW_HINT = re.compile(
    r"\b(?:multiple\s+flows?|two\s+flows?|several\s+flows?|both\s+flows?|"
    r"multiple\s+scenarios?|separate\s+flows?|flow\s*1\b|scenario\s*1\b|"
    r"test\s+case\s*1\b|create\s+(?:two|multiple|several)\s+(?:flows?|scenarios?))\b",
    re.I,
)

_CRED_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"login\s+(?:as|with)\s+['\"]?([^/\s'\"]+)['\"]?/['\"]?(\S+)['\"]?",
        re.I,
    ),
    re.compile(
        r"sign\s+in\s+as\s+['\"]?([^/\s'\"]+)['\"]?/['\"]?(\S+)['\"]?",
        re.I,
    ),
    re.compile(
        r"sign\s+in\s+with\s+['\"]?([^/\s'\"]+)['\"]?/['\"]?(\S+)['\"]?",
        re.I,
    ),
    re.compile(
        r"(?:username|user(?:\s*name)?|email)\s*[:=]\s*['\"]?(\S+)['\"]?\s*"
        r"(?:and|,|\s+)(?:password|pass(?:word)?|pwd)\s*[:=]\s*['\"]?(\S+)['\"]?",
        re.I,
    ),
    re.compile(r"credentials?\s*[:=]?\s*['\"]?(\S+)['\"]?\s*[/:,]\s*['\"]?(\S+)['\"]?", re.I),
    re.compile(
        r"using\s+['\"]?([^/\s'\"]+)['\"]?/['\"]?(\S+)['\"]?\s+(?:to\s+)?(?:login|log in|sign in)",
        re.I,
    ),
    re.compile(
        r"(?:with|using)\s+(?:user(?:name)?\s+)?['\"]?(\S+)['\"]?\s+and\s+(?:password\s+)?['\"]?(\S+)['\"]?",
        re.I,
    ),
]

_STRIP_CRED_LINES = re.compile(
    r"^\s*(?:login|log in|sign in|credentials?|username|password|user(?:\s*name)?)\s*[:=/].*$",
    re.I | re.M,
)


@dataclass
class FormFieldSpec:
    label: str
    value: str


@dataclass
class PlannedStep:
    """One automation step taken from the user's instructions (authoritative)."""

    order: int
    description: str
    action: str = ""
    element: str | None = None
    url: str | None = None
    field: str | None = None
    value: str | None = None
    expected: str | None = None
    interaction: str | None = None


@dataclass
class PlannedFlow:
    """One named automation flow (supports multiple flows in a single prompt)."""

    name: str
    steps: list[PlannedStep] = field(default_factory=list)
    order: int = 1


_FORM_SUBMIT_HINT = re.compile(
    r"\b(?:submit|send|fill\s+out|complete|fill)\s+(?:an?\s+)?(?:the\s+)?"
    r"(?:enquiry|inquiry|contact(?:\s+us)?|feedback|registration|request)\s*(?:form)?\b|"
    r"\b(?:enquiry|inquiry|contact)\s+form\b",
    re.I,
)

# Skip when parsing generic field lines (login credentials handled separately)
_FORM_FIELD_SKIP = frozenset(
    {
        "login", "log", "password", "pass", "pwd", "username", "user",
        "credential", "credentials", "base url", "base", "url", "prompt",
        "instructions", "instruction", "requirements", "debug", "discovery",
    }
)

_NAV_TARGET_BLOCKLIST = frozenset(
    {
        "debug", "prompt", "test", "flow", "base", "url", "base url", "submit",
        "form", "instructions", "instruction", "agent", "discovery", "strict",
        "enquiry", "inquiry", "product", "demo", "session", "prompt submit",
        "category", "categories", "external links", "external link", "for each",
        "each menu", "the category", "application", "dashboard", "homepage",
        "rules", "expected outcome", "one combined test case", "each step",
    }
)

_NAV_BOILERPLATE = re.compile(
    r"(?i)(?:stay\s+on|do\s+not\s+open|external\s+links?|^for\s+each\b|open\s+the\s+category|"
    r"verify\s+the\s+page|flipkart\.com|\.com\s+only)",
)

_MENU_BLOCK_END = re.compile(
    r"(?i)^(?:for\s+each|stay\s+on|do\s+not|don't|verify\s+the|only\s+|rules\b|"
    r"expected\s+outcome|also\s+verify|create\s+one|one\s+combined|each\s+step|"
    r"close\s+any|skip\s+broken|if\s+a\s+menu|if\s+the\s+menu|return\s+to|"
    r"start\s+from|click\s+the|navigate\s+each)",
)

_MENU_INSTRUCTION_LINE = re.compile(
    r"(?i)\b(?:starting\s+from|navigation\s+journey|end-to-end|homepage|test\s+case|"
    r"in\s+the\s+list\s+above|top\s+navigation|category\s+page|product\s+grid|"
    r"main\s+menu\s+navigation|deep-link|flyout|submenu|checkout|third-party)\b",
)

_NAV_NOISE_SUFFIX = re.compile(
    r"\s+(?:tab|menu|module|section|screen|page|flow|form)\b.*$",
    re.I,
)
_NAV_NOISE_AFTER_AND = re.compile(r"\s+and\s+.*$", re.I)

_MENU_LIST_HEADER = re.compile(
    r"(?i)^(?:navigate\s+(?:to\s+)?(?:each\s+of\s+)?(?:the\s+)?(?:below\s+)?menus?|"
    r"menus?\s+to\s+navigate|open\s+each\s+menu|visit\s+each\s+menu|"
    r"navigate\s+each\s+(?:of\s+)?(?:the\s+)?(?:below\s+)?(?:menu|category|categories))"
    r"\s*:?\s*(.*)$",
)

_MENU_LINE_VERBS = re.compile(
    r"^(?:navigate\s+to|open|go\s+to|visit|click|check|test|verify)\s+",
    re.I,
)

_NUMBERED_STEP = re.compile(r"^\d+\.\s+")


def _looks_like_menu_instruction_line(line: str) -> bool:
    """True when a line is prompt guidance, not a menu label."""
    stripped = line.strip().lstrip("-*• ")
    if not stripped:
        return False
    if _NUMBERED_STEP.match(stripped):
        return True
    if _MENU_BLOCK_END.match(stripped):
        return True
    if _MENU_INSTRUCTION_LINE.search(stripped):
        return True
    # Form field lines (Name: Jane) are not menu labels
    if re.search(r"[A-Za-z][\w\s-]{0,30}\s*[:=]\s*\S+", stripped):
        return False
    if stripped.endswith(":") and len(stripped.split()) <= 4:
        return True
    if len(stripped.split()) > 8:
        return True
    return False


def normalize_nav_target(label: str) -> str:
    """Reduce 'Contact Us tab and view the page' → 'Contact Us'."""
    t = label.strip().strip(".,;")
    t = _NAV_NOISE_AFTER_AND.sub("", t)
    t = _NAV_NOISE_SUFFIX.sub("", t)
    return t.strip() or label.strip()


def _is_prompt_meta_line(line: str) -> bool:
    s = line.strip()
    if re.match(r"^(base\s+url|url|prompt|instructions?|requirements?)\s*[:=]", s, re.I):
        return True
    if re.match(r"^https?://", s, re.I):
        return True
    return False


def sanitize_prompt_text(text: str) -> str:
    """Remove Base URL / Prompt header lines — URL belongs in Discovery Base URL field only."""
    lines: list[str] = []
    for line in text.splitlines():
        if _is_prompt_meta_line(line):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def filter_form_fields(fields: list[FormFieldSpec]) -> list[FormFieldSpec]:
    """Drop meta lines (Base URL, Prompt) and values that look like URLs."""
    out: list[FormFieldSpec] = []
    for field in fields:
        key = field.label.lower().strip()
        val = field.value.strip()
        if key in _FORM_FIELD_SKIP or key in _NAV_TARGET_BLOCKLIST:
            continue
        if val.lower().startswith(("http://", "https://", "www.")):
            continue
        out.append(field)
    return out


@dataclass
class DiscoveryIntent:
    raw: str
    username: str | None = None
    password: str | None = None
    should_login: bool = False
    skip_login: bool = False
    goals: str = ""
    summary: str = ""
    """When True, agent only acts on prompt instructions — no broad site crawl."""
    strict_follow: bool = True
    """When True, user explicitly asked to explore broadly (overrides strict_follow)."""
    broad_exploration: bool = False
    explicit_targets: list[str] = field(default_factory=list)
    menu_list_navigation: bool = False
    """When True, generate separate test cases per target (only when user asks for multiple cases)."""
    split_test_cases: bool = False
    wants_form_submit: bool = False
    form_fields: list[FormFieldSpec] = field(default_factory=list)
    """Authoritative automation steps parsed from the prompt (numbered / Steps: section)."""
    planned_steps: list[PlannedStep] = field(default_factory=list)
    """Multiple labeled flows from one prompt (Flow 1 / Scenario A / …)."""
    planned_flows: list[PlannedFlow] = field(default_factory=list)
    """as_written = use planned_steps as the case; single_journey = one menu/form journey; per_target = split."""
    case_mode: str = "single_journey"


def _clean_token(value: str) -> str:
    return value.strip().strip("\"'`,;")


def _split_menu_tokens(value: str) -> list[str]:
    parts = re.split(r"[,;|]", value)
    return [p.strip() for p in parts if p.strip()]


def _is_nav_boilerplate(label: str) -> bool:
    key = label.strip().lower()
    if not key or key in _NAV_TARGET_BLOCKLIST:
        return True
    if _NAV_BOILERPLATE.search(key):
        return True
    if key.startswith("stay on ") or key.startswith("for each"):
        return True
    return False


def extract_menu_list_targets(text: str) -> list[str]:
    """Parse explicit menu lists, e.g. 'Navigate each menu:' followed by one menu per line."""
    targets: list[str] = []
    seen: set[str] = set()
    in_menu_block = False

    def add(label: str) -> None:
        t = normalize_nav_target(label.strip().strip(".,;"))
        if len(t) < 2 or _is_nav_boilerplate(t):
            return
        key = t.lower()
        if key in seen:
            return
        seen.add(key)
        targets.append(t)

    for line in text.splitlines():
        stripped = line.strip().lstrip("-*• ")
        if not stripped:
            if in_menu_block and targets:
                in_menu_block = False
            continue

        header_match = _MENU_LIST_HEADER.match(stripped)
        if header_match:
            in_menu_block = True
            remainder = header_match.group(1).strip()
            for token in _split_menu_tokens(remainder):
                add(token)
            continue

        if in_menu_block:
            if (
                _looks_like_menu_instruction_line(stripped)
                or _is_prompt_meta_line(stripped)
                or _FORM_SUBMIT_HINT.search(stripped)
            ):
                in_menu_block = False
                continue
            cleaned = _MENU_LINE_VERBS.sub("", stripped).strip().rstrip(".,;")
            if cleaned:
                add(cleaned)
            continue

        inline_match = re.search(
            r"(?i)\b(?:navigate|open|visit)\s+each\s+(?:of\s+)?(?:the\s+)?menus?\s*:\s*(.+)$",
            stripped,
        )
        if inline_match:
            in_menu_block = True
            for token in _split_menu_tokens(inline_match.group(1)):
                add(token)

    return targets


def _extract_menu_list_targets(text: str, add) -> None:
    for target in extract_menu_list_targets(text):
        add(target)


def _is_search_or_product_query(label: str) -> bool:
    """True for product/search phrases that must never be treated as nav menu labels."""
    t = (label or "").strip()
    if not t:
        return True
    lower = t.lower()
    if lower in _NAV_TARGET_BLOCKLIST:
        return True
    # Known product brands / models
    if re.search(
        r"\b(?:iphone|ipad|airpods|macbook|galaxy|pixel|oneplus|nothing phone|"
        r"thinkpad|surface pro)\b",
        lower,
    ):
        return True
    if re.search(r"\b\d+\s?(?:gb|tb|ml|kg|inch)\b", lower):
        return True
    # "iPhone 15", "S24 Ultra" — brand/model token + number, not "2 Wheelers"
    if re.search(r"\b(?:iphone|galaxy|pixel|airpods|pro|max|plus|ultra)\s*\d+", lower):
        return True
    if re.search(r"\b[a-z]{3,}\s+\d{1,4}(?:\s|$)", lower) and re.search(
        r"\b(?:iphone|samsung|apple|google|oneplus|xiaomi|realme|vivo|oppo)\b",
        lower,
    ):
        return True
    return False


def _quoted_value_is_operand(text: str, match_start: int) -> bool:
    """Quoted string is a search/fill value, not a menu name."""
    before = text[max(0, match_start - 48) : match_start]
    return bool(
        re.search(
            r"(?i)(?:search\s+for|search|find|look\s+for|query|type|enter|fill(?:\s+\w+)?\s+with|with)\s*$",
            before.rstrip(),
        )
    )


def extract_explicit_targets(text: str) -> list[str]:
    """Module/page names the user named in their instructions."""
    if not text:
        return []

    menu_list = extract_menu_list_targets(text)
    if menu_list:
        return menu_list

    targets: list[str] = []
    seen: set[str] = set()

    def add(label: str) -> None:
        t = normalize_nav_target(label.strip().strip(".,;"))
        if len(t) < 2 or _is_nav_boilerplate(t):
            return
        if _is_search_or_product_query(t):
            return
        key = t.lower()
        if key in seen:
            return
        if key.startswith("http") or "://" in key:
            return
        seen.add(key)
        targets.append(t)

    for match in re.finditer(r"['\"]([^'\"]{2,60})['\"]", text):
        if _quoted_value_is_operand(text, match.start()):
            continue
        add(match.group(1))

    for line in text.splitlines():
        line = line.strip().lstrip("-*• ")
        if not line:
            continue
        if _is_prompt_meta_line(line):
            continue
        # Never mine menu targets from search/fill lines
        if re.search(r"(?i)\b(?:search\s+for|search|find|look\s+for|add\s+to\s+cart|buy\s+now)\b", line):
            continue
        if re.match(r"^[A-Za-z][\w\s]{0,30}?\s*[:=]\s*.+", line):
            continue
        tab_match = re.search(
            r"\b(?:open|go\s+to|visit|navigate\s+to)\s+(?:the\s+)?"
            r"([A-Za-z][\w\s/&-]+?)\s+tab\b",
            line,
            re.I,
        )
        if tab_match:
            add(normalize_nav_target(tab_match.group(1)))
            continue
        page_match = re.search(
            r"\b(?:open|go\s+to|visit|navigate\s+to)\s+(?:the\s+)?"
            r"([A-Za-z][\w\s/&-]+?)\s+(?:module|menu|page|screen|flow)\b",
            line,
            re.I,
        )
        if page_match:
            add(normalize_nav_target(page_match.group(1)))
            continue
        nav_match = re.search(
            r"\b(?:go\s+to|open|visit|navigate\s+to|check|test|verify)\s+(?:the\s+)?"
            r"([A-Za-z][\w\s/&-]+?)(?:\s+tab)?(?:\s+module|\s+page|\s+screen|\s+flow|\s+form)?"
            r"(?:\s+and\b|\s*$|,|\.)",
            line,
            re.I,
        )
        if nav_match:
            add(normalize_nav_target(nav_match.group(1)))
            continue
        if _FORM_SUBMIT_HINT.search(line):
            continue

    for match in re.finditer(
        r"\b([A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*)*)\s+and\s+([A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*)*)\s+(?:modules?|menus?|pages?)",
        text,
    ):
        add(match.group(1))
        add(match.group(2))

    _NAV_VERBS = frozenset({"open", "go", "visit", "navigate", "check", "test", "verify"})
    for match in re.finditer(
        r"\b([A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*)*)\s+(?:module|menu|page|screen|flow)\b",
        text,
    ):
        label = match.group(1).strip()
        first = label.split()[0].lower() if label else ""
        if first in _NAV_VERBS:
            continue
        add(label)

    return targets


def extract_form_fields(text: str) -> list[FormFieldSpec]:
    """Parse field names and values from the discovery prompt."""
    if not text:
        return []
    fields: list[FormFieldSpec] = []
    seen: set[str] = set()

    def add(label: str, value: str) -> None:
        label = label.strip()
        value = value.strip().strip("\"'`.,;")
        key = label.lower()
        if len(label) < 2 or not value:
            return
        if key in _FORM_FIELD_SKIP:
            return
        if key in seen:
            return
        seen.add(key)
        fields.append(FormFieldSpec(label=label, value=value))

    inline_patterns = [
        re.compile(
            r"(?i)\b([A-Za-z][\w-]{0,25}?)\s*[:=]\s*['\"]?([^,;]+?)['\"]?(?:\s*,|\s+and\s+[A-Za-z]|\s*$)",
        ),
        re.compile(r"(?i)\bfill\s+([a-z][\w\s]{0,25}?)\s+with\s+['\"]?([^'\"]+?)['\"]?(?:\s|,|$)"),
        re.compile(r"(?i)\benter\s+([a-z][\w\s]{0,25}?)\s+['\"]?([^'\"]+?)['\"]?(?:\s|,|$)"),
    ]

    for line in text.splitlines():
        line = line.strip().lstrip("-*• ")
        if not line:
            continue
        if _is_prompt_meta_line(line):
            continue
        # Allow field extraction from numbered fill steps (e.g. "3. Enter Name: Jane")
        body = _NUMBERED_STEP.sub("", line).strip()
        if _looks_like_menu_instruction_line(body) and not re.search(r"[A-Za-z].*[:=]", body):
            continue
        line = body
        match = re.match(r"^([A-Za-z][\w\s-]{0,30}?)\s*[:=]\s*(.+)$", line)
        if match:
            label, value = match.group(1), match.group(2)
            # Reject sentence-like "labels" (inline Name:/Email: belong to patterns below)
            label_words = label.strip().split()
            if (
                len(label_words) <= 4
                and not re.search(r"https?://|//www\.", value, re.I)
                and not re.search(r"\bwith\b", label, re.I)
            ):
                add(label, value)
                continue
        match = re.match(r"^([A-Za-z][\w\s]{0,30}?)\s+['\"]([^'\"]+)['\"]\s*$", line)
        if match:
            add(match.group(1), match.group(2))
            continue
        for pattern in inline_patterns:
            for match in pattern.finditer(line):
                add(match.group(1), match.group(2))

    return fields


_ORDINAL_WORDS = {
    "first": 1,
    "1st": 1,
    "top": 1,
    "second": 2,
    "2nd": 2,
    "third": 3,
    "3rd": 3,
    "fourth": 4,
    "4th": 4,
    "fifth": 5,
    "5th": 5,
}


def _parse_result_index(lower: str) -> int | str:
    """1-based index for 'second phone', or 'random' for random product pick."""
    if re.search(r"\brandom\b", lower):
        return "random"
    m = re.search(r"\b(\d+)(?:st|nd|rd|th)?\b", lower)
    if m:
        n = int(m.group(1))
        if 1 <= n <= 20:
            return n
    for word, idx in _ORDINAL_WORDS.items():
        if re.search(rf"\b{re.escape(word)}\b", lower):
            return idx
    return 1


def _ordinal_label(index: int | str) -> str:
    if index == "random" or str(index).lower() == "random":
        return "random"
    index = int(index)
    special = {1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth"}
    if index in special:
        return special[index]
    if 10 < index % 100 < 14:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(index % 10, "th")
    return f"{index}{suffix}"


def _is_result_selection_step(lower: str) -> bool:
    """True for 'click/select the second phone from search results' (not 'search for X')."""
    has_select = bool(
        re.search(r"\b(?:click|select|choose|tap|pick|open|view)\b", lower)
        or re.search(r"\b(?:first|second|third|fourth|fifth|\d+(?:st|nd|rd|th)|top|random)\b", lower)
    )
    has_item = bool(
        re.search(r"\b(?:phone|product|item|listing|result|mobile|handset)\b", lower)
    )
    has_results_ctx = bool(
        re.search(r"\b(?:search\s+)?results?\b", lower)
        or re.search(r"\bfrom\s+(?:the\s+)?(?:list|listing|grid)\b", lower)
    )
    if has_results_ctx and (has_select or has_item):
        return True
    if has_select and has_item and re.search(
        r"\b(?:first|second|third|fourth|fifth|\d+(?:st|nd|rd|th)|top|random)\b", lower
    ):
        return True
    return False


def _classify_planned_step(order: int, description: str) -> PlannedStep:
    """Infer action/element/url from a free-text automation step description."""
    desc = description.strip()
    lower = desc.lower()
    step = PlannedStep(order=order, description=desc)

    url_match = re.search(r"https?://[^\s)\"']+", desc, re.I)
    if url_match:
        step.url = url_match.group(0).rstrip(".,;")

    quoted = re.search(r"['\"]([^'\"]{1,80})['\"]", desc)
    quoted_val = quoted.group(1).strip() if quoted else None

    if re.search(r"\b(?:dismiss|close)\b.+\b(?:popup|overlay|modal|dialog|cookie)\b", lower) or lower.startswith(
        ("dismiss ", "close popup", "close any popup")
    ):
        step.action = "dismiss"
        step.interaction = "popup"
        return step

    # Assert/verify must run before "home" — "homepage is loaded" is not navigation
    if re.search(r"\b(?:verify|confirm|assert|ensure|check\s+that)\b", lower):
        step.action = "verify"
        step.expected = desc
        return step

    if re.search(
        r"\b(?:return|go)\s+back\s+to\s+(?:the\s+)?home|"
        r"(?:click|via)\s+(?:the\s+)?(?:site\s+)?logo\b|"
        r"\bgo\s+to\s+(?:the\s+)?home(?:\s*page)?\b",
        lower,
    ):
        step.action = "click"
        step.interaction = "home"
        step.element = "Home"
        return step

    # MUST run before search — "search results" used to become Search for "results"
    if _is_result_selection_step(lower):
        idx = _parse_result_index(lower)
        label = _ordinal_label(idx)
        step.action = "click"
        step.interaction = "result"
        step.element = str(idx)
        step.description = (
            "Click a random product in the search results"
            if idx == "random"
            else f"Click the {label} product in the search results"
        )
        return step

    if re.search(
        r"\bremove\b.+\bcart\b|\bdelete\b.+\bcart\b|"
        r"\bdelete\s+(?:the\s+)?(?:1|one|\d+)\s+item\b|"
        r"\bremove\s+(?:the\s+)?(?:1|one|\d+)\s+item\b|"
        r"\bempty\s+(?:the\s+)?cart\b",
        lower,
    ):
        step.action = "click"
        step.interaction = "cart_remove"
        step.element = quoted_val or "Remove"
        step.description = desc if ("remove" in lower or "delete" in lower) else "Remove item from cart"
        return step

    # Quantity / qty change on PDP (must not match "remove … quantity …")
    qty_match = re.search(
        r"\b(?:change|set|update|enter|select)\s+(?:the\s+)?(?:buying\s+)?(?:quantity|qty)\s*(?:to\s*)?(\d+)\b",
        lower,
    ) or re.search(r"\b(?:buying\s+)?(?:quantity|qty)\s+to\s+(\d+)\b", lower) or re.search(
        r"\bquantity\s*[:=]\s*(\d+)\b", lower
    )
    if qty_match:
        n = qty_match.group(1)
        step.action = "fill"
        step.interaction = "quantity"
        step.field = "Quantity"
        step.value = str(n)
        step.element = str(n)
        step.description = f"Change the buying quantity to {n}"
        return step

    if re.search(r"\badd\s+to\s+cart\b|\bbuy\s+now\b|\badd\s+to\s+bag\b", lower):
        step.action = "click"
        step.element = quoted_val or ("Add to cart" if "cart" in lower else "Buy now")
        step.interaction = None
        return step

    if re.search(r"\b(?:go\s+to|open|view|navigate\s+to)\s+(?:the\s+)?cart\b|\bcart\s+page\b", lower):
        step.action = "click"
        step.interaction = "cart"
        step.element = "Cart"
        step.description = "Go to Cart"
        return step

    # Real product search only — never match the phrase "search results"
    if (
        re.search(r"\bsearch\s+for\b", lower)
        or re.search(r"\btype\s+.+\s+in\s+(?:the\s+)?search", lower)
        or (
            re.search(r"\b(?:find|look\s+for)\s+", lower)
            and not re.search(r"\b(?:search\s+)?results?\b", lower)
        )
    ):
        step.action = "search"
        step.interaction = "search"
        value = quoted_val
        if not value:
            m = re.search(r"(?:search\s+for\s+|find\s+|look\s+for\s+)(.+)$", desc, re.I)
            if m:
                value = m.group(1).strip().strip(".,;")
        if value:
            value = re.sub(r"^(?:the\s+)?(?:product\s+)?", "", value, flags=re.I).strip()
            # Guard: never persist mis-parsed "results" as a search query
            if value.lower() in {"results", "result", "search results", "the results"}:
                idx = _parse_result_index(lower) if _is_result_selection_step(lower) else 1
                label = _ordinal_label(idx)
                step.action = "click"
                step.interaction = "result"
                step.element = str(idx)
                step.description = f"Click the {label} product in the search results"
                return step
        step.value = value
        step.field = "Search"
        if value:
            step.description = f'Search for "{value}"'
        return step

    if re.search(r"\b(?:enter|fill|type|input)\b", lower):
        step.action = "fill"
        field_match = re.search(
            r"(?i)\b(?:enter|fill|type|input)\s+(?:the\s+)?(?:value\s+)?(?:for\s+)?"
            r"([A-Za-z][\w\s-]{0,40}?)(?:\s*[:=]\s*|\s+with\s+|\s+as\s+)\s*['\"]?([^'\"]+?)['\"]?\s*$",
            desc,
        )
        if field_match:
            step.field = field_match.group(1).strip()
            step.value = field_match.group(2).strip().strip(".,;")
        elif quoted_val:
            step.value = quoted_val
        return step

    if (
        re.search(r"\b(?:navigate|go\s+to|open|visit|start\s+from|launch)\b", lower)
        or step.url
        or re.search(r"\bhomepage\b|\bhome\s+page\b", lower)
    ):
        # Prefer navigate for entry / URL steps; menu clicks handled below
        if re.search(r"\b(?:click|select)\b.+\b(?:menu|nav|category)\b", lower):
            step.action = "click"
            step.interaction = "menu"
            step.element = quoted_val or _extract_menu_label_from_step(desc)
            return step
        # "Go to cart" already handled; leftover cart phrases
        if re.search(r"\bcart\b", lower) and not step.url:
            step.action = "click"
            step.interaction = "cart"
            step.element = "Cart"
            return step
        step.action = "navigate"
        if not step.url and re.search(r"\b(?:homepage|home\s+page|application|site)\b", lower):
            step.interaction = "home"
        return step

    if re.search(r"\b(?:click|select|tap|press|open)\b", lower):
        step.action = "click"
        if re.search(r"\b(?:menu|nav(?:igation)?|category|mega-?menu)\b", lower):
            step.interaction = "menu"
        step.element = quoted_val or _extract_click_label(desc)
        # Product / search-result clicks are never top-nav menus
        if step.element and _is_search_or_product_query(step.element):
            step.interaction = None
        if step.interaction == "menu" and re.search(r"\b(?:product|result|cart|buy)\b", lower):
            step.interaction = None
        return step

    step.action = "verify" if "should" in lower else "click"
    if quoted_val:
        step.element = quoted_val
        if _is_search_or_product_query(quoted_val):
            # Bare product name in a step → search, not menu click
            step.action = "search"
            step.interaction = "search"
            step.value = quoted_val
            step.field = "Search"
            step.description = f'Search for "{quoted_val}"'
    return step


def _extract_menu_label_from_step(desc: str) -> str | None:
    m = re.search(
        r"(?i)\b(?:menu(?:\s+item)?|category|nav(?:igation)?(?:\s+item)?)\s+"
        r"['\"]?([A-Za-z0-9][\w\s,&'/-]{1,40})['\"]?",
        desc,
    )
    if m:
        return normalize_nav_target(m.group(1))
    m = re.search(r"(?i)\bclick\s+(?:the\s+)?['\"]?([A-Za-z0-9][\w\s,&'/-]{1,40})['\"]?", desc)
    if m:
        return normalize_nav_target(m.group(1))
    return None


def _extract_click_label(desc: str) -> str | None:
    m = re.search(
        r"(?i)\b(?:click|select|tap|press|open)\s+(?:on\s+)?(?:the\s+)?"
        r"(?:button|link|item|option|tab)?\s*['\"]?([A-Za-z0-9][\w\s,&'/-]{1,50})['\"]?",
        desc,
    )
    if m:
        label = m.group(1).strip()
        # Drop trailing filler
        label = re.sub(r"\s+(?:button|link|in\s+the.+)$", "", label, flags=re.I).strip()
        return label or None
    return None


def _looks_like_per_menu_template(step_texts: list[str]) -> bool:
    """True when numbered steps are a short template under 'for each menu', not a full scenario."""
    if not step_texts or len(step_texts) > 6:
        return False
    blob = " ".join(step_texts).lower()
    template_hits = sum(
        1
        for phrase in (
            "for each",
            "menu item",
            "top navigation",
            "do not use direct",
            "category page",
            "the menu",
            "each menu",
        )
        if phrase in blob
    )
    return template_hits >= 2


def _parse_raw_step_lines(raw_steps: list[str]) -> list[PlannedStep]:
    planned: list[PlannedStep] = []
    for i, desc in enumerate(raw_steps, start=1):
        if _is_prompt_meta_line(desc):
            continue
        if re.match(r"(?i)^(?:rules|expected\s+outcome)\b", desc):
            continue
        if len(desc.strip()) < 3:
            continue
        planned.append(_classify_planned_step(i, desc))
    for i, step in enumerate(planned, start=1):
        step.order = i
    return planned


def _extract_raw_steps_from_block(text: str) -> list[str]:
    """Extract numbered/bullet step descriptions from a text block (no flow headers)."""
    if not text or not text.strip():
        return []
    cleaned = sanitize_prompt_text(text)
    lines = cleaned.splitlines()

    section_lines: list[str] = []
    in_section = False
    for line in lines:
        stripped = line.strip()
        if _FLOW_HEADER.match(stripped):
            continue
        if _STEPS_SECTION_HEADER.match(stripped):
            in_section = True
            continue
        if in_section:
            if not stripped:
                if section_lines:
                    break
                continue
            if re.match(r"(?i)^(?:rules|expected\s+outcome|notes|also)\b", stripped):
                break
            if _MENU_LIST_HEADER.match(stripped):
                break
            if _FLOW_HEADER.match(stripped):
                break
            section_lines.append(stripped)

    numbered: list[str] = []
    for line in lines:
        stripped = line.strip().lstrip("-*• ")
        if _FLOW_HEADER.match(stripped) or _STEPS_SECTION_HEADER.match(stripped):
            continue
        m = _NUMBERED_STEP.match(stripped)
        if m:
            numbered.append(_NUMBERED_STEP.sub("", stripped).strip())

    raw_steps = section_lines if len(section_lines) >= 2 else numbered
    if section_lines and len(section_lines) >= 2:
        raw_steps = [
            _NUMBERED_STEP.sub("", s.lstrip("-*• ")).strip()
            for s in section_lines
            if s.strip()
        ]
    return [s for s in raw_steps if len(s) >= 3]


def extract_planned_flows(text: str) -> list[PlannedFlow]:
    """
    Split a prompt into multiple flows when labeled (Flow 1 / Scenario A / Test Case: …).
    Returns [] when the prompt is a single untitled flow (use extract_planned_steps).
    """
    if not text or not text.strip():
        return []

    cleaned = sanitize_prompt_text(text)
    lines = cleaned.splitlines()

    # Collect blocks under flow headers
    blocks: list[tuple[str, list[str]]] = []
    current_name: str | None = None
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_name, current_lines
        if current_name is None:
            current_lines = []
            return
        body = "\n".join(current_lines).strip()
        if body:
            blocks.append((current_name, current_lines[:]))
        current_name = None
        current_lines = []

    for line in lines:
        stripped = line.strip()
        # Steps section headers are not flow markers
        if _STEPS_SECTION_HEADER.match(stripped):
            if current_name is not None:
                current_lines.append(line)
            continue
        m = _FLOW_HEADER.match(stripped)
        if m:
            keyword_line = re.match(
                r"^(?:#{1,3}\s*)?(flow|scenario|journey|test\s*case|use\s*case)\b",
                stripped,
                re.I,
            )
            if not keyword_line:
                if current_name is not None:
                    current_lines.append(line)
                continue
            g1 = (m.group(1) or "").strip(" :=-")
            g2 = (m.group(2) or "").strip(" :=-")
            # "Test case steps" captured as g1=steps — reject; that's a steps header variant
            if g1.lower() in {"steps", "step"} and not g2:
                if current_name is not None:
                    current_lines.append(line)
                continue
            # Require clear flow marker: numbered/lettered, or title after colon, or bare Flow:
            head = stripped.lower()
            is_bare = bool(
                re.match(
                    r"^(?:#{1,3}\s*)?(?:flow|scenario|journey|test\s*case|use\s*case)\s*:?\s*$",
                    stripped,
                    re.I,
                )
            )
            is_numbered = bool(re.search(r"(?:flow|scenario|journey|test\s*case)\s*\d", head))
            has_title = bool(g1 or g2)
            if not (is_bare or is_numbered or (has_title and (":" in stripped or is_numbered))):
                # e.g. free text mentioning "test case" mid-sentence — skip
                if current_name is not None:
                    current_lines.append(line)
                continue
            flush()
            if g1 and g2:
                label = f"{g1} — {g2}"
            else:
                label = g1 or g2 or f"Flow {len(blocks) + 1}"
            if re.match(r"^\d+$", label):
                label = f"Flow {label}"
            elif re.match(r"^\d+\b", label) and not label.lower().startswith("flow"):
                label = f"Flow {label}"
            current_name = label[:100]
            current_lines = []
            continue
        if current_name is not None:
            current_lines.append(line)

    flush()

    # Also detect blank-line separated numbered lists when user asked for multiple flows
    if len(blocks) < 2 and _MULTI_FLOW_HINT.search(cleaned):
        chunks = re.split(r"\n\s*\n+", cleaned)
        multi: list[tuple[str, list[str]]] = []
        for i, chunk in enumerate(chunks):
            raw = _extract_raw_steps_from_block(chunk)
            if len(raw) >= 2:
                multi.append((f"Flow {i + 1}", chunk.splitlines()))
        if len(multi) >= 2:
            blocks = multi

    if len(blocks) < 2:
        return []

    flows: list[PlannedFlow] = []
    for i, (name, block_lines) in enumerate(blocks, start=1):
        body = "\n".join(block_lines)
        raw = _extract_raw_steps_from_block(body)
        # Fallback: treat non-empty non-header lines as steps
        if len(raw) < 2:
            raw = []
            for ln in block_lines:
                s = ln.strip().lstrip("-*• ")
                if not s or _FLOW_HEADER.match(s) or _STEPS_SECTION_HEADER.match(s):
                    continue
                s = _NUMBERED_STEP.sub("", s).strip()
                if len(s) >= 3 and not _is_prompt_meta_line(s):
                    raw.append(s)
        steps = _parse_raw_step_lines(raw)
        if len(steps) < 2:
            continue
        flows.append(PlannedFlow(name=name or f"Flow {i}", steps=steps, order=i))

    return flows if len(flows) >= 2 else []


def extract_planned_steps(text: str) -> list[PlannedStep]:
    """
    Parse authoritative automation steps from the user prompt.
    Prefers an explicit Steps: section, otherwise a contiguous numbered list.
    Skips short 'for each menu' templates when a menu list is already present.
    """
    if not text or not text.strip():
        return []

    cleaned = sanitize_prompt_text(text)
    # Prefer multi-flow when labeled — primary steps = first flow (compat)
    flows = extract_planned_flows(cleaned)
    if flows:
        return list(flows[0].steps)

    raw_steps = _extract_raw_steps_from_block(cleaned)
    if len(raw_steps) < 2:
        return []

    menu_list = extract_menu_list_targets(cleaned)
    if len(menu_list) >= 2 and _looks_like_per_menu_template(raw_steps):
        return []

    return _parse_raw_step_lines(raw_steps)


def navigation_targets(intent: DiscoveryIntent) -> list[str]:
    """Pages/modules the user asked to open — exclude bare form-action phrases."""
    skip_exact = {"enquiry", "inquiry", "form", "submit", "feedback"}
    out: list[str] = []
    seen: set[str] = set()
    # Explicit menu lists (Flipkart categories etc.) are authoritative — do not drop "2 Wheelers"
    skip_product_filter = bool(intent.menu_list_navigation)
    for target in intent.explicit_targets:
        cleaned = normalize_nav_target(target)
        key = cleaned.lower().strip()
        if key in skip_exact:
            continue
        if key.endswith(" form") or key.startswith("submit "):
            continue
        if not skip_product_filter and _is_search_or_product_query(cleaned):
            continue
        if key in seen:
            continue
        seen.add(key)
        out.append(cleaned)
    return out


def has_actionable_instructions(intent: DiscoveryIntent) -> bool:
    return bool(
        intent.planned_steps
        or intent.planned_flows
        or intent.form_fields
        or intent.wants_form_submit
        or navigation_targets(intent)
        or intent.should_login
    )


def parse_discovery_prompt(text: str | None) -> DiscoveryIntent:
    raw = (text or "").strip()
    cleaned = sanitize_prompt_text(raw)
    intent = DiscoveryIntent(raw=raw, goals=cleaned or raw)

    if not raw:
        intent.summary = "provide instructions in the Discovery prompt"
        intent.strict_follow = True
        intent.broad_exploration = False
        return intent

    intent.skip_login = bool(_LOGIN_SKIP.search(raw))
    intent.should_login = bool(_LOGIN_HINT.search(raw)) and not intent.skip_login
    intent.broad_exploration = bool(_BROAD_EXPLORE.search(raw))
    # Split into many tiny cases ONLY when the user explicitly asks — never just because "explore all"
    intent.split_test_cases = bool(_MULTIPLE_CASES_HINT.search(raw)) and not bool(_SINGLE_CASE_HINT.search(raw))
    menu_list = extract_menu_list_targets(cleaned or raw)
    intent.menu_list_navigation = len(menu_list) >= 2
    intent.explicit_targets = menu_list if menu_list else extract_explicit_targets(cleaned or raw)
    intent.form_fields = filter_form_fields(extract_form_fields(cleaned or raw))
    intent.wants_form_submit = bool(_FORM_SUBMIT_HINT.search(raw)) or (
        len(intent.form_fields) >= 1
        and bool(re.search(r"\b(?:submit|send|form|enquiry|inquiry|contact)\b", raw, re.I))
    ) or len(intent.form_fields) >= 2
    intent.planned_steps = extract_planned_steps(cleaned or raw)
    intent.planned_flows = extract_planned_flows(cleaned or raw)
    if intent.planned_flows:
        # Keep planned_steps as first flow for backward-compatible callers
        intent.planned_steps = list(intent.planned_flows[0].steps)

    if intent.menu_list_navigation and not intent.planned_steps:
        intent.wants_form_submit = False
        intent.form_fields = []

    # Case mode: planned steps win; otherwise one combined journey unless user asked to split
    if intent.planned_steps or intent.planned_flows:
        intent.case_mode = "as_written"
        intent.strict_follow = True
        intent.broad_exploration = False
        # Multi-flow prompts produce multiple cases; never invent extra cases beyond labeled flows
        intent.split_test_cases = len(intent.planned_flows) >= 2
    elif intent.split_test_cases:
        intent.case_mode = "per_target"
    else:
        intent.case_mode = "single_journey"
        # Default to one full journey for menu lists / form flows
        if intent.menu_list_navigation or intent.wants_form_submit or intent.form_fields:
            intent.split_test_cases = False

    cred_span: tuple[int, int] | None = None
    for pattern in _CRED_PATTERNS:
        match = pattern.search(raw)
        if match:
            intent.username = _clean_token(match.group(1))
            intent.password = _clean_token(match.group(2))
            if "/" in intent.username and not intent.password:
                user_part, pass_part = intent.username.split("/", 1)
                intent.username = _clean_token(user_part)
                intent.password = _clean_token(pass_part)
            intent.should_login = True
            cred_span = match.span()
            break

    goals = cleaned or raw
    if cred_span and cred_span[0] < len(raw):
        stripped = (raw[: cred_span[0]] + raw[cred_span[1] :]).strip(" ,.-")
        goals = sanitize_prompt_text(stripped) or goals
    goals = sanitize_prompt_text(_STRICT_HINT.sub("", goals))
    goals = _STRIP_CRED_LINES.sub("", goals)
    goals = re.sub(r"^\s*(?:and|then)\s+", "", goals, flags=re.I)
    goals = re.sub(r"\s+", " ", goals).strip()
    intent.goals = goals or ""

    if intent.case_mode != "as_written":
        intent.strict_follow = not intent.broad_exploration
        if _STRICT_HINT.search(raw) or _SINGLE_CASE_HINT.search(raw):
            intent.strict_follow = True
            intent.broad_exploration = False

    if intent.skip_login:
        if intent.goals:
            intent.summary = f"public access — {intent.goals[:100]}"
        else:
            intent.summary = "public access — follow prompt instructions only"
    elif intent.username and intent.should_login:
        goal_hint = intent.goals[:80].rstrip(" ,.-") if intent.goals else ""
        if goal_hint:
            intent.summary = f"login as {intent.username}, then {goal_hint.lower()}"
        else:
            intent.summary = f"login as {intent.username} only (no extra exploration)"
    elif intent.should_login:
        intent.summary = "login required — add credentials in prompt (e.g. login as user/pass)"
    elif intent.planned_flows and len(intent.planned_flows) >= 2:
        intent.summary = (
            f"as-written multi-flow — {len(intent.planned_flows)} flows, "
            f"{sum(len(f.steps) for f in intent.planned_flows)} steps from prompt"
        )
    elif intent.planned_steps:
        intent.summary = f"as-written automation — {len(intent.planned_steps)} steps from prompt"
    elif intent.wants_form_submit and intent.form_fields:
        names = ", ".join(f.label for f in intent.form_fields[:4])
        intent.summary = f"submit form — fields: {names}"
    elif intent.goals:
        intent.summary = intent.goals[:120]
    else:
        intent.summary = "follow Discovery prompt instructions only"

    if intent.broad_exploration and intent.case_mode != "as_written":
        intent.summary = f"broad exploration — {intent.summary}" if intent.goals else "broad exploration of the application"
    elif intent.strict_follow and intent.explicit_targets and intent.case_mode != "as_written":
        names = ", ".join(intent.explicit_targets[:4])
        intent.summary = f"strict — {intent.summary} (targets: {names})"
    elif intent.case_mode == "as_written":
        if intent.planned_flows and len(intent.planned_flows) >= 2:
            intent.summary = (
                f"strict as-written — {len(intent.planned_flows)} flows "
                f"({sum(len(f.steps) for f in intent.planned_flows)} steps)"
            )
        else:
            intent.summary = f"strict as-written — {len(intent.planned_steps)} automation steps"

    return intent


def resolve_discovery_auth(
    requirements: str | None,
    username: str | None = None,
    password: str | None = None,
) -> tuple[str | None, str | None, DiscoveryIntent]:
    """Merge explicit API credentials (legacy) with prompt-parsed credentials."""
    intent = parse_discovery_prompt(requirements)
    user = (username or intent.username or "").strip() or None
    pwd = (password or intent.password or "").strip() or None
    if intent.skip_login:
        return None, None, intent
    return user, pwd, intent

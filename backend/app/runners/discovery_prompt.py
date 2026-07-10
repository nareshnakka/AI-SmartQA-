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
    }
)

_NAV_BOILERPLATE = re.compile(
    r"(?i)(?:stay\s+on|do\s+not\s+open|external\s+links?|^for\s+each\b|open\s+the\s+category|"
    r"verify\s+the\s+page|flipkart\.com|\.com\s+only)",
)

_MENU_BLOCK_END = re.compile(
    r"(?i)^(?:for\s+each|stay\s+on|do\s+not|don't|verify\s+the|only\s+)",
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
    """When True, generate separate test cases per target (broad exploration or explicit request)."""
    split_test_cases: bool = False
    wants_form_submit: bool = False
    form_fields: list[FormFieldSpec] = field(default_factory=list)


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
                _NUMBERED_STEP.match(stripped)
                or _is_prompt_meta_line(stripped)
                or _MENU_BLOCK_END.match(stripped)
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
        key = t.lower()
        if key in seen:
            return
        if key.startswith("http") or "://" in key:
            return
        seen.add(key)
        targets.append(t)

    for match in re.finditer(r"['\"]([^'\"]{2,60})['\"]", text):
        add(match.group(1))

    for line in text.splitlines():
        line = line.strip().lstrip("-*• ")
        if not line:
            continue
        if _is_prompt_meta_line(line):
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
        match = re.match(r"^([A-Za-z][\w\s-]{0,30}?)\s*[:=]\s*(.+)$", line)
        if match:
            add(match.group(1), match.group(2))
            continue
        match = re.match(r"^([A-Za-z][\w\s]{0,30}?)\s+['\"]([^'\"]+)['\"]\s*$", line)
        if match:
            add(match.group(1), match.group(2))
            continue
        for pattern in inline_patterns:
            for match in pattern.finditer(line):
                add(match.group(1), match.group(2))

    return fields


def navigation_targets(intent: DiscoveryIntent) -> list[str]:
    """Pages/modules the user asked to open — exclude bare form-action phrases."""
    skip_exact = {"enquiry", "inquiry", "form", "submit", "feedback"}
    out: list[str] = []
    seen: set[str] = set()
    for target in intent.explicit_targets:
        cleaned = normalize_nav_target(target)
        key = cleaned.lower().strip()
        if key in skip_exact:
            continue
        if key.endswith(" form") or key.startswith("submit "):
            continue
        if key in seen:
            continue
        seen.add(key)
        out.append(cleaned)
    return out


def has_actionable_instructions(intent: DiscoveryIntent) -> bool:
    return bool(
        intent.form_fields
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
    intent.split_test_cases = bool(_MULTIPLE_CASES_HINT.search(raw)) or intent.broad_exploration
    menu_list = extract_menu_list_targets(cleaned or raw)
    intent.menu_list_navigation = len(menu_list) >= 2
    intent.explicit_targets = menu_list if menu_list else extract_explicit_targets(cleaned or raw)
    intent.form_fields = filter_form_fields(extract_form_fields(cleaned or raw))
    intent.wants_form_submit = bool(_FORM_SUBMIT_HINT.search(raw)) or (
        len(intent.form_fields) >= 1
        and bool(re.search(r"\b(?:submit|send|form|enquiry|inquiry|contact)\b", raw, re.I))
    ) or len(intent.form_fields) >= 2

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

    intent.strict_follow = not intent.broad_exploration
    if _STRICT_HINT.search(raw):
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
    elif intent.wants_form_submit and intent.form_fields:
        names = ", ".join(f.label for f in intent.form_fields[:4])
        intent.summary = f"submit form — fields: {names}"
    elif intent.goals:
        intent.summary = intent.goals[:120]
    else:
        intent.summary = "follow Discovery prompt instructions only"

    if intent.broad_exploration:
        intent.summary = f"broad exploration — {intent.summary}" if intent.goals else "broad exploration of the application"
    elif intent.strict_follow and intent.explicit_targets:
        names = ", ".join(intent.explicit_targets[:4])
        intent.summary = f"strict — {intent.summary} (targets: {names})"

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

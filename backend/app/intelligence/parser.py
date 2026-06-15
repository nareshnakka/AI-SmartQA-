"""Requirement parser — extracts structured requirements from raw text."""

import re
from dataclasses import dataclass, field


@dataclass
class ParsedRequirement:
    id: str
    title: str
    description: str
    acceptance_criteria: list[str] = field(default_factory=list)
    actor: str | None = None
    action: str | None = None
    benefit: str | None = None
    priority: str = "medium"
    keywords: list[str] = field(default_factory=list)


class RequirementParser:
    """Parses BRD, FRD, user stories, and acceptance criteria into structured requirements."""

    USER_STORY_PATTERN = re.compile(
        r"as\s+(?:a|an)\s+(.+?),?\s+i\s+(?:want|need)\s+(?:to\s+)?(.+?),?\s+so\s+(?:that\s+)?(.+)",
        re.IGNORECASE,
    )
    REQ_ID_PATTERN = re.compile(r"(?:REQ|US|AC|FR|BRD|TC)[-\s]?(\d+)", re.IGNORECASE)
    GIVEN_WHEN_THEN = re.compile(
        r"Given\s+(.+?)(?:\s+When\s+(.+?))?(?:\s+Then\s+(.+?))?(?:\s*$|\s+And\s+)",
        re.IGNORECASE | re.DOTALL,
    )
    BULLET_PATTERN = re.compile(r"^[\s]*[-*•]\s+(.+)$", re.MULTILINE)
    NUMBERED_PATTERN = re.compile(r"^[\s]*\d+[.)]\s+(.+)$", re.MULTILINE)

    def parse(self, content: str, source_type: str = "requirements") -> list[ParsedRequirement]:
        content = content.strip()
        if not content:
            return []

        requirements: list[ParsedRequirement] = []

        # Try user story format first
        stories = self._extract_user_stories(content)
        if stories:
            requirements.extend(stories)

        # Extract BDD scenarios
        bdd = self._extract_bdd_scenarios(content)
        if bdd:
            requirements.extend(bdd)

        # Extract numbered/bulleted requirements
        structured = self._extract_structured_items(content)
        if structured and not requirements:
            requirements.extend(structured)

        # Fallback: treat paragraphs as requirements
        if not requirements:
            requirements = self._extract_paragraphs(content)

        # Enrich with keywords and priority
        for req in requirements:
            req.keywords = self._extract_keywords(req.description + " " + req.title)
            req.priority = self._infer_priority(req)

        return requirements

    def _extract_user_stories(self, content: str) -> list[ParsedRequirement]:
        results = []
        for i, match in enumerate(self.USER_STORY_PATTERN.finditer(content)):
            actor, action, benefit = match.groups()
            req_id = self._find_nearby_id(content, match.start()) or f"US-{i + 1:03d}"
            results.append(ParsedRequirement(
                id=req_id,
                title=f"As {actor.strip()}, I want {action.strip()[:60]}",
                description=match.group(0).strip(),
                actor=actor.strip(),
                action=action.strip(),
                benefit=benefit.strip(),
                acceptance_criteria=self._find_acceptance_criteria(content, match.end()),
            ))
        return results

    def _extract_bdd_scenarios(self, content: str) -> list[ParsedRequirement]:
        results = []
        scenarios = re.split(r"(?:Scenario|SCENARIO)\s*[:#]?\s*", content)
        for i, scenario in enumerate(scenarios[1:], 1):
            match = self.GIVEN_WHEN_THEN.search(scenario)
            if match:
                given, when, then = match.groups()
                ac = []
                if given:
                    ac.append(f"Given {given.strip()}")
                if when:
                    ac.append(f"When {when.strip()}")
                if then:
                    ac.append(f"Then {then.strip()}")
                results.append(ParsedRequirement(
                    id=f"SC-{i:03d}",
                    title=f"Scenario {i}: {given.strip()[:50] if given else 'BDD Scenario'}",
                    description=scenario.strip()[:500],
                    acceptance_criteria=ac,
                ))
        return results

    def _extract_structured_items(self, content: str) -> list[ParsedRequirement]:
        results = []
        lines = content.split("\n")
        current_id = None
        current_title = ""
        current_ac: list[str] = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            id_match = self.REQ_ID_PATTERN.search(line)
            if id_match:
                if current_title:
                    results.append(ParsedRequirement(
                        id=current_id or f"REQ-{len(results) + 1:03d}",
                        title=current_title,
                        description=current_title,
                        acceptance_criteria=current_ac,
                    ))
                current_id = id_match.group(0).upper().replace(" ", "-")
                current_title = re.sub(self.REQ_ID_PATTERN, "", line).strip(" :-")
                current_ac = []
            elif line.lower().startswith("acceptance criteria"):
                continue
            elif self.BULLET_PATTERN.match(line) or self.NUMBERED_PATTERN.match(line):
                bullet = self.BULLET_PATTERN.match(line) or self.NUMBERED_PATTERN.match(line)
                if bullet:
                    current_ac.append(bullet.group(1).strip())
            elif not current_title:
                current_title = line

        if current_title:
            results.append(ParsedRequirement(
                id=current_id or f"REQ-{len(results) + 1:03d}",
                title=current_title,
                description=current_title,
                acceptance_criteria=current_ac,
            ))

        return results

    def _extract_paragraphs(self, content: str) -> list[ParsedRequirement]:
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", content) if p.strip()]
        return [
            ParsedRequirement(
                id=f"REQ-{i + 1:03d}",
                title=p[:80] + ("..." if len(p) > 80 else ""),
                description=p,
            )
            for i, p in enumerate(paragraphs)
        ]

    def _find_nearby_id(self, content: str, position: int) -> str | None:
        search_window = content[max(0, position - 100):position + 50]
        match = self.REQ_ID_PATTERN.search(search_window)
        return match.group(0).upper().replace(" ", "-") if match else None

    def _find_acceptance_criteria(self, content: str, after_pos: int) -> list[str]:
        section = content[after_pos:after_pos + 500]
        criteria = []
        for match in self.BULLET_PATTERN.finditer(section):
            criteria.append(match.group(1).strip())
            if len(criteria) >= 5:
                break
        return criteria

    def _extract_keywords(self, text: str) -> list[str]:
        text_lower = text.lower()
        keywords = set()
        word_patterns = [
            "login", "logout", "register", "payment", "checkout", "search", "filter",
            "create", "update", "delete", "upload", "download", "api", "report",
            "dashboard", "notification", "email", "password", "role", "permission",
            "cart", "order", "invoice", "export", "import", "validate", "submit",
        ]
        for word in word_patterns:
            if word in text_lower:
                keywords.add(word)
        return sorted(keywords)

    def _infer_priority(self, req: ParsedRequirement) -> str:
        text = (req.title + " " + req.description).lower()
        from app.intelligence.knowledge_base import HIGH_RISK_KEYWORDS
        if any(kw in text for kw in HIGH_RISK_KEYWORDS):
            return "high"
        if any(kw in text for kw in ["should", "must", "shall", "required", "critical"]):
            return "high"
        if any(kw in text for kw in ["optional", "nice to have", "could", "may"]):
            return "low"
        return "medium"

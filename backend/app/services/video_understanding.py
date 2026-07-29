"""Build automation test cases from screen recordings or screenshot sequences."""

from __future__ import annotations

import base64
import json
import logging
import re
import shutil
import subprocess
import uuid
from pathlib import Path

from app.config import settings
from app.services.test_steps import steps_for_storage

try:
    import structlog

    logger = structlog.get_logger()
except ImportError:
    logger = logging.getLogger(__name__)

_VIDEO_EXT = {".webm", ".mp4", ".mov", ".mkv", ".avi"}
_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
_MAX_FRAMES = 12
_MAX_UPLOAD_MB = 80

_VISION_SYSTEM = """You are a senior QA automation engineer.
You watch ordered screenshots (or video keyframes) of a user testing a web app.
Infer ONE complete end-to-end browser test that replays what the user did.

Rules:
- Prefer Search for product queries — never treat product names as top-nav menu items.
- Selecting the 2nd/3rd result must be a click on that search result, not another search.
- Include dismiss-popup steps when login/location/cookie overlays appear.
- Use concrete UI labels (Add to cart, Cart, Remove) when visible.
- Order steps chronologically to match the frames.
- Return ONLY valid JSON (no markdown) with this shape:
{
  "title": "short title",
  "steps": [
    {"order": 1, "action": "navigate|dismiss|search|click|fill|verify", "description": "...", "url": "optional", "element": "optional", "field": "optional", "interaction": "optional popup|search|result|cart|cart_remove|menu|home", "expected": "optional"}
  ],
  "expected_results": ["..."]
}
"""


def _find_ffmpeg() -> str | None:
    found = shutil.which("ffmpeg")
    if found:
        return found
    for candidate in (
        Path("C:/ffmpeg/bin/ffmpeg.exe"),
        Path("C:/Program Files/ffmpeg/bin/ffmpeg.exe"),
        Path.home() / "ffmpeg" / "bin" / "ffmpeg.exe",
    ):
        if candidate.is_file():
            return str(candidate)
    return None


def extract_video_frames(video_path: Path, max_frames: int = _MAX_FRAMES) -> list[Path]:
    """Sample evenly spaced JPEG frames via ffmpeg. Raises ValueError if ffmpeg missing."""
    ffmpeg = _find_ffmpeg()
    if not ffmpeg:
        raise ValueError(
            "ffmpeg is required to read video files. Install ffmpeg and restart, "
            "or upload screenshots (PNG/JPEG) of the flow instead."
        )

    out_dir = video_path.parent / f"{video_path.stem}_frames"
    out_dir.mkdir(parents=True, exist_ok=True)
    # ~1 frame every few seconds; fps filter keeps count near max_frames for short clips
    pattern = str(out_dir / "frame_%03d.jpg")
    # Use fps so short clips still get multiple frames
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(video_path),
        "-vf",
        f"fps=1/{max(1, 3)},scale=1280:-2",
        "-frames:v",
        str(max_frames),
        pattern,
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=120)
    except subprocess.CalledProcessError as exc:
        err = (exc.stderr or b"").decode("utf-8", errors="replace")[:400]
        raise ValueError(f"ffmpeg failed to extract frames: {err or exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise ValueError("ffmpeg timed out while extracting frames") from exc

    frames = sorted(out_dir.glob("frame_*.jpg"))
    if not frames:
        raise ValueError("No frames could be extracted from the video")
    return frames[:max_frames]


def _mime_for(path: Path) -> str:
    ext = path.suffix.lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(ext, "image/jpeg")


def frames_to_llm_images(frame_paths: list[Path], *, max_frames: int = _MAX_FRAMES):
    from app.llm.base import LLMImage

    images = []
    for path in frame_paths[:max_frames]:
        data = path.read_bytes()
        if len(data) > 4_000_000:
            continue
        images.append(
            LLMImage(
                data_base64=base64.b64encode(data).decode("ascii"),
                mime_type=_mime_for(path),
                detail="low",
            )
        )
    return images


def _parse_case_json(raw: str) -> dict:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            raise ValueError("Vision model did not return JSON test steps")
        data = json.loads(m.group(0))

    if "test_cases" in data and isinstance(data["test_cases"], list) and data["test_cases"]:
        data = data["test_cases"][0]
    if not isinstance(data, dict):
        raise ValueError("Unexpected vision response shape")
    steps = data.get("steps") or []
    if not steps:
        raise ValueError("Vision response had no steps")
    return data


def _planned_to_stored(planned, base_url: str) -> list[dict]:
    raw: list[dict] = []
    for s in planned:
        row: dict = {
            "order": s.order,
            "action": s.action,
            "description": s.description,
        }
        if s.url:
            row["url"] = s.url
        elif s.action == "navigate" and base_url:
            row["url"] = base_url
        if s.element:
            row["element"] = s.element
        if s.field:
            row["field"] = s.field
        if s.interaction:
            row["interaction"] = s.interaction
        if s.expected:
            row["expected"] = s.expected
        raw.append(row)
    steps = steps_for_storage(raw)
    if base_url and steps and (steps[0].get("action") or "").lower() != "navigate":
        steps = steps_for_storage([
            {"order": 1, "action": "navigate", "description": f"Navigate to {base_url}", "url": base_url},
            *steps,
        ])
    return steps


def _case_from_notes_only(notes: str, base_url: str) -> dict:
    from app.runners.discovery_prompt import extract_planned_steps, parse_discovery_prompt

    intent = parse_discovery_prompt(notes)
    planned = list(intent.planned_steps or [])
    if len(planned) >= 2:
        return {
            "id": str(uuid.uuid4()),
            "title": "Automation — from recording notes",
            "type": "e2e",
            "priority": "high",
            "source": "video_notes",
            "risk": "high",
            "module": "Automation",
            "screen": "from_video",
            "flow_kind": "as_written",
            "steps": _planned_to_stored(planned, base_url),
            "expected_results": ["Flow from recording notes completes successfully"],
        }

    steps = extract_planned_steps(notes)
    if len(steps) >= 2:
        stored = _planned_to_stored(steps, base_url)
    else:
        lines = [ln.strip().lstrip("-*• ") for ln in notes.splitlines() if ln.strip()]
        lines = [re.sub(r"^\d+[\.\)]\s*", "", ln) for ln in lines]
        lines = [ln for ln in lines if len(ln) >= 3]
        if len(lines) < 2:
            raise ValueError(
                "Could not parse automation steps from notes. "
                "Add numbered steps, or upload screenshots/video with OpenAI/Gemini configured."
            )
        stored = steps_for_storage([{"order": i + 1, "description": ln} for i, ln in enumerate(lines)])

    return {
        "id": str(uuid.uuid4()),
        "title": "Automation — from recording notes",
        "type": "e2e",
        "priority": "high",
        "source": "video_notes",
        "risk": "high",
        "module": "Automation",
        "screen": "from_video",
        "flow_kind": "as_written",
        "steps": stored,
        "expected_results": ["Flow from recording notes completes successfully"],
    }


def _pick_vision_provider(requested: str | None) -> tuple[str, str]:
    from app.llm.router import get_llm_router

    router = get_llm_router()
    providers = {p["name"]: p for p in router.list_providers()}

    order: list[str] = []
    if requested and requested not in ("qeos-native", "qeos-hybrid", "ollama"):
        order.append(requested)
    order.extend(["openai", "gemini", "anthropic"])

    for name in order:
        info = providers.get(name)
        if not info or not info.get("available"):
            continue
        try:
            llm = router.get_provider(name)
        except Exception:
            continue
        if getattr(llm, "supports_vision", lambda: False)():
            if name == "openai":
                model = "gpt-4o"
            elif name == "gemini":
                model = "gemini-2.0-flash"
            else:
                model = (info["models"][0] if info.get("models") else settings.default_llm_model)
            return name, model or settings.default_llm_model

    raise ValueError(
        "No vision-capable LLM is configured. Set OPENAI_API_KEY (gpt-4o) or GOOGLE_API_KEY (Gemini) "
        "in .env, or paste numbered Automation steps in Notes and analyze without frames."
    )


async def understand_recording(
    *,
    frame_paths: list[Path] | None = None,
    notes: str = "",
    base_url: str = "",
    llm_provider: str | None = None,
) -> dict:
    """
    Build one proposed test case from screenshots/video frames (+ optional notes).
    Returns a Discovery-compatible proposed_test_case dict.
    """
    notes = (notes or "").strip()
    frames = list(frame_paths or [])

    if not frames and notes:
        return _case_from_notes_only(notes, base_url)

    if not frames:
        raise ValueError("Upload a video or screenshots (or provide numbered Notes).")

    images = frames_to_llm_images(frames)
    if not images:
        raise ValueError("Could not read any frame images")

    try:
        provider_name, model = _pick_vision_provider(llm_provider)
    except ValueError:
        if notes:
            logger.warning("vision_unavailable_falling_back_to_notes")
            return _case_from_notes_only(notes, base_url)
        raise

    from app.llm.base import LLMMessage, MessageRole
    from app.llm.router import get_llm_router

    user_text = (
        f"Base URL / app under test: {base_url or '(infer from frames)'}\n"
        f"Frames are in chronological order ({len(images)} images).\n"
    )
    if notes:
        user_text += f"\nTester notes / intended steps:\n{notes}\n"
    user_text += "\nInfer the automation steps that match what is shown."

    router = get_llm_router()
    resp = await router.complete(
        [
            LLMMessage(role=MessageRole.SYSTEM, content=_VISION_SYSTEM),
            LLMMessage(role=MessageRole.USER, content=user_text, images=images),
        ],
        provider=provider_name,
        model=model,
        temperature=0.2,
        max_tokens=2500,
    )

    parsed = _parse_case_json(resp.content)
    title = (parsed.get("title") or "Automation — from video").strip()[:120]
    steps = steps_for_storage(parsed.get("steps") or [])
    expected = parsed.get("expected_results") or ["Recording flow completes successfully"]
    if not isinstance(expected, list):
        expected = [str(expected)]

    # Ensure navigate entry when base_url known and first step isn't navigate
    if base_url and steps and (steps[0].get("action") or "").lower() != "navigate":
        steps = [
            {
                "order": 1,
                "action": "navigate",
                "description": f"Navigate to {base_url}",
                "url": base_url,
                "expected": "Application loads without errors",
            },
            *steps,
        ]
        steps = steps_for_storage(steps)

    return {
        "id": str(uuid.uuid4()),
        "title": title if title.lower().startswith("automation") else f"Automation — {title}",
        "type": "e2e",
        "priority": "high",
        "source": "video_understanding",
        "risk": "high",
        "module": "Automation",
        "screen": "from_video",
        "flow_kind": "as_written",
        "steps": steps,
        "expected_results": expected[:12],
        "vision_provider": provider_name,
        "vision_model": model,
        "frames_used": len(images),
    }


async def save_uploads_and_understand(
    *,
    files: list[tuple[str, bytes]],
    notes: str = "",
    base_url: str = "",
    llm_provider: str | None = None,
) -> dict:
    """
    Persist uploads under execution_artifacts/video_ingest, extract frames, run understanding.
    files: list of (filename, raw_bytes)
    """
    if not files and not (notes or "").strip():
        raise ValueError("Provide a video, screenshots, and/or notes")

    root = Path(settings.execution_artifacts_dir) / "video_ingest" / str(uuid.uuid4())
    root.mkdir(parents=True, exist_ok=True)

    frame_paths: list[Path] = []
    video_saved: Path | None = None

    for name, data in files:
        if not data:
            continue
        if len(data) > _MAX_UPLOAD_MB * 1024 * 1024:
            raise ValueError(f"{name} exceeds {_MAX_UPLOAD_MB} MB limit")
        safe = re.sub(r"[^\w.\-]+", "_", Path(name).name)[:80] or "upload.bin"
        dest = root / safe
        dest.write_bytes(data)
        ext = dest.suffix.lower()
        if ext in _IMAGE_EXT:
            frame_paths.append(dest)
        elif ext in _VIDEO_EXT:
            video_saved = dest
        else:
            raise ValueError(f"Unsupported file type: {ext or name}")

    if video_saved:
        extracted = extract_video_frames(video_saved, max_frames=_MAX_FRAMES)
        frame_paths = extracted + frame_paths

    # Keep chronological: videos first (extracted), then uploaded screenshots in order
    case = await understand_recording(
        frame_paths=frame_paths,
        notes=notes,
        base_url=base_url,
        llm_provider=llm_provider,
    )
    case["artifact_dir"] = str(root)
    return case

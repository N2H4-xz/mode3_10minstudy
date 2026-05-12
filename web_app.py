from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal
import openai
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import config as cfg
from analyzer import analyze_chat_log
from models import Characteristic, RawStats, StyleProfile
from prompt_builder import build_template_mimicry_prompt


ROOT = Path(__file__).parent
STATIC_DIR = ROOT / "static"
SESSION_OUTPUT_DIR = ROOT / "transcripts" / "web_sessions"
USER_DATA_DIR = ROOT / "transcripts" / "users"
DEFAULT_USER_ID = "local_user"

COLLECTION_TARGET_CHARS = 400
COLLECTION_SOFT_TURNS = 15
COLLECTION_SOFT_CHARS = 200

INITIAL_COLLECTION_QUESTION = "最近有哪些值得分享的事？"
COLLECTION_PRESET_TOPIC_QUESTIONS = [
    INITIAL_COLLECTION_QUESTION,
    "五一怎么过的？",
    "平时喜欢吃什么？",
    "你觉得身边哪一个人最有特点或者最有趣？",
]

COLLECTION_CHAT_SYSTEM = """\
你正在以好朋友的视角和用户自然聊天，目标是收集用户的真实说话语料，用于之后分析其语言风格。

要求：
1. 像真实生活里的朋友聊天一样回应用户，不要像问卷调查，不要端着。
2. 每次只回复一个自然追问，或一句简短回应加一个追问。
3. 一个问题相关的话题可以适度连问 1-2 次，但不要过度深入、审问式追问或连续挖隐私。
4. 优先根据用户上一轮回答继续聊，鼓励用户自然多说一点细节、感受、原因、处理过程或看法。
5. 当确实需要换话题时，优先围绕这些生活话题：五一怎么过的、平时喜欢吃什么、身边哪一个人最有特点或者最有趣。
6. 不要解释你在收集语料，不要提语言风格分析，不要输出编号列表。
7. 回复不超过 80 字。
"""


class CollectRequest(BaseModel):
    session_id: str
    message: str = Field(min_length=1)
    collection_identity: str | None = None


class GuidanceRequest(BaseModel):
    session_id: str
    action: Literal["switch_topic", "continue_topic"]


class SessionRequest(BaseModel):
    session_id: str


class NewSessionRequest(BaseModel):
    user_id: str = DEFAULT_USER_ID
    force_collect: bool = False


class UserRequest(BaseModel):
    user_id: str = Field(min_length=1)


class ImportStyleRequest(BaseModel):
    user_id: str = Field(min_length=1)
    profile: dict
    profile_name: str = "导入风格"
    session_id: str | None = None


class ManualStyleForm(BaseModel):
    identity: str = ""
    school_status: str = ""
    situation: str = ""
    goal: str = ""
    language_style: str = ""
    constraints: str = ""
    opening: str = ""


class ManualStyleSaveRequest(BaseModel):
    session_id: str
    form: ManualStyleForm


class CollectionIdentitySaveRequest(BaseModel):
    session_id: str
    collection_identity: str = ""


class DialogueRequest(BaseModel):
    session_id: str
    message: str = Field(min_length=1)


class ManualDialogueRequest(DialogueRequest):
    form: ManualStyleForm


class ScoreRequest(BaseModel):
    session_id: str
    learned_style_score_0_to_10: int | None = Field(default=None, ge=0, le=10)
    manual_style_score_0_to_10: int | None = Field(default=None, ge=0, le=10)


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def make_client() -> openai.OpenAI:
    return openai.OpenAI(api_key=cfg.get_api_key(), base_url=cfg.get_base_url())


def normalize_user_id(value: str) -> str:
    name = value.strip() or DEFAULT_USER_ID
    invalid = set('<>:"/\\|?*')
    safe = "".join("_" if ch in invalid or ord(ch) < 32 else ch for ch in name)
    safe = safe.strip(" .")[:80]
    return safe or DEFAULT_USER_ID


def user_file(user_id: str) -> Path:
    return USER_DATA_DIR / f"{normalize_user_id(user_id)}.json"


def default_user(user_id: str) -> dict:
    safe_id = normalize_user_id(user_id)
    return {
        "user_id": safe_id,
        "display_name": user_id.strip() or safe_id,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "active_profile_id": None,
        "profiles": [],
        "manual_style_form": None,
        "collection_identity": "",
    }


def save_user(user: dict) -> None:
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    user["updated_at"] = now_iso()
    user_file(user["user_id"]).write_text(
        json.dumps(user, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_or_create_user(user_id: str) -> dict:
    path = user_file(user_id)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    user = default_user(user_id)
    save_user(user)
    return user


def profile_record_summary(record: dict, active_profile_id: str | None = None) -> dict:
    profile = record.get("profile") or {}
    raw_stats = profile.get("raw_stats") or {}
    return {
        "profile_id": record["profile_id"],
        "name": record["name"],
        "source": record["source"],
        "created_at": record["created_at"],
        "active": record["profile_id"] == active_profile_id,
        "raw_stats": raw_stats,
    }


def public_user(user: dict) -> dict:
    active_profile_id = user.get("active_profile_id")
    return {
        "user_id": user["user_id"],
        "display_name": user.get("display_name", user["user_id"]),
        "created_at": user.get("created_at"),
        "updated_at": user.get("updated_at"),
        "active_profile_id": active_profile_id,
        "manual_style_form": user.get("manual_style_form"),
        "collection_identity": user.get("collection_identity", ""),
        "profiles": [
            profile_record_summary(record, active_profile_id)
            for record in user.get("profiles", [])
        ],
    }


def save_manual_style_form_for_user(user_id: str, form: ManualStyleForm) -> dict:
    user = get_or_create_user(user_id)
    user["manual_style_form"] = manual_style_form_to_dict(form)
    save_user(user)
    return user


def save_collection_identity_for_user(user_id: str, identity: str) -> dict:
    user = get_or_create_user(user_id)
    user["collection_identity"] = identity.strip()
    save_user(user)
    return user


def manual_style_form_to_dict(form: ManualStyleForm) -> dict:
    return form.model_dump() if hasattr(form, "model_dump") else form.dict()


def list_users() -> list[dict]:
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    users = []
    for path in sorted(USER_DATA_DIR.glob("*.json")):
        try:
            users.append(public_user(json.loads(path.read_text(encoding="utf-8"))))
        except json.JSONDecodeError:
            continue
    if not users:
        users.append(public_user(get_or_create_user(DEFAULT_USER_ID)))
    return users


def active_profile_record(user: dict) -> dict | None:
    active_profile_id = user.get("active_profile_id")
    for record in user.get("profiles", []):
        if record["profile_id"] == active_profile_id:
            return record
    return None


def normalize_profile_payload(data: dict) -> dict:
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="profile must be a JSON object")
    candidate = data.get("style_profile") or data.get("profile") or data
    if not isinstance(candidate, dict) or "characteristics" not in candidate:
        raise HTTPException(status_code=400, detail="style profile JSON is invalid")
    try:
        return profile_to_dict(dict_to_profile(candidate))
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="style profile JSON is invalid") from exc


def save_profile_for_user(user_id: str, profile_dict: dict, name: str, source: str) -> dict:
    user = get_or_create_user(user_id)
    profile = dict_to_profile(profile_dict)
    record = {
        "profile_id": uuid.uuid4().hex[:12],
        "name": (name.strip() or "语言风格画像")[:80],
        "source": source,
        "created_at": now_iso(),
        "profile": profile_to_dict(profile),
        "prompt": build_template_mimicry_prompt(profile),
    }
    user.setdefault("profiles", []).append(record)
    user["active_profile_id"] = record["profile_id"]
    save_user(user)
    return record


def apply_collection_identity_to_prompt(prompt: str, identity: str | None) -> str:
    identity = (identity or "").strip()
    if not identity:
        return prompt
    return (
        f"你正在模仿的用户基本身份：{identity}\n"
        "回答时保持这个基本身份，不要编造与该身份明显冲突的信息。\n\n"
        f"{prompt}"
    )


def build_session_learned_prompt(profile_dict: dict, identity: str | None = None) -> str:
    prompt = build_template_mimicry_prompt(dict_to_profile(profile_dict))
    return apply_collection_identity_to_prompt(prompt, identity)


def refresh_session_learned_prompt(session: dict) -> None:
    if session.get("style_profile"):
        session["learned_style_prompt"] = build_session_learned_prompt(
            session["style_profile"],
            session.get("collection_identity"),
        )


def attach_profile_to_session(session: dict, record: dict) -> None:
    session["style_profile"] = record["profile"]
    # Rebuild at attach time so older saved profiles pick up current prompt rules.
    refresh_session_learned_prompt(session)
    session["user_profile_id"] = record["profile_id"]
    session["stage"] = "manual_style"


def collection_finished(messages: list[str]) -> bool:
    total_chars = sum(len(m) for m in messages)
    turns = len(messages)
    return total_chars > COLLECTION_TARGET_CHARS or (
        turns > COLLECTION_SOFT_TURNS and total_chars > COLLECTION_SOFT_CHARS
    )


def next_preset_topic_question(dialogue: list[dict]) -> str | None:
    asked = {
        item.get("content", "").strip()
        for item in dialogue
        if item.get("role") == "assistant"
    }
    for question in COLLECTION_PRESET_TOPIC_QUESTIONS:
        if question not in asked:
            return question
    return None


def build_collection_messages(dialogue: list[dict], guidance: str | None = None) -> list[dict]:
    messages = [{"role": "system", "content": COLLECTION_CHAT_SYSTEM}]
    for item in dialogue:
        if item["role"] in {"user", "assistant"}:
            messages.append({"role": item["role"], "content": item["content"]})
    if guidance == "switch_topic":
        next_question = next_preset_topic_question(dialogue)
        if next_question:
            content = f"请自然切换到下一个生活话题，并直接问这个问题：{next_question}"
        else:
            content = "请你换一个新的真实生活话题继续聊，只问一个问题。"
        messages.append({
            "role": "user",
            "content": content,
        })
    elif guidance == "continue_topic":
        messages.append({
            "role": "user",
            "content": "请你继续围绕刚刚的话题像朋友一样自然追问，只问一个问题，不要追得太深。",
        })
    return messages


def generate_collection_reply(dialogue: list[dict], guidance: str | None = None) -> str:
    if guidance == "switch_topic":
        next_question = next_preset_topic_question(dialogue)
        if next_question:
            return next_question
    client = make_client()
    response = client.chat.completions.create(
        model=cfg.get_model_name(),
        max_tokens=160,
        messages=build_collection_messages(dialogue, guidance),
    )
    return response.choices[0].message.content.strip()


def characteristic_to_dict(c: Characteristic) -> dict:
    return {
        "key": c.key,
        "label": c.label,
        "value": c.value,
        "examples": c.examples,
        "evidence": c.evidence,
        "confidence": c.confidence,
    }


def profile_to_dict(profile: StyleProfile) -> dict:
    return {
        "characteristics": {
            key: characteristic_to_dict(value)
            for key, value in profile.characteristics.items()
        },
        "raw_stats": {
            "total_messages": profile.raw_stats.total_messages,
            "avg_chars_per_message": profile.raw_stats.avg_chars_per_message,
            "total_chars": profile.raw_stats.total_chars,
        },
        "source_length_chars": profile.source_length_chars,
        "analysis_version": profile.analysis_version,
    }


def dict_to_profile(data: dict) -> StyleProfile:
    characteristics = {
        key: Characteristic(
            key=item["key"],
            label=item["label"],
            value=item["value"],
            examples=list(item.get("examples", [])),
            evidence=item.get("evidence", ""),
            confidence=float(item.get("confidence", 0.0)),
        )
        for key, item in data["characteristics"].items()
    }
    stats = data["raw_stats"]
    return StyleProfile(
        characteristics=characteristics,
        raw_stats=RawStats(
            total_messages=int(stats["total_messages"]),
            avg_chars_per_message=float(stats["avg_chars_per_message"]),
            total_chars=int(stats["total_chars"]),
        ),
        source_length_chars=int(data["source_length_chars"]),
        analysis_version=int(data.get("analysis_version", 1)),
    )


def build_manual_style_prompt(form: ManualStyleForm) -> str:
    return f"""请你扮演以下角色和用户对话。

身份：{form.identity or "未填写"}
你觉得自己说话方式是怎样的：{form.language_style or "未填写"}
限制：{form.constraints or "未填写"}

强制规则：
1. 严格按照上述身份、说话方式和限制说话。
2. 不出现任何动作描写、舞台说明或括号内动作。
3. 每次回复不超过 300 字。
4. 适合多轮逐步推进，但本次只回复一轮。
5. 不要暴露你是 AI 或语言模型。"""


def chat_once(system_prompt: str, user_message: str) -> str:
    return chat_with_messages([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ])


def chat_with_messages(messages: list[dict]) -> str:
    client = make_client()
    response = client.chat.completions.create(
        model=cfg.get_model_name(),
        max_tokens=512,
        messages=messages,
    )
    return response.choices[0].message.content.strip()


def build_learned_style_messages(
    system_prompt: str,
    dialogue: list[dict],
    user_message: str,
) -> list[dict]:
    messages = [{"role": "system", "content": system_prompt}]
    for item in dialogue:
        role = item.get("role")
        content = str(item.get("content", "")).strip()
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_message})
    return messages


def build_manual_style_messages(
    system_prompt: str,
    dialogue: list[dict],
    user_message: str,
) -> list[dict]:
    return build_learned_style_messages(system_prompt, dialogue, user_message)


def profile_summary(profile: StyleProfile) -> list[dict]:
    return [
        {
            "key": c.key,
            "label": c.label,
            "value": c.value,
            "confidence": c.confidence,
        }
        for c in profile.characteristics.values()
    ]


def new_session(user_id: str = DEFAULT_USER_ID, force_collect: bool = False) -> dict:
    user = get_or_create_user(user_id)
    session_id = uuid.uuid4().hex[:12]
    record = active_profile_record(user)
    session = {
        "session_id": session_id,
        "user_id": user["user_id"],
        "user_display_name": user.get("display_name", user["user_id"]),
        "user_profile_id": None,
        "created_at": now_iso(),
        "stage": "collect",
        "collected_user_messages": [],
        "collection_dialogue": [
            {"role": "assistant", "content": INITIAL_COLLECTION_QUESTION, "at": now_iso()}
        ],
        "style_profile": None,
        "learned_style_prompt": None,
        "manual_style_form": user.get("manual_style_form"),
        "collection_identity": user.get("collection_identity", ""),
        "manual_style_dialogue": [],
        "learned_style_dialogue": [],
        "score": None,
    }
    if record and not force_collect:
        attach_profile_to_session(session, record)
        session["collection_dialogue"] = [
            {
                "role": "assistant",
                "content": f"已载入用户「{user['user_id']}」的语言风格画像：{record['name']}。可以直接进行设定风格或学习风格对话。",
                "at": now_iso(),
            }
        ]
    SESSIONS[session_id] = session
    return session


def require_session(session_id: str) -> dict:
    session = SESSIONS.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    return session


def ensure_profile(session: dict) -> StyleProfile:
    data = session.get("style_profile")
    if not data:
        raise HTTPException(status_code=400, detail="style profile is not ready")
    return dict_to_profile(data)


def analyze_session(session: dict) -> StyleProfile:
    if not collection_finished(session["collected_user_messages"]):
        raise HTTPException(status_code=400, detail="collection is not finished")
    chat_text = "\n\n".join(session["collected_user_messages"])
    profile = analyze_chat_log(chat_text, make_client())
    profile_dict = profile_to_dict(profile)
    record = save_profile_for_user(
        session.get("user_id", DEFAULT_USER_ID),
        profile_dict,
        f"采集学习风格 {now_iso()}",
        "collected",
    )
    session["style_profile"] = record["profile"]
    refresh_session_learned_prompt(session)
    session["user_profile_id"] = record["profile_id"]
    session["stage"] = "manual_style"
    return profile


def save_session_report(session: dict) -> dict:
    SESSION_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    session_id = session["session_id"]
    json_path = SESSION_OUTPUT_DIR / f"{session_id}.json"
    md_path = SESSION_OUTPUT_DIR / f"{session_id}.md"
    json_path.write_text(
        json.dumps(session, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    md_path.write_text(render_markdown_report(session), encoding="utf-8")
    return {
        "json_path": str(json_path),
        "markdown_path": str(md_path),
    }


def render_dialogue(dialogue: list[dict]) -> str:
    lines: list[str] = []
    for item in dialogue:
        role = "用户" if item["role"] == "user" else "LLM"
        lines.append(f"- **{role}**：{item['content']}")
    return "\n".join(lines) or "（无）"


def render_blind_winner(value: str | None) -> str:
    return {
        "manual_style": "第一种",
        "learned_style": "第二种",
        "tie": "持平",
    }.get(value or "", "未比较")


def render_markdown_report(session: dict) -> str:
    score = session.get("score") or {}
    profile = session.get("style_profile") or {}
    characteristics = profile.get("characteristics", {})
    lines = [
        "# StyleLab 实验记录",
        "",
        f"- Session ID：`{session['session_id']}`",
        f"- 用户：{session.get('user_id', DEFAULT_USER_ID)}",
        f"- 创建时间：{session['created_at']}",
        f"- 语料采集基本身份：{session.get('collection_identity') or '未填写'}",
        "",
        "## 采集语料",
        "",
    ]
    for i, message in enumerate(session["collected_user_messages"], 1):
        lines.append(f"{i}. {message}")
    lines.extend(["", "## 风格画像", ""])
    for item in characteristics.values():
        lines.append(f"### {item['label']}")
        lines.append("")
        lines.append(item["value"])
        lines.append("")
    lines.extend([
        "## 主动设定风格",
        "",
        json.dumps(session.get("manual_style_form") or {}, ensure_ascii=False, indent=2),
        "",
        "## 第一种 LLM 多轮对话",
        "",
        render_dialogue(session["manual_style_dialogue"]),
        "",
        "## 第二种 LLM 多轮对话",
        "",
        render_dialogue(session["learned_style_dialogue"]),
        "",
        "## 评分",
        "",
        f"- 第一种整体相似度分数：{score.get('manual_style_score_0_to_10', '未评分')}",
        f"- 第二种整体相似度分数：{score.get('learned_style_score_0_to_10', '未评分')}",
        f"- 更接近用户的风格：{render_blind_winner(score.get('winner'))}",
        "",
    ])
    return "\n".join(lines)


app = FastAPI(title="StyleLab")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
SESSIONS: dict[str, dict] = {}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/favicon.ico")
def favicon() -> FileResponse:
    return FileResponse(STATIC_DIR / "favicon.svg")


@app.get("/api/users")
def api_users() -> dict:
    return {"users": list_users()}


@app.post("/api/user/switch")
def api_switch_user(payload: UserRequest) -> dict:
    user = get_or_create_user(payload.user_id)
    return {"user": public_user(user)}


@app.post("/api/user/raw")
def api_user_raw(payload: UserRequest) -> dict:
    user = get_or_create_user(payload.user_id)
    return {
        "user_id": user["user_id"],
        "path": str(user_file(user["user_id"])),
        "user_json": user,
    }


@app.post("/api/user/import-style")
def api_import_style(payload: ImportStyleRequest) -> dict:
    profile_dict = normalize_profile_payload(payload.profile)
    record = save_profile_for_user(
        payload.user_id,
        profile_dict,
        payload.profile_name,
        "imported",
    )
    user = get_or_create_user(payload.user_id)
    session = None
    if payload.session_id:
        session = require_session(payload.session_id)
        if session.get("user_id") != user["user_id"]:
            raise HTTPException(status_code=400, detail="session belongs to another user")
        attach_profile_to_session(session, record)
    return {
        "user": public_user(user),
        "profile": profile_record_summary(record, user.get("active_profile_id")),
        "session": session,
    }


@app.post("/api/session/new")
def api_new_session(payload: NewSessionRequest = NewSessionRequest()) -> dict:
    session = new_session(payload.user_id, payload.force_collect)
    return {"session": session, "user": public_user(get_or_create_user(session["user_id"]))}


@app.post("/api/collect/identity")
def api_collect_identity(payload: CollectionIdentitySaveRequest) -> dict:
    session = require_session(payload.session_id)
    identity = payload.collection_identity.strip()
    session["collection_identity"] = identity
    refresh_session_learned_prompt(session)
    user = save_collection_identity_for_user(session.get("user_id", DEFAULT_USER_ID), identity)
    return {"session": session, "user": public_user(user)}


@app.post("/api/collect/respond")
def api_collect_respond(payload: CollectRequest) -> dict:
    session = require_session(payload.session_id)
    if session["stage"] != "collect":
        raise HTTPException(status_code=400, detail="collection stage is closed")
    if payload.collection_identity is not None:
        identity = payload.collection_identity.strip()
        if identity != session.get("collection_identity", ""):
            session["collection_identity"] = identity
            save_collection_identity_for_user(session.get("user_id", DEFAULT_USER_ID), identity)
    text = payload.message.strip()
    if not text:
        raise HTTPException(status_code=400, detail="message is empty")
    session["collected_user_messages"].append(text)
    session["collection_dialogue"].append({"role": "user", "content": text, "at": now_iso()})

    total_chars = sum(len(m) for m in session["collected_user_messages"])
    turns = len(session["collected_user_messages"])
    finished = collection_finished(session["collected_user_messages"])
    profile = None

    if finished:
        profile = analyze_session(session)
        session["collection_dialogue"].append({
            "role": "assistant",
            "content": "语料已达到学习条件，风格画像已经生成。请继续填写设定风格表单。",
            "at": now_iso(),
        })
    else:
        question = generate_collection_reply(session["collection_dialogue"])
        session["collection_dialogue"].append({"role": "assistant", "content": question, "at": now_iso()})

    return {
        "session": session,
        "user": public_user(get_or_create_user(session["user_id"])),
        "finished": finished,
        "turns": turns,
        "total_chars": total_chars,
        "profile_summary": profile_summary(profile) if profile else None,
    }


@app.post("/api/collect/guidance")
def api_collect_guidance(payload: GuidanceRequest) -> dict:
    session = require_session(payload.session_id)
    if session["stage"] != "collect":
        raise HTTPException(status_code=400, detail="collection stage is closed")

    turns = len(session["collected_user_messages"])
    question = generate_collection_reply(session["collection_dialogue"], payload.action)
    session["collection_dialogue"].append({
        "role": "assistant",
        "content": question,
        "at": now_iso(),
        "guidance": payload.action,
    })

    return {
        "session": session,
        "user": public_user(get_or_create_user(session["user_id"])),
        "turns": turns,
        "total_chars": sum(len(m) for m in session["collected_user_messages"]),
    }


@app.post("/api/style/analyze")
def api_style_analyze(payload: SessionRequest) -> dict:
    session = require_session(payload.session_id)
    if session.get("style_profile"):
        profile = ensure_profile(session)
    else:
        profile = analyze_session(session)
    return {
        "session": session,
        "user": public_user(get_or_create_user(session["user_id"])),
        "profile_summary": profile_summary(profile),
    }


@app.post("/api/manual-style/save")
def api_manual_style_save(payload: ManualStyleSaveRequest) -> dict:
    session = require_session(payload.session_id)
    session["manual_style_form"] = manual_style_form_to_dict(payload.form)
    session["stage"] = "learned_style"
    user = save_manual_style_form_for_user(session.get("user_id", DEFAULT_USER_ID), payload.form)
    return {"session": session, "user": public_user(user)}


@app.post("/api/dialogue/manual-style")
def api_manual_dialogue(payload: ManualDialogueRequest) -> dict:
    session = require_session(payload.session_id)
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="message is empty")
    prompt = build_manual_style_prompt(payload.form)
    answer = chat_with_messages(
        build_manual_style_messages(
            prompt,
            session.get("manual_style_dialogue", []),
            message,
        )
    )
    session["manual_style_form"] = manual_style_form_to_dict(payload.form)
    session.setdefault("manual_style_dialogue", []).extend([
        {"role": "user", "content": message, "at": now_iso()},
        {"role": "assistant", "content": answer, "at": now_iso()},
    ])
    session["stage"] = "learned_style"
    save_manual_style_form_for_user(session.get("user_id", DEFAULT_USER_ID), payload.form)
    return {"session": session, "answer": answer}


@app.post("/api/dialogue/learned-style")
def api_learned_dialogue(payload: DialogueRequest) -> dict:
    session = require_session(payload.session_id)
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="message is empty")
    ensure_profile(session)
    prompt = session["learned_style_prompt"]
    answer = chat_with_messages(
        build_learned_style_messages(
            prompt,
            session.get("learned_style_dialogue", []),
            message,
        )
    )
    session.setdefault("learned_style_dialogue", []).extend([
        {"role": "user", "content": message, "at": now_iso()},
        {"role": "assistant", "content": answer, "at": now_iso()},
    ])
    session["stage"] = "learned_style"
    return {"session": session, "answer": answer}


@app.post("/api/score")
def api_score(payload: ScoreRequest) -> dict:
    session = require_session(payload.session_id)
    has_learned_dialogue = bool(session.get("learned_style_dialogue"))
    has_manual_dialogue = bool(session.get("manual_style_dialogue"))
    if not has_learned_dialogue and not has_manual_dialogue:
        raise HTTPException(status_code=400, detail="dialogue is required before scoring")

    score = {"scored_at": now_iso()}
    if has_learned_dialogue:
        if payload.learned_style_score_0_to_10 is None:
            raise HTTPException(status_code=400, detail="learned style score is required")
        score["learned_style_score_0_to_10"] = payload.learned_style_score_0_to_10
    if has_manual_dialogue:
        if payload.manual_style_score_0_to_10 is None:
            raise HTTPException(status_code=400, detail="manual style score is required")
        score["manual_style_score_0_to_10"] = payload.manual_style_score_0_to_10

    if has_manual_dialogue and has_learned_dialogue:
        if payload.manual_style_score_0_to_10 > payload.learned_style_score_0_to_10:
            score["winner"] = "manual_style"
        elif payload.manual_style_score_0_to_10 < payload.learned_style_score_0_to_10:
            score["winner"] = "learned_style"
        else:
            score["winner"] = "tie"
    session["score"] = score
    session["stage"] = "done"
    paths = save_session_report(session)
    return {"session": session, "saved": paths}


@app.get("/api/session/{session_id}")
def api_get_session(session_id: str) -> dict:
    return {"session": require_session(session_id)}

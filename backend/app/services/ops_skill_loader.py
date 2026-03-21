"""Skill 知识库加载器"""
import re
from pathlib import Path
from typing import Optional

SKILLS_DIR = Path(__file__).parent.parent.parent / "skills"


def _parse_frontmatter(content: str) -> tuple[dict, str]:
    """解析 Markdown front-matter，返回 (meta, body)。"""
    if not content.startswith("---"):
        return {}, content
    end = content.find("\n---", 3)
    if end == -1:
        return {}, content
    fm_text = content[3:end].strip()
    body = content[end + 4:].strip()
    meta: dict = {}
    for line in fm_text.splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            val = val.strip()
            # 简单列表解析（- item）
            if val == "":
                # 多行列表，跳过（后续行以 - 开头）
                continue
            meta[key.strip()] = val
    # 解析 triggers 列表
    triggers_match = re.search(r"triggers:\n((?:\s+-[^\n]+\n?)+)", content)
    if triggers_match:
        meta["triggers"] = [
            t.strip().lstrip("- ") for t in triggers_match.group(1).splitlines() if t.strip()
        ]
    return meta, body


def list_skills() -> list[dict]:
    """扫描 skills/ 目录，返回所有 Skill 的元信息。"""
    skills = []
    if not SKILLS_DIR.exists():
        return skills
    for path in sorted(SKILLS_DIR.glob("*.md")):
        content = path.read_text(encoding="utf-8")
        meta, _ = _parse_frontmatter(content)
        skills.append({
            "name": meta.get("name", path.stem),
            "description": meta.get("description", ""),
            "triggers": meta.get("triggers", []),
        })
    return skills


def load_skill(skill_name: str) -> Optional[str]:
    """读取指定 Skill 的内容（去除 front-matter）。"""
    path = SKILLS_DIR / f"{skill_name}.md"
    if not path.exists():
        return None
    content = path.read_text(encoding="utf-8")
    _, body = _parse_frontmatter(content)
    return body


def detect_relevant_skills(user_message: str) -> list[str]:
    """根据 triggers 关键词检测消息中可能相关的 Skill 名称列表。"""
    msg_lower = user_message.lower()
    matched = []
    for skill in list_skills():
        for trigger in skill.get("triggers", []):
            if trigger.lower() in msg_lower:
                matched.append(skill["name"])
                break
    return matched

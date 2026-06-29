"""POST /ops/sessions 路由回归测试。

回归 Bug：之前 create_session 会复用空白草稿（reusable check），
导致用户连续点"新建会话"按钮时永远拿到同一个 session id，
且 body.title 被忽略。修复后 POST 应当：
1. 总是创建新 session 并返回新 id
2. 持久化 body.title
3. 顺手清理用户残留的空白草稿（无消息无标题），避免堆积
4. 不删除带消息或带标题的会话
"""
import pytest
from sqlalchemy import select

from app.models.ops_message import OpsMessage
from app.models.ops_session import OpsSession


@pytest.mark.asyncio
async def test_post_sessions_returns_new_id_each_call(client, auth_headers, db_session):
    """连续两次 POST 应得到不同的 session id。"""
    r1 = await client.post("/api/v1/ops/sessions", json={}, headers=auth_headers)
    r2 = await client.post("/api/v1/ops/sessions", json={}, headers=auth_headers)
    assert r1.status_code == 200, r1.text
    assert r2.status_code == 200, r2.text
    id1 = r1.json()["id"]
    id2 = r2.json()["id"]
    assert id1 != id2, "POST /ops/sessions returned the same id twice (reuse bug)"


@pytest.mark.asyncio
async def test_post_sessions_persists_title(client, auth_headers):
    """body.title 必须落库并出现在响应里。"""
    r = await client.post(
        "/api/v1/ops/sessions",
        json={"title": "diagnose-pg-down"},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["title"] == "diagnose-pg-down"


@pytest.mark.asyncio
async def test_post_sessions_cleans_up_empty_drafts(client, auth_headers, db_session, admin_user):
    """连续创建 3 次后，DB 里只应该剩下最新的那一个空白草稿。"""
    ids = []
    for _ in range(3):
        r = await client.post("/api/v1/ops/sessions", json={}, headers=auth_headers)
        assert r.status_code == 200
        ids.append(r.json()["id"])

    # 三个 id 都不同
    assert len(set(ids)) == 3

    # 数据库里只剩最后一个
    res = await db_session.execute(
        select(OpsSession).where(OpsSession.user_id == admin_user.id)
    )
    rows = res.scalars().all()
    assert len(rows) == 1
    assert rows[0].id == ids[-1]


@pytest.mark.asyncio
async def test_post_sessions_preserves_titled_and_messaged_sessions(
    client, auth_headers, db_session, admin_user
):
    """带 title 或带消息的会话不应被空白草稿清理逻辑删除。"""
    # 1. 一个带 title 的旧会话
    titled = OpsSession(user_id=admin_user.id, title="keep-me", status="active")
    db_session.add(titled)
    await db_session.commit()
    await db_session.refresh(titled)
    titled_id = titled.id

    # 2. 一个带消息的空标题会话
    with_msg = OpsSession(user_id=admin_user.id, title=None, status="active")
    db_session.add(with_msg)
    await db_session.commit()
    await db_session.refresh(with_msg)
    msg = OpsMessage(
        session_id=with_msg.id,
        role="user",
        msg_type="text",
        content={"text": "hello"},
    )
    db_session.add(msg)
    await db_session.commit()
    with_msg_id = with_msg.id

    # 3. 触发 POST，会清理空白草稿（这两个都不该被清掉）
    r = await client.post("/api/v1/ops/sessions", json={}, headers=auth_headers)
    assert r.status_code == 200
    new_id = r.json()["id"]

    # 验证：标题会话、有消息会话、新会话都还在
    res = await db_session.execute(
        select(OpsSession.id).where(OpsSession.user_id == admin_user.id)
    )
    surviving_ids = {row[0] for row in res.all()}
    assert titled_id in surviving_ids, "带 title 的会话被错误删除"
    assert with_msg_id in surviving_ids, "带消息的会话被错误删除"
    assert new_id in surviving_ids

from fastapi.testclient import TestClient

from src.narrativeos.api import create_app
from src.narrativeos.repository import SQLAlchemyRepository
from src.narrativeos.services.analytics import AnalyticsService
from src.narrativeos.services.async_jobs import AsyncJobService
from src.narrativeos.services.author_collaboration import AuthorCollaborationService
from src.narrativeos.services.authoring import AuthoringService
from src.narrativeos.services.billing import BillingService


def _grant_author_access(repository: SQLAlchemyRepository, *, account_id: str = "acct_author") -> None:
    billing = BillingService(repository)
    billing.grant_subscription(
        {
            "account_id": account_id,
            "tier_id": "creator_pass",
            "provider": "ops_manual",
            "status": "active",
        }
    )
    billing.grant_wallet_credits(
        account_id=account_id,
        wallet_type="studio_credits",
        amount=20,
        tier_id="creator_pass",
    )


def _make_draft(authoring: AuthoringService, *, account_id: str = "acct_author") -> str:
    draft = authoring.create_draft_from_brief(
        {
            "genre_preset": "urban_mystery",
            "world_title": "协作测试世界",
            "lead_name": "江屿",
            "counterpart_name": "周岚",
            "core_premise": "用于验证 collaboration / compare。",
            "life_theme": "真话是否值得承担失去",
            "locations": "旧巷\n便利店门口\n天桥下",
            "author_id": account_id,
            "account_id": account_id,
        }
    )
    return draft["world_version_id"]


def test_author_collaboration_service_can_create_reply_and_resolve_thread(tmp_path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "author_collab.db"))
    service = AuthorCollaborationService(repository)
    authoring = AuthoringService(repository)
    world_version_id = _make_draft(authoring)

    created = service.create_comment_thread(
        world_version_id=world_version_id,
        payload={
            "anchor_type": "character",
            "anchor_key": "lead",
            "severity": "blocker",
            "assignee_id": "editor_b",
            "actor_id": "acct_author",
            "actor_role": "author",
            "body": "主角卡这里还需要再收紧。",
        },
    )
    assert created["thread"]["anchor_type"] == "character"
    assert created["collaboration_summary"]["blocking_thread_count"] == 1
    assert created["collaboration_summary"]["queue_summary"]["blocking_thread_count"] == 1
    assert created["collaboration_summary"]["assignee_queues"][0]["assignee_id"] == "editor_b"

    replied = service.reply_to_thread(
        created["thread"]["thread_id"],
        payload={"actor_id": "editor_b", "actor_role": "editor", "body": "先按 blocking 处理。"},
    )
    assert replied["thread"]["thread_id"] == created["thread"]["thread_id"]

    resolved = service.update_thread_status(
        created["thread"]["thread_id"],
        payload={"status": "resolved", "actor_id": "editor_b", "actor_role": "editor", "body": "已处理。"},
    )
    assert resolved["thread"]["status"] == "resolved"
    assert resolved["collaboration_summary"]["open_thread_count"] == 0


def test_author_collaboration_service_tracks_watchers_and_async_delivery(tmp_path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "author_collab_async.db"))
    analytics = AnalyticsService(repository)
    async_jobs = AsyncJobService(repository, analytics_service=analytics, base_dir=tmp_path)
    service = AuthorCollaborationService(repository, analytics_service=analytics, async_job_service=async_jobs)
    authoring = AuthoringService(repository)
    world_version_id = _make_draft(authoring)

    created = service.create_comment_thread(
        world_version_id=world_version_id,
        payload={
            "anchor_type": "draft",
            "anchor_key": world_version_id,
            "severity": "normal",
            "assignee_id": "editor_b",
            "actor_id": "acct_author",
            "actor_role": "author",
            "body": "请 @editor_c 一起处理。",
        },
    )
    watcher_ids = created["thread"]["watcher_ids"]
    assert watcher_ids == ["acct_author", "editor_b", "editor_c"]
    async_delivery = created["notifications"][0]["metadata_json"]["async_delivery"]
    assert async_delivery["status"] == "sent"
    assert async_delivery["event_type"] in {"author_notification_thread_assigned", "author_notification_thread_mentioned"}
    assert async_delivery["event_id"] is not None

    replied = service.reply_to_thread(
        created["thread"]["thread_id"],
        payload={
            "actor_id": "editor_b",
            "actor_role": "reviewer",
            "body": "收到，我会继续 @editor_d。",
        },
    )
    assert "editor_d" in replied["thread"]["watcher_ids"]

    added = service.add_thread_watcher(created["thread"]["thread_id"], payload={"actor_id": "acct_author", "watcher_id": "editor_e"})
    assert "editor_e" in added["thread"]["watcher_ids"]
    removed = service.remove_thread_watcher(created["thread"]["thread_id"], "editor_e", payload={"actor_id": "acct_author"})
    assert removed["watcher"]["deleted"] is True


def test_author_collaboration_service_supports_draft_watchers_preferences_and_throttling(tmp_path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "author_collab_phase25.db"))
    analytics = AnalyticsService(repository)
    async_jobs = AsyncJobService(repository, analytics_service=analytics, base_dir=tmp_path)
    service = AuthorCollaborationService(repository, analytics_service=analytics, async_job_service=async_jobs)
    authoring = AuthoringService(repository)
    world_version_id = _make_draft(authoring)

    service.add_draft_watcher(world_version_id, payload={"actor_id": "acct_author", "watcher_id": "draft_editor"})
    requested = service.request_approval(
        world_version_id=world_version_id,
        payload={"reviewer_id": "lead_editor", "reason": "请求审批", "actor_id": "acct_author"},
    )
    draft_watcher_ids = requested["collaboration_summary"]["draft_watcher_summary"]["watcher_ids"]
    assert "lead_editor" in draft_watcher_ids
    assert "draft_editor" in draft_watcher_ids

    service.update_notification_preference(
        {
            "actor_id": "draft_editor",
            "notification_type": "thread_updated",
            "in_app_enabled": True,
            "async_mirror_enabled": False,
            "async_sink_name": "default",
        }
    )
    created = service.create_comment_thread(
        world_version_id=world_version_id,
        payload={
            "anchor_type": "draft",
            "anchor_key": world_version_id,
            "actor_id": "acct_author",
            "actor_role": "author",
            "body": "创建一个新 thread。",
        },
    )
    draft_editor_notification = next(item for item in created["notifications"] if item["recipient_id"] == "draft_editor")
    assert draft_editor_notification["notification_type"] == "thread_updated"
    assert "async_delivery" not in (draft_editor_notification.get("metadata_json") or {})

    service.reply_to_thread(
        created["thread"]["thread_id"],
        payload={"actor_id": "acct_author", "actor_role": "author", "body": "再推一条更新。"},
    )
    draft_editor_notifications = repository.list_author_notifications(
        recipient_id="draft_editor",
        thread_id=created["thread"]["thread_id"],
        notification_type="thread_updated",
    )
    assert len(draft_editor_notifications) == 1
    assert draft_editor_notifications[0]["metadata_json"]["throttle"]["collapsed_count"] >= 1

    service.update_notification_preference(
        {
            "actor_id": "muted_editor",
            "notification_type": "thread_mentioned",
            "in_app_enabled": False,
            "async_mirror_enabled": True,
        }
    )
    muted = service.create_comment_thread(
        world_version_id=world_version_id,
        payload={
            "anchor_type": "scene",
            "anchor_key": "scene_2",
            "actor_id": "acct_author",
            "actor_role": "author",
            "body": "这里 @muted_editor 不应收到本地通知。",
        },
    )
    assert all(item["recipient_id"] != "muted_editor" for item in muted["notifications"])
    assert repository.list_author_notifications(recipient_id="muted_editor") == []

    service.update_notification_preference(
        {
            "actor_id": "lead_editor",
            "notification_type": "approval_requested",
            "in_app_enabled": True,
            "async_mirror_enabled": True,
            "async_sink_name": "email",
            "delivery_target": "lead_editor@example.com",
        }
    )
    routed = service.request_approval(
        world_version_id=world_version_id,
        payload={"reviewer_id": "lead_editor", "reason": "改走 email", "actor_id": "acct_author"},
    )
    assert routed["notification"]["metadata_json"]["async_delivery"]["sink_name"] == "email"
    assert routed["notification"]["metadata_json"]["async_delivery"]["delivery_target"] == "lead_editor@example.com"


def test_author_collaboration_service_builds_reviewer_inbox_and_notifications(tmp_path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "author_collab_inbox.db"))
    service = AuthorCollaborationService(repository)
    authoring = AuthoringService(repository)
    world_version_id = _make_draft(authoring)

    created = service.create_comment_thread(
        world_version_id=world_version_id,
        payload={
            "anchor_type": "scene",
            "anchor_key": "scene_false_peace",
            "severity": "high",
            "assignee_id": "editor_b",
            "actor_id": "acct_author",
            "actor_role": "author",
            "body": "这里请 @editor_c 和 @editor_b 一起看。",
        },
    )
    notification_types = {item["notification_type"] for item in created["notifications"]}
    assert notification_types == {"thread_assigned", "thread_mentioned"}
    assert created["thread"]["mentioned_actor_ids"] == ["editor_b", "editor_c"]
    assert created["collaboration_summary"]["notification_summary"]["unread_count"] == 2

    replied = service.reply_to_thread(
        created["thread"]["thread_id"],
        payload={"actor_id": "editor_b", "actor_role": "editor", "body": "先接，我再 @writer_a 回你。"},
    )
    assert any(item["recipient_id"] == "writer_a" for item in replied["notifications"])

    inbox = service.reviewer_inbox(reviewer_id="editor_b", limit=10)
    assert inbox["queue_summary"]["assigned_open_thread_count"] == 1
    assert inbox["queue_summary"]["blocking_assigned_thread_count"] == 1
    assert inbox["queue_summary"]["unread_notification_count"] >= 1

    first_unread = inbox["unread_notifications"][0]
    updated = service.update_notification_status(
        first_unread["notification_id"],
        payload={"status": "read", "recipient_id": "editor_b", "limit": 10},
    )
    assert updated["notification"]["status"] == "read"
    assert updated["reviewer_inbox"]["queue_summary"]["unread_notification_count"] == inbox["queue_summary"]["unread_notification_count"] - 1

    filtered = service.reviewer_inbox(
        reviewer_id="editor_b",
        limit=10,
        world_version_id=world_version_id,
        status_filter="active",
        notification_type="thread_assigned",
        blocking_only=True,
    )
    assert filtered["filters"]["status_filter"] == "active"
    assert filtered["filters"]["blocking_only"] is True
    assert filtered["queue_summary"]["blocking_assigned_thread_count"] == 1

    service.reply_to_thread(
        created["thread"]["thread_id"],
        payload={"actor_id": "acct_author", "actor_role": "author", "body": "再请 @editor_b 看一眼。"},
    )
    inbox_after_bulk_target = service.reviewer_inbox(reviewer_id="editor_b", limit=10)
    remaining_notifications = [item for item in inbox_after_bulk_target["notifications"] if item["status"] != "archived"]
    bulk = service.bulk_update_notification_status(
        {
            "notification_ids": [item["notification_id"] for item in remaining_notifications[:1]],
            "recipient_id": "editor_b",
            "status": "archived",
            "limit": 10,
        }
    )
    assert bulk["updated_count"] == 1
    assert bulk["notifications"][0]["status"] == "archived"


def test_author_collaboration_service_tracks_approval_summary(tmp_path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "author_collab_approval.db"))
    service = AuthorCollaborationService(repository)
    authoring = AuthoringService(repository)
    world_version_id = _make_draft(authoring)

    requested = service.request_approval(
        world_version_id=world_version_id,
        payload={"reviewer_id": "lead_editor", "reason": "请求内部审批。", "actor_id": "acct_author"},
    )
    assert requested["approval"]["status"] == "requested"
    assert requested["notification"]["recipient_id"] == "lead_editor"

    approved = service.approval_decision(
        world_version_id=world_version_id,
        payload={"reviewer_id": "lead_editor", "status": "approved", "reason": "可以送审。"},
    )
    assert approved["approval"]["status"] == "approved"
    assert approved["collaboration_summary"]["approval_summary"]["latest_status"] == "approved"
    assert approved["notification"]["recipient_id"] == "acct_author"


def test_author_collaboration_service_enforces_permissions(tmp_path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "author_collab_permissions.db"))
    service = AuthorCollaborationService(repository)
    authoring = AuthoringService(repository)
    world_version_id = _make_draft(authoring)

    try:
        service.create_comment_thread(
            world_version_id=world_version_id,
            payload={
                "anchor_type": "draft",
                "anchor_key": world_version_id,
                "actor_id": "not_author",
                "actor_role": "reviewer",
                "body": "越权创建。",
            },
        )
        assert False, "expected create thread permission error"
    except PermissionError:
        pass

    created = service.create_comment_thread(
        world_version_id=world_version_id,
        payload={
            "anchor_type": "draft",
            "anchor_key": world_version_id,
            "assignee_id": "editor_b",
            "actor_id": "acct_author",
            "actor_role": "author",
            "body": "请处理。",
        },
    )

    try:
        service.reply_to_thread(
            created["thread"]["thread_id"],
            payload={"actor_id": "outsider", "actor_role": "reviewer", "body": "不能回复。"},
        )
        assert False, "expected reply permission error"
    except PermissionError:
        pass

    try:
        service.update_thread_status(
            created["thread"]["thread_id"],
            payload={"status": "resolved", "actor_id": "outsider", "actor_role": "reviewer"},
        )
        assert False, "expected status permission error"
    except PermissionError:
        pass

    approval = service.request_approval(
        world_version_id=world_version_id,
        payload={"reviewer_id": "lead_editor", "reason": "请求审批", "actor_id": "acct_author"},
    )
    try:
        service.approval_decision(
            world_version_id=world_version_id,
            payload={"reviewer_id": "wrong_editor", "status": "approved", "reason": "错误 reviewer"},
        )
        assert False, "expected approval permission error"
    except PermissionError:
        pass

    try:
        service.update_notification_status(
            approval["notification"]["notification_id"],
            payload={"status": "read", "recipient_id": "someone_else"},
        )
        assert False, "expected notification permission error"
    except PermissionError:
        pass


def test_author_workflow_reflects_blocking_threads_and_approval_states(tmp_path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "author_collab_workflow.db"))
    _grant_author_access(repository)
    authoring = AuthoringService(repository)
    collab = AuthorCollaborationService(repository)
    world_version_id = _make_draft(authoring)
    authoring.run_simulation_for_world_version(world_version_id)

    collab.create_comment_thread(
        world_version_id=world_version_id,
        payload={
            "anchor_type": "simulation",
            "anchor_key": "1",
            "severity": "blocker",
            "actor_id": "acct_author",
            "actor_role": "author",
            "body": "这一章要先修。",
        },
    )
    blocked = authoring.workflow_summary(account_id="acct_author", world_version_id=world_version_id)
    assert blocked["stage"] == "changes_requested"
    assert blocked["open_blocking_threads"] == 1

    for thread in repository.list_author_comment_threads(world_version_id=world_version_id):
        collab.update_thread_status(thread["thread_id"], payload={"status": "resolved", "actor_id": "acct_author", "actor_role": "author"})
    collab.request_approval(world_version_id=world_version_id, payload={"reviewer_id": "lead_editor", "reason": "请求审批"})
    requested = authoring.workflow_summary(account_id="acct_author", world_version_id=world_version_id)
    assert requested["stage"] == "review_requested"

    collab.approval_decision(world_version_id=world_version_id, payload={"reviewer_id": "lead_editor", "status": "approved", "reason": "批准"})
    approved = authoring.workflow_summary(account_id="acct_author", world_version_id=world_version_id)
    assert approved["stage"] in {"approved_for_submit", "ready_to_submit"}


def test_draft_detail_includes_revision_compare_and_before_after_chapter_compare(tmp_path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "author_compare.db"))
    authoring = AuthoringService(repository)
    world_version_id = _make_draft(authoring)
    authoring.run_simulation_for_world_version(world_version_id)
    detail = authoring.get_draft(world_version_id)
    worldpack = detail["worldpack"]
    worldpack["characters"][0]["display_name"] = "江沉"
    authoring.update_draft(world_version_id, worldpack, change_context={"source": "character_editor", "label": "保存角色卡"})
    authoring.run_simulation_for_world_version(world_version_id)
    detail = authoring.get_draft(world_version_id)
    assert detail["revision_compare"]["available"] is True
    assert detail["before_after_chapter_compare"]["available"] is True
    assert detail["before_after_chapter_compare"]["top_changed_chapters"]


def test_author_collaboration_api_exposes_summary_and_actions(tmp_path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "author_collab_api.db"))
    _grant_author_access(repository)
    app = create_app(repository=repository)
    client = TestClient(app)
    draft_id = client.post(
        "/v1/author/drafts/from-brief",
        json={
            "brief": {
                "genre_preset": "synthetic",
                "world_title": "协作 API 世界",
                "lead_name": "甲",
                "counterpart_name": "乙",
                "core_premise": "用于验证 author collaboration API。",
                "life_theme": "如何在协作里推进创作",
                "locations": "中庭\n长廊\n窗边",
                "author_id": "acct_author",
                "account_id": "acct_author",
            }
        },
    ).json()["world_version_id"]

    thread = client.post(
        f"/v1/author/drafts/{draft_id}/comments",
        json={
            "anchor_type": "draft",
            "anchor_key": draft_id,
            "severity": "normal",
            "actor_id": "acct_author",
            "actor_role": "author",
            "body": "先留一条评论。",
        },
    )
    assert thread.status_code == 200

    summary = client.get(f"/v1/author/drafts/{draft_id}/collaboration")
    assert summary.status_code == 200
    assert "threads_by_anchor" in summary.json()
    assert "queue_summary" in summary.json()
    assert "assignee_queues" in summary.json()
    assert "notification_summary" in summary.json()

    inbox = client.get("/v1/author/reviewer-inbox", params={"reviewer_id": "ops_author_reviewer"})
    assert inbox.status_code == 200
    assert "queue_summary" in inbox.json()

    approval = client.post(
        f"/v1/author/drafts/{draft_id}/approval/request",
        json={"reviewer_id": "lead_editor", "reason": "请求审批", "actor_id": "acct_author"},
    )
    assert approval.status_code == 200
    assert approval.json()["notification"]["recipient_id"] == "lead_editor"

    reviewer_inbox = client.get("/v1/author/reviewer-inbox", params={"reviewer_id": "lead_editor"})
    assert reviewer_inbox.status_code == 200
    assert reviewer_inbox.json()["queue_summary"]["pending_approval_count"] == 1
    notification_id = reviewer_inbox.json()["notifications"][0]["notification_id"]
    notification_status = client.post(
        f"/v1/author/notifications/{notification_id}/status",
        json={"status": "read", "recipient_id": "lead_editor"},
    )
    assert notification_status.status_code == 200
    assert notification_status.json()["notification"]["status"] == "read"

    watcher = client.post(
        f"/v1/author/comments/{thread.json()['thread']['thread_id']}/watchers",
        json={"actor_id": "acct_author", "watcher_id": "lead_editor"},
    )
    assert watcher.status_code == 200
    assert "lead_editor" in watcher.json()["thread"]["watcher_ids"]

    bulk = client.post(
        "/v1/author/notifications/bulk-status",
        json={
            "notification_ids": [item["notification_id"] for item in reviewer_inbox.json()["notifications"]],
            "recipient_id": "lead_editor",
            "status": "archived",
        },
    )
    assert bulk.status_code == 200
    assert bulk.json()["updated_count"] >= 1

    forbidden = client.post(
        f"/v1/author/comments/{thread.json()['thread']['thread_id']}/status",
        json={"status": "resolved", "actor_id": "outsider", "actor_role": "reviewer"},
    )
    assert forbidden.status_code == 403

    decision = client.post(
        f"/v1/author/drafts/{draft_id}/approval/decision",
        json={"reviewer_id": "lead_editor", "status": "approved", "reason": "批准"},
    )
    assert decision.status_code == 200

    workflow = client.get(f"/v1/author/workflow?account_id=acct_author&world_version_id={draft_id}")
    assert workflow.status_code == 200
    assert "collaboration_summary" in workflow.json()
    assert "approval_summary" in workflow.json()
    assert "can_request_approval" in workflow.json()
    assert "can_submit" in workflow.json()


def test_author_collaboration_api_supports_identity_headers_pagination_and_preferences(tmp_path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "author_collab_headers.db"))
    _grant_author_access(repository)
    app = create_app(repository=repository)
    client = TestClient(app)
    draft_id = client.post(
        "/v1/author/drafts/from-brief",
        json={
            "brief": {
                "genre_preset": "synthetic",
                "world_title": "协作 Header 世界",
                "lead_name": "甲",
                "counterpart_name": "乙",
                "core_premise": "验证 Phase 2.5。",
                "life_theme": "身份优先级",
                "locations": "中庭",
                "author_id": "acct_author",
                "account_id": "acct_author",
            }
        },
    ).json()["world_version_id"]

    create_headers = {
        "X-NarrativeOS-Actor-Id": "acct_author",
        "X-NarrativeOS-Actor-Role": "author",
        "X-NarrativeOS-Account-Id": "acct_author",
    }
    created = client.post(
        f"/v1/author/drafts/{draft_id}/comments",
        headers=create_headers,
        json={
            "anchor_type": "draft",
            "anchor_key": draft_id,
            "assignee_id": "lead_editor",
            "actor_id": "wrong_actor",
            "actor_role": "reviewer",
            "body": "这里 @lead_editor 来看。",
        },
    )
    assert created.status_code == 200
    assert created.json()["thread"]["created_by"] == "acct_author"

    decision = client.post(
        f"/v1/author/drafts/{draft_id}/approval/request",
        headers=create_headers,
        json={"reviewer_id": "lead_editor", "reason": "请求审批", "actor_id": "wrong_actor"},
    )
    assert decision.status_code == 200

    pref = client.post(
        "/v1/author/notification-preferences",
        headers={"X-NarrativeOS-Actor-Id": "lead_editor", "X-NarrativeOS-Actor-Role": "reviewer"},
        json={
            "actor_id": "someone_else",
            "notification_type": "thread_updated",
            "in_app_enabled": True,
            "async_mirror_enabled": False,
        },
    )
    assert pref.status_code == 200
    assert pref.json()["preference"]["actor_id"] == "lead_editor"

    inbox_page_1 = client.get(
        "/v1/author/reviewer-inbox",
        headers={"X-NarrativeOS-Actor-Id": "lead_editor", "X-NarrativeOS-Actor-Role": "reviewer"},
        params={"reviewer_id": "wrong_editor", "limit": 1},
    )
    assert inbox_page_1.status_code == 200
    assert inbox_page_1.json()["reviewer_id"] == "lead_editor"
    assert inbox_page_1.json()["returned_count"] == 1
    assert inbox_page_1.json()["has_more"] is True
    next_cursor = inbox_page_1.json()["next_cursor"]
    inbox_page_2 = client.get(
        "/v1/author/reviewer-inbox",
        headers={"X-NarrativeOS-Actor-Id": "lead_editor", "X-NarrativeOS-Actor-Role": "reviewer"},
        params={"limit": 1, "cursor": next_cursor},
    )
    assert inbox_page_2.status_code == 200
    assert inbox_page_2.json()["notifications"][0]["notification_id"] != inbox_page_1.json()["notifications"][0]["notification_id"]

    searched = client.get(
        "/v1/author/reviewer-inbox",
        headers={"X-NarrativeOS-Actor-Id": "lead_editor", "X-NarrativeOS-Actor-Role": "reviewer"},
        params={"q": "请求审批", "limit": 5},
    )
    assert searched.status_code == 200
    assert searched.json()["notifications"]
    assert any("请求审批" in (item["body"] or "") or "请求审批" in (item["title"] or "") for item in searched.json()["notifications"])


def test_author_auth_api_supports_register_login_me_logout_and_bearer_authoring(tmp_path):
    repository = SQLAlchemyRepository(database_url="sqlite:///%s" % (tmp_path / "author_auth_api.db"))
    _grant_author_access(repository, account_id="acct_author")
    app = create_app(repository=repository)
    client = TestClient(app)

    registered = client.post(
        "/v1/auth/register",
        json={
            "actor_id": "acct_author",
            "actor_role": "author",
            "password": "secret-pass",
            "account_id": "acct_author",
            "display_name": "Author One",
        },
    )
    assert registered.status_code == 200

    logged_in = client.post(
        "/v1/auth/login",
        json={"actor_id": "acct_author", "password": "secret-pass"},
    )
    assert logged_in.status_code == 200
    token = logged_in.json()["token"]["access_token"]
    auth_headers = {"Authorization": f"Bearer {token}"}

    me = client.get("/v1/auth/me", headers=auth_headers)
    assert me.status_code == 200
    assert me.json()["identity"]["actor_id"] == "acct_author"

    draft_id = client.post(
        "/v1/author/drafts/from-brief",
        headers=auth_headers,
        json={
            "brief": {
                "genre_preset": "synthetic",
                "world_title": "Bearer 世界",
                "lead_name": "甲",
                "counterpart_name": "乙",
                "core_premise": "验证 bearer auth。",
                "life_theme": "身份来源",
                "locations": "中庭",
                "author_id": "acct_author",
                "account_id": "acct_author",
            }
        },
    ).json()["world_version_id"]

    created = client.post(
        f"/v1/author/drafts/{draft_id}/comments",
        headers=auth_headers,
        json={
            "anchor_type": "draft",
            "anchor_key": draft_id,
            "actor_id": "forged_actor",
            "body": "由 bearer token 代理作者身份。",
        },
    )
    assert created.status_code == 200
    assert created.json()["thread"]["created_by"] == "acct_author"

    logged_out = client.post("/v1/auth/logout", headers=auth_headers)
    assert logged_out.status_code == 200
    post_logout_me = client.get("/v1/auth/me", headers=auth_headers)
    assert post_logout_me.status_code == 401

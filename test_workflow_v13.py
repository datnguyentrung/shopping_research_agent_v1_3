import asyncio

from app.agents import shopping_agent_native as agent_module
from app.core.shopping_flow.handlers import category_drilldown as category_drilldown_module
from app.core.shopping_flow.handlers import product_swipe as product_swipe_module
from app.memory.session_store import clear_session, get_or_create_session
from app.models.ui_chunks import ChatRequest, HiddenEventRequest, MessageChunk


def _collect_chunks(async_iterable):
	async def _consume():
		return [chunk async for chunk in async_iterable]

	return asyncio.run(_consume())


def test_greeting_returns_plain_text_without_tool_flow(monkeypatch):
	session_id = "test-greeting"
	clear_session(session_id)

	async def _should_not_run(*args, **kwargs):
		raise AssertionError("initial flow should not be called for greetings")

	monkeypatch.setattr(agent_module, "handle_initial_phase", _should_not_run)

	chunks = _collect_chunks(
		agent_module.stream_shopping_agent_native(
			ChatRequest(message="Xin chào", sessionId=session_id)
		)
	)

	assert len(chunks) == 1
	assert isinstance(chunks[0], MessageChunk)
	assert "mua" in chunks[0].content.lower()


def test_search_message_routes_to_initial_handler(monkeypatch):
	session_id = "test-initial"
	clear_session(session_id)
	called = {}

	async def _fake_initial(payload, session):
		called["message"] = payload.message
		called["phase"] = session.get("phase")
		yield MessageChunk(content="initial flow reached")

	monkeypatch.setattr(agent_module, "handle_initial_phase", _fake_initial)

	chunks = _collect_chunks(
		agent_module.stream_shopping_agent_native(
			ChatRequest(message="áo khoác", sessionId=session_id)
		)
	)

	assert called["message"] == "áo khoác"
	assert called["phase"] == "INIT"
	assert any(isinstance(chunk, MessageChunk) and chunk.content == "initial flow reached" for chunk in chunks)


def test_category_drilldown_submit_routes_to_category_handler(monkeypatch):
	session_id = "test-category-drilldown"
	clear_session(session_id)
	session = get_or_create_session(session_id)
	session["phase"] = "CATEGORY_DRILLDOWN"

	called = {}

	async def _fake_category(payload, session, action, data):
		called["handler"] = "category"
		called["action"] = action
		called["data"] = data
		yield MessageChunk(content="category handler reached")

	async def _should_not_run(*args, **kwargs):
		raise AssertionError("questionnaire handler should not be called in CATEGORY_DRILLDOWN phase")

	monkeypatch.setattr(agent_module, "handle_category_drilldown", _fake_category)
	monkeypatch.setattr(agent_module, "handle_questionnaire", _should_not_run)

	chunks = _collect_chunks(
		agent_module.stream_shopping_agent_native(
			ChatRequest(
				sessionId=session_id,
				hidden_events=HiddenEventRequest(action="SUBMIT_SURVEY", payload=["Áo khoác nam"]),
			)
		)
	)

	assert called == {"handler": "category", "action": "SUBMIT_SURVEY", "data": ["Áo khoác nam"]}
	assert any(isinstance(chunk, MessageChunk) and chunk.content == "category handler reached" for chunk in chunks)


def test_questionnaire_submit_routes_to_questionnaire_handler(monkeypatch):
	session_id = "test-questionnaire"
	clear_session(session_id)
	session = get_or_create_session(session_id)
	session["phase"] = "QUESTIONNAIRE"

	called = {}

	async def _fake_questionnaire(payload, session, action, data):
		called["handler"] = "questionnaire"
		called["action"] = action
		called["data"] = data
		yield MessageChunk(content="questionnaire handler reached")

	async def _should_not_run(*args, **kwargs):
		raise AssertionError("category handler should not be called in QUESTIONNAIRE phase")

	monkeypatch.setattr(agent_module, "handle_questionnaire", _fake_questionnaire)
	monkeypatch.setattr(agent_module, "handle_category_drilldown", _should_not_run)

	chunks = _collect_chunks(
		agent_module.stream_shopping_agent_native(
			ChatRequest(
				sessionId=session_id,
				hidden_events=HiddenEventRequest(action="SUBMIT_SURVEY", payload=["Đen", "Size M"]),
			)
		)
	)

	assert called == {"handler": "questionnaire", "action": "SUBMIT_SURVEY", "data": ["Đen", "Size M"]}
	assert any(isinstance(chunk, MessageChunk) and chunk.content == "questionnaire handler reached" for chunk in chunks)


def test_product_feedback_routes_to_swipe_handler(monkeypatch):
	session_id = "test-feedback"
	clear_session(session_id)
	session = get_or_create_session(session_id)

	called = {}

	async def _fake_swipe(session_arg, session_id_arg, action, data):
		called["handler"] = "swipe"
		called["session_id"] = session_id_arg
		called["action"] = action
		called["data"] = data
		yield MessageChunk(content="swipe handler reached")

	monkeypatch.setattr(agent_module, "handle_product_swipe", _fake_swipe)

	chunks = _collect_chunks(
		agent_module.stream_shopping_agent_native(
			ChatRequest(
				sessionId=session_id,
				hidden_events=HiddenEventRequest(
					action="PRODUCT_FEEDBACK",
					payload={"decision": "dislike", "reason": "Khác"},
				),
			)
		)
	)

	assert called == {
		"handler": "swipe",
		"session_id": session_id,
		"action": "PRODUCT_FEEDBACK",
		"data": {"decision": "dislike", "reason": "Khác"},
	}
	assert any(isinstance(chunk, MessageChunk) and chunk.content == "swipe handler reached" for chunk in chunks)


def test_category_drilldown_no_products_yields_text_fallback(monkeypatch):
	session_id = "test-category-empty"
	clear_session(session_id)
	session = get_or_create_session(session_id)
	session["phase"] = "CATEGORY_DRILLDOWN"
	session["current_category_id"] = 123
	session["category_map"] = {"Áo khoác": 123}

	async def _empty_stream():
		if False:
			yield None

	monkeypatch.setattr(category_drilldown_module, "get_child_categories", lambda category_id, trace_id=None: ([], {}, []))
	monkeypatch.setattr(category_drilldown_module, "build_attribute_questions", lambda category_id, trace_id=None: [])
	monkeypatch.setattr(category_drilldown_module, "search_and_prepare_stream", lambda **kwargs: asyncio.sleep(0, result=([], _empty_stream())))

	chunks = _collect_chunks(
		category_drilldown_module.handle_category_drilldown(
			ChatRequest(message="áo khoác", sessionId=session_id),
			session,
			"SUBMIT_SURVEY",
			["Áo khoác"],
		)
	)

	assert any(isinstance(chunk, MessageChunk) and "không tìm thấy" in chunk.content.lower() for chunk in chunks)
	assert session["phase"] == "DONE"


def test_dislike_reason_analysis_filters_pending_products(monkeypatch):
	session_id = "test-dislike-analysis"
	clear_session(session_id)
	session = get_or_create_session(session_id)
	session["pending_products"] = [
			{"name": "Áo khoác gió", "price_current": 199000, "platform": "tiki", "product_id": "1", "product_url": "u", "main_image": "i", "rating_star": 4.0, "rating_count": 1},
		{"name": "Mũ bảo hiểm", "price_current": 99000},
	]

	async def _fake_analysis(reason: str):
		return {"banned_keywords": ["mũ"], "preferred_keywords": ["áo khoác"]}

	monkeypatch.setattr(product_swipe_module, "analyze_dislike_reason", _fake_analysis)
	monkeypatch.setattr(product_swipe_module, "build_interactive_product_chunk", lambda product: MessageChunk(content=f"next:{product.get('name', '')}"))

	chunks = _collect_chunks(
		product_swipe_module.handle_product_swipe(
			session,
			session_id,
			"PRODUCT_FEEDBACK",
			{"decision": "dislike", "reason": "Khác", "product": {"name": "Áo khoác gió"}},
		)
	)

	assert any(
		hasattr(chunk, "a2ui") and (chunk.a2ui.get("data") or {}).get("statusText", "").startswith("AI đang phân tích")
		for chunk in chunks
	)
	assert len(session["pending_products"]) == 0
	assert any(isinstance(chunk, MessageChunk) and chunk.content == "next:Áo khoác gió" for chunk in chunks)
	assert session["preferred_keywords"] == ["áo khoác"]




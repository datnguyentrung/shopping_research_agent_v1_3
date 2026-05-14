from typing import TypedDict, Optional, Any, Dict, List

from app.models.product_schemas import CapturedData


class ShoppingState(TypedDict, total=False):
    session_id: str
    phase: str # INIT, CATEGORY_DRILLDOWN, QUESTIONNAIRE, PRODUCT_SWIPE, FINAL_SUMMARY

    # User Input
    original_keyword: str
    vi_keyword: str
    current_message: str
    hidden_action: Optional[str]
    hidden_payload: Any

    # Flow Data
    category_map: Dict[str, str]
    current_category_id: str
    leaf_category_name: str
    attributes: List[Dict[str, Any]]
    current_attribute_id: int
    answers: List[Dict[str, Any]]
    chat_history: List[Dict[str, Any]]

    # Products & Feedback
    raw_products: List[CapturedData]
    pending_products: List[CapturedData]
    whitelist: List[Dict[str, Any]]
    blacklist: List[Dict[str, Any]]
    preferred_keywords: List[str]
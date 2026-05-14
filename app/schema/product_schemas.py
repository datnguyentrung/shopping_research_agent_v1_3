"""
Stub file cho Product Schemas
"""
from typing import Any, List, Optional, Union
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

class ShopInfo(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)
    shop_id: Optional[str] = "Unknown"
    shop_name: Optional[str] = "Unknown"
    shop_location: Optional[str] = None

class TierVariation(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)
    name: str
    options: List[str]

class CapturedData(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)
    platform: str
    product_id: Union[str, int]
    product_url: str
    name: str
    price_current: float
    price_original: Optional[float] = None
    currency: str = "VND"
    main_image: str
    rating_star: float
    rating_count: int
    sold_count: Optional[int] = None
    shop: Optional[ShopInfo] = None
    tier_variations: List[TierVariation] = []

class ProductList(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)
    products: List[CapturedData]

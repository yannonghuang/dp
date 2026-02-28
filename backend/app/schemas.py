from pydantic import BaseModel
from typing import Optional


class HierarchyNode(BaseModel):
    Plant: int
    Series: str
    Model: str
    Version: Optional[str] = None


class ForecastRow(BaseModel):
    Plant: int
    Series: Optional[str] = None
    Model: Optional[str] = None
    Version: Optional[str] = None
    # 2024-01 .. 2024-12 and optional 2024-TOTAL
    # Dynamic keys handled in response as dict

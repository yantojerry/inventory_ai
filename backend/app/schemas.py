"""Pydantic request schemas for API validation."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, constr


NonEmptyStr = constr(strip_whitespace=True, min_length=1)


class SchemaModel(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class ResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class SellRequest(SchemaModel):
    sku: NonEmptyStr = Field(..., examples=["RTL-COF-001"])
    quantity: int = Field(..., gt=0, examples=[3])
    unit_price: Optional[float] = Field(None, gt=0, examples=[149.0])
    notes: str = ""


class ItemRequest(SchemaModel):
    sku: NonEmptyStr = Field(..., examples=["IT-LAP-100"])
    name: NonEmptyStr = Field(..., examples=["Business Laptop"])
    industry: NonEmptyStr = Field(..., examples=["it"])
    stock_quantity: int = Field(..., ge=0, examples=[6])
    unit_cost: float = Field(..., gt=0, examples=[42000.0])
    expiry_date: Optional[date] = Field(None, examples=["2027-05-08"])
    attributes: Dict[str, Any] = Field(default_factory=dict)


class ItemUpdateRequest(SchemaModel):
    name: Optional[NonEmptyStr] = None
    stock_quantity: Optional[int] = Field(None, ge=0)
    unit_cost: Optional[float] = Field(None, gt=0)
    expiry_date: Optional[date] = None
    attributes: Optional[Dict[str, Any]] = None


class TransactionRequest(SchemaModel):
    sku: NonEmptyStr
    change: int = Field(..., examples=[-3])
    reason: str = ""
    unit_price: Optional[float] = Field(None, gt=0)

    @field_validator("change")
    @classmethod
    def change_cannot_be_zero(cls, value: int) -> int:
        if value == 0:
            raise ValueError("Transaction change cannot be zero.")
        return value


class IndustryConfigRequest(SchemaModel):
    fields: Optional[List[str]] = None
    track_expiry: Optional[bool] = None
    track_batch: Optional[bool] = None
    workflow: Optional[Dict[str, Any]] = None
    forecast: Optional[Dict[str, Any]] = None
    reorder: Optional[Dict[str, Any]] = None
    anomaly: Optional[Dict[str, Any]] = None
    expiry: Optional[Dict[str, Any]] = None
    dynamic_attributes: Optional[Dict[str, Any]] = None


class IndustryCreateRequest(SchemaModel):
    key: Optional[NonEmptyStr] = Field(None, examples=["food_service"])
    display_name: NonEmptyStr = Field(..., examples=["Food Service"])
    description: str = ""
    task_keys: List[str] = Field(default_factory=list, examples=[["inventory_management", "sales_transactions"]])
    fields: List[str] = Field(default_factory=list)
    track_expiry: Optional[bool] = None
    track_batch: bool = False
    dynamic_attributes: Dict[str, Any] = Field(default_factory=dict)
    workflow: Dict[str, Any] = Field(default_factory=dict)
    forecast: Dict[str, Any] = Field(default_factory=dict)
    reorder: Dict[str, Any] = Field(default_factory=dict)
    anomaly: Dict[str, Any] = Field(default_factory=dict)
    expiry: Dict[str, Any] = Field(default_factory=dict)


class IndustryTasksRequest(SchemaModel):
    task_keys: List[str] = Field(default_factory=list)


class ChatMessageRequest(SchemaModel):
    role: NonEmptyStr = Field("user", examples=["user"])
    content: NonEmptyStr = Field(..., examples=["What modules should I enable for healthcare?"])


class IndustrySetupChatRequest(SchemaModel):
    industry: str = Field("", examples=["healthcare"])
    display_name: Optional[str] = Field(None, examples=["Healthcare"])
    selected_tasks: List[str] = Field(default_factory=list)
    message: NonEmptyStr = Field(..., examples=["Help me choose tasks for this industry."])
    history: List[ChatMessageRequest] = Field(default_factory=list)


class LoginRequest(SchemaModel):
    username: NonEmptyStr = Field(..., examples=["superadmin"])
    password: NonEmptyStr = Field(..., examples=["admin123"])


class UserCreateRequest(SchemaModel):
    username: NonEmptyStr
    full_name: NonEmptyStr
    password: str = Field(..., min_length=6)
    role: NonEmptyStr = Field(..., examples=["industry_admin"])
    industries: List[str] = Field(default_factory=list)
    is_active: bool = True


class UserUpdateRequest(SchemaModel):
    username: Optional[NonEmptyStr] = None
    full_name: Optional[NonEmptyStr] = None
    password: Optional[str] = Field(None, min_length=6)
    role: Optional[NonEmptyStr] = None
    industries: Optional[List[str]] = None
    is_active: Optional[bool] = None


class HealthResponse(ResponseSchema):
    status: str


class InventoryItemResponse(ResponseSchema):
    sku: NonEmptyStr
    name: NonEmptyStr
    industry: NonEmptyStr
    stock_quantity: int
    unit_cost: float
    inventory_value: float
    expiry_date: Optional[date] = None
    days_to_expiry: Optional[int] = None
    attributes: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class InventoryRowResponse(ResponseSchema):
    item: InventoryItemResponse
    ai: Dict[str, Any]
    workflow_alert_count: int


class InventoryListResponse(ResponseSchema):
    items: List[InventoryRowResponse]
    count: int


class InventoryDetailResponse(ResponseSchema):
    item: InventoryItemResponse
    ai: Dict[str, Any]
    advisory_note: str


class TransactionResponse(ResponseSchema):
    id: int
    sku: NonEmptyStr
    transaction_type: NonEmptyStr
    quantity: int
    unit_price: Optional[float] = None
    transaction_date: datetime
    notes: str = ""
    metadata: Optional[Dict[str, Any]] = None


class TransactionListResponse(ResponseSchema):
    transactions: List[TransactionResponse]
    count: int


class ItemMutationResponse(ResponseSchema):
    message: str
    item: InventoryItemResponse
    workflow: Dict[str, Any]


class InventoryTransactionMutationResponse(ResponseSchema):
    message: str
    item: InventoryItemResponse
    transaction: TransactionResponse
    ai: Dict[str, Any]


class SellResponse(ResponseSchema):
    message: str
    item: InventoryItemResponse
    transaction: TransactionResponse
    ai_reorder_recommendation: Dict[str, Any]


class TaskModuleResponse(ResponseSchema):
    key: str
    display_name: str
    description: str
    category: str


class TaskModulesResponse(ResponseSchema):
    task_modules: List[TaskModuleResponse]
    count: int


class IndustryRecordResponse(ResponseSchema):
    key: str
    display_name: str
    description: str
    is_system: bool
    enabled_tasks: List[str]
    profile: Dict[str, Any]


class IndustryCatalogResponse(ResponseSchema):
    industries: Dict[str, Dict[str, Any]]
    industry_records: List[IndustryRecordResponse]
    task_modules: List[TaskModuleResponse]


class IndustryOperationResponse(ResponseSchema):
    message: Optional[str] = None
    industry: IndustryRecordResponse
    config: Dict[str, Any]


class UserResponse(ResponseSchema):
    id: int
    username: NonEmptyStr
    full_name: NonEmptyStr
    role: NonEmptyStr
    industries: List[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime


class UserListResponse(ResponseSchema):
    users: List[UserResponse]
    count: int


class UserMutationResponse(ResponseSchema):
    message: str
    user: UserResponse


class AuthResponse(ResponseSchema):
    access_token: str
    token_type: str
    user: UserResponse


class CurrentUserResponse(ResponseSchema):
    user: UserResponse


class MessageResponse(ResponseSchema):
    message: str


class AiAnalysisResponse(ResponseSchema):
    sku: NonEmptyStr
    industry: NonEmptyStr
    ai: Dict[str, Any]
    advisory_note: str


class SetupChatResponse(ResponseSchema):
    model_config = ConfigDict(from_attributes=True, extra="allow")

    provider: str
    used_external_ai: bool
    provider_error: Optional[str] = None
    recommendation_ready: bool
    inferred_industry: str
    inferred_display_name: Optional[str] = None
    reply: str
    recommended_task_keys: List[str]
    selected_task_keys: List[str]
    add_task_keys: List[str]
    review_task_keys: List[str]
    recommended_config: Dict[str, Any]
    setup_hints: List[str]
    follow_up_questions: List[str]

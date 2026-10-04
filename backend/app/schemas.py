from decimal import Decimal
from pydantic import BaseModel, Field, EmailStr, ConfigDict, field_validator


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Login(Input):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class ClientInput(Input):
    name: str = Field(min_length=2, max_length=250)
    rut: str = Field(pattern=r"^\d{12}$")
    account_number: str = Field(min_length=1, max_length=100)
    manager_id: str
    profile_id: str
    contact: str = Field(default="", max_length=200)
    email: EmailStr | str = ""
    phone: str = Field(default="", max_length=100)
    address: str = Field(default="", max_length=500)
    activity: str = Field(default="", max_length=200)
    branch: str = Field(default="", max_length=100)
    financials: dict = Field(default_factory=dict)
    guarantees: str = Field(default="", max_length=20000)
    related_companies: list = Field(default_factory=list, max_length=100)
    guarantors: list = Field(default_factory=list, max_length=100)

    @field_validator("financials")
    @classmethod
    def financial_check(cls, v):
        allowed = {"income", "revenue", "ebitda", "total_debt", "bbva_debt", "currency"}
        if set(v) - allowed:
            raise ValueError("Campos financieros desconocidos.")
        for key, value in v.items():
            if key != "currency":
                d = Decimal(str(value))
                if not d.is_finite() or abs(d) > Decimal("100000000000000000"):
                    raise ValueError("Importe financiero inválido.")
                v[key] = str(d)
            elif value not in {"UYU", "USD", "EUR"}:
                raise ValueError("Moneda financiera inválida.")
        return v


class ProposalInput(Input):
    client_id: str
    product_id: str
    amount: Decimal = Field(gt=0, max_digits=20, decimal_places=2)
    currency: str = Field(pattern="^(UYU|USD|EUR)$", default="UYU")
    term_months: int = Field(gt=0, le=1200)
    rate: Decimal = Field(default=Decimal("0"), ge=0, le=100, decimal_places=4)
    purpose: str = Field(min_length=3, max_length=20000)
    guarantees: str = Field(default="", max_length=20000)
    payment_method: str = Field(default="", max_length=10000)
    observations: str = Field(default="", max_length=20000)
    participants: dict = Field(default_factory=dict)


class ProposalPatch(Input):
    version: int = Field(ge=1)
    amount: Decimal | None = Field(default=None, gt=0, max_digits=20, decimal_places=2)
    currency: str | None = Field(default=None, pattern="^(UYU|USD|EUR)$")
    term_months: int | None = Field(default=None, gt=0, le=1200)
    rate: Decimal | None = Field(default=None, ge=0, le=100)
    purpose: str | None = Field(default=None, min_length=3, max_length=20000)
    guarantees: str | None = Field(default=None, max_length=20000)
    payment_method: str | None = Field(default=None, max_length=10000)
    observations: str | None = Field(default=None, max_length=20000)
    participants: dict | None = None


class Transition(Input):
    action: str
    reason: str = Field(default="", max_length=20000)
    version: int = Field(ge=1)
    requirements: list[str] = Field(default_factory=list, max_length=100)
    client_visible: bool = True


class Assignment(Input):
    analyst_ids: list[str] = Field(min_length=1, max_length=20)
    reason: str = Field(min_length=3, max_length=2000)


class Validation(Input):
    status: str = Field(pattern="^(correct|incorrect)$")
    reason: str = Field(min_length=3, max_length=5000)


class ReportInput(Input):
    content: str = Field(min_length=1, max_length=100000)
    final: bool = False
    version: int | None = None
    human_assessment: dict | None = None


class CommentInput(Input):
    content: str = Field(min_length=1, max_length=10000)
    attachment_ids: list[str] = Field(default_factory=list, max_length=10)


class UserInput(Input):
    email: EmailStr
    name: str = Field(min_length=2, max_length=200)
    password: str = Field(min_length=12, max_length=128)
    role_ids: list[str] = Field(min_length=1, max_length=20)
    client_id: str | None = None
    branch: str = Field(default="", max_length=100)
    supervisor_id: str | None = None


class RoleInput(Input):
    name: str = Field(min_length=2, max_length=100)
    permissions: list[str] = Field(default_factory=list)


class ResetRequest(Input):
    email: EmailStr


class ResetConfirm(Input):
    token: str = Field(min_length=20, max_length=200)
    password: str = Field(min_length=12, max_length=128)

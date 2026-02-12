from pydantic import BaseModel


# --- Typeform webhook payload models ---

class TypeformFieldRef(BaseModel):
    ref: str

class TypeformAnswer(BaseModel):
    field: TypeformFieldRef
    type: str
    text: str | None = None
    email: str | None = None
    phone_number: str | None = None

class TypeformFormResponse(BaseModel):
    answers: list[TypeformAnswer]

class TypeformWebhookPayload(BaseModel):
    form_response: TypeformFormResponse


# --- Website contact form payload ---

class WebsiteWebhookPayload(BaseModel):
    name: str
    email: str
    phone: str | None = None
    company: str | None = None
    title: str | None = None
    message: str | None = None

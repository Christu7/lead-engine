from pydantic import BaseModel


# --- Apollo webhook payload models ---

class ApolloPhoneNumber(BaseModel):
    raw_number: str | None = None
    sanitized_number: str | None = None
    type: str | None = None


class ApolloContact(BaseModel):
    id: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    name: str | None = None
    email: str | None = None
    organization_name: str | None = None
    title: str | None = None
    linkedin_url: str | None = None
    phone_numbers: list[ApolloPhoneNumber] = []


class ApolloWebhookPayload(BaseModel):
    event_type: str | None = None
    contact: ApolloContact


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

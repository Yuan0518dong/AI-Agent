from pydantic import BaseModel, Field, model_validator


class MaterialCreate(BaseModel):
    goalId: str | None = None
    title: str = Field(min_length=1)
    type: str = Field(pattern="^(text|link)$")
    content: str = ""
    url: str = ""

    @model_validator(mode="after")
    def validate_material_body(self):
        if self.type == "text" and not self.content.strip():
            raise ValueError("Text materials require content")
        if self.type == "link" and not self.url.strip():
            raise ValueError("Link materials require url")
        return self


class MaterialUpdate(BaseModel):
    goalId: str | None = None
    title: str | None = Field(default=None, min_length=1)
    type: str | None = Field(default=None, pattern="^(text|link)$")
    content: str | None = None
    url: str | None = None

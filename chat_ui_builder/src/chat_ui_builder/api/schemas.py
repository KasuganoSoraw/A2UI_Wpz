from __future__ import annotations

from pydantic import BaseModel, model_validator


class ChatRequest(BaseModel):
  message: str | None = None
  source_data: dict | list | str | int | float | bool | None = None
  user_query: str | None = None

  @model_validator(mode='after')
  def ensure_non_empty_request(self) -> 'ChatRequest':
    if self.source_data is None and not self.message:
      raise ValueError('`source_data` 或 `message` 至少提供一个。')
    return self

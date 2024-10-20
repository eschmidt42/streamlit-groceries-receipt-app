import logging

import instructor
from anthropic import Anthropic
from instructor import Instructor

import library.schemas as schemas
from library.settings import Services

logger = logging.getLogger(__name__)


def get_anthropic_client(services: Services) -> Instructor:
    api_key = services.get_anthropic_key()
    client = Anthropic(api_key=api_key)
    return instructor.from_anthropic(client)


def create_anthropic_messages(base64_image: str) -> list[dict]:
    # https://docs.anthropic.com/en/docs/build-with-claude/vision
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "What shop and items info is in this image of a supermarket receipt?",
                },
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": base64_image,
                    },
                },
            ],
        }
    ]
    return messages


def make_anthropic_request(
    base64_image: str, client: Instructor, services: Services, max_retries: int = 3
) -> schemas.Receipt:
    # https://docs.anthropic.com/en/docs/vision
    logger.debug("Making an anthropic API request")
    return client.chat.completions.create(
        response_model=schemas.Receipt,
        messages=create_anthropic_messages(base64_image),  # type: ignore
        model=services.anthropic.model,
        max_tokens=services.anthropic.max_tokens,
        max_retries=max_retries,
    )  # type: ignore

from __future__ import annotations

import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Literal, NamedTuple, cast, override

import click
from dotenv import load_dotenv
from numpy import float64
from openai import OpenAI
from openai.types.chat import ChatCompletionChunk
from pangea import PangeaConfig
from pangea.services import AuthZ
from pangea.services.authz import Resource, Subject
from pydantic import SecretStr
from scipy.spatial import distance  # type: ignore[import-untyped]

from user_authn.auth_server import prompt_authn

load_dotenv(override=True)


SYSTEM_PROMPT = """
You are an assistant for question-answering tasks. Use the following pieces of
retrieved context to answer the question. If you don't know the answer, just say
that you don't know and that the user may not be authorized to know the answer.
Use three sentences maximum and keep the answer concise.
Context: {context}
"""


class Document(NamedTuple):
    category: Literal["engineering", "finance"]
    content: str
    embedding: list[float]


def chunk_text(text: str, max_tokens: int) -> list[str]:
    # Assuming each token is 4 characters (ranges from 3-6).
    char_limit = max_tokens * 4

    # Split text into chunks based on character limits.
    return [text[i : i + char_limit] for i in range(0, len(text), char_limit)]


def compute_cosine_similarity(vec1: Iterable[float], vec2: Iterable[float]) -> float64:
    return 1 - distance.cosine(vec1, vec2)


class SecretStrParamType(click.ParamType):
    name = "secret"

    @override
    def convert(self, value: Any, param: click.Parameter | None = None, ctx: click.Context | None = None) -> SecretStr:
        if isinstance(value, SecretStr):
            return value

        return SecretStr(value)


SECRET_STR = SecretStrParamType()


@click.command()
@click.option(
    "--authn-client-token",
    envvar="PANGEA_AUTHN_CLIENT_TOKEN",
    type=str,
    required=True,
    help="Pangea AuthN Client API token. May also be set via the `PANGEA_AUTHN_CLIENT_TOKEN` environment variable.",
)
@click.option(
    "--authn-hosted-login",
    envvar="PANGEA_AUTHN_HOSTED_LOGIN",
    type=str,
    required=True,
    help="Pangea AuthN Hosted Login URL. May also be set via the `PANGEA_AUTHN_HOSTED_LOGIN` environment variable.",
)
@click.option(
    "--authz-token",
    envvar="PANGEA_AUTHZ_TOKEN",
    type=SECRET_STR,
    required=True,
    help="Pangea AuthZ API token. May also be set via the `PANGEA_AUTHZ_TOKEN` environment variable.",
)
@click.option(
    "--pangea-domain",
    envvar="PANGEA_DOMAIN",
    default="aws.us.pangea.cloud",
    show_default=True,
    required=True,
    help="Pangea API domain. May also be set via the `PANGEA_DOMAIN` environment variable.",
)
@click.option("--model", default="gpt-4o-mini", show_default=True, required=True, help="OpenAI model.")
@click.option(
    "--openai-api-key",
    envvar="OPENAI_API_KEY",
    type=SECRET_STR,
    required=True,
    help="OpenAI API key. May also be set via the `OPENAI_API_KEY` environment variable.",
)
@click.argument("prompt")
def main(
    *,
    prompt: str,
    authn_client_token: str,
    authn_hosted_login: str,
    authz_token: SecretStr,
    pangea_domain: str,
    model: str,
    openai_api_key: SecretStr,
) -> None:
    # Split data into chunks.
    click.echo("Reading documents...")
    data_dir = Path(__file__).parent.joinpath("data").resolve(strict=True)
    docs: list[Document] = []
    for md_file in data_dir.glob("**/*.md"):
        content = md_file.read_text(encoding="utf-8")
        for chunk in chunk_text(content, max_tokens=500):
            docs.append(Document(category=Path(md_file).parent.name, content=chunk, embedding=[]))  # type: ignore[arg-type]

    # Generate embeddings for each chunk.
    click.echo("Generating embeddings...")
    openai = OpenAI(api_key=openai_api_key.get_secret_value())
    docs = [
        Document(doc.category, doc.content, res.embedding)
        for doc, res in zip(
            docs, openai.embeddings.create(input=[doc.content for doc in docs], model="text-embedding-3-small").data
        )
    ]

    # Generate embedding for the user's prompt.
    prompt_embedding = (
        openai.embeddings.create(
            input=prompt,
            model="text-embedding-3-small",
        )
        .data[0]
        .embedding
    )

    # Login via Pangea AuthN.
    check_result = prompt_authn(
        authn_client_token=authn_client_token, authn_hosted_login=authn_hosted_login, pangea_domain=pangea_domain
    )
    click.echo()
    click.echo(f"Authenticated as {check_result.owner} ({check_result.identity}).")  # type: ignore[attr-defined]
    click.echo()

    # At inference time, exclude documents that the user is not authorized to
    # access.
    authz = AuthZ(token=authz_token.get_secret_value(), config=PangeaConfig(domain=pangea_domain))
    subject = Subject(type="user", id=check_result.owner)  # type: ignore[attr-defined]
    for doc in docs:
        resource = Resource(type=doc.category, id=doc.category)
        response = authz.check(subject=subject, action="read", resource=resource)
        if response.result is None or not response.result.allowed:
            docs.remove(doc)

    # Find the most similar content
    similarities = [(item.content, compute_cosine_similarity(prompt_embedding, item.embedding)) for item in docs]

    # Sort by similarity score in descending order.
    similarities.sort(reverse=True, key=lambda x: float(x[1]))

    # Only take top 5 results.
    top_results = similarities[:5]

    # Build the context
    context = ""
    for content, _ in top_results:
        context += content + "\n--------------\n"

    # Generate chat completions.
    stream = openai.chat.completions.create(
        messages=(
            {"role": "system", "content": SYSTEM_PROMPT.format(context=context)},
            {"role": "user", "content": prompt},
        ),
        model=model,
        stream=True,
    )
    for chunk in stream:  # type: ignore[assignment]
        for choice in cast(ChatCompletionChunk, chunk).choices:
            sys.stdout.write(choice.delta.content or "")
            sys.stdout.flush()

        sys.stdout.flush()

    sys.stdout.write("\n")


if __name__ == "__main__":
    main()

import typing

import pydantic_extra_types.ulid
from pydantic import AnyHttpUrl
from ulid import ULID


def gen_ulid() -> pydantic_extra_types.ulid.ULID:
    """Generate a ULID

    Uses some type coercion to persuade typecheckers that it works
    with Pydantic models"""
    return typing.cast(pydantic_extra_types.ulid.ULID, ULID())


def url(url: str) -> AnyHttpUrl:
    return typing.cast(AnyHttpUrl, url)

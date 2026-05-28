import typing

if typing.TYPE_CHECKING:
    from pangloss.model_config.models_base import (
        ReifiedRelation,
        RootNode,
        SemanticSpace,
    )


def set_type_to_literal_on_base_model(
    cls: type["RootNode"] | type["ReifiedRelation"] | type["SemanticSpace"],
):
    cls.__annotations__["type"] = typing.Literal[cls.__name__]

    if (
        generic_metadata := getattr(cls, "__pydantic_generic_metadata__", None)
    ) and generic_metadata["origin"]:
        cls.type = generic_metadata["origin"].__name__

    else:
        cls.type = cls.__name__

import typing

from pydantic import create_model

from pangloss.model_config.field_definitions import PropertyFieldDefinition
from pangloss.model_config.model_setup_functions.field_builders import (
    build_property_type_field,
)
from pangloss.model_config.model_setup_functions.utils import (
    unpack_fields_onto_model,
)
from pangloss.model_config.models_base import (
    ReferenceCreateBase,
    ReferenceSetBase,
    ReferenceViewBase,
    RootNode,
)


def build_reference_set(model: type["RootNode"]):
    # Reference Setter only needs an identifier and a type
    model.ReferenceSet = create_model(
        f"{model.__name__}ReferenceSet",
        __base__=ReferenceSetBase,
        __module__=model.__module__,
        type=(typing.Literal[model.__name__], model.__name__),
    )
    model.ReferenceSet.__pg_base_class__ = model


def build_reference_view(model: type["RootNode"]):
    extra_fields = {}

    if model.Meta.label_field:
        extra_fields[model.Meta.label_field] = build_property_type_field(
            typing.cast(
                PropertyFieldDefinition,
                model.__pg_field_definitions__[model.Meta.label_field],
            ),
            model,
        )

    model.ReferenceView = create_model(
        f"{model.__name__}ReferenceView",
        __base__=ReferenceViewBase,
        __module__=model.__module__,
        type=(typing.Literal[model.__name__], model.__name__),
    )
    unpack_fields_onto_model(model.ReferenceView, extra_fields)
    model.ReferenceView.__pg_base_class__ = model
    model.ReferenceView.model_rebuild(force=True)


def build_reference_create(model: type["RootNode"]):
    if model.Meta.create_by_reference:
        extra_fields = {}

        if model.Meta.label_field:
            extra_fields[model.Meta.label_field] = build_property_type_field(
                typing.cast(
                    PropertyFieldDefinition,
                    model.__pg_field_definitions__[model.Meta.label_field],
                ),
                model,
            )

        model.ReferenceCreate = create_model(
            f"{model.__name__}ReferenceCreate",
            __base__=ReferenceCreateBase,
            __module__=model.__module__,
            type=(typing.Literal[model.__name__], model.__name__),
        )
        unpack_fields_onto_model(model.ReferenceCreate, extra_fields)
        model.ReferenceCreate.__pg_base_class__ = model
        model.ReferenceCreate.model_rebuild(force=True)

import typing

from pydantic.fields import FieldInfo

from pangloss.model_config.models_base import ReifiedRelation, RootNode, SemanticSpace

if typing.TYPE_CHECKING:
    from pangloss.model_config.field_definitions import (
        ListFieldDefinition,
        MultiKeyFieldDefinition,
        PropertyFieldDefinition,
    )


def build_property_type_field(
    field: "PropertyFieldDefinition",
    model: type[RootNode] | type[ReifiedRelation] | type[SemanticSpace],
    bound: bool = False,
) -> FieldInfo:
    if bound:
        field_info = FieldInfo(
            annotation=typing.cast(
                type[typing.Any | None], field.field_annotation | None
            ),
            default=None,
        )
    else:
        field_info = FieldInfo(annotation=field.field_annotation)

    if field.field_name == "type":
        field_info.default = model.__name__

    if field.validators:
        field_info.metadata = field.validators

    field_info.rebuild_annotation()
    return field_info


def build_list_property_type_field(
    field: "ListFieldDefinition",
    model: type[RootNode] | type[ReifiedRelation] | type[SemanticSpace],
    bound: bool = False,
) -> FieldInfo:
    inner_type = field.field_annotation
    if field.internal_type_validators:
        inner_type = typing.Annotated[
            field.field_annotation, *field.internal_type_validators
        ]

    if bound:
        FieldInfo(
            annotation=typing.cast(type[typing.Any | None], list[inner_type] | None),
            default=None,
        )
    else:
        field_info = FieldInfo.from_annotation(list[inner_type])

    if field.validators:
        field_info.metadata = field.validators

    return field_info


def build_multikey_property_type_field(
    field: "MultiKeyFieldDefinition",
    model: type[RootNode] | type[ReifiedRelation] | type[SemanticSpace],
    bound: bool = False,
) -> FieldInfo:
    if bound:
        return FieldInfo(
            annotation=typing.cast(
                type[typing.Any | None], field.field_annotation | None
            ),
            default=None,
        )
    return FieldInfo.from_annotation(field.field_annotation)


def build_property_fields(
    model: type["RootNode | ReifiedRelation | SemanticSpace"],
    bound_field_names: set[str],
) -> dict[str, FieldInfo]:
    fields = {}
    for field in model._meta.fields.property_fields:
        is_bound = (
            bound_field_names is not None and field.field_name in bound_field_names
        )
        if field.field_metatype == "PropertyField":
            fields[field.field_name] = build_property_type_field(
                field, model, bound=is_bound
            )
        elif field.field_metatype == "ListField":
            fields[field.field_name] = build_list_property_type_field(
                field, model, bound=is_bound
            )
        elif field.field_metatype == "MultiKeyField":
            fields[field.field_name] = build_multikey_property_type_field(
                field, model, bound=is_bound
            )
    return fields

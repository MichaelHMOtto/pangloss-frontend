import types
import typing
from functools import cache

from pydantic import create_model
from pydantic.fields import FieldInfo

from pangloss.model_config.field_definitions import (
    EmbeddedFieldDefinition,
    RelationFieldDefinition,
)
from pangloss.model_config.model_setup_functions.field_builders import (
    build_property_fields,
)
from pangloss.model_config.model_setup_functions.utils import (
    get_base_models_for_relations_to_node,
    get_concrete_model_types,
    get_specialised_models_for_semantic_space,
    unpack_fields_onto_model,
)
from pangloss.model_config.models_base import (
    EdgeModel,
    EditHeadViewBase,
    EmbeddedViewBase,
    ReferenceViewBase,
    ReifiedRelation,
    ReifiedRelationViewBase,
    RootNode,
    SemanticSpace,
    SemanticSpaceViewBase,
    ViewBase,
)


def parse_union_names(t) -> str:
    if (
        getattr(t, "__origin__", None) is typing.Union
        or isinstance(t, types.UnionType)
        or t == typing.Union
    ):
        return " | ".join(a.__name__ for a in typing.get_args(t))
    return t.__name__


def get_reified_or_semantic_space_model_name(
    model: type[ReifiedRelation] | type[SemanticSpace],
) -> str:
    """Build a more elegant model name for reified models, omitting the module name
    and other ugliness"""
    origin_name = typing.cast(
        type, model.__pydantic_generic_metadata__["origin"]
    ).__name__
    args_names = [
        parse_union_names(arg) for arg in model.__pydantic_generic_metadata__["args"]
    ]
    return f"{origin_name}[{', '.join(args_names)}]"


def get_field_type_definitions(
    model: type[RootNode | ReifiedRelation | SemanticSpace],
):
    """For each type of possible field, build a dict of field name
    and pydantic tuple-type definition"""

    fields = {}
    fields.update(build_property_fields(model, set()))

    for field in model._meta.fields.relation_fields:
        fields[field.field_name] = get_relation_field(field)

    for field in model._meta.fields.embedded_fields:
        fields[field.field_name] = get_embedded_field(field, model)

    return fields


def build_edit_head_view_model(model: type[RootNode]):
    """Builds model.Create for a RootNode/ReifiedRelation where it does not exist"""

    # If model.Create already exists, return early
    if model.has_own("EditHeadView"):
        return

    # Construct class

    # To avoid recursion of self-referencing models, the create model
    # needs to be built and *then* have its fields generated and added!
    model.EditHeadView = create_model(
        f"{model.__name__}EditHeadView",
        __module__=model.__module__,
        __base__=EditHeadViewBase,
    )

    unpack_fields_onto_model(model.EditHeadView, get_field_type_definitions(model))
    model.EditHeadView.__pg_base_class__ = model
    model.EditHeadView.model_rebuild(force=True)


def build_view_model(
    model: type[RootNode] | type[ReifiedRelation] | type[SemanticSpace],
):
    # If model.Create already exists, return early
    if model.has_own("View"):
        return

    # Construct class
    if issubclass(model, ReifiedRelation):
        model.View = create_model(
            f"{get_reified_or_semantic_space_model_name(model)}View",
            __module__=model.__module__,
            __base__=ReifiedRelationViewBase,
        )

        unpack_fields_onto_model(model.View, get_field_type_definitions(model))
        model.View.__pg_base_class__ = typing.cast(
            type[ReifiedRelation], model.__pydantic_generic_metadata__["origin"]
        )
        model.View.model_rebuild(force=True)
    elif issubclass(model, SemanticSpace):
        model.View = create_model(
            f"{get_reified_or_semantic_space_model_name(model)}View",
            __module__=model.__module__,
            __base__=SemanticSpaceViewBase,
        )

        unpack_fields_onto_model(model.View, get_field_type_definitions(model))
        model.View.__pg_base_class__ = typing.cast(
            type[SemanticSpace], model.__pydantic_generic_metadata__["origin"]
        )
        model.View.model_rebuild(force=True)

    else:
        # To avoid recursion of self-referencing models, the create model
        # needs to be built and *then* have its fields generated and added!
        model.View = create_model(
            f"{model.__name__}View",
            __module__=model.__module__,
            __base__=ViewBase,
        )

        unpack_fields_onto_model(model.View, get_field_type_definitions(model))
        model.View.__pg_base_class__ = model
        model.View.model_rebuild(force=True)


@cache
def add_edge_model[T: type[ReferenceViewBase] | type[ReifiedRelationViewBase]](
    model: T,
    edge_model: EdgeModel,
) -> T:
    """Creates and returns a subclass of the model with the edge_model
    added as model.edge_properties field.

    Also stores the newly created model under model.via.<edge_model name>"""

    model_with_edge = create_model(
        f"{model.__name__}__via__{edge_model.__name__}",
        __base__=model,
        __module__=model.__module__,
        edge_properties=(edge_model, ...),
    )

    # As fields are deferred being added, just inheriting from the model class does not work
    # and we need to manually add the fields and rebuild the model_with_edge
    model_with_edge.model_fields.update(model.model_fields)
    model.via._add(edge_model_name=edge_model.__name__, model=model_with_edge)  # type: ignore

    return model_with_edge


def get_models_for_relation_field(
    field: RelationFieldDefinition,
) -> list[type[ReferenceViewBase | ReifiedRelationViewBase]]:
    """Creates a list of actual classes to be referenced by a relation"""
    related_models = []

    # Add relations_to_nodes to concrete_model_types
    for base_type in get_base_models_for_relations_to_node(field.relations_to_node):
        if field.edit_inline:
            build_view_model(base_type)
            related_models.append(base_type.View)
        else:
            related_models.append(base_type.ReferenceView)

    # Add relations_to_reified_to_concrete_model_Types
    for field_type_definition in field.relations_to_reified:
        build_view_model(field_type_definition.annotated_type)
        related_models.append(field_type_definition.annotated_type.View)

    for field_type_definition in field.relations_to_semantic_space:
        bound_types = get_specialised_models_for_semantic_space(field_type_definition)
        for bound_type in bound_types:
            build_view_model(bound_type)
            related_models.append(bound_type.View)

    return related_models


def get_relation_field(field: RelationFieldDefinition) -> FieldInfo:
    related_models = get_models_for_relation_field(field)

    if field.edge_model:
        related_models = [add_edge_model(t, field.edge_model) for t in related_models]

    # For unknown reasons, need to force rebuild models here
    for m in related_models:
        m.model_rebuild(force=True)

    field_info = FieldInfo.from_annotation(list[typing.Union[*related_models]])

    if field.validators:
        field_info.metadata = field.validators
    return field_info


def build_embedded_view_model(model: type[RootNode]) -> None:
    """Builds model.Create for a RootNode/ReifiedRelation where it does not exist"""

    # If model.Create already exists, return early
    if model.has_own("EmbeddedView"):
        return

    model.EmbeddedView = create_model(
        f"{model.__name__}EmbeddedView",
        __module__=model.__module__,
        __base__=EmbeddedViewBase,
    )
    fields = get_field_type_definitions(model)
    for field_name, field_info in fields.items():
        model.EmbeddedView.model_fields[field_name] = field_info
    model.EmbeddedView.__pg_base_class__ = model
    model.EmbeddedView.model_rebuild(force=True)


def get_models_for_embedded_field(
    field: EmbeddedFieldDefinition,
) -> list[type[EmbeddedViewBase]]:
    """Creates a list of actual classes to be embedded by a relation"""

    embedded_types = []

    for base_type in get_concrete_model_types(
        field.field_annotation, include_subclasses=True
    ):
        build_embedded_view_model(base_type)
        embedded_types.append(base_type.EmbeddedView)

    return embedded_types


def get_embedded_field(
    field: EmbeddedFieldDefinition,
    model: type["RootNode"] | type["ReifiedRelation"] | type["SemanticSpace"],
) -> FieldInfo:
    embedded_types = get_models_for_embedded_field(field)

    field_info = FieldInfo.from_annotation(list[typing.Union[*embedded_types]])
    if field.validators:
        field_info.metadata = field.validators
    return field_info

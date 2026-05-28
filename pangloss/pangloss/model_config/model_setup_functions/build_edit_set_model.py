import types
import typing
import warnings

import humps
from pydantic import AliasChoices, create_model, model_validator
from pydantic.fields import FieldInfo

from pangloss.model_config.field_definitions import (
    EmbeddedFieldDefinition,
    RelationFieldDefinition,
)
from pangloss.model_config.model_setup_functions.build_create_model import (
    add_edge_model,
    build_bound_field_creation_model,
    build_create_model,
    build_embedded_create_model,
    build_semantic_space_create_model_with_bound_model,
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
    BoundField,
    EditHeadSetBase,
    EditSetBase,
    EmbeddedCreateBase,
    EmbeddedSetBase,
    ReferenceCreateBase,
    ReferenceSetBase,
    ReifiedRelation,
    ReifiedRelationEditSetBase,
    RootNode,
    SemanticSpace,
    SemanticSpaceEditSetBase,
)

type BoundFieldsType = BoundField | tuple[str, str] | tuple[str, str, typing.Callable]


def parse_union_names(t) -> str:
    if (
        getattr(t, "__origin__", None) is typing.Union
        or isinstance(t, types.UnionType)
        or t == typing.Union
    ):
        return " | ".join(a.__name__ for a in typing.get_args(t))
    return t.__name__


def build_reified_or_semantic_space_model_name(
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


def build_field_type_definitions(
    model: type[RootNode | ReifiedRelation | SemanticSpace],
    bound_field_definitions: set[BoundFieldsType],
    top_parent_model: type[RootNode | ReifiedRelation | SemanticSpace] | None = None,
    bound_field_name: str | None = None,
):
    """For each type of possible field, build a dict of field name
    and pydantic tuple-type definition"""

    fields = {}
    bound_field_names = set([br[1] for br in bound_field_definitions])

    fields.update(build_property_fields(model, bound_field_names))
    for field in model._meta.fields.relation_fields:
        if (
            bound_field_definitions
            and issubclass(model, SemanticSpace)
            and field.field_name == "contents"
        ):
            fields[field.field_name] = build_relation_field(
                field,
                model,
                bound_fields=bound_field_definitions,
                top_parent_model=top_parent_model,
                bound_field_name=bound_field_name,
            )
        elif bound_field_definitions and field.field_name in bound_field_names:
            fields[field.field_name] = build_relation_field(
                field,
                model,
                bound_fields=bound_field_definitions,
                top_parent_model=top_parent_model,
                bound_field_name=field.field_name,
            )

        else:
            fields[field.field_name] = build_relation_field(
                field,
                model,
                bound_fields=bound_field_definitions,
                top_parent_model=top_parent_model,
                bound_field_name=field.field_name,
            )

    for field in model._meta.fields.embedded_fields:
        fields[field.field_name] = build_embedded_field(field, model)

    return fields


def build_edit_head_set_model(
    model: type[RootNode],
):
    """Builds model.Create for a RootNode/ReifiedRelation where it does not exist"""

    # If model.Create already exists, return early
    if model.has_own("EditHeadSet"):
        return

    model.EditHeadSet = create_model(
        f"{model.__name__}EditHeadSet",
        __module__=model.__module__,
        __base__=EditHeadSetBase,
    )

    unpack_fields_onto_model(
        model.EditHeadSet,
        build_field_type_definitions(
            model,
            bound_field_definitions=get_bound_relation_fields_for_parent_model(model),
            top_parent_model=model,
        ),
    )
    model.EditHeadSet.__pg_base_class__ = model
    model.EditHeadSet.set_has_bindable_relations()
    model.EditHeadSet.model_rebuild(force=True)


def build_edit_set_model(
    model: type[RootNode] | type[ReifiedRelation] | type[SemanticSpace],
):
    """Builds model.Create for a RootNode/ReifiedRelation where it does not exist"""

    # If model.Create already exists, return early
    if model.has_own("EditSet"):
        return

    # Construct class
    if issubclass(model, ReifiedRelation):
        model.EditSet = create_model(
            f"{build_reified_or_semantic_space_model_name(model)}EditSet",
            __module__=model.__module__,
            __base__=ReifiedRelationEditSetBase,
        )

        unpack_fields_onto_model(
            model.EditSet,
            build_field_type_definitions(
                model,
                bound_field_definitions=get_bound_relation_fields_for_parent_model(
                    model
                ),
            ),
        )
        model.EditSet.__pg_base_class__ = typing.cast(
            type[ReifiedRelation], model.__pydantic_generic_metadata__["origin"]
        )
        model.EditSet.model_rebuild(force=True)

    elif issubclass(model, SemanticSpace):
        model.EditSet = create_model(
            f"{build_reified_or_semantic_space_model_name(model)}EditSet",
            __module__=model.__module__,
            __base__=SemanticSpaceEditSetBase,
        )

        unpack_fields_onto_model(
            model.EditSet,
            build_field_type_definitions(
                model,
                bound_field_definitions=get_bound_relation_fields_for_parent_model(
                    model
                ),
            ),
        )
        model.EditSet.__pg_base_class__ = typing.cast(
            type[SemanticSpace], model.__pydantic_generic_metadata__["origin"]
        )
        model.EditSet.model_rebuild(force=True)

    else:
        # To avoid recursion of self-referencing models, the create model
        # needs to be built and *then* have its fields generated and added!
        model.EditSet = create_model(
            f"{model.__name__}EditSet",
            __module__=model.__module__,
            __base__=EditSetBase,
        )

        unpack_fields_onto_model(
            model.EditSet,
            build_field_type_definitions(
                model,
                bound_field_definitions=get_bound_relation_fields_for_parent_model(
                    model
                ),
                top_parent_model=model,
            ),
        )
        model.EditSet.__pg_base_class__ = model
        model.EditSet.set_has_bindable_relations()
        model.EditSet.model_rebuild(force=True)


def build_semantic_space_edit_set_model_with_bound_model(
    model: type[SemanticSpace],
    parent_model: type[RootNode] | type[ReifiedRelation] | type[SemanticSpace],
    field_name: str,
    bound_field_name: str | None = None,
):
    semantic_space_with_bound_model = create_model(
        f"{build_reified_or_semantic_space_model_name(model)}EditSet__in_context_of__{parent_model.__name__}__{field_name}",
        __module__=model.__module__,
        __base__=SemanticSpaceEditSetBase,
    )
    bound_fields_for_parent_model = get_bound_relation_fields_for_parent_model(
        parent_model
    )

    unpack_fields_onto_model(
        semantic_space_with_bound_model,
        build_field_type_definitions(
            model,
            bound_field_definitions=bound_fields_for_parent_model,
            top_parent_model=parent_model,
            bound_field_name=bound_field_name,
        ),
    )
    semantic_space_with_bound_model.__pg_base_class__ = typing.cast(
        type[ReifiedRelation], model.__pydantic_generic_metadata__["origin"]
    )
    semantic_space_with_bound_model.model_rebuild(force=True)

    model.EditSet.in_context_of._add(
        parent_model, semantic_space_with_bound_model, field_name
    )
    return semantic_space_with_bound_model


'''@cache
def add_edge_model[
    T: type[ReferenceSetBase]
    | type[ReferenceCreateBase]
    | type[ReifiedRelationEditSetBase]
    | type[CreateBase]
    | type[EditSetBase]
](
    model: T,
    edge_model: type[EdgeModel],
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
    print(model_with_edge)
    return model_with_edge'''


@model_validator(mode="after")
def bound_field_creation_model_after_validator(
    self: "EditSetBase",
) -> typing.Any:
    """Validator to validate the created object after the fields have
    been bound"""
    self.__pg_base_class__.EditSet.model_validate(self)
    return self


def build_bound_field_edit_set_model(
    field: RelationFieldDefinition,
    parent_model: type[RootNode] | type[ReifiedRelation] | type[SemanticSpace],
    base_type_for_bound_model: type[RootNode],
    bound_field_definitions: set[BoundFieldsType],
    top_parent_model: type[RootNode]
    | type[ReifiedRelation]
    | type[SemanticSpace]
    | None,
    bound_field_name: str,
):
    """Creates a variant of a model (base_type_for_bound_models) with the fields
    that are bound to the parent made optional. Also adds a validator function that
    checks the data from parent-bound fields are included"""

    # Bug with Pydantic: adding __validators__ (as per documentation) causes a
    # runtime warning that fields should not start with an underscore... but of course it can
    # so suppress the warning here
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")

        build_edit_set_model(base_type_for_bound_model)

        # Create a new model
        bound_field_model = create_model(
            f"{base_type_for_bound_model.__name__}_EditSet__in_context_of__{parent_model.__name__}__{field.field_name}",
            __base__=base_type_for_bound_model.EditSet,
            __model__=base_type_for_bound_model.__module__,
            __validators__={
                "post_validator": typing.cast(
                    typing.Callable, bound_field_creation_model_after_validator
                )
            },
        )

    unpack_fields_onto_model(
        bound_field_model,
        build_field_type_definitions(
            base_type_for_bound_model,
            bound_field_definitions,
            top_parent_model,
            bound_field_name,
        ),
    )
    bound_field_model.__pg_base_class__ = base_type_for_bound_model
    bound_field_model.model_rebuild(force=True)

    if top_parent_model:
        # Register the model using the EditSet.in_context_of mechanism
        base_type_for_bound_model.EditSet.in_context_of._add(
            relation_target_model=top_parent_model,
            view_in_context_model=bound_field_model,
            field_name=bound_field_name,
        )
    else:
        base_type_for_bound_model.EditSet.in_context_of._add(
            relation_target_model=parent_model,
            view_in_context_model=bound_field_model,
            field_name=field.field_name,
        )

    return bound_field_model


# Event.View.in_context_of.Cat.is_involved_in = ContextViewModel
#           ^target


def get_models_for_relation_field(
    field: RelationFieldDefinition,
    parent_model: type[RootNode] | type[ReifiedRelation] | type[SemanticSpace],
    bound_field_definitions: set[BoundFieldsType] | None = None,
    top_parent_model: type[RootNode]
    | type[ReifiedRelation]
    | type[SemanticSpace]
    | None = None,
    bound_field_name: str | None = None,
) -> list[type[ReferenceCreateBase | ReferenceSetBase | ReifiedRelationEditSetBase]]:
    """Creates a list of actual classes to be referenced by a relation"""
    related_models = []

    # Add relations_to_nodes to concrete_model_types
    for base_type in get_base_models_for_relations_to_node(field.relations_to_node):
        if field.edit_inline:
            # Check if any of the fields bound to parent_model field are in this model,
            # and if so, create a bound_field_model instead of the usual one
            if bound_field_definitions and any(
                bf[1] in base_type._meta.fields for bf in bound_field_definitions
            ):
                bound_field_edit_set_model = build_bound_field_edit_set_model(
                    field=field,
                    parent_model=parent_model,
                    base_type_for_bound_model=base_type,
                    bound_field_definitions=bound_field_definitions,
                    top_parent_model=top_parent_model,
                    bound_field_name=bound_field_name
                    if bound_field_name
                    else field.field_name,
                )
                related_models.append(bound_field_edit_set_model)

                bound_field_create_model = build_bound_field_creation_model(
                    field=field,
                    parent_model=parent_model,
                    base_type_for_bound_model=base_type,
                    bound_field_definitions=frozenset(bound_field_definitions),
                    top_parent_model=top_parent_model,
                    bound_field_name=bound_field_name
                    if bound_field_name
                    else field.field_name,
                )
                related_models.append(bound_field_create_model)

            else:
                build_edit_set_model(base_type)
                related_models.append(base_type.EditSet)
                build_create_model(base_type)
                related_models.append(base_type.Create)

        else:
            related_models.append(base_type.ReferenceSet)
            if base_type.Meta.create_by_reference:
                related_models.append(base_type.ReferenceCreate)

    for field_type_definition in field.relations_to_reified:
        build_edit_set_model(field_type_definition.annotated_type)
        related_models.append(field_type_definition.annotated_type.EditSet)
        build_create_model(field_type_definition.annotated_type)
        related_models.append(field_type_definition.annotated_type.Create)

    for field_type_definition in field.relations_to_semantic_space:
        specialised_generic_types = get_specialised_models_for_semantic_space(
            field_type_definition
        )
        for specialised_generic_type in specialised_generic_types:
            build_create_model(specialised_generic_type)
            related_models.append(specialised_generic_type.Create)
            build_edit_set_model(specialised_generic_type)
            related_models.append(specialised_generic_type.EditSet)
            if bound_field_definitions:
                bound_field_edit_set_model = (
                    build_semantic_space_edit_set_model_with_bound_model(
                        specialised_generic_type,
                        parent_model,
                        field.field_name,
                        bound_field_name,
                    )
                )
                related_models.append(bound_field_edit_set_model)
                bound_field_create_model = (
                    build_semantic_space_create_model_with_bound_model(
                        specialised_generic_type,
                        parent_model,
                        field.field_name,
                        bound_field_name,
                    )
                )
                related_models.append(bound_field_create_model)

            # Build a specialised create_model function for SemanticSpace,
            # forwarding bound_fields down to the next model...

    return related_models


def get_bound_relation_fields_for_parent_model(
    model: type["RootNode | SemanticSpace | ReifiedRelation"],
) -> set[BoundFieldsType]:
    bound_relations = [
        rf for rf in model._meta.fields.relation_fields if rf.bind_fields_to_related
    ]
    bound_relation_field_names = set()
    for bound_relation in bound_relations:
        assert bound_relation.bind_fields_to_related
        bound_relation_field_names.update(bound_relation.bind_fields_to_related)
    return bound_relation_field_names


def build_relation_field(
    field: RelationFieldDefinition,
    model: type["RootNode"] | type["ReifiedRelation"] | type["SemanticSpace"],
    bound_field_name: str | None,
    bound_fields: set[BoundFieldsType] | None = None,
    top_parent_model: type["RootNode"]
    | type["ReifiedRelation"]
    | type["SemanticSpace"]
    | None = None,
) -> FieldInfo:
    related_models = get_models_for_relation_field(
        field, model, bound_fields, top_parent_model, bound_field_name
    )

    if field.edge_model:
        related_models = [add_edge_model(t, field.edge_model) for t in related_models]

    # For unknown reasons, need to force rebuild models here
    for m in related_models:
        m.model_rebuild(force=True)

    if (
        bound_fields
        and not issubclass(model, SemanticSpace)
        and not field.create_inline
    ):  # If the field is bound to value from parent field, make this field optional
        field_info = FieldInfo.from_annotation(
            typing.cast(
                type[typing.Any], typing.Optional[list[typing.Union[*related_models]]]
            )
        )
        field_info.default = None
        field_info.rebuild_annotation()
    else:
        field_info = FieldInfo.from_annotation(list[typing.Union[*related_models]])

    if len(field.relation_labels) > 1:
        field_info.validation_alias = AliasChoices(
            *field.relation_labels,
            *(humps.camelize(label) for label in field.relation_labels),
        )
        field_info.alias_priority = 2

    if field.validators:
        field_info.metadata = field.validators
    return field_info


def build_embedded_set_model(model: type[RootNode]):
    """Builds model.Create for a RootNode/ReifiedRelation where it does not exist"""

    # If model.Create already exists, return early
    if model.has_own("EmbeddedSet"):
        return

    model.EmbeddedSet = create_model(
        f"{model.__name__}EmbeddedSet",
        __module__=model.__module__,
        __base__=EmbeddedSetBase,
    )
    fields = build_field_type_definitions(
        model, get_bound_relation_fields_for_parent_model(model)
    )
    for field_name, field_info in fields.items():
        model.EmbeddedSet.model_fields[field_name] = field_info
    model.EmbeddedSet.__pg_base_class__ = model
    model.EmbeddedSet.model_rebuild(force=True)


def get_models_for_embedded_field(
    field: EmbeddedFieldDefinition,
) -> list[type[EmbeddedSetBase | EmbeddedCreateBase]]:
    """Creates a list of actual classes to be embedded by a relation"""
    embedded_types = []

    for base_type in get_concrete_model_types(
        field.field_annotation, include_subclasses=True
    ):
        build_embedded_set_model(base_type)
        embedded_types.append(base_type.EmbeddedSet)
        build_embedded_create_model(base_type)
        embedded_types.append(base_type.EmbeddedCreate)

    return embedded_types


def build_embedded_field(
    field: EmbeddedFieldDefinition,
    model: type["RootNode"] | type["ReifiedRelation"] | type["SemanticSpace"],
) -> FieldInfo:
    embedded_types = get_models_for_embedded_field(field)
    field_info = FieldInfo.from_annotation(list[typing.Union[*embedded_types]])
    if field.validators:
        field_info.metadata = field.validators
    return field_info

import types
import typing

from pangloss.exceptions import PanglossConfigError
from pangloss.model_config.field_definitions import (
    RelationDefinition,
    RelationFieldDefinition,
    RelationToNodeDefinition,
    RelationToReifiedDefinition,
    SubclassedRelationNames,
    TypeParamsToTypeMap,
)
from pangloss.model_config.model_setup_functions.utils import (
    get_concrete_model_types,
)
from pangloss.model_config.models_base import (
    HeritableTrait,
    NonHeritableTrait,
    ReifiedRelation,
    RootNode,
)


def recurse_type_params_to_type_map_for_base_types(
    t: dict[str, TypeParamsToTypeMap], types
):
    tp = t[list(t.keys())[0]]
    if issubclass(tp.type, RootNode):
        types.append(tp.type)

    if hasattr(tp.type, "__pydantic_generic_metadata__") and issubclass(
        tp.type.__pydantic_generic_metadata__["args"][0],  # type: ignore
        RootNode,
    ):
        types.append(tp.type.__pydantic_generic_metadata__["args"][0])  # type: ignore


def get_types(relation_definitions: list[RelationDefinition]):
    types = []
    for rd in relation_definitions:
        if isinstance(rd, RelationToNodeDefinition):
            types.append(rd.annotated_type)
        if isinstance(rd, RelationToReifiedDefinition):
            recurse_type_params_to_type_map_for_base_types(
                rd.type_params_to_type_map, types
            )
    return types


def subclassed_relation_not_subclass_of_relation(
    current_relation_defintion: RelationFieldDefinition,
    subclassed_relation_definition: RelationFieldDefinition,
):
    """Checks whether a relation that subclasses another relation's types is a subset of the
    subclassed relation"""

    current_relation_types = []

    for t in get_types(current_relation_defintion.field_type_definitions):
        current_relation_types.extend(
            get_concrete_model_types(
                typing.cast(
                    type["RootNode"]
                    | type[HeritableTrait]
                    | type[NonHeritableTrait]
                    | types.UnionType
                    | type[ReifiedRelation],
                    t,
                ),
                include_subclasses=True,
                include_abstract=True,
            )
        )

    subclassed_relation_types = []

    for t in get_types(subclassed_relation_definition.field_type_definitions):
        subclassed_relation_types = get_concrete_model_types(
            typing.cast(
                type["RootNode"]
                | type[HeritableTrait]
                | type[NonHeritableTrait]
                | types.UnionType
                | type[ReifiedRelation],
                t,
            ),
            include_subclasses=True,
            include_abstract=True,
        )

    if not all(
        t in subclassed_relation_types for t in current_relation_types
    ) or not any(t in current_relation_types for t in subclassed_relation_types):
        return True

    return False


def initialise_subclassed_relations(model: type[RootNode]):
    """Identifies relation fields that override another inherited relation and
    removes the inherited relation field from the class, adding its relation-
    and reverse-relation labels to the field definition;

    This relies on the assumption that fields declared in parent models will be tackled first
    (which seems reasonable)"""

    for relation_definition in model._meta.fields.relation_fields:
        # Add the names of the field itself to the relation_labels for convenience
        relation_definition.relation_labels.add(relation_definition.field_name)
        relation_definition.reverse_relation_labels.add(
            relation_definition.reverse_name
        )

        if relation_definition.subclasses_relation:
            for subclassed_relation_name in relation_definition.subclasses_relation:
                # Check we are actually trying to subclass something that exists
                # on the class
                if subclassed_relation_name not in model._meta.fields:
                    raise PanglossConfigError(
                        f"Relation '{model.__name__}.{relation_definition.field_name}' "
                        f"is trying to subclass the relation "
                        f"'{subclassed_relation_name}', but this "
                        f"does not exist on any parent class of '{model.__name__}'"
                    )

                if subclassed_relation_not_subclass_of_relation(
                    relation_definition,
                    typing.cast(
                        RelationFieldDefinition,
                        model._meta.fields[subclassed_relation_name],
                    ),
                ):
                    raise PanglossConfigError(
                        f"Relation '{model.__name__}.{relation_definition.field_name}' "
                        f"is trying to subclass the relation '{subclassed_relation_name}', "
                        f"but the type of '{relation_definition.field_name}' ({relation_definition.field_annotation})"
                        f"is not a subset of the type of '{subclassed_relation_name} ({model._meta.fields[subclassed_relation_name].field_annotation})'"
                    )

                # Add the relation labels from the inherited field
                relation_definition.relation_labels.update(
                    typing.cast(
                        RelationFieldDefinition,
                        model._meta.fields[subclassed_relation_name],
                    ).relation_labels
                )

                # Add reverse relation labels from inherited field
                relation_definition.reverse_relation_labels.update(
                    typing.cast(
                        RelationFieldDefinition,
                        model._meta.fields[subclassed_relation_name],
                    ).reverse_relation_labels
                )

                relation_definition.subclassed_relations.update(
                    (
                        SubclassedRelationNames(f, r)
                        for f, r in zip(
                            typing.cast(
                                RelationFieldDefinition,
                                model._meta.fields[subclassed_relation_name],
                            ).relation_labels,
                            typing.cast(
                                RelationFieldDefinition,
                                model._meta.fields[subclassed_relation_name],
                            ).reverse_relation_labels,
                        )
                    )
                )

                del model._meta.fields[subclassed_relation_name]

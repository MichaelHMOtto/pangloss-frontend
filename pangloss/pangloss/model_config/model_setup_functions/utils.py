import inspect
import types
import typing

from pangloss.model_config.field_definitions import (
    RelationToNodeDefinition,
    RelationToSemanticSpaceDefinition,
)
from pangloss.model_config.model_setup_functions.build_pg_annotations import (
    build_pg_annotations,
)
from pangloss.model_config.model_setup_functions.build_pg_model_definition import (
    build_pg_bound_model_definition_for_instatiated_semantic_space,
    build_pg_model_definitions,
)
from pangloss.model_config.model_setup_functions.build_semantic_space_meta import (
    initialise_semantic_space_meta_inheritance,
)
from pangloss.model_config.models_base import (
    HeritableTrait,
    NonHeritableTrait,
    ReifiedRelation,
    RootNode,
    SemanticSpace,
)
from pangloss.models import BaseNode
from pydantic import BaseModel
from pydantic.fields import FieldInfo


# TODO: This is not necessary at all as far as I can tell
def generic_get_subclasses[T](cls: type[T] | None) -> set[type[T]] | set:
    if not cls:
        return set()
    subclasses = []
    for subclass in cls.__subclasses__():
        subclasses.append(subclass)
        subclasses.extend(generic_get_subclasses(subclass))

    return set(subclasses)


def get_all_subclasses(cls, include_abstract: bool = False) -> set[type["BaseNode"]]:
    """Get all subclasses of a BaseNode type"""

    subclasses = []
    for subclass in cls.__subclasses__():
        if not subclass._meta.abstract or include_abstract:
            subclasses += [subclass, *get_all_subclasses(subclass)]
        else:
            subclasses += get_all_subclasses(subclass)
    return set(subclasses)


def get_trait_subclasses(
    trait: type[HeritableTrait] | type[NonHeritableTrait],
) -> set[type[HeritableTrait] | type[NonHeritableTrait]]:
    """Get subclasses of a Trait that are Traits, not instantiations
    of a Trait"""

    subclasses = [trait]
    for subclass in trait.__subclasses__():
        if model_is_trait(subclass):
            subclasses.extend(get_trait_subclasses(subclass))
    return set(subclasses)


def is_subclass_of_heritable_trait(
    cls: type[HeritableTrait] | type[NonHeritableTrait],
) -> bool:
    """Determine whether a class is a subclass of a Trait,
    not the application of a trait to a real BaseNode class.

    This should work by not having BaseNode in its class hierarchy
    """
    for parent in cls.mro()[1:]:
        if issubclass(parent, BaseNode):
            return False
    else:
        return True


def model_is_trait(
    cls: type[BaseNode] | type[HeritableTrait] | type[NonHeritableTrait],
):
    """Determines whether a model is a Trait, or subclass of a Trait,
    rather than a BaseNode type to which a Trait has been applied"""

    return (
        inspect.isclass(cls)
        and issubclass(cls, (HeritableTrait, NonHeritableTrait))
        and is_subclass_of_heritable_trait(cls)
    )


def get_direct_instantiations_of_trait(
    trait: type[HeritableTrait] | type[NonHeritableTrait],
    follow_trait_subclasses: bool = False,
):
    """Given a Trait class, find the models to which it is *directly* applied,
    i.e. omitting children"""

    if follow_trait_subclasses:
        trait_subclasses = [
            trait_subclass for trait_subclass in get_trait_subclasses(trait)
        ]
        instantiations_of_trait = []
        for trait_subclass in trait_subclasses:
            instantiations_of_trait.extend(
                subclass
                for subclass in trait_subclass.__subclasses__()
                if issubclass(subclass, BaseNode)
            )
        return set(instantiations_of_trait)

    return set(
        [
            subclass
            for subclass in trait.__subclasses__()
            if issubclass(subclass, BaseNode)
        ]
    )


def get_subclasses_of_reified_relations(cls: type[ReifiedRelation]):
    """Gets the subclasses of a ReifiedRelation, with following rules:

    Where a generic type is passed with a type argument, the subclasses are found
    and applied with the same argument.

    Where a ReifiedRelation has a type already manually bound, the subclasses of
    this class are found.
    """

    # If it is a generic type...
    if origin_type := cls.__pydantic_generic_metadata__.get("origin", False):
        subclasses = set()
        # ... get all the subclasses of the generic type...
        for subclass in generic_get_subclasses(origin_type):
            origin = subclass.__pydantic_generic_metadata__.get("origin", False)
            args = subclass.__pydantic_generic_metadata__.get("args", False)
            # ... and, checking the wrapped type is something real...
            if (
                args
                and inspect.isclass(args[0])
                and (
                    issubclass(
                        args[0],
                        (BaseNode, ReifiedRelation, HeritableTrait, NonHeritableTrait),
                    )
                    or (
                        typing.get_origin(args[0]) is types.UnionType
                        or typing.get_origin(args[0]) == typing.Union
                    )
                )
            ):
                # ...get the subclasses of that type which are generic (i.e. have "parameters")
                subclasses.add(subclass)
                # ... get all the subclasses of that, and construct types out of that
                # by applying the original arg
                for ssc in generic_get_subclasses(origin):
                    if ssc.__pydantic_generic_metadata__.get("parameters"):
                        subclasses.add(ssc[*args])  # type: ignore
        return subclasses
    else:
        # Otherwise, it's a non-generic type; just get the subclasses and itself
        return set([cls, *generic_get_subclasses(cls)])


def get_concrete_model_types(
    classes: type["RootNode"]
    | type[HeritableTrait]
    | type[NonHeritableTrait]
    | types.UnionType
    | type[ReifiedRelation],
    include_subclasses: bool = False,
    include_abstract: bool = False,
    include_self: bool = True,
    follow_trait_subclasses: bool = False,
) -> set[type[BaseNode]]:
    concrete_model_types = []

    if (
        typing.get_origin(classes) is types.UnionType
        or typing.get_origin(classes) == typing.Union
    ):
        for cl in typing.get_args(classes):
            concrete_model_types.extend(
                get_concrete_model_types(
                    cl,
                    include_abstract=include_abstract,
                    include_subclasses=include_subclasses,
                )
            )
    elif (
        inspect.isclass(classes)
        and issubclass(classes, HeritableTrait)
        and model_is_trait(classes)
    ):
        for instantiated_trait in get_direct_instantiations_of_trait(
            classes, follow_trait_subclasses=follow_trait_subclasses
        ):
            if not instantiated_trait._meta.abstract or include_abstract:
                concrete_model_types.append(instantiated_trait)

            if include_subclasses:
                concrete_model_types.extend(
                    get_all_subclasses(
                        instantiated_trait, include_abstract=include_abstract
                    )
                )
    elif (
        inspect.isclass(classes)
        and issubclass(classes, NonHeritableTrait)
        and model_is_trait(classes)
    ):
        for instantiated_trait in get_direct_instantiations_of_trait(
            classes, follow_trait_subclasses=follow_trait_subclasses
        ):
            if not instantiated_trait._meta.abstract or include_abstract:
                concrete_model_types.append(instantiated_trait)
    elif inspect.isclass(classes) and issubclass(classes, ReifiedRelation):
        concrete_model_types.append(classes)

    elif inspect.isclass(classes) and issubclass(classes, BaseNode):
        if not classes._meta.abstract or include_abstract:
            concrete_model_types.append(classes)

        if include_subclasses:
            concrete_model_types.extend(
                get_all_subclasses(classes, include_abstract=include_abstract)
            )

    return typing.cast(set[type[BaseNode]], set(concrete_model_types))


def get_base_models_for_relations_to_node(
    relations_to_node: list[RelationToNodeDefinition],
) -> list[type[RootNode]]:
    related_node_base_type: list[type[RootNode]] = []
    for field_type_definition in relations_to_node:
        related_node_base_type.extend(
            get_concrete_model_types(
                field_type_definition.annotated_type,
                include_subclasses=True,
                follow_trait_subclasses=True,
            )
        )

    return related_node_base_type


def get_root_semantic_space_subclasses(
    cls: type[SemanticSpace],
) -> set[type[SemanticSpace]]:
    if not cls:
        return set()
    subclasses = []

    if not cls.__pydantic_generic_metadata__["origin"] and not cls._meta.abstract:
        subclasses.append(cls)

    for subclass in cls.__subclasses__():
        if (
            not subclass.__pydantic_generic_metadata__["origin"]
            and not subclass._meta.abstract
        ):
            subclasses.append(subclass)
        subclasses.extend(get_root_semantic_space_subclasses(subclass))

    return set(subclasses)


def get_specialised_models_for_semantic_space(
    relation_to_semantic_space: RelationToSemanticSpaceDefinition,
) -> set[type[SemanticSpace]]:
    """Get unbound base semantic space models for a relation"""

    from pangloss.model_config.model_manager import ModelManager

    root_semantic_space_subclasses = get_root_semantic_space_subclasses(
        relation_to_semantic_space.origin_type
    )
    bound_types = []
    for unbound_model_type in root_semantic_space_subclasses:
        generic_type_arg = relation_to_semantic_space.type_params_to_type_map[
            str(unbound_model_type.__pydantic_generic_metadata__["parameters"][0])
        ].type

        bound_model = ModelManager.semantic_space_models[
            unbound_model_type[generic_type_arg].__name__  # type: ignore
        ]
        if not getattr(bound_model, "__pg__pg_bound_field_definitions__", None):
            initialise_semantic_space_meta_inheritance(bound_model)
            build_pg_annotations(bound_model)
            build_pg_model_definitions(bound_model)
            build_pg_bound_model_definition_for_instatiated_semantic_space(bound_model)
        bound_types.append(bound_model)
    return set(bound_types)


def unpack_fields_onto_model(
    model: type[BaseModel], field_definitions: dict[str, FieldInfo]
):
    for field_name, field_info in field_definitions.items():
        model.model_fields[field_name] = field_info

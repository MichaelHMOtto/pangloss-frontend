import dataclasses
import datetime
import inspect
import types
import typing
from enum import Enum

import annotated_types
from pydantic import BaseModel

from pangloss.exceptions import PanglossConfigError
from pangloss.model_config.field_definitions import (
    EmbeddedFieldDefinition,
    EnumFieldDefinition,
    FieldDefinition,
    ListFieldDefinition,
    ModelFieldDefinitions,
    MultiKeyFieldDefinition,
    PropertyFieldDefinition,
    RelationDefinition,
    RelationFieldDefinition,
    RelationToNodeDefinition,
    RelationToReifiedDefinition,
    RelationToSemanticSpaceDefinition,
    RelationToTypeVarDefinition,
    TypeParamsToTypeMap,
    annotation_types,
)
from pangloss.model_config.model_manager import ModelManager
from pangloss.model_config.models_base import (
    AbstractBaseMeta,
    EdgeModel,
    EmbeddedCreateBase,
    MultiKeyField,
    ReferenceSetBase,
    ReferenceViewBase,
    ReifiedBase,
    ReifiedRelation,
    RelationConfig,
    RootNode,
    SemanticSpace,
    Trait,
    ViewBase,
    _BaseClassProxy,
)
from pangloss.models import Embedded


def get_relation_config_from_field_metadata(
    field_metadata: tuple[typing.Any], field_name: str, model: typing.Any
) -> RelationConfig:
    try:
        return [
            metadata_item
            for metadata_item in field_metadata
            if isinstance(metadata_item, RelationConfig)
        ][0]
    except IndexError:
        raise PanglossConfigError(
            f"Relation field {field_name} on model {model.__name__} is missing a RelationConfig object"
        )


def is_relation_field__(
    annotation,
    field_name: str,
    model: type[RootNode]
    | type[ReifiedRelation]
    | type[ReferenceSetBase]
    | type[MultiKeyField]
    | type[EdgeModel]
    | type[ReferenceViewBase]
    | type[EmbeddedCreateBase]
    | type[ViewBase],
) -> bool:
    type_origin = typing.get_origin(annotation)

    field_annotation = typing.get_args(annotation)[0]

    relation_config = get_relation_config_from_field_metadata(
        typing.get_args(annotation)[1:], field_name=field_name, model=model
    )

    # If annotation type is a Union
    if (
        type_origin is types.UnionType or type_origin == typing.Union
    ) and relation_config:
        union_types = typing.get_args(field_annotation)

        # Check all args to Union are RootNode or ReifiedRelation subclasses
        if all(
            (inspect.isclass(t) and issubclass(t, (RootNode, ReifiedRelation, Trait)))
            for t in union_types
        ):
            return True

        # Otherwise, throw an error
        else:
            raise PanglossConfigError(
                f"Field '{field_name}' on model '{model.__name__}' is a union of types that are not a BaseNode or ReifiedRelation"
            )

    # If annotation type is a ReifiedRelation...
    if (
        field_annotation
        and inspect.isclass(field_annotation)
        and issubclass(field_annotation, ReifiedRelation)
        and relation_config
    ):
        return True

    # If annotation type is a RootNode or Trait...
    if (
        field_annotation
        and inspect.isclass(field_annotation)
        and issubclass(field_annotation, (RootNode, Trait))
        and relation_config
    ):
        return True
    return False


def pg_is_subclass(
    cls: typing.Any, parent_classes: tuple[typing.Any, ...] | typing.Any
) -> bool:
    """Checks whether at least one parent_class is in cls.mro()

    Use instead of builtin issubclass, which does not seem to work
    on resolved typing.ForwardRef
    """
    if not isinstance(parent_classes, tuple):
        parent_classes = (parent_classes,)
    for parent_class in parent_classes:
        if not hasattr(cls, "mro"):
            continue
        if parent_class in cls.mro():
            return True
    return False


def resolve_forward_ref(annotation: typing.Any):
    if isinstance(annotation, str):
        annotation = typing.ForwardRef(annotation)

    if not isinstance(annotation, (typing.ForwardRef)):
        return annotation

    for f in inspect.stack():
        try:
            frame = f.frame

            resolved_cls = annotation._evaluate(
                globalns={
                    **frame.f_globals,
                    **ModelManager.base_models,
                    **ModelManager.reified_relation_models,
                    **ModelManager.edge_models,
                    **ModelManager.multikeyfields_models,
                    **ModelManager.trait_models,
                    **ModelManager.semantic_space_models,
                },
                localns={**frame.f_locals, **locals()},
                type_params=(),
                recursive_guard=frozenset(),
            )

            return resolved_cls
        except NameError:
            pass

    return annotation


def build_relation_fields_definitions(
    field_name: str, annotation: typing.Any, model, primary_type
) -> list[RelationDefinition]:
    """Possible primary_types:

    RootNode -> [RelationDefinition] TICK
    Union[RootNode | ReifiedRelation[RootNode]] -> [RelationDefinition, ReifiedRelationDefinition] TICK
    ReifiedRelation[RootNode] -> [ReifiedRelationDefinition] TICK
    ReifiedRelation[Union[RootNode | ReifiedRelation]] -> ReifiedRelationDefinition
    """

    if isinstance(primary_type, typing.TypeVar):
        return [
            RelationToTypeVarDefinition(
                field_name=field_name,
                field_annotation=primary_type,
                annotated_type=primary_type,
                typevar_name=primary_type.__name__,
            )
        ]

    # If the primary type is a ReifiedRelation, it is a ReifiedRelation
    elif issubclass(primary_type, ReifiedRelation):
        possible_generic_type = typing.cast(
            type[ReifiedRelation], primary_type.__pydantic_generic_metadata__["origin"]
        )

        inner_types = primary_type.__pydantic_generic_metadata__["args"]
        inner_types = typing.cast(
            list[type[RootNode | ReifiedRelation]],
            [resolve_forward_ref(inner_type) for inner_type in inner_types],
        )

        type_param_to_types_map = {
            type_param.__name__: TypeParamsToTypeMap(type_param, real_type)
            for type_param, real_type in zip(
                possible_generic_type.__parameters__, inner_types
            )
        }

        return [
            RelationToReifiedDefinition(
                field_name=field_name,
                field_annotation=primary_type,
                annotated_type=primary_type,
                origin_type=possible_generic_type,
                type_params_to_type_map=type_param_to_types_map,
            )
        ]
    elif issubclass(primary_type, SemanticSpace):
        possible_generic_type = typing.cast(
            type[SemanticSpace], primary_type.__pydantic_generic_metadata__["origin"]
        )

        inner_types = primary_type.__pydantic_generic_metadata__["args"]
        inner_types = typing.cast(
            list[type[RootNode | ReifiedRelation]],
            [resolve_forward_ref(inner_type) for inner_type in inner_types],
        )

        type_param_to_types_map = {
            type_param.__name__: TypeParamsToTypeMap(type_param, real_type)
            for type_param, real_type in zip(
                possible_generic_type.__parameters__, inner_types
            )
        }

        return [
            RelationToSemanticSpaceDefinition(
                field_name=field_name,
                field_annotation=primary_type,
                annotated_type=primary_type,
                origin_type=possible_generic_type,
                type_params_to_type_map=type_param_to_types_map,
            )
        ]

    # Check whether the Annotated[Type, ...] is to a related model
    elif pg_is_subclass(primary_type, (RootNode, Trait)):
        return [
            RelationToNodeDefinition(
                field_name=field_name,
                field_annotation=primary_type,
                annotated_type=primary_type,
            )
        ]

    else:
        return []


def is_annotated(ann: typing.Any) -> bool:
    return typing.get_origin(ann) is typing.Annotated


def is_union(ann: typing.Any) -> bool:
    # Check if is a union type via various mechanisms:
    # - Union of RootNode and ReifiedRelation can only be checked by __origin__
    # - Union of other types using "|" syntax are instances of types.UnionType
    # - Union of other types using typing.Union are equal to typing.Union
    return (
        getattr(ann, "__origin__", None) is typing.Union
        or isinstance(ann, types.UnionType)
        or ann == typing.Union
    )


def build_field_definition(
    field_name: str,
    annotation: typing.Any,
    model: type[RootNode]
    | type[ReifiedBase]
    | type[EdgeModel]
    | type[MultiKeyField]
    | type["SemanticSpace"]
    | type[_BaseClassProxy],
    default_value: typing.Any | None = None,
) -> FieldDefinition | None:
    # Handle annotated types, normally indicative of a relation but not necessarily:
    # Annotated[RelatedType, RelationConfig] or Annotated[str, some_validator]

    annotation = resolve_forward_ref(annotation)

    # Find derived Meta declarations on classes and don't make into a field!
    if (
        typing.get_origin(annotation) is typing.ClassVar
        and typing.get_args(annotation)
        and issubclass(
            typing.get_args(typing.get_args(annotation)[0])[0], AbstractBaseMeta
        )
    ):
        return None

    if issubclass(model, (ReifiedBase, EdgeModel, SemanticSpace)):
        # ReifiedBase/SemanticSpace is already necessarily a pydantic.BaseModel, which interprets
        # the annotation as a string; so need to do the actual lookups of types on the model
        # and then can reconstruct the type back to the unadulterated Python format
        # i.e. typing.Annotated[<Type>, *<Metadata>]
        # so we can use the same code below
        if (
            typing.get_args(annotation)
            and inspect.isclass(typing.get_args(annotation)[0])
            and issubclass(typing.get_args(annotation)[0], AbstractBaseMeta)
        ):
            return None

        primary_type = model.model_fields[field_name].annotation

        if metadata := model.model_fields[field_name].metadata:
            annotation = typing.Annotated[primary_type, *metadata]

    elif is_annotated(annotation):
        # If it is an annotation, unpack to get the primary type
        validators = []
        # Get the first argument from the Annotated: should be the actual type
        primary_type = typing.get_args(annotation)[0]

        # Resolve any forward refs if required
        primary_type = resolve_forward_ref(primary_type)

    else:
        annotation = resolve_forward_ref(annotation)

    if is_annotated(annotation) and isinstance(primary_type, typing.TypeVar):
        relation_fields_definitions = build_relation_fields_definitions(
            field_name=field_name,
            annotation=annotation,
            model=model,
            primary_type=primary_type,
        )

        relation_config = get_relation_config_from_field_metadata(
            typing.get_args(annotation)[1:], field_name=field_name, model=model
        )

        # Check the annotation for additional validators
        additional_validators = [
            metadata_item
            for metadata_item in typing.get_args(annotation)
            if isinstance(metadata_item, annotated_types.BaseMetadata)
        ]

        # Convert relation_config to dict for splat-unpacking below
        relation_config_dict = dataclasses.asdict(relation_config)

        # Update the validators in the relation_config_dict to include
        # additional_validators. n.b. must be done after converting to dict
        # as relation_config validators will have been turned to dict!
        relation_config_dict["validators"] = [
            *relation_config.validators,
            *additional_validators,
        ]

        field_definition = RelationFieldDefinition(
            field_name=field_name,
            field_annotation=primary_type,
            field_type_definitions=relation_fields_definitions,
            containing_model=model,
            **relation_config_dict,
        )
        return field_definition

    if is_annotated(annotation) and is_union(primary_type):
        # Union can be of RootNode/ReifiedRelation type or literal
        # If literal, raise error

        union_types = typing.get_args(primary_type)

        if not all(
            pg_is_subclass(t, (RootNode, Trait, ReifiedRelation, SemanticSpace))
            for t in union_types
        ):
            raise PanglossConfigError(
                f"{field_name} on {model.__name__} contains a mix of relations"
                " and literal value types, or a mix of literal value types"
            )

        relation_fields_definitions = []
        for union_type in union_types:
            relation_fields_definitions.extend(
                build_relation_fields_definitions(
                    field_name=field_name,
                    annotation=annotation,
                    model=model,
                    primary_type=union_type,
                )
            )

        relation_config = get_relation_config_from_field_metadata(
            typing.get_args(annotation)[1:], field_name=field_name, model=model
        )

        # Check the annotation for additional validators
        additional_validators = [
            metadata_item
            for metadata_item in typing.get_args(annotation)
            if isinstance(metadata_item, annotated_types.BaseMetadata)
        ]

        # Convert relation_config to dict for splat-unpacking below
        relation_config_dict = dataclasses.asdict(relation_config)

        # Update the validators in the relation_config_dict to include
        # additional_validators. n.b. must be done after converting to dict
        # as relation_config validators will have been turned to dict!
        relation_config_dict["validators"] = [
            *relation_config.validators,
            *additional_validators,
        ]

        field_definition = RelationFieldDefinition(
            containing_model=model,
            field_name=field_name,
            field_annotation=typing.cast(type[RootNode], primary_type),
            field_type_definitions=relation_fields_definitions,
            **relation_config_dict,
        )

        return field_definition

    if is_annotated(annotation) and pg_is_subclass(
        primary_type, (RootNode, ReifiedRelation, Trait, SemanticSpace)
    ):
        # If primary type is one class, build relation_definition here and get
        # relation fields definitions
        relation_fields_definitions = build_relation_fields_definitions(
            field_name=field_name,
            annotation=annotation,
            model=model,
            primary_type=primary_type,
        )
        # Get the RelationConfig instance from annotation
        relation_config = get_relation_config_from_field_metadata(
            typing.get_args(annotation)[1:], field_name=field_name, model=model
        )

        # Check the annotation for additional validators
        additional_validators = [
            metadata_item
            for metadata_item in typing.get_args(annotation)
            if isinstance(metadata_item, annotated_types.BaseMetadata)
        ]

        # Convert relation_config to dict for splat-unpacking below
        relation_config_dict = dataclasses.asdict(relation_config)

        # Update the validators in the relation_config_dict to include
        # additional_validators. n.b. must be done after converting to dict
        # as relation_config validators will have been turned to dict!
        relation_config_dict["validators"] = [
            *relation_config.validators,
            *additional_validators,
        ]

        field_definition = RelationFieldDefinition(
            containing_model=model,
            field_name=field_name,
            field_annotation=typing.cast(type[RootNode], primary_type),
            field_type_definitions=relation_fields_definitions,
            **relation_config_dict,
        )

        return field_definition

    if (
        is_annotated(annotation)
        and typing.get_origin(primary_type) is list
        and is_annotated(typing.get_args(primary_type)[0])
    ):
        # Annotation of list and inner type, e.g.
        # Annotated[list[Annotated[str, MaxLen(10)]], MaxLen(2)]

        inner_type = typing.get_args(typing.get_args(primary_type)[0])[0]
        validators = [
            metadata_item
            for metadata_item in typing.get_args(annotation)
            if isinstance(metadata_item, annotated_types.BaseMetadata)
        ]
        internal_type_validators = [
            metadata_item
            for metadata_item in typing.get_args(typing.get_args(primary_type)[0])
            if isinstance(metadata_item, annotated_types.BaseMetadata)
        ]
        return ListFieldDefinition(
            field_name=field_name,
            field_annotation=inner_type,
            validators=validators,
            internal_type_validators=internal_type_validators,
        )

    if is_annotated(annotation) and typing.get_origin(primary_type) is list:
        # Annotation of list type
        # Annotated[list[str], MaxLen(2)]
        validators = [
            metadata_item
            for metadata_item in typing.get_args(annotation)
            if isinstance(metadata_item, annotated_types.BaseMetadata)
        ]
        return ListFieldDefinition(
            field_name=field_name,
            field_annotation=typing.get_args(primary_type)[0],
            validators=validators,
        )

    if (
        is_annotated(annotation)
        and typing.get_origin(typing.get_args(annotation)[0]) is Embedded
    ):
        inner_type = typing.get_args(typing.get_args(annotation)[0])[0]
        inner_type = resolve_forward_ref(inner_type)
        inner_type = typing.cast(type[RootNode], inner_type)
        validators = [
            metadata_item
            for metadata_item in typing.get_args(annotation)
            if isinstance(metadata_item, annotated_types.BaseMetadata)
        ]
        return EmbeddedFieldDefinition(
            field_name=field_name,
            field_annotation=inner_type,
            validators=validators,
        )

    if (
        is_annotated(annotation)
        and primary_type
        and not isinstance(primary_type, typing.ForwardRef)
    ):
        # Annotation of base property type
        # e.g. Annotated[str, MaxLen(10)]

        validators = [
            metadata_item
            for metadata_item in typing.get_args(annotation)
            if isinstance(metadata_item, annotated_types.BaseMetadata)
        ]

        return PropertyFieldDefinition(
            field_name=field_name,
            field_annotation=primary_type,
            validators=validators,
            default_value=default_value,
        )
    if typing.get_origin(annotation) is list and is_annotated(
        typing.get_args(annotation)[0]
    ):
        # List of annotated type
        # e.g. list[typing.Annotated[str, annotated_types.MaxLen(1)]]

        internal_type_validators = [
            metadata_item
            for metadata_item in typing.get_args(typing.get_args(annotation)[0])
            if isinstance(metadata_item, annotated_types.BaseMetadata)
        ]
        return ListFieldDefinition(
            field_name=field_name,
            field_annotation=typing.get_args(typing.get_args(annotation)[0])[0],
            internal_type_validators=internal_type_validators,
        )

    if typing.get_origin(annotation) is Embedded and is_union(
        inner_type := resolve_forward_ref(typing.get_args(annotation)[0])
    ):
        if not all(
            pg_is_subclass(t, (RootNode, Trait)) for t in typing.get_args(inner_type)
        ):
            raise PanglossConfigError(
                f"{model.__name__} {field_name}: cannot embed a literal typing, only subclass of BaseNode"
            )

        inner_type = typing.cast(types.UnionType, inner_type)

        return EmbeddedFieldDefinition(
            field_name=field_name, field_annotation=inner_type
        )

    if typing.get_origin(annotation) is Embedded:
        inner_type = resolve_forward_ref(typing.get_args(annotation)[0])
        if not pg_is_subclass(inner_type, (RootNode,)):
            raise PanglossConfigError(
                f"{model.__name__} {field_name}: cannot embed a literal type, only subclass of BaseNode"
            )
        inner_type = typing.cast(type[RootNode], inner_type)
        return EmbeddedFieldDefinition(
            field_name=field_name, field_annotation=inner_type
        )

    if typing.get_origin(annotation) is list:
        # List of base property type
        # e.g. list[str]
        return ListFieldDefinition(
            field_name=field_name,
            field_annotation=typing.get_args(annotation)[0],
        )

    if inspect.isclass(annotation) and issubclass(annotation, MultiKeyField):
        multi_key_field_type = typing.cast(
            type[MultiKeyField], annotation.__pydantic_generic_metadata__["origin"]
        )
        multi_key_field_value_type = annotation.__pydantic_generic_metadata__["args"][0]
        multi_key_field_value_validators = []

        # If the inner type is Annotated, get the primary type and search
        # for potential validators among the annotations
        if typing.get_origin(multi_key_field_value_type) is typing.Annotated:
            multi_key_field_value_validators = [
                item
                for item in typing.get_args(multi_key_field_value_type)
                if isinstance(item, annotated_types.BaseMetadata)
            ]
            multi_key_field_value_type = typing.get_args(multi_key_field_value_type)[0]

        return MultiKeyFieldDefinition(
            field_name=field_name,
            field_annotation=annotation,
            multi_key_field_type=multi_key_field_type,
            multi_key_field_value_type=multi_key_field_value_type,
            multi_key_field_value_validators=multi_key_field_value_validators,
        )

    if inspect.isclass(annotation) and issubclass(annotation, Enum):
        return EnumFieldDefinition(field_name=field_name, field_annotation=annotation)

    # Checks to make sure that anything that is a Meta class of any sort is
    # not turned into a FieldDefinition
    if (
        typing.get_args(annotation)
        and inspect.isclass(typing.get_args(annotation)[0])
        and issubclass(typing.get_args(annotation)[0], AbstractBaseMeta)
    ):
        return None

    return PropertyFieldDefinition[annotation](
        field_name=field_name, field_annotation=annotation, default_value=default_value
    )


def build_pg_model_definitions(
    model: type["RootNode"]
    | type["ReifiedBase"]
    | type["EdgeModel"]
    | type["MultiKeyField"]
    | type["SemanticSpace"],
) -> None:
    field_definitions = {}
    for field_name, annotation in model.__pg_annotations__.items():
        if (
            issubclass(model, BaseModel)
            and field_name != "type"
            and field_name in model.model_fields
            and isinstance(
                model.model_fields[field_name].default,
                (
                    bool,
                    int,
                    float,
                    str,
                    datetime.date,
                    datetime.timedelta,
                    datetime.datetime,
                    Enum,
                ),
            )
        ):
            default_value = model.model_fields[field_name].default
        elif getattr(model, field_name, None) and field_name != "type":
            default_value = getattr(model, field_name, None)
        else:
            default_value = None

        definition = build_field_definition(
            field_name=field_name,
            annotation=annotation,
            model=model,
            default_value=default_value,
        )
        if definition:
            field_definitions[field_name] = definition

    model.__pg_field_definitions__ = ModelFieldDefinitions(field_definitions)


class BaseModelBaseClassProxy(BaseModel, _BaseClassProxy):
    __pg_annotations__: typing.ClassVar[dict[str, typing.Any]]


def build_abstract_specialist_type_model_definitions(
    model: type[BaseModelBaseClassProxy],
):
    field_definitions = {}
    for field_name, annotation in model.__pg_annotations__.items():
        if field_name in model.__class_vars__:
            continue
        field_definitions[field_name] = build_field_definition(
            field_name,
            annotation,
            model=model,
            default_value=field_name != "type" and getattr(model, field_name, None),
        )

    model.__pg_specialist_type_fields_definitions__ = ModelFieldDefinitions(
        field_definitions
    )


def create_relation_with_bound_type(
    field_name: str,
    bound_type: type[RootNode] | type[ReifiedRelation] | type[SemanticSpace],
) -> RelationDefinition:
    if pg_is_subclass(bound_type, RootNode):
        return RelationToNodeDefinition(
            field_name=field_name,
            field_annotation=typing.cast(type[RootNode], bound_type),
            annotated_type=typing.cast(type[RootNode], bound_type),
        )

    elif pg_is_subclass(bound_type, ReifiedRelation):
        bound_type = typing.cast(type[ReifiedRelation], bound_type)

        build_pg_bound_model_definition_for_instatiated_reified(bound_type)

        origin_type = typing.cast(
            type[ReifiedRelation], bound_type.__pydantic_generic_metadata__["origin"]
        )

        inner_types = bound_type.__pydantic_generic_metadata__["args"]
        inner_types = typing.cast(
            list[type[RootNode | ReifiedRelation]],
            [resolve_forward_ref(inner_type) for inner_type in inner_types],
        )

        type_param_to_types_map = {
            type_param.__name__: TypeParamsToTypeMap(type_param, real_type)
            for type_param, real_type in zip(origin_type.__parameters__, inner_types)
        }
        return RelationToReifiedDefinition(
            field_name=field_name,
            field_annotation=bound_type,
            annotated_type=bound_type,
            origin_type=origin_type,
            type_params_to_type_map=type_param_to_types_map,
        )

    elif pg_is_subclass(bound_type, SemanticSpace):
        bound_type = typing.cast(type[SemanticSpace], bound_type)

        build_pg_bound_model_definition_for_instatiated_semantic_space(bound_type)

        origin_type = typing.cast(
            type[SemanticSpace], bound_type.__pydantic_generic_metadata__["origin"]
        )

        inner_types = bound_type.__pydantic_generic_metadata__["args"]
        inner_types = typing.cast(
            list[type[RootNode | ReifiedRelation]],
            [resolve_forward_ref(inner_type) for inner_type in inner_types],
        )

        type_param_to_types_map = {
            type_param.__name__: TypeParamsToTypeMap(type_param, real_type)
            for type_param, real_type in zip(origin_type.__parameters__, inner_types)
        }
        return RelationToSemanticSpaceDefinition(
            field_name=field_name,
            field_annotation=bound_type,
            annotated_type=bound_type,
            origin_type=origin_type,
            type_params_to_type_map=type_param_to_types_map,
        )
    raise PanglossConfigError(
        f"Create Relation With Bound type failed with {bound_type}"
    )


def build_pg_bound_model_definition_for_instatiated_reified(
    model: type[ReifiedRelation[typing.Any]],
):
    """Created a ModelFieldDefinition object for a reified relation
    with bound generic type, i.e. Intermediate[Model] not Intermediate"""

    field_definitions = {}
    for field in model.__pg_field_definitions__:
        if isinstance(field, RelationFieldDefinition):
            field_type_definitions: list[RelationDefinition] = []
            for relation_definition in field.field_type_definitions:
                if isinstance(relation_definition, RelationToNodeDefinition):
                    field_type_definitions.append(relation_definition)
                elif isinstance(relation_definition, RelationToTypeVarDefinition):
                    if is_union(model.model_fields[field.field_name].annotation):
                        for union_part in typing.get_args(
                            model.model_fields[field.field_name].annotation
                        ):
                            new_relation_definition = create_relation_with_bound_type(
                                field_name=field.field_name,
                                bound_type=typing.cast(
                                    type[RootNode] | type[ReifiedRelation],
                                    union_part,
                                ),
                            )
                            field_type_definitions.append(new_relation_definition)
                    else:
                        new_relation_definition = create_relation_with_bound_type(
                            field_name=field.field_name,
                            bound_type=typing.cast(
                                type[RootNode] | type[ReifiedRelation],
                                model.model_fields[field.field_name].annotation,
                            ),
                        )
                        field_type_definitions.append(new_relation_definition)
            annotation = model.model_fields[field.field_name].annotation
            annotation = typing.cast(annotation_types, annotation)
            field_as_dict = {
                **dataclasses.asdict(field),
                "field_annotation": annotation,
                "field_type_definitions": field_type_definitions,
            }

            field_definitions[field.field_name] = RelationFieldDefinition(
                **field_as_dict
            )
        else:
            field_definitions[field.field_name] = field

    model.__pg_bound_field_definitions__ = ModelFieldDefinitions(field_definitions)


def build_pg_bound_model_definition_for_instatiated_semantic_space(
    model: type[SemanticSpace[typing.Any]],
):
    """Created a ModelFieldDefinition object for a semantic space
    with bound generic type, i.e. Negative[Model] not Negative"""

    field_definitions = {}
    for field in model.__pg_field_definitions__:
        if isinstance(field, RelationFieldDefinition):
            field_type_definitions: list[RelationDefinition] = []
            for relation_definition in field.field_type_definitions:
                if isinstance(relation_definition, RelationToNodeDefinition):
                    field_type_definitions.append(relation_definition)
                elif isinstance(relation_definition, RelationToTypeVarDefinition):
                    new_relation_definition = create_relation_with_bound_type(
                        field_name=field.field_name,
                        bound_type=typing.cast(
                            type[RootNode]
                            | type[ReifiedRelation]
                            | type[SemanticSpace],
                            model.model_fields[field.field_name].annotation,
                        ),
                    )
                    field_type_definitions.append(new_relation_definition)
            annotation = model.model_fields[field.field_name].annotation
            annotation = typing.cast(annotation_types, annotation)
            field_as_dict = {
                **dataclasses.asdict(field),
                "field_annotation": annotation,
                "field_type_definitions": field_type_definitions,
            }

            field_definitions[field.field_name] = RelationFieldDefinition(
                **field_as_dict
            )
        else:
            field_definitions[field.field_name] = field

    model.__pg_bound_field_definitions__ = ModelFieldDefinitions(field_definitions)

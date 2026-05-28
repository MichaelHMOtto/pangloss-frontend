import dataclasses
import datetime
import enum
import types
import typing
from abc import ABC
from collections import ChainMap, defaultdict

import annotated_types

from pangloss.model_config.models_base import ReifiedRelationNode, SemanticSpace

if typing.TYPE_CHECKING:
    from pangloss.model_config.model_setup_functions.build_reverse_relation_definitions import (
        Path,
    )
    from pangloss.model_config.models_base import (
        EdgeModel,
        HeritableTrait,
        MultiKeyField,
        NonHeritableTrait,
        ReifiedBase,
        ReifiedRelation,
        RootNode,
        _BaseClassProxy,
    )


@dataclasses.dataclass(kw_only=True, frozen=True, slots=True)
class FieldDefinition(ABC):
    field_annotation: typing.Any
    field_name: str
    field_metatype: typing.ClassVar[
        typing.Literal["Field"]
        | typing.Literal["PropertyField"]
        | typing.Literal["MultiKeyField"]
        | typing.Literal["ListField"]
        | typing.Literal["EmbeddedField"]
        | typing.Literal["RelationField"]
    ]


type MappedCypherTypes = (
    bool
    | int
    | float
    | str
    | datetime.date
    | datetime.timedelta
    | datetime.datetime
    | enum.Enum
)


@dataclasses.dataclass(kw_only=True, frozen=True, slots=True)
class PropertyFieldDefinition[T: MappedCypherTypes](FieldDefinition):
    field_annotation: type[T]
    default_value: T | None = None
    validators: list[annotated_types.BaseMetadata] = dataclasses.field(
        default_factory=list
    )
    field_metatype: typing.ClassVar[typing.Literal["PropertyField"]] = "PropertyField"


@dataclasses.dataclass(kw_only=True, frozen=True, slots=True)
class MultiKeyFieldDefinition(FieldDefinition):
    field_annotation: type["MultiKeyField[MappedCypherTypes]"]
    multi_key_field_type: type["MultiKeyField"]
    multi_key_field_value_type: typing.Any
    multi_key_field_value_validators: list[annotated_types.BaseMetadata] = (
        dataclasses.field(default_factory=list)
    )
    field_metatype: typing.ClassVar[typing.Literal["MultiKeyField"]] = "MultiKeyField"
    validators: list[annotated_types.BaseMetadata] = dataclasses.field(
        default_factory=list
    )  # TODO: validators in this case should really refer to the value_type


@dataclasses.dataclass(kw_only=True, frozen=True, slots=True)
class ListFieldDefinition(FieldDefinition):
    field_annotation: type[MappedCypherTypes]
    field_metatype: typing.ClassVar[typing.Literal["ListField"]] = "ListField"
    validators: list[annotated_types.BaseMetadata] = dataclasses.field(
        default_factory=list
    )
    """Validators for the list type as a whole"""

    internal_type_validators: list[annotated_types.BaseMetadata] = dataclasses.field(
        default_factory=list
    )
    """Validators for each item in the list type"""


@dataclasses.dataclass(kw_only=True, frozen=True, slots=True)
class EnumFieldDefinition(FieldDefinition):
    field_annotation: type[enum.Enum]
    field_metatype: typing.ClassVar[typing.Literal["EnumField"]] = "EnumField"


@dataclasses.dataclass(kw_only=True, frozen=True, slots=True)
class EmbeddedFieldDefinition(FieldDefinition):
    field_annotation: type["RootNode"] | types.UnionType
    validators: list[annotated_types.BaseMetadata] = dataclasses.field(
        default_factory=list
    )
    field_metatype: typing.ClassVar[typing.Literal["EmbeddedField"]] = "EmbeddedField"
    field_concrete_types: typing.Iterable[type["RootNode"]] = dataclasses.field(
        default_factory=set
    )

    def __post_init__(self):
        if not self.validators:
            object.__setattr__(
                self,
                "validators",
                [annotated_types.MinLen(1), annotated_types.MaxLen(1)],
            )


@dataclasses.dataclass(kw_only=True, frozen=True, slots=True)
class RelationDefinition(FieldDefinition):
    metatype: typing.ClassVar[typing.Literal["Relation"]] = "Relation"


@dataclasses.dataclass(kw_only=True, frozen=True, slots=True)
class RelationToNodeDefinition(RelationDefinition):
    annotated_type: type["RootNode"]
    metatype: typing.ClassVar[typing.Literal["RelationToNode"]] = "RelationToNode"


@dataclasses.dataclass(kw_only=True, frozen=True, slots=True)
class RelationToTypeVarDefinition(RelationDefinition):
    annotated_type: typing.TypeVar
    typevar_name: str
    metatype: typing.ClassVar[typing.Literal["RelationToTypeVar"]] = "RelationToTypeVar"


@dataclasses.dataclass
class TypeParamsToTypeMap:
    type_param: typing.TypeVar | typing.ParamSpec | typing.TypeVarTuple
    type: type["RootNode"] | type["ReifiedRelation"]


@dataclasses.dataclass(kw_only=True, frozen=True, slots=True)
class RelationToReifiedDefinition(RelationDefinition):
    annotated_type: type["ReifiedRelation"]
    origin_type: type["ReifiedRelation"]
    type_params_to_type_map: dict[
        str,
        TypeParamsToTypeMap,
    ]
    metatype: typing.ClassVar[typing.Literal["RelationToReified"]] = "RelationToReified"


@dataclasses.dataclass(kw_only=True, frozen=True, slots=True)
class RelationToSemanticSpaceDefinition(RelationDefinition):
    annotated_type: type["SemanticSpace"]
    origin_type: type["SemanticSpace"]
    type_params_to_type_map: dict[
        str,
        TypeParamsToTypeMap,
    ]
    metatype: typing.ClassVar[typing.Literal["RelationToSemanticSpace"]] = (
        "RelationToSemanticSpace"
    )


type annotation_types = (
    type["RootNode"]
    | types.UnionType
    | type["HeritableTrait"]
    | type["NonHeritableTrait"]
    | type["ReifiedRelation"]
    | typing.TypeVar
)


class SubclassedRelationNames(typing.NamedTuple):
    name: str
    reverse_name: str


@dataclasses.dataclass(kw_only=True, frozen=True, slots=True)
class RelationFieldDefinition(FieldDefinition):
    containing_model: "type[ReifiedBase] | type[EdgeModel] | type[SemanticSpace] | type[RootNode] | type[MultiKeyField] | type[_BaseClassProxy]"
    field_annotation: annotation_types
    reverse_name: str

    field_type_definitions: list[RelationDefinition] = dataclasses.field(
        default_factory=list
    )
    bind_fields_to_related: typing.Optional[
        typing.Iterable[tuple[str, str] | tuple[str, str, typing.Callable]]
    ] = dataclasses.field(default_factory=list)

    edge_model: typing.Optional[type["EdgeModel"]] = None
    subclasses_relation: typing.Optional[str] = None

    create_inline: bool = False
    edit_inline: bool = False
    delete_related_on_detach: bool = False
    validators: list[annotated_types.BaseMetadata] = dataclasses.field(
        default_factory=list
    )

    field_metatype: typing.ClassVar[typing.Literal["RelationField"]] = "RelationField"
    relation_labels: set[str] = dataclasses.field(default_factory=set)
    reverse_relation_labels: set[str] = dataclasses.field(default_factory=set)
    subclassed_relations: set[SubclassedRelationNames] = dataclasses.field(
        default_factory=set
    )
    default_reified_type: typing.Optional["ReifiedRelation | str"] = None

    def __hash__(self):
        return hash(self.containing_model.__name__ + self.field_name)

    @property
    def relations_to_node(self) -> list[RelationToNodeDefinition]:
        return [
            relation
            for relation in self.field_type_definitions
            if isinstance(relation, RelationToNodeDefinition)
        ]

    @property
    def relations_to_reified(self) -> list[RelationToReifiedDefinition]:
        return [
            relation
            for relation in self.field_type_definitions
            if isinstance(relation, RelationToReifiedDefinition)
        ]

    @property
    def relations_to_semantic_space(self) -> list[RelationToSemanticSpaceDefinition]:
        return [
            relation
            for relation in self.field_type_definitions
            if isinstance(relation, RelationToSemanticSpaceDefinition)
        ]

    @property
    def relations_to_typevar(self) -> list[RelationToTypeVarDefinition]:
        return [
            relation
            for relation in self.field_type_definitions
            if isinstance(relation, RelationToTypeVarDefinition)
        ]


@dataclasses.dataclass
class FieldSubset[T]:
    fields: dict[str, T] = dataclasses.field(default_factory=dict)

    def __getitem__(self, key) -> T | None:
        return self.fields[key]

    def __contains__(self, key):
        return key in self.fields

    def __iter__(self) -> typing.Generator[T, None, None]:
        for field in self.fields.values():
            yield field

    def keys(self):
        return self.fields.keys()

    def values(self):
        return self.fields.values()

    def items(self):
        return self.fields.items()


@dataclasses.dataclass
class ModelFieldDefinitions:
    fields: dict[str, FieldDefinition] | typing.ChainMap[str, FieldDefinition] = (
        dataclasses.field(default_factory=dict)
    )
    reverse_relations: dict[str, set["IncomingRelationDefinition"]] = dataclasses.field(
        default_factory=lambda: defaultdict(set)
    )

    def __getitem__(self, key) -> FieldDefinition | None:
        return self.fields[key]

    def __setitem__(self, key, value):
        self.fields[key] = value

    def __contains__(self, key):
        return key in self.fields

    def __iter__(self) -> typing.Generator[FieldDefinition, None, None]:
        for field in self.fields.values():
            yield field

    def __delitem__(self, key):
        if key in self.fields:
            del self.fields[key]

    def keys(self):
        return self.fields.keys()

    def values(self):
        return self.fields.values()

    def items(self):
        return self.fields.items()

    @property
    def relation_fields(
        self,
    ) -> FieldSubset[RelationFieldDefinition]:
        items = {
            field_name: field
            for field_name, field in self.fields.items()
            if isinstance(field, RelationFieldDefinition)
        }

        return FieldSubset[RelationFieldDefinition](fields=items)

    @property
    def embedded_fields(self) -> FieldSubset[EmbeddedFieldDefinition]:
        items = {
            field_name: field
            for field_name, field in self.fields.items()
            if isinstance(field, EmbeddedFieldDefinition)
        }

        return FieldSubset[EmbeddedFieldDefinition](fields=items)

    @property
    def property_fields(
        self,
    ) -> FieldSubset[
        PropertyFieldDefinition | ListFieldDefinition | MultiKeyFieldDefinition
    ]:
        items = {
            field_name: field
            for field_name, field in self.fields.items()
            if isinstance(
                field,
                (PropertyFieldDefinition, ListFieldDefinition, MultiKeyFieldDefinition),
            )
        }

        return FieldSubset[
            PropertyFieldDefinition | ListFieldDefinition | MultiKeyFieldDefinition
        ](items)


class CombinedModelFieldDefinitions(ModelFieldDefinitions):
    def __init__(
        self,
        main_model_definitions: ModelFieldDefinitions,
        specialised_model_definitions: ModelFieldDefinitions,
    ):
        self.fields = ChainMap(
            main_model_definitions.fields, specialised_model_definitions.fields
        )


@dataclasses.dataclass
class IncomingRelationDefinition:
    reverse_name: str

    forward_path_object: "Path"
    relation_definition: RelationFieldDefinition

    def __hash__(self):
        return hash(self.forward_path_object)


@dataclasses.dataclass
class DirectIncomingRelationDefinition(IncomingRelationDefinition):
    reverse_target: type["RootNode"]

    def __hash__(self):
        return hash(self.forward_path_object)


@dataclasses.dataclass
class ContextIncomingRelationDefinition(IncomingRelationDefinition):
    reverse_target: type["RootNode"] | type["ReifiedRelationNode"]

    def __hash__(self):
        return hash(self.forward_path_object)

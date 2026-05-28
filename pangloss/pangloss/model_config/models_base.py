import dataclasses
import datetime
import typing
from collections import ChainMap

import annotated_types
import neo4j.time
from pydantic import (
    AnyHttpUrl,
    BaseModel,
    Field,
    PlainSerializer,
    computed_field,
    field_validator,
)
from pydantic_extra_types.ulid import ULID as ExtraTypeULID

from pangloss.exceptions import PanglossConfigError
from pangloss.model_config.model_base_mixins import (
    _BaseClassProxy,
    _BindingSubModelValidator,
    _OwnsMethods,
    _RelationInContextOf,
    _StandardModel,
    _ViaEdge,
)

if typing.TYPE_CHECKING:
    from pangloss.model_config.field_definitions import (
        IncomingRelationDefinition,
        ModelFieldDefinitions,
    )
    from pangloss.models import BaseNode


type ULID = typing.Annotated[ExtraTypeULID, PlainSerializer(lambda ulid: str(ulid))]

"""API OPERATIONS

- Create
- GetExistingToEdit
- PostEdit
- View

"""


class EdgeModel(BaseModel, _StandardModel):
    show_in_reverse_relation: typing.ClassVar[bool] = False

    __pg_annotations__: typing.ClassVar[ChainMap[str, type]]
    __pg_field_definitions__: typing.ClassVar["ModelFieldDefinitions"]

    @classmethod
    def __pydantic_init_subclass__(cls) -> None:
        from pangloss.model_config.model_manager import ModelManager

        ModelManager.register_edge_model(cls)


@dataclasses.dataclass
class AbstractBaseMeta:
    pass


@dataclasses.dataclass
class BaseMeta(AbstractBaseMeta):
    """Base class for BaseNode Meta fields"""

    base_model: type["RootNode"]

    supertypes: list[type["RootNode"]] = dataclasses.field(default_factory=list)
    traits: list[type["Trait"]] = dataclasses.field(default_factory=list)

    abstract: bool = False
    """The model is an abstract model"""
    create: bool = True
    """Model can be directly created"""
    edit: bool = True
    """Model can be directly edited"""
    delete: bool = True
    """Model can be directly deleted"""
    view: bool = True
    """Model can be directly viewed"""
    search: bool = True
    """Model can be directly searched"""

    create_by_reference: bool = False
    "Allow creation by reference by providing a URI/ULID and a label"

    label_field: str | None = None
    """Alternative field to be displayed as label"""

    @property
    def fields(self) -> "ModelFieldDefinitions":
        return self.base_model.__pg_field_definitions__

    @property
    def reverse_relations(self) -> dict[str, set["IncomingRelationDefinition"]]:
        return self.base_model.__pg_field_definitions__.reverse_relations

    @property
    def type_labels(self) -> list[str]:
        return [
            "BaseNode",
            *[m.__name__ for m in [self.base_model, *self.supertypes, *self.traits]],
        ]


@dataclasses.dataclass
class RelationConfig:
    reverse_name: str
    """Reverse name for the relationship"""
    bind_fields_to_related: typing.Optional[
        typing.Iterable[
            "tuple[str, str] | tuple[str, str, typing.Callable] | BoundField"
        ]
    ] = dataclasses.field(default_factory=list)
    """Use the value of the containing model field as the value of contained model 
    field, via optional transforming function"""

    subclasses_relation: typing.Optional[list[str] | frozenset[str]] = None
    """This relation is a subclass of the relation of a parent model"""

    edge_model: typing.Optional[type["EdgeModel"]] = None
    """Model to use as for edge of the relationship"""

    validators: list[annotated_types.BaseMetadata] = dataclasses.field(
        default_factory=list
    )

    create_inline: bool = False
    edit_inline: bool = False
    delete_related_on_detach: bool = False
    default_reified_type: typing.Optional[str] = None

    def __hash__(self):
        if self.subclasses_relation:
            self.subclasses_relation = frozenset(self.subclasses_relation)
        return hash(self.__dict__)

    def __post_init__(self):
        self.reverse_name = self.reverse_name.lower().replace(" ", "_")

        if self.bind_fields_to_related and not self.create_inline:
            raise PanglossConfigError(
                "Cannot use `bind_field_to_related` unless also `create_inline=True`"
            )


class RootNode(_OwnsMethods):
    """Base class for basic BaseModel"""

    type: str

    Create: typing.ClassVar["type[CreateBase]"]
    HeadView: typing.ClassVar["type[HeadViewBase]"]
    View: typing.ClassVar["type[ViewBase]"]
    EditHeadView: typing.ClassVar["type[EditHeadViewBase]"]
    EditHeadSet: typing.ClassVar["type[EditHeadSetBase]"]
    EditSet: typing.ClassVar["type[EditSetBase]"]
    ReferenceCreate: "typing.ClassVar[type[ReferenceCreateBase]] | None" = None
    ReferenceView: typing.ClassVar["type[ReferenceViewBase]"]
    ReferenceSet: typing.ClassVar["type[ReferenceSetBase]"]
    EmbeddedCreate: typing.ClassVar["type[EmbeddedCreateBase]"]
    EmbeddedView: typing.ClassVar["type[EmbeddedViewBase]"]
    EmbeddedSet: typing.ClassVar["type[EmbeddedSetBase]"]

    Meta: typing.ClassVar["type[BaseMeta]"] = BaseMeta
    _meta: typing.ClassVar[BaseMeta]

    __pg_annotations__: typing.ClassVar["ChainMap[str, type]"]
    __pg_field_definitions__: typing.ClassVar["ModelFieldDefinitions"]

    def __init_subclass__(cls):
        from pangloss.model_config.model_manager import ModelManager

        ModelManager.register_base_model(typing.cast("type[BaseNode]", cls))

    def __new__(cls, *args, **kwargs):
        return cls.Create(*args, **kwargs)

    # Functions for pretty API
    class edit:
        # TODO: rig up this to the init — or make into descriptor??
        __pg_base_class__: typing.ClassVar["type[RootNode]"]

        @classmethod
        def get(cls, id: ULID | AnyHttpUrl) -> "EditHeadViewBase":
            # TODO: Sketching API so far
            return cls.__pg_base_class__.EditHeadView()  # type: ignore

        def __new__(cls, *args, **kwargs) -> "EditSetBase":
            # TODO: Sketching API so far
            return cls.__pg_base_class__.EditSet(*args, **kwargs)

    class view:
        __pg_base_class__: typing.ClassVar["type[RootNode]"]

        @classmethod
        def get(cls, id: ULID | AnyHttpUrl):
            # TODO: Sketching API so far
            return cls.__pg_base_class__.HeadView


class CreateBase(
    BaseModel,
    _StandardModel,
    _BaseClassProxy,
    _ViaEdge["CreateBase"],
    _BindingSubModelValidator,
    _RelationInContextOf["CreateBase"],
):
    # id: Can take an optional ID or URI

    post_validator: typing.ClassVar[typing.Callable]

    type: str
    id: ULID | AnyHttpUrl | list[AnyHttpUrl] | None = None
    label: str
    uris: list[AnyHttpUrl] = Field(default_factory=list)

    async def create_and_get(self, username: str | None = None) -> "EditHeadSetBase":
        """Create this instance in the database and return the created object"""

        return await typing.cast("BaseNode", self.__pg_base_class__)._create_method(
            self,
            current_username=username,
            return_edit_view=True,
            use_deferred_query=False,
        )

    async def create(
        self, username: str | None = None, use_deferred_query: bool = False
    ) -> "ReferenceViewBase":
        """Create this instance in the database and return a Reference object"""

        return await typing.cast("BaseNode", self.__pg_base_class__)._create_method(
            self,
            current_username=username,
            use_deferred_query=use_deferred_query,
            return_edit_view=False,
        )


class ViewBase(
    BaseModel,
    _StandardModel,
    _BaseClassProxy,
    _ViaEdge["ViewBase"],
    _RelationInContextOf["ViewBase"],
):
    """Base model returned by API for viewing/editing when not Head.

    Contains all fields, no metadata or reverse relations"""

    type: str
    id: ULID
    label: str
    head_node: ULID | None = None
    head_type: str | None = None
    semantic_spaces: list[str] | None = Field(default_factory=list)


class HeadViewBase(BaseModel, _StandardModel, _BaseClassProxy):
    """Base model returned by API for viewing when Head.

    Includes reverse relations and additional metadata"""

    type: str
    id: ULID
    label: str
    uris: list[AnyHttpUrl] = Field(default_factory=list)

    created_by: str
    created_when: datetime.datetime
    modified_by: str | None = None
    modified_when: datetime.datetime | None = None
    semantic_spaces: list[str] = Field(default_factory=list)

    @field_validator("*", mode="before")
    @classmethod
    def convert_neo4j_dates(cls, value: typing.Any, field) -> typing.Any:
        if isinstance(value, (neo4j.time.DateTime, neo4j.time.Date)):
            return value.to_native()
        return value


class EditHeadViewBase(BaseModel, _StandardModel, _BaseClassProxy):
    """Head Base model returned by API for editing.

    Includes additional metadata but not reverse relations"""

    type: str
    id: ULID
    label: str
    uris: list[AnyHttpUrl] = Field(default_factory=list)

    created_by: str
    created_when: datetime.datetime
    modified_by: str | None = None
    modified_when: datetime.datetime | None = None
    semantic_spaces: list[str] | None = Field(default_factory=list)

    @field_validator("*", mode="before")
    @classmethod
    def convert_neo4j_dates(cls, value: typing.Any, field) -> typing.Any:
        if isinstance(value, (neo4j.time.DateTime, neo4j.time.Date)):
            return value.to_native()
        return value

    async def update(
        self, username: str | None = None, use_deferred_query: bool = False
    ):
        """Update this instance in the database"""

        return await typing.cast("BaseNode", self.__pg_base_class__)._update_method(
            self,
            current_username=username or "DefaultUser",
            use_deferred_query=use_deferred_query,
        )


class EditHeadSetBase(
    BaseModel,
    _StandardModel,
    _BaseClassProxy,
    _ViaEdge["EditHeadSetBase"],
    _BindingSubModelValidator,
):
    """Base Head model for updates PATCH-ed to API

    Nested items can be other ReferenceSetBase, EditSetBase or CreateBase models"""

    id: ULID
    type: str
    label: str
    uris: list[AnyHttpUrl] = Field(default_factory=list)
    semantic_spaces: list[str] | None = Field(default_factory=list)

    async def update(
        self, username: str | None = None, use_deferred_query: bool = False
    ) -> None:
        """Write this instance to the database"""
        return await typing.cast("BaseNode", self.__pg_base_class__)._update_method(
            self,
            current_username=username or "DefaultUser",
            use_deferred_query=use_deferred_query,
        )


class EditSetBase(
    BaseModel,
    _StandardModel,
    _BaseClassProxy,
    _ViaEdge["EditSetBase"],
    _BindingSubModelValidator,
    _RelationInContextOf["EditSetBase"],
):
    """Base model for updates PATCH-ed to API"""

    id: ULID
    type: str
    label: str
    semantic_spaces: list[str] = Field(default_factory=list)


class ReferenceViewBase(
    BaseModel, _StandardModel, _BaseClassProxy, _ViaEdge["ReferenceViewBase"]
):
    """Base model for viewing a Reference to an entity"""

    type: str
    id: ULID
    label: str
    head_node: ULID | None = None
    head_type: str | None = None
    uris: list[AnyHttpUrl] | None = Field(default_factory=list)
    semantic_spaces: list[str] | None = Field(default_factory=list)

    def __hash__(self):
        return hash(str(self.id))


class ReferenceCreateBase(
    BaseModel, _StandardModel, _BaseClassProxy, _ViaEdge["ReferenceCreateBase"]
):
    """Base model for setting a Reference to an entity"""

    type: str
    id: ULID | AnyHttpUrl
    label: str
    create: bool


class ReferenceSetBase(
    BaseModel, _StandardModel, _BaseClassProxy, _ViaEdge["ReferenceSetBase"]
):
    """Base model for setting a Reference to an entity"""

    type: str
    id: ULID | AnyHttpUrl
    label: str | None = None


class ReifiedCreateBase(
    BaseModel, _StandardModel, _BaseClassProxy, _ViaEdge["ReifiedCreateBase"]
):
    type: str


@dataclasses.dataclass
class ReifiedMeta:
    base_model: type["ReifiedBase"]

    @property
    def fields(self) -> "ModelFieldDefinitions":
        return self.base_model.__pg_get_fields__()

    @property
    def type_labels(self) -> list[str]:
        return [self.base_model.__name__]


class ReifiedBase(BaseModel, _OwnsMethods):
    model_config = {"arbitrary_types_allowed": True}

    Create: typing.ClassVar[type[ReifiedCreateBase]]
    View: typing.ClassVar[type["ReifiedRelationViewBase"]]
    EditSet: typing.ClassVar[type["ReifiedRelationEditSetBase"]]

    __pg_annotations__: typing.ClassVar[ChainMap[str, type]]
    __pg_field_definitions__: typing.ClassVar["ModelFieldDefinitions"]
    __pg_bound_field_definitions__: typing.ClassVar["ModelFieldDefinitions"]

    _meta: typing.ClassVar[ReifiedMeta]

    collapse_when: typing.ClassVar[
        typing.Optional[typing.Callable[[typing.Self], bool]]
    ] = None

    @classmethod
    def __pydantic_init_subclass__(cls):
        """Create a _meta object with pointer back to this class,
        either the generic type or the bound type"""
        cls._meta = ReifiedMeta(base_model=cls)

    @classmethod
    def __pg_get_fields__(cls) -> "ModelFieldDefinitions":
        """Internal getter for reified relation fields to present a consistent API
        and avoid potentially accidentally omitting logic in other spots.

        If it is a generic class, return __pg_field_definitions__;
        if bound (i.e. has origin and args set in __pydantic_generic_metadata,
        check whether the bound field definitions have been created and return, or just return"""
        if (
            cls.__pydantic_generic_metadata__["origin"]
            and cls.__pydantic_generic_metadata__["args"]
        ):
            if not getattr(cls, "__pg_bound_field_definitions__", None):
                from pangloss.model_config.model_setup_functions.build_pg_model_definition import (
                    build_pg_bound_model_definition_for_instatiated_reified,
                )

                build_pg_bound_model_definition_for_instatiated_reified(
                    typing.cast(type[ReifiedRelation], cls)
                )
            return cls.__pg_bound_field_definitions__
        return cls.__pg_field_definitions__


class ReifiedRelation[T](ReifiedBase, _StandardModel):
    """Base model for creating a reified relation"""

    type: str
    target: typing.Annotated[T, RelationConfig(reverse_name="is_target_of")]

    def __init_subclass__(cls) -> None:
        from pangloss.model_config.model_manager import ModelManager

        # Dubious hack to update the parameters used by typing module to allow
        # inheriting class to include additional type parameters
        cls.__parameters__ = cls.__type_params__

        ModelManager.register_reified_relation_model(cls)


class ReifiedRelationNode[T](ReifiedRelation[T]):
    label: str


class ReifiedRelationViewBase(
    BaseModel,
    _StandardModel,
    _BaseClassProxy,
    _ViaEdge["ReifiedRelationViewBase"],
    _RelationInContextOf["ReifiedRelationViewBase"],
):
    """Base model for viewing a reified relation (contains uuid and additional metadata)"""

    type: str
    id: ULID
    head_node: typing.Optional[ULID] = None
    head_type: typing.Optional[str] = None
    semantic_spaces: list[str] = Field(default_factory=list)

    @computed_field
    @property
    def collapsed(self) -> bool:
        return self.__pg_base_class__.collapse_when(self)  # type: ignore


class ReifiedRelationNodeHeadViewBase(
    BaseModel,
    _StandardModel,
    _BaseClassProxy,
    _ViaEdge["ReifiedRelationNodeHeadViewBase"],
):
    """Base model for viewing a reified relation (contains uuid and additional metadata)"""

    type: str
    id: ULID
    head_node: typing.Optional[ULID] = None
    head_type: typing.Optional[str] = None

    created_by: str
    created_when: datetime.datetime
    modified_by: str | None = None
    modified_when: datetime.datetime | None = None


class ReifiedRelationEditSetBase(
    BaseModel, _StandardModel, _BaseClassProxy, _ViaEdge["ReifiedRelationEditSetBase"]
):
    type: str
    id: ULID
    semantic_spaces: list[str] = Field(default_factory=list)


class Embedded[T]:
    embedded_type: T


class EmbeddedCreateBase(
    BaseModel, _StandardModel, _BaseClassProxy, _ViaEdge["EmbeddedCreateBase"]
):
    """Base model for creating an embedded node (same as RootNode without id)"""

    type: str


class EmbeddedViewBase(
    BaseModel, _StandardModel, _BaseClassProxy, _ViaEdge["EmbeddedViewBase"]
):
    """Base model for viewing an embedded model"""

    type: str
    id: ULID
    head_node: typing.Optional[ULID] = None
    head_type: typing.Optional[str] = None
    semantic_spaces: list[str] = Field(default_factory=list)


class EmbeddedSetBase(
    BaseModel, _StandardModel, _BaseClassProxy, _ViaEdge["EmbeddedSetBase"]
):
    type: str
    id: ULID
    semantic_spaces: list[str] = Field(default_factory=list)


class Trait:
    def __init_subclass__(cls):
        from pangloss.model_config.model_manager import ModelManager

        cls.__parameters__ = cls.__type_params__

        ModelManager.register_trait_model(cls)


class HeritableTrait(Trait):
    pass


class NonHeritableTrait(Trait):
    pass


@dataclasses.dataclass
class MultiKeyFieldMeta:
    base_model: type["MultiKeyField"]

    @property
    def fields(self) -> "ModelFieldDefinitions":
        return self.base_model.__pg_field_definitions__


class MultiKeyField[T](BaseModel, _StandardModel):
    """Define a field with multiple additional fields.

    The main field type is supplied by the type param T and is assigned to the `value` field.
    Additional fields may be defined on the subclassed model."""

    value: T

    __pg_annotations__: typing.ClassVar[ChainMap[str, type]]
    __pg_field_definitions__: typing.ClassVar["ModelFieldDefinitions"]
    _meta: typing.ClassVar[MultiKeyFieldMeta]

    def __init_subclass__(cls) -> None:
        from pangloss.model_config.model_manager import ModelManager

        # Dubious hack to update the parameters used by typing module to allow
        # inheriting class to include additional type parameters
        cls.__parameters__ = cls.__type_params__
        cls._meta = MultiKeyFieldMeta(base_model=cls)

        ModelManager.register_multikeyfield_model(cls)


class BoundField(typing.NamedTuple):
    parent_field_name: str
    bound_field_name: str
    transform: typing.Optional[typing.Callable] = None


@dataclasses.dataclass
class SemanticSpaceMeta:
    base_model: type["SemanticSpaceBase"]

    abstract: bool = False
    can_nest: bool = False

    supertypes: list[type["SemanticSpace"]] = dataclasses.field(default_factory=list)

    @property
    def fields(self) -> "ModelFieldDefinitions":
        return self.base_model.__pg_get_fields__()

    @property
    def type_labels(self) -> list[str]:
        labels = []
        for superclass in self.base_model.__mro__:
            if superclass is SemanticSpace:
                break
            if (
                issubclass(superclass, SemanticSpace)
                and not superclass.__pydantic_generic_metadata__["origin"]
            ):
                labels.append(superclass.__name__)
        return labels


class SemanticSpaceBase(BaseModel, _OwnsMethods):
    model_config = {"arbitrary_types_allowed": True}

    Create: typing.ClassVar[type["SemanticSpaceCreateBase"]]
    View: typing.ClassVar[type["SemanticSpaceViewBase"]]
    EditSet: typing.ClassVar[type["SemanticSpaceEditSetBase"]]

    __pg_annotations__: typing.ClassVar[ChainMap[str, type]]
    __pg_field_definitions__: typing.ClassVar["ModelFieldDefinitions"]
    __pg_bound_field_definitions__: typing.ClassVar["ModelFieldDefinitions"]

    Meta: typing.ClassVar["type[SemanticSpaceMeta]"] = SemanticSpaceMeta
    _meta: typing.ClassVar[SemanticSpaceMeta]

    collapse_when: typing.ClassVar[
        typing.Optional[typing.Callable[[typing.Self], bool]]
    ] = None

    @classmethod
    def __pg_get_fields__(cls) -> "ModelFieldDefinitions":
        """Internal getter for semantic space fields to present a consistent API
        and avoid potentially accidentally omitting logic in other spots.

        If it is a generic class, return __pg_field_definitions__;
        if bound (i.e. has origin and args set in __pydantic_generic_metadata,
        check whether the bound field definitions have been created and return, or just return"""

        if getattr(cls, "__pg_bound_field_definitions__", None):
            return cls.__pg_bound_field_definitions__

        return cls.__pg_field_definitions__


class SemanticSpace[T](SemanticSpaceBase, _StandardModel):
    """Base model for creating a reified relation"""

    type: str
    contents: typing.Annotated[
        T,
        RelationConfig(
            reverse_name="is_contents_of", create_inline=True, edit_inline=True
        ),
        annotated_types.MinLen(1),
    ]

    def __init_subclass__(cls) -> None:
        from pangloss.model_config.model_manager import ModelManager

        # Dubious hack to update the parameters used by typing module to allow
        # inheriting class to include additional type parameters
        cls.__parameters__ = cls.__type_params__

        ModelManager.register_semantic_space_model(cls)


class SemanticSpaceViewBase(
    BaseModel,
    _StandardModel,
    _BaseClassProxy,
    _RelationInContextOf["SemanticSpaceViewBase"],
):
    """Base model for viewing a semantic space (contains id and additional metadata)"""

    type: str
    id: ULID
    head_node: typing.Optional[ULID] = None
    head_type: typing.Optional[str] = None
    semantic_spaces: list[str] = Field(default_factory=list)


class SemanticSpaceCreateBase(
    BaseModel,
    _StandardModel,
    _BaseClassProxy,
    _RelationInContextOf["SemanticSpaceCreateBase"],
    _BindingSubModelValidator["SemanticSpaceCreateBase"],
):
    type: str


class SemanticSpaceEditSetBase(
    BaseModel,
    _StandardModel,
    _BaseClassProxy,
    _RelationInContextOf["SemanticSpaceEditSetBase"],
    _BindingSubModelValidator["SemanticSpaceEditSetBase"],
):
    type: str
    id: ULID
    semantic_spaces: list[str] = Field(default_factory=list)

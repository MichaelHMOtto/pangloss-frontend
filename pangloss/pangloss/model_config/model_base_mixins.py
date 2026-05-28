import typing

import humps
from pydantic import ConfigDict, model_validator

from pangloss.exceptions import PanglossValidationError
from pangloss.model_config.model_manager import ModelManager

if typing.TYPE_CHECKING:
    from pangloss.model_config.field_definitions import ModelFieldDefinitions
    from pangloss.model_config.models_base import (
        BaseMeta,
        CreateBase,
        EditHeadSetBase,
        EditSetBase,
        ReferenceSetBase,
        ReifiedCreateBase,
        ReifiedMeta,
        ReifiedRelation,
        ReifiedRelationViewBase,
        RootNode,
        SemanticSpace,
        SemanticSpaceMeta,
        ViewBase,
    )


STANDARD_MODEL_CONFIG: ConfigDict = {
    "alias_generator": humps.camelize,
    "populate_by_name": True,
    "use_enum_values": True,
    "arbitrary_types_allowed": True,
    "validate_assignment": True,
}


class _StandardModel:
    model_config = STANDARD_MODEL_CONFIG


class _BindingSubModelValidator[T]:
    _has_bindable_relations: typing.ClassVar[bool] = False
    _bindable_relations: typing.ClassVar[list]

    @classmethod
    def set_has_bindable_relations(cls) -> None:
        # Change this to allow bound through SemanticSpace...

        bindable_relations = [
            rf
            for rf in typing.cast(
                type["CreateBase | EditHeadSetBase | EditSetBase"], cls
            ).__pg_base_class__._meta.fields.relation_fields
            if rf.bind_fields_to_related
        ]
        if bindable_relations:
            cls._bindable_relations = bindable_relations
            cls._has_bindable_relations = True

    @model_validator(mode="before")
    @classmethod
    def binding_submodel_validator(cls, data):
        # Change this to allow bound through SemanticSpace...
        if not cls._has_bindable_relations:
            return data

        for bindable_relation in cls._bindable_relations:
            assert bindable_relation.bind_fields_to_related

            for binding_def in bindable_relation.bind_fields_to_related:
                if data.get(binding_def[0], None):
                    for c in data[bindable_relation.field_name]:
                        if c["type"] in ModelManager.semantic_space_models:
                            for d in c["contents"]:
                                if not d.get(binding_def[1], None):
                                    if (
                                        len(binding_def) == 3
                                        and binding_def[2] is not None
                                    ):
                                        d[binding_def[1]] = binding_def[2](
                                            data[binding_def[0]]
                                        )
                                    else:
                                        d[binding_def[1]] = data[binding_def[0]]

                        else:
                            if not c.get(binding_def[1], None):
                                if len(binding_def) == 3 and binding_def[2] is not None:
                                    c[binding_def[1]] = binding_def[2](
                                        data[binding_def[0]]
                                    )
                                else:
                                    c[binding_def[1]] = data[binding_def[0]]
                else:
                    raise PanglossValidationError(
                        f"{typing.cast('_BaseClassProxy', cls).__pg_base_class__.__name__} missing {binding_def[0]}",
                    )

        return data


class _OwnsMethods:
    """Adds methods to check whether a model has attribute
    set on itself, not in inheritance chain, by inspecting cls.__dict__"""

    @classmethod
    def has_own(cls, key: str) -> bool:
        if key in cls.__dict__:
            return True
        if item := getattr(cls, key, None) and hasattr(cls, "__pg_base_class__"):
            if getattr(item, "__pg_base_class__", None) is cls:
                return True
        return False

    @classmethod
    def get_own(cls, key: str) -> typing.Any:
        return cls.__dict__.get(key, None)


class _MetaDescriptor:
    def __get__(
        self, obj, parent_type: "_BaseClassProxy | None" = None
    ) -> "BaseMeta | ReifiedMeta | SemanticSpaceMeta":
        assert parent_type
        return parent_type.__pg_base_class__._meta


class _BaseClassProxy(_OwnsMethods):
    __pg_base_class__: typing.ClassVar[
        type["RootNode"] | type["ReifiedRelation"] | type["SemanticSpace"]
    ]
    __pg_specialist_type_fields_definitions__: typing.ClassVar["ModelFieldDefinitions"]

    @property
    def __pg_field_definitions__(self) -> "ModelFieldDefinitions":
        return self.__pg_base_class__.__pg_field_definitions__

    @property
    def collapse_when(self):
        return getattr(self.__pg_base_class__, "collapse_when", None)

    _meta: typing.ClassVar["BaseMeta"] = typing.cast("BaseMeta", _MetaDescriptor())

    @model_validator(mode="before")
    @classmethod
    def unpack_edge_properties(cls, data):
        """
        When initialising, any dot-separated property of a neo4j representation of
        a relation property, ie. relation_name.relation_field_name; these need to be
        splint and added as "relation_properties" before initialising the instance
        """
        if isinstance(data, dict):
            if "edge_properties" not in data:
                data["edge_properties"] = {}

            for key, value in data.items():
                if "." in key:
                    data["edge_properties"][key.split(".")[1]] = value
        return data


RelationViaEdgeType = typing.TypeVar(
    "RelationViaEdgeType", bound="type[ReferenceSetBase | ReifiedCreateBase]"
)


class _RelationsViaEdge(typing.Generic[RelationViaEdgeType]):
    _classes: dict[str, type[RelationViaEdgeType]]

    def __init__(self):
        self._classes = {}

    def _add(self, edge_model_name: str, model: type[RelationViaEdgeType]):
        if edge_model_name not in self._classes:
            self._classes[edge_model_name] = model

    def __getattr__(self, name: str) -> type[RelationViaEdgeType] | None:
        try:
            return getattr(super(), name)
        except AttributeError:
            if name in self._classes:
                return self._classes[name]
            else:
                raise AttributeError


class _ViaEdge(typing.Generic[RelationViaEdgeType]):
    via: typing.ClassVar[_RelationsViaEdge[RelationViaEdgeType]]  # type: ignore

    def __init_subclass__(cls) -> None:
        cls.via = _RelationsViaEdge[RelationViaEdgeType]()
        return super().__init_subclass__()


RelationInContextType = typing.TypeVar(
    "RelationInContextType",
    bound="type[ViewBase | ReifiedRelationViewBase | CreateBase | ReifiedCreateBase]",
)


class _ContextFieldName[V]:
    _context_field_names: dict[str, V]

    def __init__(self):
        self._context_field_names = {}

    def _add(
        self,
        reverse_field_name: str,
        view_in_context_model: V,
    ):
        self._context_field_names[reverse_field_name] = view_in_context_model

    def __getattr__(self, name: str) -> V | None:
        try:
            return getattr(super(), name)
        except AttributeError:
            if name in self._context_field_names:
                return self._context_field_names[name]
            else:
                raise AttributeError


# Event.View.in_context_of.Cat.is_involved_in = ContextViewModel
#           ^target


class _RelationInContext(typing.Generic[RelationInContextType]):
    _classes: dict[str, _ContextFieldName[type[RelationInContextType]]]
    _cls: type[RelationInContextType]

    def __init__(self, cls):
        self._cls = cls
        self._classes = dict()

    def _add(
        self,
        relation_target_model: type["RootNode | ReifiedRelation | SemanticSpace"],
        view_in_context_model: type[RelationInContextType],
        field_name: str,
    ):
        if relation_target_model.__name__ not in self._classes:
            self._classes[relation_target_model.__name__] = _ContextFieldName()
        self._classes[relation_target_model.__name__]._add(
            reverse_field_name=field_name,
            view_in_context_model=view_in_context_model,
        )

    def __getattr__(
        self, name: str
    ) -> _ContextFieldName[type[RelationInContextType]] | None:
        try:
            return getattr(super(), name)
        except AttributeError:
            if name in self._classes:
                return self._classes[name]
            else:
                raise AttributeError(
                    f"{self._cls.__pg_base_class__.__name__}"
                    f".{self._cls.__name__.replace(self._cls.__pg_base_class__.__name__, '')} "
                    f"has no in_context model for model {name}"
                )


class _RelationInContextOf(typing.Generic[RelationInContextType]):
    in_context_of: typing.ClassVar[_RelationInContext[RelationInContextType]]  # type: ignore

    def __init_subclass__(cls) -> None:
        cls.in_context_of = _RelationInContext[RelationInContextType](cls)
        return super().__init_subclass__()

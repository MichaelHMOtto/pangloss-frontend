import typing

from pydantic import AnyHttpUrl
from ulid import ULID

from pangloss.model_config.model_manager import ModelManager
from pangloss.model_config.models_base import (
    ReferenceCreateBase,
    ReferenceSetBase,
    ReferenceViewBase,
)
from pangloss.models import BaseMeta, BaseNode
from pangloss.utils import gen_ulid, url


def test_reference_set_on_model():
    class Entity(BaseNode):
        name: str

    class Person(Entity):
        pass

    ModelManager.initialise_models()

    assert Entity.ReferenceSet
    assert issubclass(Entity.ReferenceSet, ReferenceSetBase)
    assert Entity.ReferenceSet.__pg_base_class__ is Entity
    assert Entity.ReferenceSet.__pg_field_definitions__
    assert (
        Entity.ReferenceSet.model_fields["type"].annotation == typing.Literal["Entity"]
    )
    assert Entity.ReferenceSet.model_fields["type"].default == "Entity"
    Entity.ReferenceSet.model_fields.keys()

    e = Entity.ReferenceSet(id=gen_ulid(), type="Entity")
    assert isinstance(e.id, ULID)
    assert e.type == "Entity"

    e = Entity.ReferenceSet(id=url("http://www.madeup.com/entity/1"), type="Entity")
    assert isinstance(e.id, AnyHttpUrl)
    assert e.type == "Entity"

    assert Person.ReferenceSet
    assert issubclass(Person.ReferenceSet, ReferenceSetBase)


def test_reference_view_on_model():
    class Entity(BaseNode):
        name: str

    class Person(Entity):
        pass

    ModelManager.initialise_models()

    assert Entity.ReferenceView
    assert Entity.ReferenceView.__name__ == "EntityReferenceView"
    assert issubclass(Entity.ReferenceView, ReferenceViewBase)
    assert Entity.ReferenceView.__pg_base_class__ is Entity
    assert Entity.ReferenceView.__pg_field_definitions__
    assert (
        Entity.ReferenceView.model_fields["type"].annotation == typing.Literal["Entity"]
    )
    assert Entity.ReferenceView.model_fields["type"].default == "Entity"
    assert set(Entity.ReferenceView.model_fields.keys()) == set(
        ["id", "type", "label", "head_node", "head_type", "uris", "semantic_spaces"]
    )

    e = Entity.ReferenceView(id=gen_ulid(), type="Entity", label="An Entity")
    assert isinstance(e.id, ULID)
    assert e.type == "Entity"

    assert Person.ReferenceView
    assert issubclass(Person.ReferenceView, ReferenceViewBase)


def test_reference_view_on_model_with_label_field():
    class Entity(BaseNode):
        name: str

        class Meta(BaseMeta):
            label_field = "name"

    ModelManager.initialise_models()

    assert "name" in Entity.ReferenceView.model_fields
    assert Entity.ReferenceView.model_fields["name"].annotation is str


def test_reference_create_on_model():
    class Entity(BaseNode):
        name: str

    class Person(Entity):
        class Meta(BaseMeta):
            create_by_reference = True

    ModelManager.initialise_models()

    assert not Entity.ReferenceCreate

    assert Person.ReferenceCreate
    assert issubclass(Person.ReferenceCreate, ReferenceCreateBase)


def test_reference_create_on_model_with_label_field():
    class Entity(BaseNode):
        name: str

        class Meta(BaseMeta):
            label_field = "name"

    ModelManager.initialise_models()

    assert "name" in Entity.ReferenceView.model_fields
    assert Entity.ReferenceView.model_fields["name"].annotation is str

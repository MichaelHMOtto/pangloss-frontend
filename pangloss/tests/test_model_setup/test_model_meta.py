import typing

import pytest

from pangloss.exceptions import PanglossConfigError
from pangloss.model_config.model_manager import ModelManager
from pangloss.model_config.models_base import (
    HeritableTrait,
    NonHeritableTrait,
    ReifiedRelation,
)
from pangloss.models import BaseMeta, BaseNode, RelationConfig


def test_base_meta_not_inherited_by_class_not_called_meta_raises_error():
    with pytest.raises(PanglossConfigError):

        class Thing(BaseNode):
            class SomeShit(BaseMeta):
                abstract = True

        ModelManager.initialise_models()


def test_base_meta_inherits_except_abstract():
    class Thing(BaseNode):
        class Meta(BaseMeta):
            abstract = True
            create = False

    class SubThing(Thing):
        pass

    class SubSubThing(SubThing):
        class Meta(BaseMeta):
            abstract = True
            delete = False

    class Other(BaseNode):
        class Meta(BaseMeta):
            view: bool = False

    ModelManager.initialise_models()

    assert Thing._meta.abstract
    assert not Thing._meta.create
    assert Thing._meta.edit
    assert Thing.Meta.delete

    assert not SubThing._meta.abstract
    assert not SubThing._meta.create
    assert SubThing._meta.edit
    assert SubThing.Meta.delete

    assert SubSubThing._meta.abstract
    assert not SubSubThing._meta.create
    assert SubSubThing._meta.edit
    assert not SubSubThing._meta.delete

    assert not Other._meta.view

    assert not Other._meta.view


def test_error_if_meta_label_field_not_a_field():
    with pytest.raises(PanglossConfigError):

        class Entity(BaseNode):
            name: str

            class Meta(BaseMeta):
                label_field = "wank"

        ModelManager.initialise_models()


def test_error_if_meta_label_field_not_a_property_field():
    with pytest.raises(PanglossConfigError):

        class Cat(BaseNode):
            pass

        class Entity(BaseNode):
            has_cat: typing.Annotated[Cat, RelationConfig(reverse_name="is_cat_of")]

            class Meta(BaseMeta):
                label_field = "has_cat"

        ModelManager.initialise_models()


def test_can_get_fields_through_meta():
    class Person(BaseNode):
        age: int

    ModelManager.initialise_models()

    assert Person._meta.fields is Person.__pg_field_definitions__


def test_can_get_reified_fields_through_meta():
    class Cat(BaseNode):
        pass

    class Intermediate[T](ReifiedRelation[T]):
        pass

    ModelManager.initialise_models()

    assert Intermediate._meta.fields is Intermediate.__pg_field_definitions__
    assert (
        Intermediate[Cat]._meta.fields
        is Intermediate[Cat].__pg_bound_field_definitions__
    )


def test_simple_supertypes():
    class Text(BaseNode):
        pass

    class Book(Text):
        pass

    class NiceBook(Book):
        pass

    class Magazine(Text):
        pass

    ModelManager.initialise_models()

    assert NiceBook._meta.type_labels == ["BaseNode", "NiceBook", "Book", "Text"]


def test_supertypes():
    class HeritableA(HeritableTrait):
        pass

    class HeritableB(HeritableTrait):
        pass

    class NonHeritableA(NonHeritableTrait):
        pass

    class NonHeritableB(NonHeritableTrait):
        pass

    class Thing(BaseNode, HeritableA):
        class Meta(BaseMeta):
            abstract = True
            create = False

    class SubThing(Thing, NonHeritableA):
        pass

    class SubSubThing(SubThing, HeritableB, NonHeritableB):
        class Meta(BaseMeta):
            abstract = True
            delete = False

    ModelManager.initialise_models()

    assert SubSubThing._meta.supertypes == [SubThing, Thing]
    assert set(SubSubThing._meta.traits) == set([HeritableA, HeritableB, NonHeritableB])
    assert SubSubThing._meta.type_labels == [
        "BaseNode",
        "SubSubThing",
        "SubThing",
        "Thing",
        "HeritableA",
        "HeritableB",
        "NonHeritableB",
    ]


def test_model_meta_of_derived_types():
    class Event(BaseNode):
        when: int

    ModelManager.initialise_models()

    assert Event.Create._meta is Event._meta

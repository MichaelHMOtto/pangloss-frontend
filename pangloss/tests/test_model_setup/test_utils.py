from pangloss import initialise_models
from pangloss.model_config.model_setup_functions.utils import (
    get_concrete_model_types,
)
from pangloss.model_config.models_base import (
    BaseMeta,
    HeritableTrait,
    NonHeritableTrait,
)
from pangloss.models import BaseNode


def test_get_concrete_classes_from_abstract():
    class Animal(BaseNode):
        class Meta(BaseMeta):
            abstract = True

    class Cat(Animal):
        pass

    initialise_models()

    assert not Cat._meta.abstract

    assert get_concrete_model_types(Animal, include_subclasses=True) == set([Cat])


def test_get_concrete_classes_from_heritable_trait():
    class Purchaseable(HeritableTrait):
        pass

    class Cat(BaseNode, Purchaseable):
        pass

    class Dog(BaseNode, Purchaseable):
        pass

    class NiceCat(Cat):
        pass

    initialise_models()

    assert get_concrete_model_types(Purchaseable, include_subclasses=True) == set(
        [Cat, Dog, NiceCat]
    )


def test_get_concrete_classes_from_non_heritable_trait():
    class Purchaseable(NonHeritableTrait):
        pass

    class Cat(BaseNode, Purchaseable):
        pass

    class Dog(BaseNode, Purchaseable):
        pass

    class NiceCat(Cat):
        pass

    initialise_models()

    assert get_concrete_model_types(Purchaseable, include_subclasses=True) == set(
        [Cat, Dog]
    )

import typing
from enum import Enum

import annotated_types
import pytest

from pangloss.exceptions import PanglossConfigError
from pangloss.model_config.field_definitions import (
    EmbeddedFieldDefinition,
    EnumFieldDefinition,
    ListFieldDefinition,
    MultiKeyFieldDefinition,
    PropertyFieldDefinition,
    RelationFieldDefinition,
    RelationToNodeDefinition,
    RelationToReifiedDefinition,
    RelationToTypeVarDefinition,
)
from pangloss.model_config.model_manager import ModelManager
from pangloss.model_config.model_setup_functions.build_pg_annotations import (
    build_pg_annotations,
)
from pangloss.model_config.model_setup_functions.build_pg_model_definition import (
    build_field_definition,
    build_pg_bound_model_definition_for_instatiated_reified,
    build_pg_model_definitions,
)
from pangloss.model_config.models_base import (
    CreateBase,
    EdgeModel,
    HeadViewBase,
    HeritableTrait,
    MultiKeyField,
    ReifiedRelationNode,
)
from pangloss.models import BaseNode, Embedded, ReifiedRelation, RelationConfig


def test_model_annotations():
    """Should set __pg_annotations__ to a ChainMap of dicts representing
    the annotations objects for class and its parents"""

    class Official(BaseNode):
        department: str

    class Human(BaseNode):
        age: int
        department: int

    class PoliceOfficer(Human, Official):
        rank: str

    ModelManager.initialise_models(_defined_in_test=True)

    assert PoliceOfficer.__pg_annotations__["rank"] is str
    assert PoliceOfficer.__pg_annotations__["age"] is int
    assert PoliceOfficer.__pg_annotations__["department"] is int


def test_literal_type_set_on_model():
    class Official(BaseNode):
        pass

    class Human(BaseNode):
        pass

    class PoliceOfficer(Human, Official):
        pass

    ModelManager.initialise_models(_defined_in_test=True)

    assert Official.type == "Official"
    assert Human.type == "Human"
    assert PoliceOfficer.type == "PoliceOfficer"


def test_register_reified_relation_model():
    class Intermediate[T](ReifiedRelation[T]):
        pass

    class Cat(BaseNode):
        pass

    class Person(BaseNode):
        related_via_intermediate: typing.Annotated[
            Intermediate[Cat],
            RelationConfig(reverse_name="reverse_related_via_intermeidate"),
        ]

    ModelManager.initialise_models(_defined_in_test=True)

    assert ModelManager.reified_relation_models == {"Intermediate": Intermediate}


def test_literal_type_set_on_reified_relation():
    class Intermediate[T](ReifiedRelation[T]):
        pass

    ModelManager.initialise_models(_defined_in_test=True)

    assert Intermediate.type == "Intermediate"


def test_reified_relation_types_can_have_additional_type_params():
    class Cat(BaseNode):
        pass

    class Dog(BaseNode):
        pass

    class Intermediate[T, U](ReifiedRelation[T]):
        other: U

    ModelManager.initialise_models(_defined_in_test=True)

    Intermediate[Cat, Dog]


def test_create_field_definition_with_basic_relation():
    class Cat(BaseNode):
        pass

    class Person(BaseNode):
        pass

    # Test we can annotate with related to basic type
    rel_to_basic_field_definition = build_field_definition(
        "related",
        typing.Annotated[
            Cat,
            RelationConfig(
                reverse_name="reverse_related", validators=[annotated_types.MinLen(1)]
            ),
            annotated_types.MaxLen(2),
        ],
        Person,
    )
    assert isinstance(rel_to_basic_field_definition, RelationFieldDefinition)
    assert rel_to_basic_field_definition.field_annotation is Cat
    assert isinstance(
        rel_to_basic_field_definition.field_type_definitions[0],
        RelationToNodeDefinition,
    )
    assert rel_to_basic_field_definition.field_type_definitions[0].annotated_type is Cat
    assert rel_to_basic_field_definition.reverse_name == "reverse_related"

    assert rel_to_basic_field_definition.validators == [
        annotated_types.MinLen(1),
        annotated_types.MaxLen(2),
    ]


def test_create_field_definition_raises_error_with_mix_of_relation_and_property_types():
    class Person(BaseNode):
        pass

    class Cat(BaseNode):
        pass

    # Test build_field_definition fails with a union of relation and builtin types
    with pytest.raises(PanglossConfigError):
        build_field_definition(
            "related_to_union_fail",
            typing.Annotated[Cat | str, RelationConfig(reverse_name="reverse_related")],
            Person,
        )


def test_relation_via_intermediate_builds_field_definition():
    class Intermediate[T](ReifiedRelation[T]):
        pass

    class Cat(BaseNode):
        pass

    class Person(BaseNode):
        pass

    # Test relation via intermediate returns a field definition
    # with a RelationToReifiedDefinition
    rel_via_intermediate_field_definition = build_field_definition(
        "related_via_intermediate",
        typing.Annotated[
            Intermediate[Cat],
            RelationConfig(reverse_name="reverse_related_via_intermediate"),
        ],
        Person,
    )

    assert isinstance(rel_via_intermediate_field_definition, RelationFieldDefinition)
    assert rel_via_intermediate_field_definition.field_annotation is Intermediate[Cat]
    assert isinstance(
        rel_via_intermediate_field_definition.field_type_definitions[0],
        RelationToReifiedDefinition,
    )
    assert (
        rel_via_intermediate_field_definition.field_type_definitions[0].annotated_type
        is Intermediate[Cat]
    )
    assert (
        rel_via_intermediate_field_definition.field_type_definitions[0].origin_type
        is Intermediate
    )

    T = (
        rel_via_intermediate_field_definition.field_type_definitions[0]
        .type_params_to_type_map["T"]
        .type_param
    )
    assert isinstance(
        T,
        typing.TypeVar,
    )

    V = (
        rel_via_intermediate_field_definition.field_type_definitions[0]
        .type_params_to_type_map["T"]
        .type
    )
    assert V is Cat


@typing.no_type_check
def test_create_relation_field_with_relation_to_union():
    class Intermediate[T](ReifiedRelation[T]):
        pass

    class Cat(BaseNode):
        pass

    class Dog(BaseNode):
        pass

    class Person(BaseNode):
        pass

    rel_to_union_field_definition = build_field_definition(
        "relation_to_union",
        typing.Annotated[
            Cat | Dog | Intermediate[Cat],
            RelationConfig(reverse_name="reverse_relation_to_union"),
        ],
        Person,
    )

    assert rel_to_union_field_definition
    assert isinstance(rel_to_union_field_definition, RelationFieldDefinition)
    assert rel_to_union_field_definition.field_type_definitions[0].annotated_type is Cat
    assert rel_to_union_field_definition.field_type_definitions[1].annotated_type is Dog

    assert isinstance(
        rel_to_union_field_definition.field_type_definitions[2],
        RelationToReifiedDefinition,
    )
    assert (
        rel_to_union_field_definition.field_type_definitions[2].annotated_type
        is Intermediate[Cat]
    )
    assert (
        rel_to_union_field_definition.field_type_definitions[2].origin_type
        is Intermediate
    )
    assert (
        rel_to_union_field_definition.field_type_definitions[2]
        .type_params_to_type_map["T"]
        .type
        is Cat
    )


@typing.no_type_check
def test_create_relation_field_with_relation_to_union_defined_with_typing_union():
    class Intermediate[T](ReifiedRelation[T]):
        pass

    class Cat(BaseNode):
        pass

    class Dog(BaseNode):
        pass

    class Person(BaseNode):
        pass

    rel_to_union_field_definition = build_field_definition(
        "relation_to_union",
        typing.Annotated[
            typing.Union[Cat, Dog, Intermediate[Cat]],
            RelationConfig(reverse_name="reverse_relation_to_union"),
        ],
        Person,
    )

    assert rel_to_union_field_definition
    assert isinstance(rel_to_union_field_definition, RelationFieldDefinition)
    assert rel_to_union_field_definition.field_type_definitions[0].annotated_type is Cat

    assert rel_to_union_field_definition.field_type_definitions[1].annotated_type is Dog

    assert isinstance(
        rel_to_union_field_definition.field_type_definitions[2],
        RelationToReifiedDefinition,
    )
    assert (
        rel_to_union_field_definition.field_type_definitions[2].annotated_type
        is Intermediate[Cat]
    )
    assert (
        rel_to_union_field_definition.field_type_definitions[2].origin_type
        is Intermediate
    )
    assert (
        rel_to_union_field_definition.field_type_definitions[2]
        .type_params_to_type_map["T"]
        .type
        is Cat
    )


def test_build_relation_field_to_reified_with_union_of_types():
    class Intermediate[T](ReifiedRelation[T]):
        pass

    class Cat(BaseNode):
        pass

    class Dog(BaseNode):
        pass

    class Person(BaseNode):
        pass

    rel_to_reified_union_field_definition = build_field_definition(
        "relation_to_union",
        typing.Annotated[
            Intermediate[Cat | Dog] | Cat,
            RelationConfig(reverse_name="reverse_relation_to_union"),
        ],
        Person,
    )

    assert rel_to_reified_union_field_definition
    assert isinstance(rel_to_reified_union_field_definition, RelationFieldDefinition)
    assert isinstance(
        rel_to_reified_union_field_definition.field_type_definitions[0],
        RelationToReifiedDefinition,
    )
    assert (
        rel_to_reified_union_field_definition.field_type_definitions[0].annotated_type
        is Intermediate[Cat | Dog]
    )
    assert (
        rel_to_reified_union_field_definition.field_type_definitions[0].origin_type
        is Intermediate
    )
    assert (
        rel_to_reified_union_field_definition.field_type_definitions[0]
        .type_params_to_type_map["T"]
        .type
        == Cat | Dog
    )

    assert isinstance(
        rel_to_reified_union_field_definition.field_type_definitions[1],
        RelationToNodeDefinition,
    )
    assert (
        rel_to_reified_union_field_definition.field_type_definitions[1].annotated_type
        is Cat
    )


def test_build_field_definition_for_literal_value_with_default():
    class Edge(EdgeModel):
        age: int = 100

    ModelManager.initialise_models()

    field = Edge.__pg_field_definitions__["age"]

    assert isinstance(field, PropertyFieldDefinition)
    assert field.default_value == 100


def test_build_field_definition_for_literal_value():
    class Person(BaseNode):
        pass

    string_field_definition = build_field_definition(
        "string_field",
        str,
        Person,
    )

    assert isinstance(string_field_definition, PropertyFieldDefinition)
    assert string_field_definition.field_annotation is str

    string_field_definition = build_field_definition(
        "int_field",
        int,
        Person,
    )

    assert isinstance(string_field_definition, PropertyFieldDefinition)
    assert string_field_definition.field_annotation is int

    annotated_string_field_definition = build_field_definition(
        "annotated_string_field",
        typing.Annotated[str, annotated_types.MaxLen(2), annotated_types.MinLen(1)],
        Person,
    )

    assert isinstance(annotated_string_field_definition, PropertyFieldDefinition)
    assert annotated_string_field_definition.field_annotation is str
    assert annotated_string_field_definition.validators == [
        annotated_types.MaxLen(2),
        annotated_types.MinLen(1),
    ]


def test_build_field_definition_for_list_type():
    class Person(BaseNode):
        pass

    list_string_field_definition = build_field_definition(
        "string_field",
        list[str],
        Person,
    )

    assert isinstance(list_string_field_definition, ListFieldDefinition)
    assert list_string_field_definition.field_annotation is str

    list_string_field_definition = build_field_definition(
        "string_field",
        typing.Annotated[list[str], annotated_types.MaxLen(2)],
        Person,
    )

    assert isinstance(list_string_field_definition, ListFieldDefinition)
    assert list_string_field_definition.field_annotation is str
    assert list_string_field_definition.validators == [annotated_types.MaxLen(2)]

    list_string_field_definition = build_field_definition(
        "string_field",
        typing.Annotated[
            list[typing.Annotated[str, annotated_types.MaxLen(10)]],
            annotated_types.MaxLen(2),
        ],
        Person,
    )

    assert isinstance(list_string_field_definition, ListFieldDefinition)
    assert list_string_field_definition.field_annotation is str
    assert list_string_field_definition.validators == [annotated_types.MaxLen(2)]
    assert list_string_field_definition.internal_type_validators == [
        annotated_types.MaxLen(10)
    ]

    list_string_field_definition = build_field_definition(
        "string_field", list[typing.Annotated[str, annotated_types.MaxLen(1)]], Person
    )
    assert isinstance(list_string_field_definition, ListFieldDefinition)
    assert list_string_field_definition.field_annotation is str
    assert list_string_field_definition.internal_type_validators == [
        annotated_types.MaxLen(1)
    ]


def test_build_field_definition_for_embedded_type():
    class Person(BaseNode):
        pass

    class Cat(BaseNode):
        pass

    with pytest.raises(PanglossConfigError):
        embedded_field_definition = build_field_definition(
            "embedded_field", Embedded[str], Person
        )

    embedded_field_definition = build_field_definition(
        "embedded_field", Embedded["Cat"], Person
    )

    assert isinstance(embedded_field_definition, EmbeddedFieldDefinition)
    assert embedded_field_definition.field_annotation is Cat
    assert embedded_field_definition.validators == [
        annotated_types.MinLen(1),
        annotated_types.MaxLen(1),
    ]

    embedded_field_definition = build_field_definition(
        "embedded_field",
        typing.Annotated[Embedded["Cat"], annotated_types.MaxLen(10)],
        Person,
    )

    assert isinstance(embedded_field_definition, EmbeddedFieldDefinition)
    assert embedded_field_definition.field_annotation is Cat
    assert embedded_field_definition.validators == [
        annotated_types.MaxLen(10),
    ]


def test_build_field_definition_for_embedded_union():
    class Person(BaseNode):
        pass

    class Cat(BaseNode):
        pass

    class Dog(BaseNode):
        pass

    embedded_field_definition = build_field_definition(
        "embedded_field", Embedded[Cat | Dog], Person
    )
    assert isinstance(embedded_field_definition, EmbeddedFieldDefinition)
    assert embedded_field_definition.field_annotation == Cat | Dog


def test_build_multi_key_field_definition():
    class Person(BaseNode):
        pass

    class UncertainValue[T](MultiKeyField[T]):
        certainty: int

    multi_key_field_definition = build_field_definition(
        "multi_key_field", UncertainValue[str], Person
    )
    assert isinstance(multi_key_field_definition, MultiKeyFieldDefinition)
    assert multi_key_field_definition.field_annotation is UncertainValue[str]
    assert multi_key_field_definition.multi_key_field_type is UncertainValue
    assert multi_key_field_definition.multi_key_field_value_type is str


def test_enum_field_definition():
    class Roles(Enum):
        ADMIN = "admin"
        USER = "user"

    class Person(BaseNode):
        role: Roles

    enum_field_definition = build_field_definition("multi_key_field", Roles, Person)
    assert isinstance(enum_field_definition, EnumFieldDefinition)


def test_build_relation_to_trait_field_definition():
    class Purchaseable(HeritableTrait):
        pass

    class Person(BaseNode):
        pass

    relation_to_trait_field_definition = build_field_definition(
        "relation_to_trait",
        annotation=typing.Annotated[
            Purchaseable, RelationConfig(reverse_name="is_related_to_trait")
        ],
        model=Person,
    )

    assert isinstance(relation_to_trait_field_definition, RelationFieldDefinition)

    assert relation_to_trait_field_definition.field_annotation is Purchaseable
    assert isinstance(
        relation_to_trait_field_definition.field_type_definitions[0],
        RelationToNodeDefinition,
    )
    assert (
        relation_to_trait_field_definition.field_type_definitions[0].annotated_type
        is Purchaseable
    )


@typing.no_type_check
def test_build_relation_to_union_of_node_and_trait():
    class Purchaseable(HeritableTrait):
        pass

    class Cat(BaseNode):
        pass

    class Person(BaseNode):
        pass

    relation_to_union = build_field_definition(
        "relation_to_union",
        typing.Annotated[
            "Purchaseable | Cat", RelationConfig(reverse_name="is_related_to_union")
        ],
        Person,
    )

    assert isinstance(relation_to_union, RelationFieldDefinition)
    assert relation_to_union.field_annotation == Purchaseable | Cat
    assert isinstance(
        relation_to_union.field_type_definitions[0], RelationToNodeDefinition
    )
    assert relation_to_union.field_type_definitions[0].annotated_type is Purchaseable
    assert relation_to_union.field_type_definitions[1].annotated_type is Cat


def test_build_model_field_definitions():
    class Cat(BaseNode):
        pass

    class Dog(BaseNode):
        pass

    class Person(BaseNode):
        name: str
        has_cat: typing.Annotated[Cat, RelationConfig(reverse_name="is_owned_by")]
        embedded_dog: Embedded[Dog]

    ModelManager.initialise_models(_defined_in_test=True)

    assert Person.__pg_field_definitions__["has_cat"]
    assert Person.__pg_field_definitions__.relation_fields["has_cat"]
    assert Person.__pg_field_definitions__["name"]
    assert Person.__pg_field_definitions__.property_fields["name"]
    assert "name" in Person.__pg_field_definitions__
    assert "name" in Person.__pg_field_definitions__.property_fields
    assert "name" not in Person.__pg_field_definitions__.relation_fields


def test_build_model_field_definition_on_reified():
    class Cat(BaseNode):
        pass

    class Intermediate[T](ReifiedRelation[T]):
        value: str
        has_cat: typing.Annotated[Cat, RelationConfig("cat_in_intermediate")]

    ModelManager.initialise_models()

    assert Intermediate.__pg_field_definitions__["has_cat"]
    assert isinstance(
        Intermediate.__pg_field_definitions__["has_cat"], RelationFieldDefinition
    )

    target_definition = Intermediate.__pg_field_definitions__["target"]
    assert target_definition
    assert isinstance(target_definition, RelationFieldDefinition)

    assert isinstance(
        target_definition.field_type_definitions[0], RelationToTypeVarDefinition
    )

    assert target_definition.field_type_definitions[0].typevar_name == "T"
    assert target_definition.field_type_definitions[0].annotated_type.__name__ == "T"

    value_defintion = Intermediate.__pg_field_definitions__["value"]
    assert isinstance(value_defintion, PropertyFieldDefinition)


def test_edge_model_field_definitions():
    class Thing[T](MultiKeyField[T]):
        other: str

    class Edge(EdgeModel):
        number: int
        name: str
        multikeyfield: Thing[int]

    ModelManager.initialise_models()

    number_definition = Edge.__pg_field_definitions__["number"]
    assert isinstance(number_definition, PropertyFieldDefinition)
    assert number_definition.field_annotation is int

    name_definition = Edge.__pg_field_definitions__["name"]
    assert isinstance(name_definition, PropertyFieldDefinition)
    assert name_definition.field_annotation is str

    multikeyfield_definition = Edge.__pg_field_definitions__["multikeyfield"]
    assert isinstance(multikeyfield_definition, MultiKeyFieldDefinition)
    assert multikeyfield_definition.multi_key_field_type is Thing


def test_build_pg_bound_model_definition_for_instatiated_reified():
    class Cat(BaseNode):
        pass

    class Dog(BaseNode):
        pass

    class WithAntagonist[T, U](ReifiedRelation[T]):
        antagonist: typing.Annotated[U, RelationConfig(reverse_name="is_antagonist_in")]

    build_pg_annotations(WithAntagonist)
    build_pg_model_definitions(WithAntagonist)

    W = WithAntagonist[Cat, Dog]
    build_pg_bound_model_definition_for_instatiated_reified(W)

    target_defintion = W.__pg_bound_field_definitions__["target"]
    assert isinstance(target_defintion, RelationFieldDefinition)
    assert target_defintion.field_annotation is Cat
    assert isinstance(
        target_defintion.field_type_definitions[0], RelationToNodeDefinition
    )
    assert target_defintion.field_type_definitions[0].annotated_type is Cat

    antagonist_definition = W.__pg_bound_field_definitions__["antagonist"]
    assert isinstance(antagonist_definition, RelationFieldDefinition)
    assert antagonist_definition.field_annotation is Dog
    assert isinstance(
        antagonist_definition.field_type_definitions[0], RelationToNodeDefinition
    )
    assert antagonist_definition.field_type_definitions[0].annotated_type is Dog


def test_build_pg_bound_model_definition_for_instatiated_reified_with_nested_reified():
    class Cat(BaseNode):
        pass

    class IntermediateA[T](ReifiedRelation[T]):
        pass

    class IntermediateB[T](ReifiedRelation[T]):
        pass

    build_pg_annotations(IntermediateA)
    build_pg_annotations(IntermediateB)
    build_pg_model_definitions(IntermediateA)
    build_pg_model_definitions(IntermediateB)

    IA = IntermediateA[IntermediateB[Cat]]
    build_pg_bound_model_definition_for_instatiated_reified(IA)

    IATargetDefinition = IA.__pg_bound_field_definitions__["target"]
    assert IATargetDefinition
    assert isinstance(IATargetDefinition, RelationFieldDefinition)

    assert isinstance(
        IATargetDefinition.field_type_definitions[0], RelationToReifiedDefinition
    )

    assert (
        IATargetDefinition.field_type_definitions[0].annotated_type
        is IntermediateB[Cat]
    )
    assert IATargetDefinition.field_type_definitions[0].origin_type is IntermediateB
    assert (
        IATargetDefinition.field_type_definitions[0].type_params_to_type_map["T"].type
        is Cat
    )

    IBTargetDefinition = IATargetDefinition.field_type_definitions[
        0
    ].annotated_type.__pg_bound_field_definitions__["target"]

    assert isinstance(IBTargetDefinition, RelationFieldDefinition)
    assert IBTargetDefinition.field_annotation is Cat
    assert isinstance(
        IBTargetDefinition.field_type_definitions[0], RelationToNodeDefinition
    )

    assert IBTargetDefinition.field_type_definitions[0].annotated_type is Cat


def test_build_pg_annotation_for_multikeyfield():
    class WithCertainty[T](MultiKeyField[T]):
        certainty: int

    class Person(BaseNode):
        age: WithCertainty[typing.Annotated[int, annotated_types.Gt(18)]]

    ModelManager.initialise_models()

    certainty_field = WithCertainty.__pg_field_definitions__["certainty"]
    assert isinstance(certainty_field, PropertyFieldDefinition)
    assert certainty_field.field_annotation is int

    age_field_definition = Person._meta.fields["age"]

    assert isinstance(age_field_definition, MultiKeyFieldDefinition)
    assert age_field_definition.multi_key_field_type is WithCertainty
    assert age_field_definition.multi_key_field_value_type is int
    assert age_field_definition.multi_key_field_value_validators == [
        annotated_types.Gt(18)
    ]

    assert WithCertainty._meta.fields is WithCertainty.__pg_field_definitions__


def test_build_pg_annotations_for_specialising_abstract_classes():
    ModelManager.initialise_models()
    assert list(CreateBase.__pg_specialist_type_fields_definitions__.fields.keys()) == [
        "type",
        "id",
        "label",
        "uris",
    ]

    assert list(
        HeadViewBase.__pg_specialist_type_fields_definitions__.fields.keys()
    ) == [
        "type",
        "id",
        "label",
        "uris",
        "created_by",
        "created_when",
        "modified_by",
        "modified_when",
        "semantic_spaces",
    ]


def test_build_relation_field_to_reified_with_union_of_types_curious():
    class Certainty(EdgeModel):
        certainty: float

    class TestReifiedRelation[T](ReifiedRelation[T]):
        pass

    class User(BaseNode):
        pass

    class Identification[T](ReifiedRelation[T]):
        target: typing.Annotated[
            T, RelationConfig(reverse_name="is_target_of", edge_model=Certainty)
        ]

    class WithProxy[T](ReifiedRelationNode[T]):
        proxy: typing.Annotated[
            T,
            RelationConfig(reverse_name="acts_as_proxy_in"),
        ]

    class Person(BaseNode):
        pass

    class Test(BaseNode):
        tested_person: typing.Annotated[
            TestReifiedRelation[WithProxy[Identification[Person]] | User],
            RelationConfig(reverse_name="was_tested_in"),
        ]

    field_definition = build_field_definition(
        "relation_to_union",
        typing.Annotated[
            TestReifiedRelation[WithProxy[Identification[Person]] | User],
            RelationConfig(reverse_name="was_tested_in"),
        ],
        Test,
    )

    print(field_definition)


def test_annotations_on_inherited_from_trait():
    """Make sure the annotations chainmap includes Traits"""

    class RelatedThing(BaseNode):
        pass

    class SomeTrait(HeritableTrait):
        related_thing: typing.Annotated[
            RelatedThing, RelationConfig(reverse_name="reverse_related_thing")
        ]

    class Thing(BaseNode, SomeTrait):
        pass

    build_pg_annotations(Thing)

    assert Thing.__pg_annotations__["related_thing"]

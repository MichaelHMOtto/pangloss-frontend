import datetime
from typing import Annotated, no_type_check

from pangloss import initialise_models
from pangloss.model_config.models_base import (
    EdgeModel,
    EditHeadViewBase,
    Embedded,
    ReifiedRelation,
)
from pangloss.models import BaseNode, RelationConfig
from pangloss.utils import gen_ulid


@no_type_check
def test_build_edit_head_view_model():
    class Person(BaseNode):
        pass

    class Statement(BaseNode):
        involves_person: Annotated[
            Person,
            RelationConfig(reverse_name="is_involved_in"),
        ]
        has_substatements: Annotated[
            "Statement",
            RelationConfig(
                reverse_name="is_substatement_of", create_inline=True, edit_inline=True
            ),
        ]

    class Declaration(Statement):
        pass

    class Factoid(BaseNode):
        has_statements: Annotated[
            Statement,
            RelationConfig(
                reverse_name="is_statement_in", create_inline=True, edit_inline=True
            ),
        ]

    initialise_models()

    assert Factoid.EditHeadView

    assert issubclass(Factoid.EditHeadView, EditHeadViewBase)

    # Test inherit all basic keys from EditHeadViewBase
    for key in [
        "type",
        "id",
        "label",
        "uris",
        "created_by",
        "created_when",
        "modified_by",
        "modified_when",
    ]:
        assert key in Factoid.EditHeadView.model_fields.keys()

    assert "has_statements" in Factoid.EditHeadView.model_fields.keys()

    assert (
        Factoid.EditHeadView.model_fields["has_statements"].annotation
        == list[Statement.View | Declaration.View]
    )

    f = Factoid.EditHeadView(
        type="Factoid",
        id=gen_ulid(),
        label="A Factoid",
        uris=[],
        created_by="Smith",
        created_when=datetime.datetime.now(),
        modified_by="Smith",
        modified_when=datetime.datetime.now(),
        has_statements=[
            {
                "type": "Statement",
                "id": gen_ulid(),
                "head_node": gen_ulid(),
                "label": "A statement",
                "involves_person": [
                    {
                        "type": "Person",
                        "id": gen_ulid(),
                        "label": "A Person",
                    }
                ],
                "has_substatements": [],
            }
        ],
    )

    assert f.type == "Factoid"
    assert f.id is not None
    assert f.label == "A Factoid"
    assert f.uris == []
    assert f.created_by == "Smith"
    assert f.modified_by == "Smith"
    assert f.has_statements[0].type == "Statement"
    assert f.has_statements[0].id is not None
    assert f.has_statements[0].label == "A statement"
    assert f.has_statements[0].has_substatements == []

    assert isinstance(f.has_statements[0], Statement.View)
    assert isinstance(f.has_statements[0].involves_person[0], Person.ReferenceView)


@no_type_check
def test_edit_head_view_with_relation_to_reified():
    class Certainty(EdgeModel):
        certainty: int

    class Identification[T](ReifiedRelation[T]):
        target: Annotated[
            T, RelationConfig(reverse_name="is_target_of", edge_model=Certainty)
        ]

    class Person(BaseNode):
        pass

    class Event(BaseNode):
        involves_person: Annotated[
            Person | Identification[Person],
            RelationConfig(reverse_name="is_involved_in"),
        ]

    initialise_models()

    e = Event.EditHeadView(
        type="Event",
        id=gen_ulid(),
        label="An Event",
        uris=[],
        created_by="Smith",
        created_when=datetime.datetime.now(),
        modified_by="Smith",
        modified_when=datetime.datetime.now(),
        involves_person=[
            {
                "type": "Person",
                "id": gen_ulid(),
                "label": "A Person",
            },
            {
                "type": "Identification",
                "id": gen_ulid(),
                "target": [
                    {
                        "type": "Person",
                        "id": gen_ulid(),
                        "label": "A Second Person",
                        "edge_properties": {"certainty": 1},
                    }
                ],
            },
        ],
    )

    assert e.type == "Event"
    assert e.id is not None
    assert e.label == "An Event"
    assert e.uris == []
    assert e.created_by == "Smith"
    assert e.modified_by == "Smith"
    assert e.involves_person[0].type == "Person"
    assert e.involves_person[0].id is not None
    assert e.involves_person[0].label == "A Person"
    assert e.involves_person[1].type == "Identification"
    assert e.involves_person[1].id is not None
    assert e.involves_person[1].target[0].type == "Person"
    assert e.involves_person[1].target[0].id is not None
    assert e.involves_person[1].target[0].label == "A Second Person"
    assert e.involves_person[1].target[0].edge_properties.certainty == 1
    assert isinstance(e.involves_person[0], Person.ReferenceView)
    assert isinstance(e.involves_person[1], Identification[Person].View)
    assert isinstance(
        e.involves_person[1].target[0], Person.ReferenceView.via.Certainty
    )


@no_type_check
def test_edit_head_view_model_with_embedded_node():
    class Reference(BaseNode):
        pass

    class Source(BaseNode):
        pass

    class Citation(BaseNode):
        reference: Annotated[Reference, RelationConfig(reverse_name="is_cited_by")]
        page_number: int

    class Event(BaseNode):
        citation: Embedded[Citation | Source]

    initialise_models()

    e = Event.EditHeadView(
        type="Event",
        id=gen_ulid(),
        label="An Event",
        uris=[],
        created_by="Smith",
        created_when=datetime.datetime.now(),
        modified_by="Smith",
        modified_when=datetime.datetime.now(),
        citation=[
            {
                "type": "Citation",
                "id": gen_ulid(),
                "reference": [
                    {
                        "label": "A Book",
                        "type": "Reference",
                        "id": gen_ulid(),
                    }
                ],
                "page_number": 1,
            }
        ],
    )

    assert e.type == "Event"
    assert e.id is not None
    assert e.label == "An Event"
    assert e.uris == []
    assert e.created_by == "Smith"
    assert e.modified_by == "Smith"
    assert e.citation[0].type == "Citation"
    assert e.citation[0].id is not None
    assert e.citation[0].reference[0].type == "Reference"
    assert e.citation[0].reference[0].id is not None
    assert e.citation[0].reference[0].label == "A Book"
    assert e.citation[0].page_number == 1
    assert isinstance(e.citation[0], Citation.EmbeddedView)
    assert isinstance(e.citation[0].reference[0], Reference.ReferenceView)


@no_type_check
def test_edit_head_view_model_with_double_reified():
    class Certainty(EdgeModel):
        certainty: int

    class Intermediate[T, U](ReifiedRelation[T]):
        other: Annotated[U, RelationConfig(reverse_name="is_other_in")]

    class Identification[T](ReifiedRelation[T]):
        target: Annotated[
            T, RelationConfig(reverse_name="is_target_of", edge_model=Certainty)
        ]

    class Cat(BaseNode):
        pass

    class Dog(BaseNode):
        pass

    class Person(BaseNode):
        owns_cat: Annotated[
            Intermediate[Identification[Cat], Identification[Dog]],
            RelationConfig(reverse_name="is_owned_by"),
        ]

    initialise_models()

    p = Person.EditHeadView(
        type="Person",
        id=gen_ulid(),
        label="A Person",
        uris=[],
        created_by="Smith",
        created_when=datetime.datetime.now(),
        modified_by="Smith",
        modified_when=datetime.datetime.now(),
        owns_cat=[
            {
                "type": "Intermediate",
                "id": gen_ulid(),
                "target": [
                    {
                        "type": "Identification",
                        "id": gen_ulid(),
                        "target": [
                            {
                                "type": "Cat",
                                "id": gen_ulid(),
                                "label": "A Cat",
                                "edge_properties": {"certainty": 1},
                            }
                        ],
                    }
                ],
                "other": [
                    {
                        "type": "Identification",
                        "id": gen_ulid(),
                        "target": [
                            {
                                "type": "Dog",
                                "id": gen_ulid(),
                                "label": "A Dog",
                                "edge_properties": {"certainty": 1},
                            }
                        ],
                    }
                ],
            }
        ],
    )

    assert p.type == "Person"
    assert p.id is not None
    assert p.label == "A Person"
    assert p.uris == []
    assert p.created_by == "Smith"
    assert p.modified_by == "Smith"
    assert p.owns_cat[0].type == "Intermediate"
    assert p.owns_cat[0].id is not None
    assert p.owns_cat[0].target[0].type == "Identification"
    assert p.owns_cat[0].target[0].id is not None
    assert p.owns_cat[0].target[0].target[0].type == "Cat"
    assert p.owns_cat[0].target[0].target[0].id is not None
    assert p.owns_cat[0].target[0].target[0].label == "A Cat"
    assert p.owns_cat[0].other[0].type == "Identification"
    assert p.owns_cat[0].other[0].id is not None
    assert p.owns_cat[0].other[0].target[0].type == "Dog"
    assert p.owns_cat[0].other[0].target[0].id is not None
    assert p.owns_cat[0].other[0].target[0].label == "A Dog"
    assert p.owns_cat[0].target[0].target[0].edge_properties.certainty == 1
    assert p.owns_cat[0].other[0].target[0].edge_properties.certainty == 1
    assert isinstance(
        p.owns_cat[0], Intermediate[Identification[Cat], Identification[Dog]].View
    )
    assert isinstance(p.owns_cat[0].target[0], Identification[Cat].View)
    assert isinstance(
        p.owns_cat[0].target[0].target[0], Cat.ReferenceView.via.Certainty
    )
    assert isinstance(p.owns_cat[0].other[0], Identification[Dog].View)
    assert isinstance(p.owns_cat[0].other[0].target[0], Dog.ReferenceView.via.Certainty)


@no_type_check
def test_build_edit_model_with_bound_container_value():
    class Person(BaseNode):
        name: str

    class DoingThing(BaseNode):
        when: str
        done_by: Annotated[Person, RelationConfig(reverse_name="did")]

    class OtherThing(BaseNode):
        when: str

    class NothingToDoWithIt(BaseNode):
        pass

    class Order(BaseNode):
        when: str  # <-- "Last Tuesday"
        person_giving_order: Annotated[
            Person, RelationConfig(reverse_name="gave_order")
        ]
        person_carrying_out_order: Annotated[
            Person, RelationConfig(reverse_name="carried_out_order")
        ]
        thing_ordered: Annotated[
            DoingThing | OtherThing | NothingToDoWithIt,
            RelationConfig(
                reverse_name="was_ordered_in",
                create_inline=True,
                edit_inline=True,
                bind_fields_to_related=[
                    ("person_carrying_out_order", "done_by"),
                    ("when", "when", lambda w: f"After {w}"),
                ],
            ),
        ]

    initialise_models()

    assert (
        Order.EditHeadSet.model_fields["thing_ordered"].annotation
        == list[
            DoingThing.Create.in_context_of.Order.thing_ordered
            | DoingThing.EditSet.in_context_of.Order.thing_ordered
            | OtherThing.Create.in_context_of.Order.thing_ordered
            | OtherThing.EditSet.in_context_of.Order.thing_ordered
            | NothingToDoWithIt.EditSet
            | NothingToDoWithIt.Create
        ]
    )

    order = Order.EditHeadSet(
        id=gen_ulid(),
        when="last Tuesday",
        label="An Order",
        person_giving_order=[{"type": "Person", "id": gen_ulid()}],
        person_carrying_out_order=[{"type": "Person", "id": gen_ulid()}],
        thing_ordered=[
            {"id": gen_ulid(), "type": "DoingThing", "label": "A Thing Done"}
        ],
    )

    assert order.thing_ordered[0].type == "DoingThing"
    assert order.thing_ordered[0].done_by[0].type == "Person"

    print(order.thing_ordered[0], type(order.thing_ordered[0]))

    assert isinstance(
        order.thing_ordered[0],
        DoingThing.EditSet.in_context_of.Order.thing_ordered,
    )

    """ list[
        typing.Union[
            pangloss.model_config.model_setup_functions.build_edit_set_model.DoingThing_Create__in_context_of__Order__thing_ordered,
            pangloss.model_config.model_setup_functions.build_edit_set_model.DoingThing_EditSet__in_context_of__Order__thing_ordered,
            pangloss.model_config.model_setup_functions.build_edit_set_model.OtherThing_Create__in_context_of__Order__thing_ordered,
            pangloss.model_config.model_setup_functions.build_edit_set_model.OtherThing_EditSet__in_context_of__Order__thing_ordered,
            tests.test_model_setup.test_build_edit_head_view_model.NothingToDoWithItEditSet,
            tests.test_model_setup.test_build_edit_head_view_model.NothingToDoWithItCreate,
        ]
    ] """

from typing import Annotated, no_type_check

import pytest

from pangloss import initialise_models
from pangloss.exceptions import PanglossConfigError
from pangloss.models import BaseNode, HeritableTrait, ReifiedRelation, RelationConfig
from pangloss.utils import gen_ulid


def test_override_inherited_relations_in_model_fields():
    class Task(BaseNode):
        pass

    class Agent(BaseNode):
        does_thing: Annotated[Task, RelationConfig(reverse_name="is_done_by")]

    class Person(Agent):
        person_does_thing: Annotated[
            Task,
            RelationConfig(
                reverse_name="is_done_by_person", subclasses_relation=["does_thing"]
            ),
        ]

    class Dude(Person):
        dude_does_thing: Annotated[
            Task,
            RelationConfig(
                reverse_name="is_done_by_dude",
                subclasses_relation=["person_does_thing"],
            ),
        ]

    initialise_models()

    assert "does_thing" in Agent._meta.fields
    agent_does_thing_definition = Agent._meta.fields.relation_fields["does_thing"]
    assert agent_does_thing_definition
    assert "does_thing" in agent_does_thing_definition.relation_labels
    assert "is_done_by" in agent_does_thing_definition.reverse_relation_labels

    assert "does_thing" not in Person._meta.fields
    assert "person_does_thing" in Person._meta.fields
    person_does_thing_definition = Person._meta.fields.relation_fields[
        "person_does_thing"
    ]
    assert person_does_thing_definition
    assert person_does_thing_definition.relation_labels == set(
        [
            "does_thing",
            "person_does_thing",
        ]
    )
    assert person_does_thing_definition.reverse_relation_labels == set(
        [
            "is_done_by",
            "is_done_by_person",
        ]
    )

    assert "does_thing" not in Dude._meta.fields
    assert "person_does_thing" not in Dude._meta.fields
    assert "dude_does_thing" in Dude._meta.fields

    dude_does_thing_definition = Dude._meta.fields.relation_fields["dude_does_thing"]
    assert dude_does_thing_definition
    assert dude_does_thing_definition.relation_labels == set(
        ["does_thing", "person_does_thing", "dude_does_thing"]
    )
    assert dude_does_thing_definition.reverse_relation_labels == set(
        ["is_done_by", "is_done_by_person", "is_done_by_dude"]
    )

    # Check this propogates to models by checking Create model
    assert "does_thing" in Agent.Create.model_fields
    assert "does_thing" not in Person.Create.model_fields
    assert "person_does_thing" in Person.Create.model_fields

    assert "does_thing" not in Dude.Create.model_fields
    assert "person_does_thing" not in Dude.Create.model_fields
    assert "dude_does_thing" in Dude.Create.model_fields

    # assert Dude.Create.model_fields["dude_does_thing"].validation_alias == ""
    Dude(label="Dude", doesThing=[{"type": "Task", "id": gen_ulid()}])
    Dude(label="Dude", person_does_thing=[{"type": "Task", "id": gen_ulid()}])


def test_override_relation_raises_error_when_overridden_not_in_parent():
    class Task(BaseNode):
        pass

    class Agent(BaseNode):
        does_thing: Annotated[Task, RelationConfig(reverse_name="is_done_by")]

    class Person(Agent):
        person_does_thing: Annotated[
            Task,
            RelationConfig(
                reverse_name="is_done_by_person", subclasses_relation=["not_there"]
            ),
        ]

    with pytest.raises(PanglossConfigError):
        initialise_models()


def test_override_relation_raises_error_when_overridden_not_subclass_of_parent():
    class Task(BaseNode):
        pass

    class Job(BaseNode):
        pass

    class Endeavour(BaseNode):
        pass

    class SubEndeavour(Endeavour):
        pass

    class BeingLazy(BaseNode):
        pass

    class Agent(BaseNode):
        does_thing: Annotated[
            Task | Job | Endeavour, RelationConfig(reverse_name="is_done_by")
        ]

    class Person(Agent):
        person_does_thing: Annotated[
            SubEndeavour | Job | BeingLazy,  # <-- BeingLazy is not a subclass
            RelationConfig(
                reverse_name="is_done_by_person",
                subclasses_relation=["does_thing"],
            ),
        ]

    with pytest.raises(PanglossConfigError):
        initialise_models()


@no_type_check
def test_field_from_container_model_bound_to_contained():
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
            DoingThing | OtherThing,
            RelationConfig(
                reverse_name="was_ordered_in",
                create_inline=True,
                bind_fields_to_related=[
                    ("person_carrying_out_order", "done_by"),
                    ("when", "when", lambda w: f"After {w}"),
                ],
            ),
        ]

    initialise_models()

    order = Order(
        label="An Order",
        when="Last Tuesday",
        person_giving_order=[{"type": "Person", "id": gen_ulid()}],
        person_carrying_out_order=[{"type": "Person", "id": gen_ulid()}],
        thing_ordered=[{"type": "DoingThing", "label": "A Thing Ordered"}],
    )

    assert order.thing_ordered[0].when == "After Last Tuesday"
    assert order.thing_ordered[0].done_by == order.person_carrying_out_order

    # Now check a field is not using container version if it includes
    # its own
    order = Order(
        label="An Order",
        when="Last Tuesday",
        person_giving_order=[{"type": "Person", "id": gen_ulid()}],
        person_carrying_out_order=[{"type": "Person", "id": gen_ulid()}],
        thing_ordered=[
            {
                "type": "DoingThing",
                "label": "A Thing Ordered",
                "when": "Sometime",
            }  # <-- has "when"
        ],
    )

    assert order.thing_ordered[0].when == "Sometime"
    assert order.thing_ordered[0].done_by == order.person_carrying_out_order

    order = Order(
        label="An Order",
        when="Last Tuesday",
        person_giving_order=[{"type": "Person", "id": gen_ulid()}],
        person_carrying_out_order=[{"type": "Person", "id": gen_ulid()}],
        thing_ordered=[
            {
                "type": "OtherThing",
                "label": "OtherThing Ordered",
            }
        ],
    )

    assert isinstance(order.thing_ordered[0], OtherThing.Create)
    assert order.thing_ordered[0].type == "OtherThing"
    assert order.thing_ordered[0].when == "After Last Tuesday"


def test_override_on_inherited_from_trait():
    """Make sure the annotations chainmap includes Traits"""

    class RelatedThing(BaseNode):
        pass

    class SomeTrait(HeritableTrait):
        related_thing: Annotated[
            RelatedThing, RelationConfig(reverse_name="reverse_related_thing")
        ]

    class Thing(BaseNode, SomeTrait):
        thing_related_thing: Annotated[
            RelatedThing,
            RelationConfig(
                reverse_name="reverse_name_related_thing",
                subclasses_relation=["related_thing"],
            ),
        ]

    initialise_models()


def test_override_on_inherited_with_reified():
    """Make sure the annotations chainmap includes Traits"""

    class Identification[T](ReifiedRelation[T]):
        pass

    class SecondIdentifification[T](ReifiedRelation[T]):
        pass

    class ThirdIdentification[T](ReifiedRelation[T]):
        pass

    class RelatedThing(BaseNode):
        pass

    class SomeTrait(HeritableTrait):
        related_thing: Annotated[
            RelatedThing, RelationConfig(reverse_name="reverse_related_thing")
        ]

    class Thing(BaseNode, SomeTrait):
        thing_related_thing: Annotated[
            Identification[RelatedThing],
            RelationConfig(
                reverse_name="reverse_name_related_thing",
                subclasses_relation=["related_thing"],
            ),
        ]

    class Thing2(BaseNode, SomeTrait):
        thing_related_thing: Annotated[
            SecondIdentifification[Identification[RelatedThing]],
            RelationConfig(
                reverse_name="reverse_name_related_thing",
                subclasses_relation=["related_thing"],
            ),
        ]

    initialise_models()

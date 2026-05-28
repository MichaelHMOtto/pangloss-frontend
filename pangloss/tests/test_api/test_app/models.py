from typing import Annotated

from pangloss.models import BaseNode, RelationConfig


class MyModel(BaseNode):
    name: str


class Person(BaseNode):
    pass


class Thing(BaseNode):
    is_person_of_thing: Annotated[
        Person,
        RelationConfig(reverse_name="is_thing_of_person", create_inline=True),
    ]


class SubThing(Thing):
    is_person_of_subthing: Annotated[
        Person,
        RelationConfig(
            reverse_name="is_subthing_of_person",
            subclasses_relation=["is_person_of_thing"],
        ),
    ]


class SubSubThing(SubThing):
    is_person_of_subsubthing: Annotated[
        Person,
        RelationConfig(
            reverse_name="is_person_of_subsubthing",
            subclasses_relation=["is_person_of_subthing"],
        ),
    ]

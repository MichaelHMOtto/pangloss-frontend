from typing import Annotated

from pangloss.models import BaseNode

import datetime
from typing import Annotated

from pangloss.models import BaseNode, Embedded, MultiKeyField, RelationConfig


class WithCertainty[T](MultiKeyField[T]):
    certainty: int


class Place(BaseNode):
    place_type: str
    modern_country: str
    alternative_names: list[str]


class Source(BaseNode):
    title: str
    reference: str
    year: int


class Citation(BaseNode):
    page: str
    quotation: str


class Person(BaseNode):
    name: WithCertainty[str]
    aliases: list[str]
    occupation: str
    birth_year: int
    born_in: Annotated[Place, RelationConfig(reverse_name="birthplace_of")]


class Event(BaseNode):
    event_type: str
    happened_on: datetime.datetime
    summary: str
    participant: Annotated[Person, RelationConfig(reverse_name="participated_in")]
    happened_at: Annotated[Place, RelationConfig(reverse_name="event_location_for")]
    source: Annotated[Source, RelationConfig(reverse_name="supports_event")]
    citation: Embedded[Citation]


class Object(BaseNode):
    object_type: str
    material: str
    date_description: str
    associated_person: Annotated[
        Person, RelationConfig(reverse_name="object_associated_with_person")
    ]
    associated_place: Annotated[
        Place, RelationConfig(reverse_name="object_associated_with_place")
    ]

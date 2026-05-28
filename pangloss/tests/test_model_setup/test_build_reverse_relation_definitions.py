from typing import Annotated, no_type_check

from pangloss import initialise_models
from pangloss.model_config.field_definitions import (
    ContextIncomingRelationDefinition,
    DirectIncomingRelationDefinition,
)
from pangloss.model_config.model_setup_functions.build_reverse_relation_definitions import (
    PathSegment,
    get_reverse_relation_paths,
)
from pangloss.model_config.models_base import (
    Embedded,
    ReifiedRelation,
    RelationConfig,
)
from pangloss.models import BaseNode


@no_type_check
def test_build_reverse_relation_paths():
    class Factoid(BaseNode):
        has_statements: Annotated[
            "Event", RelationConfig(reverse_name="is_statement_in")
        ]

    class Person(BaseNode):
        pass

    class Dog(BaseNode):
        pass

    class Cat(BaseNode):
        pass

    class Intermediate[T](ReifiedRelation[T]):
        pass

    class WithProxy[T, U](ReifiedRelation[T]):
        proxy: Annotated[U, RelationConfig(reverse_name="acts_as_proxy_in")]

    class Reference(BaseNode):
        pass

    class Citation(BaseNode):
        cites: Annotated[Reference, RelationConfig(reverse_name="is_cited_in")]
        cites_via_intermediate: Annotated[
            Intermediate[Reference], RelationConfig(reverse_name="is_cited_in")
        ]

    class Event(BaseNode):
        involves_entity: Annotated[
            Person
            | Dog
            | Intermediate[Cat]
            | WithProxy[Intermediate[Cat], Intermediate[Dog]],
            RelationConfig(reverse_name="is_involved_in_event"),
        ]
        involves_dog: Annotated[
            Dog, RelationConfig(reverse_name="is_involved_in_event")
        ]
        source: Embedded[Citation]

    initialise_models()

    factoid_paths = get_reverse_relation_paths(Factoid)
    assert len(factoid_paths) == 1

    assert factoid_paths[0] == [
        PathSegment(
            metatype="StartNode",
            type=Factoid,
            relation_definition=Factoid._meta.fields["has_statements"],
        ),
        PathSegment(metatype="EndNode", type=Event),
    ]

    #######
    # Sanity check: reverse_relations fields initialising correctly
    assert isinstance(Event._meta.fields.reverse_relations, dict)

    paths = get_reverse_relation_paths(Event)

    assert len(paths) == 8

    assert paths[0] == [
        PathSegment(
            metatype="StartNode",
            type=Event,
            relation_definition=Event._meta.fields["involves_entity"],
        ),
        PathSegment(metatype="EndNode", type=Person),
    ]

    assert paths[0].reverse_key == "is_involved_in_event"
    assert isinstance(
        paths[0].build_reverse_relation_definition(), DirectIncomingRelationDefinition
    )
    assert (
        paths[0].build_reverse_relation_definition().reverse_name
        == "is_involved_in_event"
    )
    assert paths[0].build_reverse_relation_definition().reverse_target is Event
    assert (
        paths[0].build_reverse_relation_definition().relation_definition
        is Event._meta.fields["involves_entity"]
    )

    assert paths[1] == [
        PathSegment(
            metatype="StartNode",
            type=Event,
            relation_definition=Event._meta.fields["involves_entity"],
        ),
        PathSegment(metatype="EndNode", type=Dog),
    ]
    assert paths[0].reverse_key == "is_involved_in_event"
    assert paths[0].reverse_key == "is_involved_in_event"
    assert isinstance(
        paths[0].build_reverse_relation_definition(), DirectIncomingRelationDefinition
    )
    assert (
        paths[0].build_reverse_relation_definition().reverse_name
        == "is_involved_in_event"
    )
    assert paths[0].build_reverse_relation_definition().reverse_target is Event
    assert (
        paths[0].build_reverse_relation_definition().relation_definition
        is Event._meta.fields["involves_entity"]
    )

    assert paths[2] == [
        PathSegment(
            metatype="StartNode",
            type=Event,
            relation_definition=Event._meta.fields["involves_entity"],
        ),
        PathSegment(
            metatype="ReifiedRelation",
            type=Intermediate[Cat],
            relation_definition=Intermediate[Cat]._meta.fields["target"],
        ),
        PathSegment(
            metatype="EndNode",
            type=Cat,
        ),
    ]
    assert paths[2].reverse_key == "is_involved_in_event"

    assert isinstance(
        paths[2].build_reverse_relation_definition(), ContextIncomingRelationDefinition
    )
    assert (
        paths[2].build_reverse_relation_definition().reverse_name
        == "is_involved_in_event"
    )
    assert paths[2].build_reverse_relation_definition().reverse_target is Event
    assert (
        paths[2].build_reverse_relation_definition().relation_definition
        is Event._meta.fields["involves_entity"]
    )

    assert paths[3] == [
        PathSegment(
            metatype="StartNode",
            type=Event,
            relation_definition=Event._meta.fields["involves_entity"],
        ),
        PathSegment(
            metatype="ReifiedRelation",
            type=WithProxy[Intermediate[Cat], Intermediate[Dog]],
            relation_definition=WithProxy[
                Intermediate[Cat], Intermediate[Dog]
            ]._meta.fields["target"],
        ),
        PathSegment(
            metatype="ReifiedRelation",
            type=Intermediate[Cat],
            relation_definition=Intermediate[Cat]._meta.fields["target"],
        ),
        PathSegment(
            metatype="EndNode",
            type=Cat,
        ),
    ]

    assert paths[3].reverse_key == "is_involved_in_event"

    assert isinstance(
        paths[3].build_reverse_relation_definition(), ContextIncomingRelationDefinition
    )
    assert (
        paths[3].build_reverse_relation_definition().reverse_name
        == "is_involved_in_event"
    )
    assert paths[3].build_reverse_relation_definition().reverse_target is Event
    assert (
        paths[3].build_reverse_relation_definition().relation_definition
        is Event._meta.fields["involves_entity"]
    )

    assert paths[4] == [
        PathSegment(
            metatype="StartNode",
            type=Event,
            relation_definition=Event._meta.fields["involves_entity"],
        ),
        PathSegment(
            metatype="ReifiedRelation",
            type=WithProxy[Intermediate[Cat], Intermediate[Dog]],
            relation_definition=WithProxy[
                Intermediate[Cat], Intermediate[Dog]
            ]._meta.fields["proxy"],
        ),
        PathSegment(
            metatype="ReifiedRelation",
            type=Intermediate[Dog],
            relation_definition=Intermediate[Dog]._meta.fields["target"],
        ),
        PathSegment(metatype="EndNode", type=Dog),
    ]
    assert paths[4].reverse_key == "acts_as_proxy_in"
    assert isinstance(
        paths[4].build_reverse_relation_definition(), ContextIncomingRelationDefinition
    )
    assert (
        paths[4].build_reverse_relation_definition().reverse_name == "acts_as_proxy_in"
    )
    assert paths[4].build_reverse_relation_definition().reverse_target is Event
    assert (
        paths[4].build_reverse_relation_definition().relation_definition
        is Event._meta.fields["involves_entity"]
    )

    assert paths[5] == [
        PathSegment(
            metatype="StartNode",
            type=Event,
            relation_definition=Event._meta.fields["involves_dog"],
        ),
        PathSegment(metatype="EndNode", type=Dog),
    ]

    assert paths[5].reverse_key == "is_involved_in_event"
    assert isinstance(
        paths[5].build_reverse_relation_definition(), DirectIncomingRelationDefinition
    )
    assert (
        paths[5].build_reverse_relation_definition().reverse_name
        == "is_involved_in_event"
    )
    assert paths[5].build_reverse_relation_definition().reverse_target is Event
    assert (
        paths[5].build_reverse_relation_definition().relation_definition
        is Event._meta.fields["involves_dog"]
    )

    assert paths[6] == [
        PathSegment(
            metatype="StartNode",
            type=Event,
            relation_definition=Event._meta.fields["source"],
        ),
        PathSegment(
            metatype="EmbeddedNode",
            type=Citation,
            relation_definition=Citation._meta.fields["cites"],
        ),
        PathSegment(metatype="EndNode", type=Reference),
    ]

    assert paths[6].reverse_key == "is_cited_in"
    assert isinstance(
        paths[6].build_reverse_relation_definition(), DirectIncomingRelationDefinition
    )
    assert paths[6].build_reverse_relation_definition().reverse_name == "is_cited_in"
    assert paths[6].build_reverse_relation_definition().reverse_target is Event
    assert (
        paths[6].build_reverse_relation_definition().relation_definition
        is Citation._meta.fields["cites"]
    )

    assert paths[7] == [
        PathSegment(
            metatype="StartNode",
            type=Event,
            relation_definition=Event._meta.fields["source"],
        ),
        PathSegment(
            metatype="EmbeddedNode",
            type=Citation,
            relation_definition=Citation._meta.fields["cites_via_intermediate"],
        ),
        PathSegment(
            metatype="ReifiedRelation",
            type=Intermediate[Reference],
            relation_definition=Intermediate[Reference]._meta.fields["target"],
        ),
        PathSegment(metatype="EndNode", type=Reference),
    ]

    assert paths[7].reverse_key == "is_cited_in"
    assert isinstance(
        paths[7].build_reverse_relation_definition(), ContextIncomingRelationDefinition
    )
    assert paths[7].build_reverse_relation_definition().reverse_name == "is_cited_in"
    assert paths[7].build_reverse_relation_definition().reverse_target is Event
    assert (
        paths[7].build_reverse_relation_definition().relation_definition
        is Event._meta.fields["source"]
    )


@no_type_check
def test_object_fields_contains_incoming_relations():
    class Factoid(BaseNode):
        has_statements: Annotated[
            "Event", RelationConfig(reverse_name="is_statement_in")
        ]

    class Person(BaseNode):
        pass

    class Dog(BaseNode):
        pass

    class Cat(BaseNode):
        pass

    class Intermediate[T](ReifiedRelation[T]):
        pass

    class WithProxy[T, U](ReifiedRelation[T]):
        proxy: Annotated[U, RelationConfig(reverse_name="acts_as_proxy_in")]

    class Reference(BaseNode):
        pass

    class Citation(BaseNode):
        cites: Annotated[Reference, RelationConfig(reverse_name="is_cited_in")]
        cites_via_intermediate: Annotated[
            Intermediate[Reference], RelationConfig(reverse_name="is_cited_in")
        ]

    class Event(BaseNode):
        involves_entity: Annotated[
            Person
            | Dog
            | Intermediate[Cat]
            | WithProxy[Intermediate[Cat], Intermediate[Dog]],
            RelationConfig(reverse_name="is_involved_in_event"),
        ]
        involves_dog: Annotated[
            Dog, RelationConfig(reverse_name="is_involved_in_event")
        ]
        source: Embedded[Citation]

    initialise_models()

    assert (
        Event._meta.reverse_relations["is_statement_in"].pop().reverse_target is Factoid
    )

    assert Cat._meta.reverse_relations["is_involved_in_event"]

    assert "is_involved_in_event" in Dog._meta.reverse_relations
    assert "acts_as_proxy_in" in Dog._meta.reverse_relations

    assert "is_cited_in" in Reference._meta.reverse_relations

import dataclasses
from typing import Literal, cast

from pangloss.model_config.field_definitions import (
    ContextIncomingRelationDefinition,
    DirectIncomingRelationDefinition,
    EmbeddedFieldDefinition,
    IncomingRelationDefinition,
    RelationFieldDefinition,
    RelationToNodeDefinition,
    RelationToReifiedDefinition,
)
from pangloss.model_config.model_setup_functions.utils import (
    get_concrete_model_types,
)
from pangloss.model_config.models_base import (
    ReifiedRelation,
    ReifiedRelationNode,
    RootNode,
)


@dataclasses.dataclass
class PathSegment:
    metatype: (
        Literal["StartNode"]
        | Literal["EndNode"]
        | Literal["EmbeddedNode"]
        | Literal["ReifiedRelation"]
    )
    type: type[RootNode] | type[ReifiedRelation]
    relation_definition: RelationFieldDefinition | EmbeddedFieldDefinition | None = None

    def __repr__(self):
        if self.relation_definition:
            return f"""PathSegment(metatype={self.metatype}, type={self.type.__name__}, relation_name="{self.relation_definition.field_name}")"""
        else:
            return f"PathSegment(metatype={self.metatype}, type={self.type.__name__})"

    def __hash__(self) -> int:
        return hash(self.type.__name__ + str(hash(self.relation_definition)))


class Path(list[PathSegment]):
    def __init__(self, *args):
        super().__init__(args)

    def __hash__(self) -> int:
        return hash("|".join(str(self)))

    @property
    def is_all_reified_target(self) -> bool:
        return all(
            cast(
                RelationFieldDefinition | EmbeddedFieldDefinition,
                segment.relation_definition,
            ).field_name
            == "target"
            for segment in self[1:-1]
        )

    @property
    def contains_embedded(self):
        return any(segment.metatype == "EmbeddedNode" for segment in self)

    def get_reverse_key_from_embedded(self) -> str:
        for i, segment in enumerate(self, start=0):
            if segment.metatype == "EmbeddedNode":
                starting_index = i
                break

        return Path(*self[starting_index:]).reverse_key

    def select_key_from_path(self) -> str:
        for i, segment in enumerate(self[1:-1], start=1):
            if (
                segment.metatype == "EmbeddedNode"
                and self[i + 1].metatype == "EmbeddedNode"
            ):
                continue

            if segment.metatype == "EmbeddedNode":
                return cast(
                    RelationFieldDefinition, segment.relation_definition
                ).reverse_name

            if (
                cast(RelationFieldDefinition, segment.relation_definition).field_name
                != "target"
            ):
                return cast(
                    RelationFieldDefinition, segment.relation_definition
                ).reverse_name

        raise Exception(f"Could not locate appropriate reverse_name for {self}")

    def get_last_embedded_index(self) -> int:
        index = 0
        for i, segment in enumerate(self, start=0):
            if segment.metatype == "EmbeddedNode":
                index = i

        return index

    def get_non_embedded_prior_to_embedded(self, index: int) -> PathSegment:
        for segment in reversed(self[0:index]):
            if (
                issubclass(segment.type, (RootNode, ReifiedRelationNode))
                and not segment.metatype == "EmbeddedNode"
            ):
                return segment
        return self[0]

    @property
    def reverse_key(self) -> str:
        if len(self) == 2 and self[1].metatype == "EndNode":
            return cast(
                RelationFieldDefinition, self[0].relation_definition
            ).reverse_name

        if len(self) > 2 and self.is_all_reified_target:
            return cast(
                RelationFieldDefinition, self[0].relation_definition
            ).reverse_name

        if len(self) > 2 and not self.is_all_reified_target:
            return self.select_key_from_path()

        if len(self) > 2 and self.contains_embedded:
            return self.get_reverse_key_from_embedded()
        return "None"

    def build_reverse_relation_definition(self) -> IncomingRelationDefinition:
        # If simple relation, return DirectRelation
        if self[0].metatype == "StartNode" and self[1].metatype == "EndNode":
            return DirectIncomingRelationDefinition(
                reverse_name=self.reverse_key,
                reverse_target=cast(type[RootNode], self[0].type),
                forward_path_object=self,
                relation_definition=cast(
                    RelationFieldDefinition, self[0].relation_definition
                ),
            )
        # If, from the point of the last embedded, get the path nodes after
        # the embedded and check whether there are two;
        # if so, it's a simple relation bound on the real item before the
        # embedded node/chain of embedded nodes
        elif (
            len(self) > 2
            and self.contains_embedded
            and len(Path(*self[self.get_last_embedded_index() :])) == 2
        ):
            return DirectIncomingRelationDefinition(
                reverse_name=self.reverse_key,
                reverse_target=cast(
                    type[RootNode],
                    self.get_non_embedded_prior_to_embedded(
                        self.get_last_embedded_index()
                    ).type,
                ),
                forward_path_object=self,
                relation_definition=cast(
                    RelationFieldDefinition,
                    self[self.get_last_embedded_index()].relation_definition,
                ),
            )

        else:
            return ContextIncomingRelationDefinition(
                reverse_name=self.reverse_key,
                reverse_target=cast(type[RootNode], self[0].type),
                forward_path_object=self,
                relation_definition=cast(
                    RelationFieldDefinition, self[0].relation_definition
                ),
            )


def get_reverse_relation_paths(
    model: type[RootNode] | type[ReifiedRelation],
    path_components: list[PathSegment] | None = None,
    paths: list[Path] | None = None,
    next_metatype: (
        Literal["StartNode"]
        | Literal["EndNode"]
        | Literal["EmbeddedNode"]
        | Literal["ReifiedRelation"]
    ) = "StartNode",
) -> list[Path]:
    if path_components is None:
        path_components = []
    if paths is None:
        paths = []

    for relation_defintion in model._meta.fields.relation_fields:
        for field_type_definition in relation_defintion.field_type_definitions:
            if isinstance(field_type_definition, RelationToNodeDefinition):
                paths.append(
                    Path(
                        *path_components,
                        PathSegment(
                            metatype=next_metatype,
                            relation_definition=relation_defintion,
                            type=model,
                        ),
                        PathSegment(
                            metatype="EndNode",
                            type=field_type_definition.annotated_type,
                        ),
                    )
                )

            elif isinstance(field_type_definition, RelationToReifiedDefinition):
                get_reverse_relation_paths(
                    model=field_type_definition.annotated_type,
                    path_components=[
                        *path_components,
                        PathSegment(
                            metatype=next_metatype,
                            type=model,
                            relation_definition=relation_defintion,
                        ),
                    ],
                    paths=paths,
                    next_metatype="ReifiedRelation",
                )
    for embedded_definition in model._meta.fields.embedded_fields:
        for field_concrete_type in get_concrete_model_types(
            embedded_definition.field_annotation, include_subclasses=True
        ):
            get_reverse_relation_paths(
                model=field_concrete_type,
                path_components=[
                    *path_components,
                    PathSegment(
                        metatype=next_metatype,
                        type=model,
                        relation_definition=embedded_definition,
                    ),
                ],
                paths=paths,
                next_metatype="EmbeddedNode",
            )

    return paths


def build_reverse_relations_definitions_to(model: type[RootNode]):
    paths = get_reverse_relation_paths(model)

    for path in paths:
        for concrete_model_type in get_concrete_model_types(
            cast(type[RootNode], path[-1].type)
        ):
            concrete_model_type._meta.reverse_relations[path.reverse_key].add(
                path.build_reverse_relation_definition()
            )

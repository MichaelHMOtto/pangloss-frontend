import typing
import uuid
from urllib.parse import urljoin

import jsonpatch

from pydantic import AnyHttpUrl, AnyUrl

from ulid import ULID
from pydantic_extra_types.ulid import ULID as PdULID

from pangloss.model_config.models_base import (
    CreateBase,
    EmbeddedCreateBase,
    ReifiedCreateBase,
    ReferenceCreateBase,
    ReferenceSetBase,
    EditHeadSetBase,
    EditSetBase,
    ReifiedRelationEditSetBase,
    EmbeddedSetBase,
    SemanticSpaceCreateBase,
    SemanticSpaceEditSetBase,
)
from pangloss.settings import SETTINGS
from pangloss.model_config.field_definitions import (
    RelationFieldDefinition,
    EmbeddedFieldDefinition,
)

if typing.TYPE_CHECKING:
    from pangloss.models import BaseNode


class Identifier(str):
    def __new__(cls):
        return super().__new__(cls, "x" + uuid.uuid4().hex[:6].lower())


class QuerySubstring(str):
    def __new__(cls, query_string: str):
        return super().__new__(cls, query_string)


class QueryParams(dict[Identifier, dict[str, typing.Any] | typing.Any]):
    def add(self, item: dict[str, typing.Any] | typing.Any) -> Identifier:
        identifier = Identifier()
        self.__setitem__(identifier, item)
        return identifier


def join_labels(labels: list[str], extra_labels: typing.Iterable[str]):
    all_labels = [*labels, *extra_labels]
    return f"{':'.join(all_labels)}"


def convert_type_for_writing(value):
    match value:
        case ULID():
            return str(value)
        case AnyUrl():
            return str(value)
        case set():
            return list(value)
        case tuple():
            return list(value)
        case _:
            return value


def convert_dict_for_writing(data: dict[str, typing.Any]):
    return {key: convert_type_for_writing(value) for key, value in data.items()}


def get_properties_as_writeable_dict(
    instance: "BaseNode | CreateBase | ReifiedCreateBase | EmbeddedCreateBase | ReferenceCreateBase | EditHeadSetBase | EditSetBase | ReifiedRelationEditSetBase  | EmbeddedSetBase | SemanticSpaceCreateBase | EditSetBase | ReifiedRelationEditSetBase | EmbeddedSetBase | SemanticSpaceEditSetBase",
    extras: dict[str, typing.Any] | None = None,
) -> dict[str, typing.Any]:
    data = {}
    for property_definition in instance._meta.fields.property_fields:
        if property_definition.field_metatype == "MultiKeyField":
            for key, value in dict(
                getattr(instance, property_definition.field_name)
            ).items():
                data[f"{property_definition.field_name}____{key}"] = (
                    convert_type_for_writing(value)
                )

        else:
            if value := getattr(instance, property_definition.field_name, None):
                data[property_definition.field_name] = convert_type_for_writing(value)
    if extras:
        for key, value in extras.items():
            data[key] = convert_type_for_writing(value)

    return data


class DeferredQueryObject:
    match_query_strings: list[str]
    create_query_strings: list[str]
    merge_query_strings: list[str]
    set_query_strings: list[str]
    params: QueryParams
    return_identifier: Identifier
    head_id: ULID | PdULID
    head_type: str | None

    def __init__(self):
        self.match_query_strings = []
        self.create_query_strings = []
        self.merge_query_strings = []
        self.set_query_strings = []
        self.params = QueryParams()
        self.head_type = None

    def to_query_string(self):
        return f"""
            {"\n".join(self.match_query_strings)}
            {"\n".join(self.create_query_strings)}
            {"\n".join(self.set_query_strings)}
            {"\n".join(self.merge_query_strings)}
            RETURN true
        """


class QueryObject:
    match_query_strings: list[str]
    create_query_strings: list[str]
    merge_query_strings: list[str]
    set_query_strings: list[str]
    params: QueryParams
    return_identifier: Identifier
    head_id: ULID | PdULID
    head_type: str | None
    deferred_query: "DeferredQueryObject"

    def __init__(self):
        self.match_query_strings = []
        self.create_query_strings = []
        self.merge_query_strings = []
        self.set_query_strings = []
        self.params = QueryParams()
        self.head_type = None
        self.deferred_query = DeferredQueryObject()

    def to_query_string(self) -> typing.LiteralString:
        if not self.return_identifier:
            raise Exception("CreateQuery.to_query_string called on non-top-level node")
        return typing.cast(
            typing.LiteralString,
            f"""
            {"\n".join(self.match_query_strings)}
            {"\n".join(self.create_query_strings)}
            {"\n".join(self.set_query_strings)}
            {"\n".join(self.merge_query_strings)}
            RETURN {self.return_identifier}{{.*, uris: []}}
        """,
        )


def add_uri_nodes_query(
    instance_uris: list[AnyHttpUrl],
    node_identifier: Identifier,
    query_object: QueryObject,
):
    """Adds PGUri nodes for HeadNode"""

    for instance_uri in instance_uris:
        uri_identifier = Identifier()
        uri_value_identifier = query_object.params.add(str(instance_uri))
        query_object.merge_query_strings.append(
            f"""
                MERGE ({uri_identifier}:PGCore:PGInternal:PGUri {{uri: ${uri_value_identifier}}})
                MERGE ({node_identifier})-[:URIS]->({uri_identifier})
            """
        )


def add_creation_data_node_query(
    instance: CreateBase | ReferenceCreateBase,
    node_identifier: Identifier,
    query_object: QueryObject,
    username: str,
):
    """Adds a PGCreation node attached to the HeadNode and a PGUser"""

    user_identifier = query_object.params.add(username)
    creation_node_identifier = Identifier()

    # Need to create a json patch from an empty object
    # to allow winding forward from nothing
    diff_from_empty = jsonpatch.JsonPatch.from_diff(
        {},
        instance.model_dump(round_trip=True, mode="json", warnings=False),
    ).to_string()
    creation_node_data_identifier = query_object.params.add(diff_from_empty)

    query_object.match_query_strings.append(
        f"""MATCH ({user_identifier}:PGUser {{username: ${user_identifier}}})"""
    )

    query_object.create_query_strings.append(
        f"""CREATE ({node_identifier})-[:PG_CREATED_IN]->({creation_node_identifier}:PGInternal:PGCore:PGCreation {{created_when: datetime.realtime('+00:00')}})-[:PG_CREATED_BY]->({user_identifier})"""
    )
    query_object.set_query_strings.append(
        f"""SET {creation_node_identifier}.creation = ${creation_node_data_identifier}"""
    )


def add_create_inline_relation(
    target_instance: CreateBase,
    source_node_identifier: Identifier,
    relation_definition: RelationFieldDefinition,
    query_object: QueryObject,
    source_node_id: ULID | PdULID,
    semantic_spaces: list[str],
):
    """Adds a query for a CreateInline node"""

    assert isinstance(target_instance, CreateBase)

    edge_properties = dict(getattr(target_instance, "edge_properties", {}))
    primary_relation_edge_properties = convert_dict_for_writing(
        {
            **edge_properties,
            "reverse_name": relation_definition.reverse_name,
            "relation_labels": relation_definition.relation_labels,
            "reverse_relation_labels": relation_definition.reverse_relation_labels,
            "_pg_primary_rel": True,
            "semantic_spaces": semantic_spaces,
        }
    )
    primary_edge_properties_identifier = query_object.params.add(
        primary_relation_edge_properties
    )

    extra_labels = ["ReadInline", "CreateInline", "PGIndexableNode"]
    if relation_definition.edit_inline:
        extra_labels.append("EditInline")
        extra_labels.append("DetachDelete")

    new_node_identifier, new_node_id = add_node_to_create_query_object(
        instance=target_instance,
        query_object=query_object,
        extra_labels=extra_labels,
        semantic_spaces=semantic_spaces,
    )

    relation_identifier = Identifier()

    query_object.create_query_strings.append(
        f"""
            CREATE ({source_node_identifier})-[{relation_identifier}:{relation_definition.field_name.upper()}]->({new_node_identifier})
            SET {relation_identifier} = ${primary_edge_properties_identifier}
        """
    )
    add_deferred_extra_relation(
        query_object=query_object,
        relation_definition=relation_definition,
        # target_node_identifier=new_node_identifier,
        target_node_id=new_node_id,
        source_node_id=source_node_id,
        primary_relation_edge_properties=primary_relation_edge_properties,
    )


def add_deferred_extra_relation(
    query_object: QueryObject,
    relation_definition: RelationFieldDefinition,
    target_node_id: AnyHttpUrl | PdULID | ULID,
    source_node_id: ULID | PdULID,
    primary_relation_edge_properties: dict[str, str | list | typing.Any],
) -> None:
    """Adds a deferred query to create inferred relations"""

    target_node_identifier = Identifier()
    deferred_source_node_identifier = Identifier()
    reverse_relation_identifier = Identifier()

    reverse_primary_edge_properties_identifier = query_object.deferred_query.params.add(
        {**primary_relation_edge_properties, "_pg_primary_rel": False}
    )

    source_node_id_identifier = query_object.deferred_query.params.add(
        str(source_node_id)
    )
    target_node_id_identifier = query_object.deferred_query.params.add(
        str(target_node_id)
    )
    if isinstance(target_node_id, AnyHttpUrl):
        query_object.deferred_query.match_query_strings.append(
            f"""
                MATCH (:PGUri {{uri: ${target_node_id_identifier}}})<-[:URIS]-({target_node_identifier}:BaseNode)  
            """
        )
    else:
        query_object.deferred_query.match_query_strings.append(
            f"""// Matching target {target_node_id}
                MATCH ({target_node_identifier}:PGIndexableNode {{id: ${target_node_id_identifier}}})        
            """
        )

    query_object.deferred_query.match_query_strings.append(
        f"""// Matching source {source_node_id}
            MATCH({deferred_source_node_identifier}:PGIndexableNode {{id: ${source_node_id_identifier}}})
        """
    )
    query_object.deferred_query.create_query_strings.append(
        f"""
            CREATE ({deferred_source_node_identifier})<-[{reverse_relation_identifier}:{relation_definition.reverse_name.upper()}]-({target_node_identifier})
            SET {reverse_relation_identifier} = ${reverse_primary_edge_properties_identifier}
           
        """
    )
    forward_sub_edge_properties_identifier = query_object.deferred_query.params.add(
        {"_pg_primary_rel": False, "_pg_superclass_of": relation_definition.field_name}
    )
    reverse_sub_edge_properties_identifier = query_object.deferred_query.params.add(
        {
            "_pg_primary_rel": False,
            "_pg_superclass_of": relation_definition.reverse_name,
        }
    )
    for (
        forward_rel_name,
        reverse_rel_name,
    ) in relation_definition.subclassed_relations:
        forward_sub_relation_identifier = Identifier()
        reverse_sub_relation_identifier = Identifier()

        query_object.deferred_query.create_query_strings.append(f"""
            CREATE ({deferred_source_node_identifier})-[{forward_sub_relation_identifier}:{forward_rel_name.upper()}]->({target_node_identifier})
            CREATE ({deferred_source_node_identifier})<-[{reverse_sub_relation_identifier}:{reverse_rel_name.upper()}]-({target_node_identifier})
            SET {forward_sub_relation_identifier} = ${forward_sub_edge_properties_identifier}
            SET {reverse_sub_relation_identifier} = ${reverse_sub_edge_properties_identifier}
        """)


def add_reference_set_relation(
    target_instance: ReferenceSetBase,
    source_node_identifier: Identifier,
    relation_definition: RelationFieldDefinition,
    query_object: QueryObject,
    source_node_id: ULID | PdULID,
    semantic_spaces: list[str],
) -> None:
    """Add relation to existing node"""
    target_node_identifier = Identifier()
    target_node_id_identifier = query_object.params.add(str(target_instance.id))

    if isinstance(target_instance.id, AnyHttpUrl):
        query_object.match_query_strings.append(
            f"""
                MATCH (:PGUri {{uri: ${target_node_id_identifier}}})<-[:URIS]-({target_node_identifier}:BaseNode)  
            """
        )
    else:
        query_object.match_query_strings.append(
            f"""
                MATCH ({target_node_identifier}:BaseNode {{id: ${target_node_id_identifier}}})        
            """
        )

    edge_properties = dict(getattr(target_instance, "edge_properties", {}))
    primary_relation_edge_properties = convert_dict_for_writing(
        {
            **edge_properties,
            "reverse_name": relation_definition.reverse_name,
            "relation_labels": relation_definition.relation_labels,
            "reverse_relation_labels": relation_definition.reverse_relation_labels,
            "_pg_primary_rel": True,
            "semantic_spaces": semantic_spaces,
        }
    )
    primary_edge_properties_identifier = query_object.params.add(
        primary_relation_edge_properties
    )

    primary_relation_identifier = Identifier()
    query_object.create_query_strings.append(
        f"""
            CREATE ({source_node_identifier})-[{primary_relation_identifier}:{relation_definition.field_name.upper()}]->({target_node_identifier})
            SET {primary_relation_identifier} = ${primary_edge_properties_identifier}
        """
    )

    add_deferred_extra_relation(
        query_object=query_object,
        relation_definition=relation_definition,
        # target_node_identifier=target_node_identifier,
        target_node_id=target_instance.id,
        source_node_id=source_node_id,
        primary_relation_edge_properties=primary_relation_edge_properties,
    )


def add_reference_create_relation(
    target_instance: ReferenceCreateBase,
    source_node_identifier: Identifier,
    relation_definition: RelationFieldDefinition,
    query_object: QueryObject,
    source_node_id: ULID | PdULID,
    username: str,
    semantic_spaces: list[str],
):
    target_node_identifier = Identifier()

    node_labels_string = join_labels(
        target_instance._meta.type_labels, ["HeadNode", "PGIndexableNode"]
    )

    if isinstance(target_instance.id, AnyHttpUrl):
        uri_identifier = query_object.params.add(target_instance.id)
        extra_node_data = {
            "id": str(ULID()),
            "label": target_instance.label,
            "is_deleted": False,
            "marked_for_delete": False,
        }
        node_data_identifier = query_object.params.add(
            get_properties_as_writeable_dict(target_instance, extras=extra_node_data)
        )

        query_object.create_query_strings.append(
            f"""MERGE ({target_node_identifier}:{node_labels_string})-[:URIS]->(u:PGCore:PGInternal:PGUri WHERE u.uri = ${uri_identifier})
                ON CREATE 
                    SET {target_node_identifier} = ${node_data_identifier}
                """
        )
    else:
        extra_node_data = {
            "id": str(target_instance.id),
            "label": target_instance.label,
            "is_deleted": False,
            "marked_for_delete": False,
        }
        node_data_identifier = query_object.params.add(
            get_properties_as_writeable_dict(target_instance, extras=extra_node_data)
        )
        new_uri_identifier = query_object.params.add(
            str(
                urljoin(
                    str(SETTINGS.ENTITY_BASE_URL),
                    f"{target_instance.type}/{str(target_instance.id)}",
                )
            )
        )

        query_object.create_query_strings.append(
            f"""MERGE ({target_node_identifier}:{node_labels_string})
                ON CREATE
                    SET {target_node_identifier} = ${node_data_identifier}
                    
                CREATE ({target_node_identifier})-[:URIS]->(:PGCore:PGInternal:PGUri {{uri: ${new_uri_identifier}}})
            """
        )
        add_creation_data_node_query(
            instance=target_instance,
            node_identifier=target_node_identifier,
            query_object=query_object,
            username=username,
        )

    edge_properties = getattr(target_instance, "edge_properties", {})
    primary_relation_edge_properties = convert_dict_for_writing(
        {
            **edge_properties,
            "reverse_name": relation_definition.reverse_name,
            "relation_labels": relation_definition.relation_labels,
            "reverse_relation_labels": relation_definition.reverse_relation_labels,
            "_pg_primary_rel": True,
            "semantic_spaces": semantic_spaces,
        }
    )
    primary_edge_properties_identifier = query_object.params.add(
        primary_relation_edge_properties
    )

    primary_relation_identifier = Identifier()
    query_object.create_query_strings.append(
        f"""
            CREATE ({source_node_identifier})-[{primary_relation_identifier}:{relation_definition.field_name.upper()}]->({target_node_identifier})
            SET {primary_relation_identifier} = ${primary_edge_properties_identifier}
        """
    )

    add_deferred_extra_relation(
        query_object=query_object,
        relation_definition=relation_definition,
        # target_node_identifier=target_node_identifier,
        target_node_id=target_instance.id,
        source_node_id=source_node_id,
        primary_relation_edge_properties=primary_relation_edge_properties,
    )


def add_create_reified_relation_node_query(
    target_instance: ReifiedCreateBase,
    source_instance: CreateBase
    | ReifiedCreateBase
    | EmbeddedCreateBase
    | EditHeadSetBase
    | SemanticSpaceCreateBase
    | SemanticSpaceEditSetBase
    | EditSetBase
    | ReifiedRelationEditSetBase
    | EmbeddedSetBase,
    source_node_identifier: Identifier,
    relation_definition: RelationFieldDefinition,
    query_object: QueryObject,
    source_node_id: ULID | PdULID,
    semantic_spaces: list[str],
) -> None:
    """Adds a query to a ReifiedRelation"""

    assert isinstance(target_instance, ReifiedCreateBase)

    edge_properties = getattr(target_instance, "edge_properties", {})
    primary_relation_edge_properties = convert_dict_for_writing(
        {
            **edge_properties,
            "reverse_name": relation_definition.reverse_name,
            "relation_labels": relation_definition.relation_labels,
            "reverse_relation_labels": relation_definition.reverse_relation_labels,
            "_pg_primary_rel": True,
            "semantic_spaces": semantic_spaces,
        }
    )
    primary_edge_properties_identifier = query_object.params.add(
        primary_relation_edge_properties
    )

    extra_labels = [
        "ReadInline",
        "CreateInline",
        "ReifiedRelation",
        "EditInline",
        "DetachDelete",
        "PGIndexableNode",
    ]

    new_node_identifier, new_node_id = add_node_to_create_query_object(
        instance=target_instance,
        query_object=query_object,
        extra_labels=extra_labels,
        semantic_spaces=semantic_spaces,
    )

    relation_identifier = Identifier()

    query_object.create_query_strings.append(
        f"""
            CREATE ({source_node_identifier})-[{relation_identifier}:{relation_definition.field_name.upper()}]->({new_node_identifier})
            SET {relation_identifier} = ${primary_edge_properties_identifier}
        """
    )

    # Check whether the source instance is a ReifiedCreateBase;
    # if so, it is part of a chain of Reifieds; otherwise (this is the case
    # we are interested in), we need to add a deferred query to map
    # the node in question to the eventual target

    if isinstance(source_instance, ReifiedCreateBase):
        return

    source_node_id_identifier = query_object.deferred_query.params.add(
        str(source_node_id)
    )
    shortcut_source_node_identifier = Identifier()
    shortcut_target_node_identifier = Identifier()
    shortcut_primary_forward_relation_identifier = Identifier()
    shortcut_primary_reverse_relation_identifier = Identifier()

    shortcut_primary_edge_properties_identifier = (
        query_object.deferred_query.params.add(
            {
                **primary_relation_edge_properties,
                "_pg_primary_rel": False,
                "_pg_shortcut": True,
                "head_id": str(source_node_id),
            }
        )
    )

    query_object.deferred_query.match_query_strings.append(
        f"""MATCH ({shortcut_source_node_identifier}:BaseNode {{id: ${source_node_id_identifier}}})-[:{relation_definition.field_name.upper()}]->(:ReifiedRelation)(()-[:TARGET]->()){{0,}}({shortcut_target_node_identifier}:BaseNode)"""
    )

    query_object.deferred_query.create_query_strings.append(
        f"""
            CREATE ({shortcut_source_node_identifier})-[{shortcut_primary_forward_relation_identifier}:{relation_definition.field_name.upper()}]->({shortcut_target_node_identifier})
            SET {shortcut_primary_forward_relation_identifier} = ${shortcut_primary_edge_properties_identifier}
            CREATE ({shortcut_source_node_identifier})<-[{shortcut_primary_reverse_relation_identifier}:{relation_definition.reverse_name.upper()}]-({shortcut_target_node_identifier})
            SET {shortcut_primary_reverse_relation_identifier} = ${shortcut_primary_edge_properties_identifier}
           
        """
    )

    forward_sub_edge_properties_identifier = query_object.deferred_query.params.add(
        {
            "_pg_primary_rel": False,
            "_pg_superclass_of": relation_definition.field_name,
            "_pg_shortcut": True,
            "head_id": str(source_node_id),
            "semantic_spaces": semantic_spaces,
        }
    )
    reverse_sub_edge_properties_identifier = query_object.deferred_query.params.add(
        {
            "_pg_primary_rel": False,
            "_pg_superclass_of": relation_definition.reverse_name,
            "_pg_shortcut": True,
            "head_id": str(source_node_id),
            "semantic_spaces": semantic_spaces,
        }
    )

    for (
        forward_rel_name,
        reverse_rel_name,
    ) in relation_definition.subclassed_relations:
        forward_sub_relation_identifier = Identifier()
        reverse_sub_relation_identifier = Identifier()

        query_object.deferred_query.create_query_strings.append(f"""
            CREATE ({shortcut_source_node_identifier})-[{forward_sub_relation_identifier}:{forward_rel_name.upper()}]->({shortcut_target_node_identifier})
            CREATE ({shortcut_source_node_identifier})<-[{reverse_sub_relation_identifier}:{reverse_rel_name.upper()}]-({shortcut_target_node_identifier})
            SET {forward_sub_relation_identifier} = ${forward_sub_edge_properties_identifier}
            SET {reverse_sub_relation_identifier} = ${reverse_sub_edge_properties_identifier}
        """)


def add_create_embedded_relation(
    target_instance: EmbeddedCreateBase,
    source_node_identifier: Identifier,
    relation_definition: EmbeddedFieldDefinition,
    query_object: QueryObject,
    semantic_spaces: list[str],
):
    extra_labels = ["Embedded", "ReadInline", "DetachDelete", "PGIndexableNode"]
    relation_identifier = Identifier()
    new_node_identifier, new_node_id = add_node_to_create_query_object(
        instance=target_instance,
        query_object=query_object,
        extra_labels=extra_labels,
        semantic_spaces=semantic_spaces,
    )

    embedded_properties_identifier = query_object.params.add(
        {"_pg_embedded": True, "_pg_primary_rel": True}
    )
    query_object.create_query_strings.append(
        f""" 
            CREATE ({source_node_identifier})-[{relation_identifier}:{relation_definition.field_name.upper()}]->({new_node_identifier})
            SET {relation_identifier} = ${embedded_properties_identifier}
        """
    )


def add_create_semantic_space_relation(
    target_instance: SemanticSpaceCreateBase,
    source_node_identifier: Identifier,
    relation_definition: RelationFieldDefinition,
    query_object: QueryObject,
    source_node_id: ULID | PdULID,
    semantic_spaces: list[str],
) -> None:
    assert isinstance(target_instance, SemanticSpaceCreateBase)

    edge_properties = dict(getattr(target_instance, "edge_properties", {}))
    primary_relation_edge_properties = convert_dict_for_writing(
        {
            **edge_properties,
            "reverse_name": relation_definition.reverse_name,
            "relation_labels": relation_definition.relation_labels,
            "reverse_relation_labels": relation_definition.reverse_relation_labels,
            "_pg_primary_rel": True,
            "semantic_spaces": semantic_spaces,
        }
    )
    primary_edge_properties_identifier = query_object.params.add(
        primary_relation_edge_properties
    )

    extra_labels = [
        "ReadInline",
        "CreateInline",
        "EditInline",
        "DetachDelete",
        "PGIndexableNode",
    ]

    new_node_identifier, new_node_id = add_node_to_create_query_object(
        instance=target_instance,
        query_object=query_object,
        extra_labels=extra_labels,
        semantic_spaces=semantic_spaces,
    )

    relation_identifier = Identifier()

    query_object.create_query_strings.append(
        f"""
            CREATE ({source_node_identifier})-[{relation_identifier}:{relation_definition.field_name.upper()}]->({new_node_identifier})
            SET {relation_identifier} = ${primary_edge_properties_identifier}
        """
    )
    add_deferred_extra_relation(
        query_object=query_object,
        relation_definition=relation_definition,
        # target_node_identifier=new_node_identifier,
        target_node_id=new_node_id,
        source_node_id=source_node_id,
        primary_relation_edge_properties=primary_relation_edge_properties,
    )


def add_create_relation_query(
    target_instance: ReferenceSetBase
    | ReferenceCreateBase
    | CreateBase
    | ReifiedCreateBase
    | EmbeddedCreateBase
    | EditSetBase,
    relation_definition: RelationFieldDefinition | EmbeddedFieldDefinition,
    source_instance: CreateBase
    | ReifiedCreateBase
    | EmbeddedCreateBase
    | EditHeadSetBase
    | SemanticSpaceCreateBase,
    source_node_identifier: Identifier,
    query_object: QueryObject,
    source_node_id: ULID,
    username: str,
    semantic_spaces: list[str],
) -> None:
    if isinstance(target_instance, EmbeddedCreateBase) and isinstance(
        relation_definition, EmbeddedFieldDefinition
    ):
        add_create_embedded_relation(
            target_instance=target_instance,
            source_node_identifier=source_node_identifier,
            relation_definition=relation_definition,
            query_object=query_object,
            semantic_spaces=semantic_spaces,
        )

    elif isinstance(target_instance, SemanticSpaceCreateBase) and isinstance(
        relation_definition, RelationFieldDefinition
    ):
        add_create_semantic_space_relation(
            target_instance=target_instance,
            source_node_identifier=source_node_identifier,
            relation_definition=relation_definition,
            query_object=query_object,
            source_node_id=source_node_id,
            semantic_spaces=semantic_spaces,
        )

    elif (
        isinstance(target_instance, CreateBase)
        and isinstance(relation_definition, RelationFieldDefinition)
        and relation_definition.create_inline
    ):
        add_create_inline_relation(
            target_instance=target_instance,
            source_node_identifier=source_node_identifier,
            relation_definition=relation_definition,
            query_object=query_object,
            source_node_id=source_node_id,
            semantic_spaces=semantic_spaces,
        )

    elif isinstance(target_instance, ReferenceCreateBase) and isinstance(
        relation_definition, RelationFieldDefinition
    ):
        add_reference_create_relation(
            target_instance=target_instance,
            source_node_identifier=source_node_identifier,
            relation_definition=relation_definition,
            query_object=query_object,
            source_node_id=source_node_id,
            username=username,
            semantic_spaces=semantic_spaces,
        )

    elif isinstance(target_instance, ReferenceSetBase) and isinstance(
        relation_definition, RelationFieldDefinition
    ):
        add_reference_set_relation(
            target_instance=target_instance,
            source_node_identifier=source_node_identifier,
            relation_definition=relation_definition,
            query_object=query_object,
            source_node_id=source_node_id,
            semantic_spaces=semantic_spaces,
        )

    elif isinstance(target_instance, ReifiedCreateBase) and isinstance(
        relation_definition, RelationFieldDefinition
    ):
        add_create_reified_relation_node_query(
            target_instance=target_instance,
            source_instance=source_instance,
            source_node_identifier=source_node_identifier,
            relation_definition=relation_definition,
            query_object=query_object,
            source_node_id=source_node_id,
            semantic_spaces=semantic_spaces,
        )


def add_node_to_create_query_object(
    instance: CreateBase
    | ReifiedCreateBase
    | EmbeddedCreateBase
    | SemanticSpaceCreateBase,
    query_object: QueryObject,
    semantic_spaces: list[str],
    extra_labels: list[str] | None = None,
    head_node: bool = False,
    username: str = "DefaultUser",
) -> tuple[Identifier, ULID]:
    if not extra_labels:
        extra_labels = []

    node_identifier: Identifier = Identifier()

    instance_id: ULID
    instance_uris: list[AnyHttpUrl] = getattr(instance, "uris", [])

    if isinstance(instance, CreateBase):
        if isinstance(instance.id, list):
            instance_uris.extend(instance.id)
        elif isinstance(instance.id, AnyHttpUrl):
            instance_uris.append(instance.id)
        elif isinstance(instance.id, ULID):
            instance_id = instance.id

    if not isinstance(getattr(instance, "id", None), ULID):
        instance_id = ULID()

    extra_node_data = {
        "id": instance_id,
        "is_deleted": False,
        "marked_for_delete": False,
        "semantic_spaces": semantic_spaces,
    }

    if head_node:
        assert isinstance(instance, CreateBase)

        extra_labels.extend(["HeadNode", "PGIndexableNode"])
        query_object.head_id = instance_id
        query_object.head_type = instance.type
        query_object.return_identifier = node_identifier

        instance_uris.append(
            AnyHttpUrl(
                urljoin(str(SETTINGS.ENTITY_BASE_URL), f"{instance.type}/{instance_id}")
            )
        )

    else:
        extra_node_data["head_id"] = query_object.head_id
        extra_node_data["head_type"] = query_object.head_type

    if isinstance(instance, CreateBase):
        extra_node_data["label"] = instance.label

    node_data_identifier = query_object.params.add(
        get_properties_as_writeable_dict(instance, extras=extra_node_data)
    )

    node_labels_string = join_labels(instance._meta.type_labels, extra_labels)

    query_object.create_query_strings.append(
        f"""
            CREATE ({node_identifier}:{node_labels_string}) // Creating {instance.type}
            SET {node_identifier} = ${node_data_identifier}
        """
    )

    if head_node:
        add_creation_data_node_query(
            instance=typing.cast(CreateBase, instance),
            node_identifier=node_identifier,
            query_object=query_object,
            username=username,
        )

    if instance_uris:
        add_uri_nodes_query(instance_uris, node_identifier, query_object)

    if isinstance(instance, SemanticSpaceCreateBase):
        semantic_spaces = semantic_spaces.copy()
        semantic_spaces.append(instance.__pg_base_class__.__name__)

    for relation_definition in instance._meta.fields.relation_fields:
        for related_instance in getattr(instance, relation_definition.field_name, []):
            add_create_relation_query(
                target_instance=related_instance,
                source_instance=instance,
                relation_definition=relation_definition,
                source_node_identifier=node_identifier,
                query_object=query_object,
                source_node_id=instance_id,
                username=username,
                semantic_spaces=semantic_spaces,
            )

    for embedded_definition in instance._meta.fields.embedded_fields:
        for embedded_instance in getattr(instance, embedded_definition.field_name, []):
            add_create_relation_query(
                target_instance=embedded_instance,
                source_instance=instance,
                relation_definition=embedded_definition,
                source_node_identifier=node_identifier,
                query_object=query_object,
                source_node_id=instance_id,
                username=username,
                semantic_spaces=semantic_spaces,
            )

    return node_identifier, instance_id


def build_create_query_object(
    instance: CreateBase, current_username: str | None = None
) -> QueryObject:
    query_object = QueryObject()

    add_node_to_create_query_object(
        instance=instance,
        query_object=query_object,
        head_node=True,
        username=current_username or "DefaultUser",
        semantic_spaces=[],
    )
    return query_object

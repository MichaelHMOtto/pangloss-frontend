import typing

import jsonpatch
from pydantic import AnyHttpUrl
from pydantic_extra_types.ulid import ULID as PydanticULID
from ulid import ULID

from pangloss.exceptions import PanglossNotFoundError
from pangloss.model_config.field_definitions import (
    EmbeddedFieldDefinition,
    RelationFieldDefinition,
)
from pangloss.model_config.models_base import (
    CreateBase,
    EditHeadSetBase,
    EditSetBase,
    EmbeddedCreateBase,
    EmbeddedSetBase,
    ReferenceCreateBase,
    ReferenceSetBase,
    ReifiedCreateBase,
    ReifiedRelationEditSetBase,
    RootNode,
    SemanticSpaceCreateBase,
    SemanticSpaceEditSetBase,
)
from pangloss.neo4j.create import (
    Identifier,
    QueryObject,
    add_create_embedded_relation,
    add_create_inline_relation,
    add_create_reified_relation_node_query,
    add_create_semantic_space_relation,
    add_deferred_extra_relation,
    add_reference_create_relation,
    add_reference_set_relation,
    add_uri_nodes_query,
    convert_dict_for_writing,
    get_properties_as_writeable_dict,
    join_labels,
)
from pangloss.neo4j.database import Transaction, database


@database.read_transaction
async def get_existing(
    model: type[RootNode], tx: Transaction, id: ULID | PydanticULID
) -> EditHeadSetBase:
    query = f"""
        MATCH path_to_node = (node:BaseNode {{id: $id}})
        
        OPTIONAL MATCH (node)-[:URIS]->(uris:PGUri)
       
        // Collect outgoing node patterns
        CALL (node) {{
            {"OPTIONAL MATCH path_to_direct_nodes = (node)-[{_pg_primary_rel: true}]->(:BaseNode)" if model._meta.fields.relation_fields else ""}
            {"OPTIONAL MATCH path_to_related_through_embedded = (node)-[{_pg_primary_rel: true}]->(:Embedded)((:Embedded)-[{_pg_primary_rel: true}]->(:Embedded)){ 0, }(:Embedded)-[{_pg_primary_rel: true}]->{0,}(:BaseNode)" if model._meta.fields.embedded_fields else ""}
            {"OPTIONAL MATCH path_through_read_nodes = (node)-[{_pg_primary_rel: true}]->(:ReadInline)((:ReadInline)-[{_pg_primary_rel: true}]->(:ReadInline)){0,}(:ReadInline)-[{_pg_primary_rel: true}]->{0,}(:BaseNode)" if model._meta.fields.relation_fields else ""}
            OPTIONAL MATCH path_to_reified = (node)-[{{_pg_primary_rel: true}}]->(first_reified:ReifiedRelation)((:ReifiedRelation)-[{{_pg_primary_rel: true}}]->(x WHERE x:BaseNode or x:ReifiedRelation)){{0,}}(:BaseNode)
            WITH apoc.coll.flatten([
                collect(path_to_reified),
                {"collect(path_through_read_nodes)," if model._meta.fields.relation_fields else ""}
                {"collect(path_to_related_through_embedded)," if model._meta.fields.embedded_fields else ""}
                {"collect(path_to_direct_nodes)," if model._meta.fields.relation_fields else ""}
                []
            ]) AS paths, node
            CALL apoc.paths.toJsonTree(paths)
                YIELD value
                RETURN value as outgoing 
        }}
       
        WITH node, outgoing, {{uris: collect(uris.uri)}} as all_uris

        RETURN apoc.map.mergeList([node, all_uris, outgoing])"""

    result = await tx.run(query, {"id": str(id)})
    records = await result.value()
    if records:
        return model.EditHeadSet(**records[0])
    raise PanglossNotFoundError(f"{model.__name__}")


def add_edit_reified_relation_node_query(
    target_instance: ReifiedRelationEditSetBase,
    relation_definition: RelationFieldDefinition,
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
    query_object: QueryObject,
    source_node_id: ULID | PydanticULID,
    semantic_spaces: list[str],
) -> None:
    original_id_identifier = query_object.params.add(str(target_instance.id))
    query_object.match_query_strings.append(
        f"""MATCH (:PGIndexableNode {{id: ${original_id_identifier}}})"""
    )
    edge_properties = getattr(target_instance, "edge_properties", {})
    primary_relation_edge_properties = convert_dict_for_writing(
        {
            **edge_properties,
            "reverse_name": relation_definition.reverse_name,
            "relation_labels": relation_definition.relation_labels,
            "reverse_relation_labels": relation_definition.reverse_relation_labels,
            "_pg_primary_rel": True,
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

    new_node_identifier, new_node_id = add_update_node_to_create_query_object(
        instance_id=target_instance.id,
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
        }
    )
    reverse_sub_edge_properties_identifier = query_object.deferred_query.params.add(
        {
            "_pg_primary_rel": False,
            "_pg_superclass_of": relation_definition.reverse_name,
            "_pg_shortcut": True,
            "head_id": str(source_node_id),
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


def add_update_node_to_create_query_object(
    instance_id: ULID | PydanticULID,
    instance: EditSetBase
    | ReifiedRelationEditSetBase
    | EmbeddedSetBase
    | SemanticSpaceEditSetBase,
    query_object: QueryObject,
    semantic_spaces: list[str],
    extra_labels: list[str] | None = None,
    head_node: bool = False,
    username: str = "DefaultUser",
) -> tuple[Identifier, ULID | PydanticULID]:
    if not extra_labels:
        extra_labels = []

    node_identifier: Identifier = Identifier()
    instance_uris: list[AnyHttpUrl] = getattr(instance, "uris", [])

    extra_node_data = {
        "id": instance_id,
        "is_deleted": False,
        "marked_for_delete": False,
        "semantic_spaces": semantic_spaces,
    }

    extra_node_data["head_id"] = query_object.head_id
    extra_node_data["head_type"] = query_object.head_type

    if isinstance(instance, (CreateBase, EditSetBase)):
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

    if instance_uris:
        add_uri_nodes_query(instance_uris, node_identifier, query_object)

    for relation_definition in instance._meta.fields.relation_fields:
        for related_instance in getattr(instance, relation_definition.field_name, []):
            add_update_relation_query(
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
            add_update_relation_query(
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


def add_update_embedded_relation(
    target_instance: EmbeddedSetBase,
    source_node_identifier: Identifier,
    relation_definition: EmbeddedFieldDefinition,
    query_object: QueryObject,
    semantic_spaces: list[str],
):
    original_id_identifier = query_object.params.add(str(target_instance.id))
    query_object.match_query_strings.append(
        f"""MATCH (:PGIndexableNode {{id: ${original_id_identifier}}})"""
    )
    extra_labels = ["Embedded", "ReadInline", "DetachDelete", "PGIndexableNode"]
    relation_identifier = Identifier()
    new_node_identifier, new_node_id = add_update_node_to_create_query_object(
        instance_id=target_instance.id,
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


def add_update_inline_relation(
    target_instance: EditSetBase,
    source_node_identifier: Identifier,
    relation_definition: RelationFieldDefinition,
    query_object: QueryObject,
    source_node_id: ULID | PydanticULID,
    semantic_spaces: list[str],
):
    """Adds a query for an EditInline node"""
    original_id_identifier = query_object.params.add(str(target_instance.id))
    query_object.match_query_strings.append(
        f"""MATCH (:PGIndexableNode {{id: ${original_id_identifier}}})"""
    )

    assert isinstance(target_instance, EditSetBase)

    edge_properties = dict(getattr(target_instance, "edge_properties", {}))
    primary_relation_edge_properties = convert_dict_for_writing(
        {
            **edge_properties,
            "reverse_name": relation_definition.reverse_name,
            "relation_labels": relation_definition.relation_labels,
            "reverse_relation_labels": relation_definition.reverse_relation_labels,
            "_pg_primary_rel": True,
        }
    )
    primary_edge_properties_identifier = query_object.params.add(
        primary_relation_edge_properties,
    )

    extra_labels = ["ReadInline", "CreateInline", "PGIndexableNode"]
    if relation_definition.edit_inline:
        extra_labels.append("EditInline")
        extra_labels.append("DetachDelete")

    new_node_identifier, new_node_id = add_update_node_to_create_query_object(
        instance_id=target_instance.id,
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


def add_update_semantic_space_query(
    target_instance: SemanticSpaceEditSetBase,
    source_node_identifier: Identifier,
    relation_definition: RelationFieldDefinition,
    query_object: QueryObject,
    source_node_id: ULID | PydanticULID,
    semantic_spaces: list[str],
):
    """Adds a query for an EditInline node"""
    original_id_identifier = query_object.params.add(str(target_instance.id))
    query_object.match_query_strings.append(
        f"""MATCH (:PGIndexableNode {{id: ${original_id_identifier}}})"""
    )

    assert isinstance(target_instance, EditSetBase)

    edge_properties = dict(getattr(target_instance, "edge_properties", {}))
    primary_relation_edge_properties = convert_dict_for_writing(
        {
            **edge_properties,
            "reverse_name": relation_definition.reverse_name,
            "relation_labels": relation_definition.relation_labels,
            "reverse_relation_labels": relation_definition.reverse_relation_labels,
            "_pg_primary_rel": True,
        }
    )
    primary_edge_properties_identifier = query_object.params.add(
        primary_relation_edge_properties,
    )

    extra_labels = [
        "ReadInline",
        "CreateInline",
        "PGIndexableNode",
        "EditInline",
        "DetachDelete",
    ]

    new_node_identifier, new_node_id = add_update_node_to_create_query_object(
        instance_id=target_instance.id,
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


def add_update_relation_query(
    target_instance: ReferenceSetBase
    | ReferenceCreateBase
    | CreateBase
    | ReifiedCreateBase
    | EmbeddedCreateBase
    | EditSetBase
    | SemanticSpaceCreateBase
    | SemanticSpaceEditSetBase,
    relation_definition: RelationFieldDefinition | EmbeddedFieldDefinition,
    source_instance: CreateBase
    | ReifiedCreateBase
    | EmbeddedCreateBase
    | EditHeadSetBase
    | SemanticSpaceCreateBase
    | SemanticSpaceEditSetBase
    | EditSetBase
    | ReifiedRelationEditSetBase
    | EmbeddedSetBase
    | SemanticSpaceEditSetBase,
    source_node_identifier: Identifier,
    query_object: QueryObject,
    source_node_id: ULID | PydanticULID,
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
    elif isinstance(target_instance, EmbeddedSetBase) and isinstance(
        relation_definition, EmbeddedFieldDefinition
    ):
        add_update_embedded_relation(
            target_instance=target_instance,
            source_node_identifier=source_node_identifier,
            relation_definition=relation_definition,
            query_object=query_object,
            semantic_spaces=semantic_spaces,
        )

    elif (
        isinstance(target_instance, CreateBase)
        and isinstance(relation_definition, RelationFieldDefinition)
        and (relation_definition.create_inline or relation_definition.edit_inline)
    ):
        add_create_inline_relation(
            target_instance=target_instance,
            source_node_identifier=source_node_identifier,
            relation_definition=relation_definition,
            query_object=query_object,
            source_node_id=source_node_id,
            semantic_spaces=semantic_spaces,
        )
    elif (
        isinstance(target_instance, EditSetBase)
        and isinstance(relation_definition, RelationFieldDefinition)
        and relation_definition.edit_inline
    ):
        add_update_inline_relation(
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
    elif isinstance(target_instance, ReifiedRelationEditSetBase) and isinstance(
        relation_definition, RelationFieldDefinition
    ):
        add_edit_reified_relation_node_query(
            target_instance=target_instance,
            source_instance=source_instance,
            source_node_identifier=source_node_identifier,
            relation_definition=relation_definition,
            query_object=query_object,
            source_node_id=source_node_id,
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
    elif isinstance(target_instance, SemanticSpaceEditSetBase) and isinstance(
        relation_definition, RelationFieldDefinition
    ):
        add_update_semantic_space_query(
            target_instance=target_instance,
            source_node_identifier=source_node_identifier,
            relation_definition=relation_definition,
            query_object=query_object,
            source_node_id=source_node_id,
            semantic_spaces=semantic_spaces,
        )


async def build_update_query(
    instance: EditHeadSetBase,
    semantic_spaces: list[str],
    current_username: str = "DefaultUser",
) -> QueryObject | None:
    if not semantic_spaces:
        semantic_spaces = []

    # Get existing item, and make a json update patch
    existing = await get_existing(
        typing.cast(type[RootNode], instance.__pg_base_class__), instance.id
    )

    update_json_patch = jsonpatch.JsonPatch.from_diff(
        existing.model_dump(round_trip=True, mode="json"),
        instance.model_dump(round_trip=True, mode="json"),
    )

    if not update_json_patch:
        # In this case, there is no change in the data and we can return None early
        return None

    query_object = QueryObject()
    node_identifier = Identifier()
    update_json_patch_identifier = query_object.params.add(
        update_json_patch.to_string()
    )

    query_object.return_identifier = node_identifier
    query_object.head_id = instance.id
    query_object.head_type = instance.type

    user_node_identifier = Identifier()
    head_id_identifier = query_object.params.add(str(query_object.head_id))
    node_properties = get_properties_as_writeable_dict(
        instance, {"label": instance.label}
    )

    head_node_data_identifier = query_object.params.add(node_properties)
    username_identifier = query_object.params.add(current_username)
    modification_id_identifier = query_object.params.add(str(ULID()))

    # Match THIS node first, and update the properties
    query_object.match_query_strings.append(
        f"""MATCH ({query_object.return_identifier}:BaseNode {{id: ${head_id_identifier}}}) // Match Head"""
    )
    query_object.set_query_strings.append(
        f"""SET {query_object.return_identifier} += ${head_node_data_identifier} // Update head node properties"""
    )

    # Create PGModification node by diffing instance and existing; add write to query
    query_object.match_query_strings.append(
        f"""MATCH ({user_node_identifier}:PGUser {{username: ${username_identifier}}}) // Find user"""
    )

    query_object.create_query_strings.append(
        f"CREATE ({query_object.return_identifier})-[:PG_MODIFIED_IN]->(:PGInternal:PGCore:PGModification {{modified_when: datetime.realtime('+00:00'), modification: ${update_json_patch_identifier}, id: ${modification_id_identifier}}})-[:PG_MODIFIED_BY]->({user_node_identifier}) "
    )

    query_object.create_query_strings.append(
        f"""
        WITH *
        CALL ({query_object.return_identifier}) {{
            WITH *
            OPTIONAL MATCH (to_delete:PGIndexableNode {{head_id: ${head_id_identifier}}})
            OPTIONAL MATCH ({query_object.return_identifier})-[relation]->(:BaseNode)
            OPTIONAL MATCH ({query_object.return_identifier})<-[relation_reversed]-(:BaseNode)
           
            DELETE relation
            DELETE relation_reversed
            DETACH DELETE to_delete
        }}
        """
    )

    add_uri_nodes_query(
        instance_uris=instance.uris,
        node_identifier=node_identifier,
        query_object=query_object,
    )

    for relation_definition in instance._meta.fields.relation_fields:
        for related_instance in getattr(instance, relation_definition.field_name, []):
            add_update_relation_query(
                target_instance=related_instance,
                source_instance=instance,
                relation_definition=relation_definition,
                source_node_identifier=node_identifier,
                query_object=query_object,
                source_node_id=instance.id,
                username=current_username,
                semantic_spaces=semantic_spaces,
            )

    for embedded_definition in instance._meta.fields.embedded_fields:
        for embedded_instance in getattr(instance, embedded_definition.field_name, []):
            add_update_relation_query(
                target_instance=embedded_instance,
                source_instance=instance,
                relation_definition=embedded_definition,
                source_node_identifier=node_identifier,
                query_object=query_object,
                source_node_id=instance.id,
                username=current_username,
                semantic_spaces=semantic_spaces,
            )

    return query_object

    # TODO: DO something about the URIs...
    # What will actually happen when we trash everything? URI nodes become disconnected
    # But then found/created and reattached!

    # and need to be connected/added again

    # Write node props updates
    # Trash all head_id == instance_id

    # Run create_relation for all options thereafter

    return query_object

import asyncio
import typing

from rich import print

from pangloss.model_config.model_manager import ModelManager
from pangloss.neo4j.database import Transaction, database

if typing.TYPE_CHECKING:
    from pangloss.models import BaseNode


class IndexAnnotation:
    def __hash__(self):
        return 0


class Index(IndexAnnotation):
    pass


class Unique(IndexAnnotation):
    pass


class TextIndex(IndexAnnotation):
    pass


class FullTextIndex(IndexAnnotation):
    pass


class OmitFromNodeFullTextIndex(IndexAnnotation):
    pass


def get_string_fields(model: type["BaseNode"]) -> list[str]:
    string_fields = []
    for field in model._meta.fields.property_fields:
        try:
            annotated_type = field.field_annotation
            annotated_string = annotated_type is str
        except ValueError:
            pass

        if field.annotation is str or annotated_string:
            string_fields.append(field_name)

    return string_fields


def create_index_queries() -> list[typing.LiteralString]:
    queries = [
        "CREATE INDEX HeadNodeID IF NOT EXISTS FOR (n:PGIndexableNode) ON (n.head_id)",
        "CREATE INDEX HeadNodeType IF NOT EXISTS FOR (n:PGIndexableNode) ON (n.head_node_type)",
        "CREATE INDEX HeadNodeTypeAndID IF NOT EXISTS FOR (n:PGIndexableNode) ON (n.head_node_type, n.head_id)",
        "CREATE CONSTRAINT NodeIdUnique IF NOT EXISTS FOR (n:PGIndexableNode) REQUIRE n.id IS UNIQUE",
        "CREATE CONSTRAINT BaseNodeIdUnique IF NOT EXISTS FOR (n:BaseNode) REQUIRE n.id IS UNIQUE",
        "CREATE CONSTRAINT URLNodeURLUnique IF NOT EXISTS FOR (n:PGUri) REQUIRE n.uri IS UNIQUE",
        "CREATE CONSTRAINT PGUserNameIndex IF NOT EXISTS FOR (n:PGUser) REQUIRE n.username IS UNIQUE",
        """CREATE FULLTEXT INDEX PgIndexableNodeFullTextIndex
                IF NOT EXISTS FOR (n:PGIndexableNode) ON EACH [n.label]
                OPTIONS {
                    indexConfig: {
                        `fulltext.analyzer`: 'standard-no-stop-words',
                        `fulltext.eventually_consistent`: true
                    }
        }""",
    ]

    for model_name, model in ModelManager.base_models.items():
        queries.append(f"""CREATE FULLTEXT INDEX {model_name}FullTextIndex
                IF NOT EXISTS FOR (n:{model_name}) ON EACH [n.label]
                OPTIONS {{
                    indexConfig: {{
                        `fulltext.analyzer`: 'standard-no-stop-words',
                        `fulltext.eventually_consistent`: true
                    }}
        }}""")

    return typing.cast(list[typing.LiteralString], queries)


@database.write_transaction
async def _clear_full_text_indexes(tx: Transaction):
    queries = []
    for model_name, model in ModelManager.base_models.items():
        queries.append(f"DROP INDEX {model_name}FullTextIndex IF EXISTS\n")

    for query in queries:
        await tx.run(query, {})


@database.write_transaction
async def _install_index_and_constraints_from_text(tx: Transaction):
    queries = create_index_queries()
    for query in queries:
        try:
            await tx.run(query, {})
        except Exception as e:
            print(e)


def install_indexes_and_constraints():
    queries = create_index_queries()

    async def _run(queries):
        @database.write_transaction
        async def _run_query(query, tx):
            try:
                await tx.run(query, {})
            except Exception as e:
                print(e)

        await asyncio.gather(*[_run_query(query) for query in queries])

    asyncio.run(_run(queries))

import asyncio
import time
import typing
from contextlib import contextmanager

from pydantic import AnyHttpUrl
from ulid import ULID

from pangloss.exceptions import PanglossNotFoundError
from pangloss.neo4j.create import build_create_query_object
from pangloss.neo4j.database import Transaction, database
from pangloss.neo4j.list import build_get_list_query
from pangloss.neo4j.read import build_edit_view_query, build_view_read_query
from pangloss.neo4j.update import build_update_query
from pangloss.neo4j.utils import SearchResultObject

if typing.TYPE_CHECKING:
    from pangloss.model_config.models_base import (
        CreateBase,
        EditHeadSetBase,
        EditHeadViewBase,
        HeadViewBase,
        ReferenceViewBase,
        RootNode,
    )
    from pangloss.models import BaseNode


@contextmanager
def time_query(label: str = "Query time"):
    start_time = time.perf_counter()
    yield
    elapsed_time = time.perf_counter() - start_time
    print(f"{label}:", elapsed_time)
    return elapsed_time


class DatabaseQueryMixin:
    @typing.overload
    @staticmethod
    async def _update_method(
        item: "EditHeadSetBase",
        current_username: str = "DefaultUser",
        use_deferred_query: bool = False,
    ) -> None: ...

    @typing.overload
    @staticmethod
    async def _update_method(
        item: "EditHeadViewBase",
        current_username: str = "DefaultUser",
        use_deferred_query: bool = False,
    ) -> None: ...

    @typing.overload
    @staticmethod
    async def _update_method(
        item: "EditHeadSetBase",
        current_username: str = "DefaultUser",
        use_deferred_query: typing.Literal[True] = True,
    ) -> typing.Awaitable[None]: ...

    @database.write_transaction
    async def _update_method(
        self,
        tx: Transaction,
        current_username: str = "DefaultUser",
        use_deferred_query: bool = False,
    ) -> None | typing.Callable[[None], typing.Awaitable[None]]:
        self = typing.cast("EditHeadSetBase", self)

        with time_query(f"Building update query time for {self.type}"):
            query_object = await build_update_query(
                instance=self,
                semantic_spaces=[],
                current_username=current_username,
            )
            # build_query_update returns None if diff of with previous value
            # results in no changes
            if query_object is None:
                return None

            query = query_object.to_query_string()

        with open("update_query_dump.cypher", "w") as f:
            f.write(f"{query}\n\n//{str(query_object.params)}")

        with time_query(f"Update query time for {self.type}"):
            result = await tx.run(
                query, typing.cast(dict[str, typing.Any], query_object.params)
            )

            record = await result.value()
            record = record[0]

        if use_deferred_query:
            deferred_query = typing.cast(
                typing.LiteralString, query_object.deferred_query.to_query_string()
            )

            @database.write_transaction
            async def deferred_update_method(tx: Transaction):
                try:
                    await tx.run(
                        typing.cast(typing.LiteralString, deferred_query),
                        typing.cast(
                            dict[str, typing.Any],
                            query_object.deferred_query.params,
                        ),
                    )
                except asyncio.CancelledError:
                    await tx._close()

            return typing.cast(
                typing.Callable[[None], typing.Awaitable[None]], deferred_update_method
            )

        if query_object.deferred_query.params:
            deferred_query = typing.cast(
                typing.LiteralString, query_object.deferred_query.to_query_string()
            )
            with open("deferred_update_query_dump.cypher", "w") as f:
                f.write(
                    f"{deferred_query}\n\n//{str(query_object.deferred_query.params)}"
                )

            with time_query(f"Deferred update query time for {self.type}"):
                deferred_query = await tx.run(
                    deferred_query,
                    typing.cast(
                        dict[str, typing.Any], query_object.deferred_query.params
                    ),
                )

    @typing.overload
    @staticmethod
    async def _create_method(
        item,
        current_username: str | None = None,
        use_deferred_query: bool = False,
        return_edit_view: typing.Literal[False] = False,
    ) -> "ReferenceViewBase": ...

    @typing.overload
    @staticmethod
    async def _create_method(
        item,
        current_username: str | None = None,
        use_deferred_query: typing.Literal[False] = False,
        return_edit_view: typing.Literal[True] = True,
    ) -> "EditHeadSetBase": ...

    @typing.overload
    @staticmethod
    async def _create_method(
        item,
        current_username: str,
        use_deferred_query: bool = True,
        return_edit_view: bool = False,
    ) -> tuple[
        "ReferenceViewBase", typing.Callable[[None], typing.Awaitable[None]]
    ]: ...

    @database.write_transaction
    async def _create_method(
        self,
        tx: Transaction,
        current_username: str | None = None,
        use_deferred_query: bool = False,
        return_edit_view: bool = True,
    ) -> "ReferenceViewBase | EditHeadSetBase | tuple[ReferenceViewBase, typing.Callable]":
        print("============= CREATE")

        self = typing.cast("CreateBase", self)

        with time_query(f"Building create query time for {self.type}"):
            query_object = build_create_query_object(
                instance=self, current_username=current_username
            )
        query = typing.cast(typing.LiteralString, query_object.to_query_string())

        with open("create_query_dump.cypher", "w") as f:
            f.write(f"{query}\n\n//{str(query_object.params)}")

        with time_query(f"Create query time for {self.type}"):
            result = await tx.run(
                query, typing.cast(dict[str, typing.Any], query_object.params)
            )
            record = await result.value()

        response = typing.cast("RootNode", self.__pg_base_class__).ReferenceView(
            **record[0]
        )

        if use_deferred_query:
            deferred_query = typing.cast(
                typing.LiteralString, query_object.deferred_query.to_query_string()
            )

            @database.write_transaction
            async def deferred_create_method(tx: Transaction):
                try:
                    await tx.run(
                        typing.cast(typing.LiteralString, deferred_query),
                        typing.cast(
                            dict[str, typing.Any],
                            query_object.deferred_query.params,
                        ),
                    )
                except asyncio.CancelledError:
                    await tx._close()

            return (response, deferred_create_method)

        if query_object.deferred_query.params:
            deferred_query = typing.cast(
                typing.LiteralString, query_object.deferred_query.to_query_string()
            )
            with open("deferred_create_query_dump.cypher", "w") as f:
                f.write(
                    f"{deferred_query}\n\n//{str(query_object.deferred_query.params)}"
                )

            with time_query(f"Deferred create query time for {self.type}"):
                deferred_query = await tx.run(
                    deferred_query,
                    typing.cast(
                        dict[str, typing.Any], query_object.deferred_query.params
                    ),
                )

        if not return_edit_view:
            return response

        with time_query(f"Building read query time for {self.type}"):
            query, query_params = build_edit_view_query(
                model=typing.cast("type[RootNode]", self.__pg_base_class__),
                id=str(response.id),
            )

        with open("get_edit_query_dump.cypher", "w") as f:
            f.write(f"{query}\n\n//{str(query_params)}")

        with time_query(f"Read query time for {self.type}"):
            result = await tx.run(
                query, typing.cast(dict[str, typing.Any], query_params)
            )
            record = await result.value()
            if record:
                result = typing.cast("BaseNode", self.__pg_base_class__).EditHeadSet(
                    **record[0]
                )
            else:
                raise PanglossNotFoundError(f"Object <{self.type} id='{id}'> not found")

        return result

    @classmethod
    @database.read_transaction
    async def get_view(cls, tx: Transaction, id: ULID | AnyHttpUrl) -> "HeadViewBase":
        print("============= GET VIEW")

        cls = typing.cast(type["RootNode"], cls)
        with time_query(f"Building read query time for {cls.type}"):
            query, query_params = build_view_read_query(model=cls, id=str(id))

        with open("get_view_query_dump.cypher", "w") as f:
            f.write(f"{query}\n\n//{str(query_params)}")

        with time_query(f"View read query time for {cls.type}"):
            result = await tx.run(
                query, typing.cast(dict[str, typing.Any], query_params)
            )
            record = await result.value()
            if record:
                result = cls.HeadView(**record[0])

            else:
                raise PanglossNotFoundError(f"Object <{cls.type} id='{id}'> not found")

        return result

    @classmethod
    @database.read_transaction
    async def get_edit_view(cls, tx: Transaction, id: ULID | str) -> "EditHeadViewBase":
        print("============= GET EDIT VIEW")
        cls = typing.cast(type["RootNode"], cls)
        with time_query(f"Building read query time for {cls.type}"):
            query, query_params = build_edit_view_query(model=cls, id=str(id))

        with open("get_edit_query_dump.cypher", "w") as f:
            f.write(f"{query}\n\n//{str(query_params)}")

        with time_query(f"EditView read query time for {cls.type}"):
            result = await tx.run(
                query, typing.cast(dict[str, typing.Any], query_params)
            )
            record = await result.value()
            if record:
                result = cls.EditHeadView(**record[0])
            else:
                raise PanglossNotFoundError(f"Object <{cls.type} id='{id}'> not found")

        return result

    @classmethod
    @database.read_transaction
    async def get_list(
        cls,
        tx: Transaction,
        q: typing.Optional[str] = None,
        page: int = 1,
        page_size: int = 10,
        deep_search: bool = False,
    ) -> SearchResultObject["ReferenceViewBase"]:
        print("=============", deep_search)

        cls = typing.cast(type["RootNode"], cls)
        with time_query(f"Building search query time for {cls.type}"):
            from pangloss.model_config.model_setup_functions.utils import (
                get_concrete_model_types,
            )

            list_base_types = get_concrete_model_types(
                cls, include_self=True, include_subclasses=True
            )
            list_reference_types = [c.ReferenceView for c in list_base_types]
            search_result_object_type = typing.Union[*list_reference_types]

            query, query_params = build_get_list_query(
                model=cls, q=q, page=page, page_size=page_size, deep_search=deep_search
            )
        with open("get_list_query_dump.cypher", "w") as f:
            f.write(f"{query}\n\n//{str(query_params)}")

        with time_query(f"List read query time for {cls.type} with query '{q}'"):
            result = await tx.run(
                query, typing.cast(dict[str, typing.Any], query_params)
            )
            records = await result.value()

            if not records:
                return SearchResultObject[search_result_object_type](
                    results=[],
                    count=0,
                    page=1,
                    total_pages=1,
                    page_size=10,
                    next_page=None,
                    previous_page=None,
                    next_url=None,
                    previous_url=None,
                )
            return_object = SearchResultObject[search_result_object_type](**records[0])

            return return_object

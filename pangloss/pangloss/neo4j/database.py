from __future__ import annotations

import functools
import logging
import typing
import uuid
from typing import (
    Awaitable,
    Callable,
    Concatenate,
)

import neo4j
import neo4j.exceptions
from rich import print

if typing.TYPE_CHECKING:
    from pangloss.settings import BaseSettings


# Define a transaction type, for short
Transaction = neo4j.AsyncManagedTransaction

# Make sure neo4j doesn't spout annoying warnings all over the place
logging.getLogger("neo4j").setLevel(logging.ERROR)

uri: str
auth: tuple[str, str]


class Database:
    settings: "BaseSettings"
    driver: neo4j.AsyncDriver

    _instances: dict[int, "Database"] = {}
    _initialised: bool = False

    def __init__(
        self, settings: "BaseSettings", instance_identifier: int | None = None
    ):
        if settings is None:
            return

        self.settings = settings
        self._initialise_driver()

        # Because @read_transaction and @write_transaction are decorators,
        # "self" is bound with non-functioning instance before initialisation of the db;
        # So we store each instance of this class, and use this
        # to look up the instance
        self.__class__._instances[instance_identifier or id(self)] = self

    def _initialise_driver(self):
        self.driver = neo4j.AsyncGraphDatabase.driver(
            self.settings.DB_URL,
            auth=(self.settings.DB_USER, self.settings.DB_PASSWORD),
            keep_alive=True,
        )

    def _check_driver(self):
        if self.driver._closed:
            self._initialise_driver()

    @typing.overload
    def read_transaction[ModelType, ReturnType, **Params](
        self,
        func: Callable[
            Concatenate[ModelType, neo4j.AsyncManagedTransaction, Params],
            Awaitable[ReturnType],
        ],
    ) -> Callable[Concatenate[ModelType, Params], Awaitable[ReturnType]]: ...

    @typing.overload
    def read_transaction[ReturnType, **Params](
        self,
        func: Callable[
            Concatenate[neo4j.AsyncManagedTransaction, Params],
            Awaitable[ReturnType],
        ],
    ) -> Callable[Concatenate[Params], Awaitable[ReturnType]]: ...

    def read_transaction[ModelType, ReturnType, **Params](
        self,
        func: Callable[
            Concatenate[ModelType, neo4j.AsyncManagedTransaction, Params],
            Awaitable[ReturnType],
        ]
        | Callable[
            Concatenate[neo4j.AsyncManagedTransaction, Params],
            Awaitable[ReturnType],
        ],
    ) -> (
        Callable[Concatenate[ModelType, Params], Awaitable[ReturnType]]
        | Callable[Concatenate[Params], Awaitable[ReturnType]]
    ):
        """Decorator to run a database read transaction

        Wraps an asynchronous function taking a pangloss.neo4j.database.Transaction
        object as its first argument.

        ```
        @read_transaction
        def get_a_thing(tx: Transaction):
            await tx.run(<QUERY>, <PARAMS>)
        ```
        """

        async def wrapper(
            instance: ModelType, *args: Params.args, **kwargs: Params.kwargs
        ) -> ReturnType:
            this: "Database" = self.__class__._instances[id(self)]
            this._check_driver()
            # async with neo4j.AsyncGraphDatabase.driver(uri, auth=auth) as driver:
            async with this.driver.session(
                database=this.settings.DB_DATABASE_NAME
            ) as session:
                bound_func = functools.partial(func, instance)
                records = await session.execute_read(bound_func, *args, **kwargs)
                return records

        return wrapper

    @typing.overload
    def write_transaction[ModelType, ReturnType, **Params](
        self,
        func: Callable[
            Concatenate[ModelType, neo4j.AsyncManagedTransaction, Params],
            Awaitable[ReturnType],
        ],
    ) -> Callable[Concatenate[ModelType, Params], Awaitable[ReturnType]]: ...

    @typing.overload
    def write_transaction[ReturnType, **Params](
        self,
        func: Callable[
            Concatenate[neo4j.AsyncManagedTransaction, Params],
            Awaitable[ReturnType],
        ],
    ) -> Callable[Concatenate[Params], Awaitable[ReturnType]]: ...

    def write_transaction[ModelType, ReturnType, **Params](
        self,
        func: Callable[
            Concatenate[ModelType, neo4j.AsyncManagedTransaction, Params],
            Awaitable[ReturnType | None],
        ]
        | Callable[
            Concatenate[neo4j.AsyncManagedTransaction, Params],
            Awaitable[ReturnType | None],
        ],
    ) -> (
        Callable[Concatenate[ModelType, Params], Awaitable[ReturnType | None]]
        | Callable[Concatenate[Params], Awaitable[ReturnType | None]]
    ):
        """Decorator to run a database read transaction

        Wraps an asynchronous function taking a pangloss.neo4j.database.Transaction
        object as its first argument.

        ```
        @read_transaction
        def get_a_thing(tx: Transaction):
            await tx.run(<QUERY>, <PARAMS>)
        ```
        """

        async def wrapper(
            instance: ModelType | None = None,
            *args: Params.args,
            **kwargs: Params.kwargs,
        ) -> ReturnType | None:
            this: "Database" = self.__class__._instances[id(self)]
            this._check_driver()

            async with this.driver.session(
                database=this.settings.DB_DATABASE_NAME
            ) as session:
                if instance:
                    bound_func = functools.partial(func, instance)
                else:
                    bound_func = func

                records = None
                try:
                    records = await session.execute_write(bound_func, **kwargs)  # type: ignore
                except neo4j.exceptions.TransactionError:
                    pass

                return records

        return wrapper

    def with_database[ReturnType, **Params](
        self, func: Callable[["Database"], Awaitable[ReturnType]]
    ) -> Callable[Concatenate[Params], Awaitable[ReturnType]]:
        """Decorator to allow access to the database instance inside a function,
        taking a `database` argument as its first argument"""

        async def wrapper(*args, **kwargs) -> ReturnType:
            this: "Database" = self.__class__._instances[id(self)]
            result = await func(this, *args, **kwargs)
            return result

        return wrapper

    @staticmethod
    def initialise_default_database(settings: "BaseSettings") -> "Database":
        global database
        database = Database(settings=settings, instance_identifier=id(database))
        return database

    async def close(self):
        await DatabaseUtils.close_database_connection()


# Fake-initialise a Database object so that the typechecker does
# not complain all the time that it hasn't been initialised ahead of time
database: Database = Database(settings=None)  # type: ignore
"""The Pangloss default neo4j database"""


class DatabaseUtils:
    @database.with_database
    @staticmethod
    async def close_database_connection(db: Database):
        print("[yellow bold]Closing Database connection...[/yellow bold]")
        try:
            await db.driver.close()
        except Exception as e:
            print("[red bold]Error closing database:[/red bold]", e)
        else:
            print("[green bold]Database connection closed[/green bold]")

    @database.read_transaction
    @staticmethod
    async def get_item(
        tx: Transaction,
        uid: uuid.UUID,
    ) -> neo4j.Record | None:
        result = await tx.run("MATCH (n {uid: $uid}) RETURN n", uid=str(uid))
        item = await result.single()
        summary = await result.consume()

        return item

    @database.write_transaction
    @staticmethod
    async def dangerously_clear_database(tx: Transaction) -> None:
        result = await tx.run("""MATCH (n) DETACH DELETE n
                                MERGE (:PGInternal:PGCore:PGUser {username: "DefaultUser"})

                                """)
        await result.consume()

    @database.write_transaction
    @staticmethod
    async def write_indexes(tx: Transaction) -> None:
        result = await tx.run(
            """CREATE CONSTRAINT BaseNodeUidUnique IF NOT EXISTS FOR (n:BaseNode) REQUIRE n.uuid IS UNIQUE"""
        )
        await result.consume()
        result = await tx.run(
            """CREATE CONSTRAINT PGUserNameIndex IF NOT EXISTS FOR (n:PGUser) REQUIRE n.username IS UNIQUE"""
        )
        await result.consume()

    @database.write_transaction
    @staticmethod
    async def create_default_user(tx: Transaction) -> None:
        result = await tx.run(
            """MERGE (:PGInternal:PGCore:PGUser {username: "DefaultUser"})"""
        )
        await result.consume()

    @database.write_transaction
    @staticmethod
    async def _cypher_write(tx: Transaction, query: str, params: dict = {}):
        result = await tx.run(
            query,  # type: ignore
            **params,
        )
        records = await result.values()
        return records

    @database.read_transaction
    @staticmethod
    async def _cypher_read(query: str, tx: Transaction, params: dict = {}):
        print(query, params)
        result = await tx.run(
            query,  # type: ignore
            **params,
        )
        records = await result.values()
        return records

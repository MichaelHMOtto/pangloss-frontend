import collections
import typing
import uuid

import pydantic
from ulid import ULID

from pangloss.model_config.model_base_mixins import _StandardModel

if typing.TYPE_CHECKING:
    from pangloss.model_config.models_base import (
        EditSetBase,
        EmbeddedCreateBase,
        EmbeddedSetBase,
        ReifiedRelation,
        RootNode,
    )


class Identifier(str):
    def __new__(cls):
        return super().__new__(cls, "x" + uuid.uuid4().hex[:6].lower())


class QuerySubstring(str):
    def __new__(cls, query_string: str):
        return super().__new__(cls, query_string)


class QueryParams(dict[Identifier, dict[str, typing.Any] | str]):
    def add(self, item: dict[str, typing.Any] | str) -> Identifier:
        identifier = Identifier()
        self.__setitem__(identifier, item)
        return identifier


class CreateQuery:
    match_query_strings: list[str]
    create_query_strings: list[str]
    set_query_strings: list[str]
    params: QueryParams
    return_identifier: str
    return_uuid: ULID
    head_type: str | None

    def __init__(self):
        self.match_query_strings = []
        self.create_query_strings = []
        self.set_query_strings = []
        self.params = QueryParams()
        self.id = ULID()
        self.head_type = None

    def to_query_string(self):
        if not self.return_identifier:
            raise Exception("CreateQuery.to_query_string called on non-top-level node")
        return f"""{"\n".join(self.match_query_strings)}
    {"\n".join(self.create_query_strings)}
    {"\n".join(self.set_query_strings)}
    RETURN {self.return_identifier}"""


class UpdateQuery:
    match_query_string_top: collections.deque[str]
    match_query_strings: collections.deque[str]
    create_query_strings: list[str]
    merge_query_strings: list[str]
    set_query_strings: list[str]
    call_query_strings: collections.deque[str]
    delete_query_strings: list[str]

    query_params: dict[str, typing.Any]
    return_identifier: str
    return_uuid: uuid.UUID
    head_type: str | None

    def __init__(self):
        self.match_query_strings_top = collections.deque()
        self.match_query_strings = collections.deque()
        self.create_query_strings = []
        self.set_query_strings = []
        self.merge_query_strings = []
        self.call_query_strings = collections.deque()
        self.delete_query_strings = []
        self.query_params = {}
        self.uuid = uuid.uuid4()
        self.head_type = None

    def to_query_string(self):
        if not self.return_identifier:
            raise Exception("UpdateQuery.to_query_string called on non-top-level node")
        return f"""
    {"\n".join(list(self.match_query_strings_top))}
    {"\n".join(self.merge_query_strings)}
    WITH *
    {"\n".join(list(self.match_query_strings))}
    {"\n".join(self.create_query_strings)}
     
    {"\n".join(self.set_query_strings)}
    {"\n".join(self.delete_query_strings)}
    {"WITH *" if self.call_query_strings else ""}
    {"\n".join(self.call_query_strings)}
    RETURN true"""


def join_labels(labels: set[str], extra_labels: typing.Iterable[str]):
    all_labels = [*labels, *extra_labels]
    return f"{':'.join(all_labels)}"


def convert_type_for_writing(value):
    match value:
        case uuid.UUID():
            return str(value)
        case pydantic.AnyUrl():
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
    instance: "RootNode | ReifiedRelation | EditSetBase | EmbeddedCreateBase | EmbeddedSetBase",
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


class SearchResultObject[T](pydantic.BaseModel, _StandardModel):
    count: int
    page: int
    total_pages: int
    page_size: int
    results: list[T]
    next_page: int | None = None
    previous_page: int | None = None
    next_url: pydantic.AnyHttpUrl | None = None
    previous_url: pydantic.AnyHttpUrl | None = None

    def __len__(self):
        return self.count

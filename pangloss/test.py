from pydantic import BaseModel


class Wrapper[T](BaseModel[T]):
    contained: list[T]


class Person:
    pass


Wrapper[Person]

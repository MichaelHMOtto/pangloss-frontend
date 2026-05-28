import typing
from collections import ChainMap

if typing.TYPE_CHECKING:
    from pangloss.model_config.models_base import (
        EdgeModel,
        MultiKeyField,
        ReifiedBase,
        RootNode,
        SemanticSpace,
    )


def build_pg_annotations(
    cls: type["RootNode"]
    | type["ReifiedBase"]
    | type["EdgeModel"]
    | type["MultiKeyField"]
    | type["SemanticSpace"],
) -> None:
    """Set the __pg_annotations__ of the class to a ChainMap
    gathering the class's own annotations and all parent class annotations
    up to (but not including) BaseNode.

    Better to do this once on initialisation of models than to do it
    dynamically and try to fake a @classmethod+@property.
    """

    from pangloss.model_config.models_base import (
        EdgeModel,
        HeritableTrait,
        MultiKeyField,
        NonHeritableTrait,
        ReifiedBase,
        RootNode,
        SemanticSpaceBase,
        Trait,
    )
    from pangloss.models import BaseNode, DatabaseQueryMixin

    annotation_dicts = []

    for parent in cls.mro():
        if (
            parent is object
            or parent is BaseNode
            or parent is ReifiedBase
            or parent is EdgeModel
            or parent is MultiKeyField
            or parent is SemanticSpaceBase
            or parent is HeritableTrait
            or parent is NonHeritableTrait
            or parent is Trait
            or parent is RootNode
            or parent is DatabaseQueryMixin
            or parent.__name__.startswith("_")
        ):
            continue

        annotation_dicts.append(parent.__annotations__)

    cls.__pg_annotations__ = ChainMap(*annotation_dicts)

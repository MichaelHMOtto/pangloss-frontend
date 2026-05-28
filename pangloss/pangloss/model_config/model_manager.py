import typing

from pangloss.exceptions import PanglossInitialisationError

if typing.TYPE_CHECKING:
    from pangloss.model_config.model_setup_functions.build_pg_model_definition import (
        BaseModelBaseClassProxy,
    )
    from pangloss.model_config.models_base import (
        EdgeModel,
        MultiKeyField,
        ReifiedRelation,
        SemanticSpace,
        Trait,
    )
    from pangloss.models import BaseNode


type AllModelTypes = (
    type["BaseNode"]
    | type["ReifiedRelation"]
    | type["EdgeModel"]
    | type["MultiKeyField"]
    | type["Trait"]
    | type["SemanticSpace"]
)


class ModelManager:
    _initialised = False
    base_models: dict[str, type["BaseNode"]] = {}
    reified_relation_models: dict[str, type["ReifiedRelation"]] = {}
    edge_models: dict[str, type["EdgeModel"]] = {}
    multikeyfields_models: dict[str, type["MultiKeyField"]] = {}
    trait_models: dict[str, type["Trait"]] = {}
    semantic_space_models: dict[str, type["SemanticSpace"]] = {}

    def __init__(self):
        raise PanglossInitialisationError("ModelManager class cannot be initialised")

    @classmethod
    def all(
        cls,
    ) -> dict[
        str,
        type["BaseNode"]
        | type["ReifiedRelation"]
        | type["EdgeModel"]
        | type["MultiKeyField"]
        | type["Trait"]
        | type["SemanticSpace"],
    ]:
        return {
            **cls.base_models,
            **cls.reified_relation_models,
            **cls.edge_models,
            **cls.multikeyfields_models,
            **cls.trait_models,
            **cls.semantic_space_models,
        }

    @classmethod
    def _reset(cls):
        cls.base_models = {}
        cls.reified_relation_models = {}
        cls.edge_models = {}
        cls.multikeyfields_models = {}
        cls.trait_models = {}
        cls.semantic_space_models = {}
        cls._initialised = False

    @classmethod
    def register_base_model(cls, base_model: type["BaseNode"]):
        if base_model.__name__ == "BaseNode":
            return

        cls.base_models[base_model.__name__] = base_model

    @classmethod
    def register_trait_model(cls, trait_model: type["Trait"]):
        if trait_model.__name__ in {"Trait", "HeritableTrait", "NonHeritableTrait"}:
            return
        cls.trait_models[trait_model.__name__] = trait_model

    @classmethod
    def register_semantic_space_model(cls, semantic_space_model: type["SemanticSpace"]):
        if semantic_space_model.__name__ == "SemanticSpace":
            return
        cls.semantic_space_models[semantic_space_model.__name__] = semantic_space_model

    @classmethod
    def register_reified_relation_model(
        cls, reified_relation_model: type["ReifiedRelation"]
    ):
        # Supposedly, this checks whether the model is a "root" generic class
        # e.g. Intermediate[T]
        # or the "instantiation" of a generic class, e.g. Intermediate[Cat]
        # If the former, add it to model manager
        if reified_relation_model.__name__ == "ReifiedRelationNode":
            return

        if reified_relation_model.__pydantic_generic_metadata__["origin"]:
            cls.reified_relation_models[reified_relation_model.__name__] = (
                reified_relation_model
            )

    @classmethod
    def register_multikeyfield_model(cls, multikeyfield_model: type["MultiKeyField"]):
        if multikeyfield_model.__pydantic_generic_metadata__["origin"]:
            cls.multikeyfields_models[multikeyfield_model.__name__] = (
                multikeyfield_model
            )

    @classmethod
    def register_edge_model(cls, edge_model: type["EdgeModel"]):
        cls.edge_models[edge_model.__name__] = edge_model

    @classmethod
    def initialise_models(cls, _defined_in_test: bool = False):
        if cls._initialised:
            return

        from pangloss.model_config.model_setup_functions.build_create_model import (
            build_create_model,
        )
        from pangloss.model_config.model_setup_functions.build_edit_head_view_model import (
            build_edit_head_view_model,
        )
        from pangloss.model_config.model_setup_functions.build_edit_set_model import (
            build_edit_head_set_model,
        )
        from pangloss.model_config.model_setup_functions.build_head_view_model import (
            build_head_view_model,
        )
        from pangloss.model_config.model_setup_functions.build_model_meta import (
            initialise_model_meta_inheritance,
        )
        from pangloss.model_config.model_setup_functions.build_pg_annotations import (
            build_pg_annotations,
        )
        from pangloss.model_config.model_setup_functions.build_pg_model_definition import (
            build_abstract_specialist_type_model_definitions,
            build_pg_bound_model_definition_for_instatiated_semantic_space,
            build_pg_model_definitions,
        )
        from pangloss.model_config.model_setup_functions.build_reference_model import (
            build_reference_create,
            build_reference_set,
            build_reference_view,
        )
        from pangloss.model_config.model_setup_functions.build_reverse_relation_definitions import (
            build_reverse_relations_definitions_to,
        )
        from pangloss.model_config.model_setup_functions.build_semantic_space_meta import (
            initialise_semantic_space_meta_inheritance,
        )
        from pangloss.model_config.model_setup_functions.initialise_subclassed_relations import (
            initialise_subclassed_relations,
        )
        from pangloss.model_config.model_setup_functions.set_type_on_base_model import (
            set_type_to_literal_on_base_model,
        )
        from pangloss.model_config.models_base import SemanticSpace, _BaseClassProxy

        for specialising_abstract_class in _BaseClassProxy.__subclasses__():
            specialising_abstract_class = typing.cast(
                type["BaseModelBaseClassProxy"], specialising_abstract_class
            )
            specialising_abstract_class.__pg_annotations__ = (
                specialising_abstract_class.__annotations__
            )
            build_abstract_specialist_type_model_definitions(
                specialising_abstract_class
            )

        for model_name, model in cls.multikeyfields_models.items():
            build_pg_annotations(model)
            build_pg_model_definitions(model)

        for model_name, model in cls.base_models.items():
            set_type_to_literal_on_base_model(model)
            build_pg_annotations(model)

        for model_name, model in cls.semantic_space_models.items():
            set_type_to_literal_on_base_model(model)

        for model_name, model in cls.reified_relation_models.items():
            set_type_to_literal_on_base_model(model)

        for model_name, model in cls.base_models.items():
            build_pg_model_definitions(model)

        for model_name, model in cls.base_models.items():
            initialise_model_meta_inheritance(model)

        for model_name, model in cls.semantic_space_models.items():
            build_pg_annotations(model)

        for model_name, model in cls.semantic_space_models.items():
            build_pg_model_definitions(model)

        for model_name, model in cls.semantic_space_models.items():
            # If this is a bound semantic space, i.e. Negative[Statement], not
            # Negative, build the bound field definition for the model as well

            if (
                model.__pydantic_generic_metadata__["origin"]
                and model.__pydantic_generic_metadata__["origin"] is not SemanticSpace
                and type(model.__pydantic_generic_metadata__["args"][0])
                is not typing.TypeVar
            ):
                build_pg_bound_model_definition_for_instatiated_semantic_space(model)

            initialise_semantic_space_meta_inheritance(model)

        for model_name, model in cls.base_models.items():
            initialise_subclassed_relations(model)

        for model_name, model in cls.reified_relation_models.items():
            build_pg_annotations(model)

        for model_name, model in cls.reified_relation_models.items():
            build_pg_model_definitions(model)

        for model_name, model in cls.edge_models.items():
            build_pg_annotations(model)

        for model_name, model in cls.edge_models.items():
            build_pg_model_definitions(model)

        for model_name, model in cls.base_models.items():
            build_reference_set(model)
            build_reference_view(model)
            build_reference_create(model)

        # for model_name, model in cls.semantic_space_models.items():
        #    build_create_model(model)

        for model_name, model in cls.base_models.items():
            build_create_model(model)

        for model_name, model in cls.base_models.items():
            build_edit_head_view_model(model)

        for model_name, model in cls.base_models.items():
            build_edit_head_set_model(model)

        for model_name, model in cls.base_models.items():
            build_reverse_relations_definitions_to(model)

        for model_name, model in cls.base_models.items():
            build_head_view_model(model)

        cls._initialised = True

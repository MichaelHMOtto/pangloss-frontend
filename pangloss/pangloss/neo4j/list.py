import re
import typing

if typing.TYPE_CHECKING:
    from pangloss.model_config.models_base import RootNode


SPLIT_TERMS_REGEX = re.compile(r"[ \-\_]")


def get_index_offsets(page: int, page_size: int) -> tuple[int, int]:
    """
    Returns the start and end index for pagination.

    Args:
        page (int): The page number (1-based).
        page_size (int): The number of items per page.

    Returns:
        tuple[int, int]: A tuple (start_index, end_index), both 0-based.
    """
    if page < 1 or page_size < 1:
        raise ValueError("Page and page_size must both be >= 1")

    page = page - 1

    start_index = (page) * page_size
    end_index = start_index + (page_size)
    return start_index, end_index


def build_deep_search_query(
    search_terms: list[str], node_type: str, model: "type[RootNode]"
):
    query = ""

    for i, term in enumerate(search_terms):
        query += f"""CALL () {{ CALL db.index.fulltext.queryNodes("PgIndexableNodeFullTextIndex", $q[{i}]) YIELD node, score RETURN collect(node) as n{i}, count(node) as c{i} }}\n"""

    query += f"""WITH apoc.coll.sortMaps([{", ".join(f"{{t: n{i}, c: c{i}}}" for i, _ in enumerate(search_terms))}], "^c") as FT"""

    query += f"""
WITH FT[0].t as fullTextResultNodes, FT
CALL (fullTextResultNodes) {{
    MATCH p = (t:{node_type})(()-[]->()){{0,}}(b:PGIndexableNode)
        WHERE (b in fullTextResultNodes OR t in fullTextResultNodes)
    RETURN DISTINCT t
    
    UNION
    
    MATCH p = (t:{node_type})(()<-[]-()){{0,}}(b:PGIndexableNode)
        WHERE (b in fullTextResultNodes OR t in fullTextResultNodes)
    RETURN DISTINCT t
    
    UNION
    
    MATCH (t:{node_type})(()<-[]-()){{0,}}(x:PGIndexableNode)
    MATCH (x)(()-[]->()){{0,}}(b:PGIndexableNode)
        WHERE (b in fullTextResultNodes OR t in fullTextResultNodes)
    RETURN DISTINCT t
}}
"""

    for i, term in enumerate(search_terms[1:], start=1):
        query += f"""WITH FT[1].t as fullTextResultNodes, FT, collect(t) as currentResults
CALL (fullTextResultNodes, currentResults) {{
    MATCH (t:{node_type})(()-[]->()){{0,}}(b:PGIndexableNode)
        WHERE t in currentResults AND (b in fullTextResultNodes OR t in fullTextResultNodes)
    RETURN DISTINCT t
    
    UNION
    
    MATCH (t:{node_type})(()<-[]-()){{0,}}(b:PGIndexableNode)
        WHERE t in currentResults AND (b in fullTextResultNodes OR t in fullTextResultNodes)
    RETURN DISTINCT t
    
    UNION
    
    MATCH (t:{node_type})(()<-[]-()){{0,}}(x:PGIndexableNode)
    MATCH (x)(()-[]->()){{0,}}(b:PGIndexableNode)
        WHERE t in currentResults AND (b in fullTextResultNodes OR t in fullTextResultNodes)
    RETURN DISTINCT t
}}"""

    query += "WITH apoc.agg.slice(t, $skip, $skipEnd) as results, count(t) as count\n"
    query += """RETURN {count: count, page: $page, page_size: $page_size, total_pages: toInteger(round((count*1.0)/$page_size, 0, "UP")),  results: results}"""
    return query


def build_get_list_query(
    model: type["RootNode"],
    q: typing.Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    deep_search: bool = False,
) -> tuple[typing.LiteralString, dict[str, typing.Any]]:
    if q and deep_search:
        print("RUNNING DEEP SEARCH")
        """Returns a list of objects of type/subclasses of model.ReferenceView
        
        Without search param q:
             matches all items
        
        With search param q:
            split search param on space, wrap each term with regex wildcards, 
            and match against model.label using full-text index
          
        With search param q and deep_search:
            - split and wrap search params individually
            - starting with the param that produces the fewest hits, match:
                - the matched node if of the correct type
                - another node pointed to by head_id or id of matched node, if this other node is of
                    correct type
                - another node pointed to by the head_id or id of a node pointed to by the matched
                    node
                - another node pointed to by the head_id or id of a node pointing to the matched
                    node
            - take these results and pass onto the above matching strategy, *with* the condition
              that it has already been matched
            - repeat for all search terms
        """

        terms = [f"/.*{re.escape(term)}.*/" for term in SPLIT_TERMS_REGEX.split(q)]

        skip, skipEnd = get_index_offsets(page, page_size)

        query = build_deep_search_query(terms, model.__name__, model)
        params = {
            "skip": skip,
            "skipEnd": skipEnd,
            "page_size": page_size,
            "page": page,
            "q": terms,
        }

    elif q:
        print("RUNNING SHALLOW SEARCH")
        terms = SPLIT_TERMS_REGEX.split(q)

        search_string = " AND ".join(f"/.*{re.escape(term)}.*/" for term in terms)

        query = f"""            
                CALL db.index.fulltext.queryNodes("{model.__name__}FullTextIndex", $q) YIELD node, score
               
MATCH (node WHERE NOT node.is_deleted) ORDER BY score
WITH apoc.agg.slice(node, $skip, $skip_end) as results, count(node) as node_count
RETURN {{count: node_count, page_size: $page_size, page: 1, total_pages: toInteger(round((node_count*1.0)/$page_size, 0, "UP")), results: results}}
            """

        skip, skipEnd = get_index_offsets(page, page_size)
        params = {
            "skip": skip,
            "skip_end": skipEnd,
            "page_size": page_size,
            "page": page,
            "q": search_string,
        }

    else:
        print("building no search term")
        query = f"""CALL () {{
                        OPTIONAL MATCH (node:{model.__name__} WHERE NOT node.is_deleted)
                        WITH collect(node) AS ns, COUNT (DISTINCT node) as total
                        UNWIND ns AS m
                        RETURN m{{.*, uris: []}} as matches, total as total_items ORDER BY m.id DESC SKIP $skip LIMIT $pageSize
                    }}
                    WITH COLLECT(matches) AS matches_list, total_items
                    RETURN {{results: matches_list, count: total_items, page: $page, page_size: $pageSize, totalPages: toInteger(round((total_items*1.0)/$pageSize, 0, "UP"))}}
                """

        skip, skipEnd = get_index_offsets(page, page_size)
        params = {
            "skip": skip,
            "pageSize": page_size,
            "page": page,
        }
    return typing.cast(typing.LiteralString, query), params

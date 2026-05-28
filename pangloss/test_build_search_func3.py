import re

search_string = "maximilian durch tochter"


def build_deep_search_query(search_string):
    SPLIT_TERMS_REGEX = re.compile("[ -_/]")

    page_size = 50
    page = 1

    terms = SPLIT_TERMS_REGEX.split(search_string)

    terms = [f"/.*{re.escape(term)}.*/" for term in terms]

    nodeType = "ZoteroEntry"

    query = ""

    for i, term in enumerate(terms):
        query += f"""CALL () {{ CALL db.index.fulltext.queryNodes("PgIndexableNodeFullTextIndex", "{term}") YIELD node, score RETURN collect(node) as n{i}, count(node) as c{i} }}\n"""

    query += f"""WITH apoc.coll.sortMaps([{", ".join(f"{{t: n{i}, c: c{i}}}" for i, _ in enumerate(terms))}], "^c") as FT"""

    query += f"""
WITH FT[0].t as fullTextResultNodes, FT
CALL (fullTextResultNodes) {{
    MATCH p = (t:{nodeType})(()-[]->()){{0,}}(b:PGIndexableNode)
        WHERE (b in fullTextResultNodes OR t in fullTextResultNodes)
    RETURN DISTINCT t
    
    UNION
    
    MATCH p = (t:{nodeType})(()<-[]-()){{0,}}(b:PGIndexableNode)
        WHERE (b in fullTextResultNodes OR t in fullTextResultNodes)
    RETURN DISTINCT t
    
    UNION
    
    MATCH (t:{nodeType})(()<-[]-()){{0,}}(x:PGIndexableNode)
    MATCH (x)(()-[]->()){{0,}}(b:PGIndexableNode)
        WHERE (b in fullTextResultNodes OR t in fullTextResultNodes)
    RETURN DISTINCT t
}}
"""

    for i, term in enumerate(terms[1:], start=1):
        query += f"""WITH FT[1].t as fullTextResultNodes, FT, collect(t) as currentResults
CALL (fullTextResultNodes, currentResults) {{
    MATCH (t:{nodeType})(()-[]->()){{0,}}(b:PGIndexableNode)
        WHERE t in currentResults AND (b in fullTextResultNodes OR t in fullTextResultNodes)
    RETURN DISTINCT t
    
    UNION
    
    MATCH (t:{nodeType})(()<-[]-()){{0,}}(b:PGIndexableNode)
        WHERE t in currentResults AND (b in fullTextResultNodes OR t in fullTextResultNodes)
    RETURN DISTINCT t
    
    UNION
    
    MATCH (t:{nodeType})(()<-[]-()){{0,}}(x:PGIndexableNode)
    MATCH (x)(()-[]->()){{0,}}(b:PGIndexableNode)
        WHERE t in currentResults AND (b in fullTextResultNodes OR t in fullTextResultNodes)
    RETURN DISTINCT t
}}"""

    query += f"WITH apoc.agg.slice(t, {(page - 1) * page_size}, {(page * page_size) - 1}) as results, count(t) as count\n"
    query += "RETURN {count: count, results: results}"
    return query


query = build_deep_search_query(search_string)

with open("test2listq.cypher", "w") as f:
    f.write(query)

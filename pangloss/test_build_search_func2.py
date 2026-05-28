import re

search_string = "maximilian"


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
    MATCH (t:{nodeType}) WHERE t IN fullTextResultNodes AND NOT t.is_deleted
    RETURN  t
    UNION
    MATCH (t:{nodeType}) WHERE any(no IN fullTextResultNodes WHERE (t.id=no.head_id OR t.head_id=no.head_id))
    RETURN  t
    UNION
    MATCH (x:PGIndexableNode WHERE x in fullTextResultNodes)<-[]-(no:BaseNode)
    MATCH (t:{nodeType} WHERE (t.id=no.head_id OR t.head_id=no.head_id) AND NOT t.is_deleted)
    RETURN t
    UNION
    MATCH (t:BaseNode)<-[]-(ni:BaseNode) WHERE NOT t.is_deleted AND any(no IN fullTextResultNodes WHERE (ni.head_id=no.head_id OR ni.id=no.head_id OR no.id=ni.head_id OR no.head_id=ni.id))
    RETURN t
    }}"""

    for i, term in enumerate(terms[1:], start=1):
        query += f"""
    WITH collect(t) as currentNodes, FT, FT[{i}].t as fullTextResultNodes
    CALL (fullTextResultNodes, currentNodes) {{
    MATCH (t) WHERE NOT t.is_deleted AND t in currentNodes AND t IN fullTextResultNodes
    RETURN  t
    UNION
    MATCH (t:{nodeType}) WHERE t in currentNodes AND any(no IN fullTextResultNodes WHERE (t.id=no.head_id OR t.head_id=no.head_id))   
    RETURN  t
    UNION
    MATCH (x:BaseNode WHERE x in fullTextResultNodes)<-[]-(no:BaseNode)
    MATCH (t:{nodeType} WHERE t in currentNodes AND (t.id=no.head_id OR t.head_id=no.head_id) AND NOT t.is_deleted)
    RETURN t
    UNION
    MATCH (t:BaseNode)<-[]-(ni:PgIndexableNode) WHERE t in currentNodes AND NOT t.is_deleted AND any(no IN fullTextResultNodes WHERE (ni.head_id=no.head_id OR ni.id=no.head_id OR no.id=ni.head_id OR no.head_id=ni.id))
    RETURN t
    }}"""

    query += f"WITH apoc.agg.slice(t, {(page - 1) * page_size}, {(page * page_size) - 1}) as results, count(t) as count\n"
    query += "RETURN {count: count, results: results}"
    return query


query = build_deep_search_query(search_string)

with open("test2listq.cypher", "w") as f:
    f.write(query)

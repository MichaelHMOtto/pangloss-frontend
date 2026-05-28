terms = ["/.*Maximilian.*/"]

query = ""


for i, term in enumerate(terms):
    query += f"""CALL () {{
        CALL db.index.fulltext.queryNodes("ZoteroEntryFullTextIndex", "{term}") YIELD node, score
        CALL (node) {{
            MATCH (target:ZoteroEntry) WHERE target = node AND NOT target.is_deleted
            RETURN target
            UNION
            MATCH (target:ZoteroEntry) WHERE node.head_type = "ZoteroEntry" AND target.id=node.head_id AND NOT target.is_deleted
            RETURN target
            UNION
            MATCH (node)<-[]-(n:BaseNode)
            MATCH (target:ZoteroEntry WHERE n.head_type = "ZoteroEntry" AND target.id=n.head_id AND NOT target.is_deleted)
            RETURN target
        }}
        RETURN collect(target) as target{i}, count(target) as c{i}
    }}
    """


query += f"""
WITH {", ".join(f"target{i}" for i, _ in enumerate(terms))}, apoc.coll.sortMaps( [{", ".join(f"{{t: target{i}, c: c{i}}}" for i, _ in enumerate(terms))}], "^c") as rr
MATCH (result) WHERE result IN {" AND result IN ".join(f"rr[{i}].t" for i, _ in enumerate(terms))}

WITH apoc.agg.slice(result, 0, 50) AS result, count(result) as count
RETURN {{count: count, result: result }}

"""


with open("testlistquery.cypher", "w") as f:
    f.write(query)

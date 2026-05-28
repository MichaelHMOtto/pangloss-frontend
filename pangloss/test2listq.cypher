CALL () { CALL db.index.fulltext.queryNodes("PgIndexableNodeFullTextIndex", "/.*maximilian.*/") YIELD node, score RETURN collect(node) as n0, count(node) as c0 }
CALL () { CALL db.index.fulltext.queryNodes("PgIndexableNodeFullTextIndex", "/.*durch.*/") YIELD node, score RETURN collect(node) as n1, count(node) as c1 }
CALL () { CALL db.index.fulltext.queryNodes("PgIndexableNodeFullTextIndex", "/.*tochter.*/") YIELD node, score RETURN collect(node) as n2, count(node) as c2 }
WITH apoc.coll.sortMaps([{t: n0, c: c0}, {t: n1, c: c1}, {t: n2, c: c2}], "^c") as FT
WITH FT[0].t as fullTextResultNodes, FT
CALL (fullTextResultNodes) {
    MATCH p = (t:ZoteroEntry)(()-[]->()){0,}(b:PGIndexableNode)
        WHERE (b in fullTextResultNodes OR t in fullTextResultNodes)
    RETURN DISTINCT t
    
    UNION
    
    MATCH p = (t:ZoteroEntry)(()<-[]-()){0,}(b:PGIndexableNode)
        WHERE (b in fullTextResultNodes OR t in fullTextResultNodes)
    RETURN DISTINCT t
    
    UNION
    
    MATCH (t:ZoteroEntry)(()<-[]-()){0,}(x:PGIndexableNode)
    MATCH (x)(()-[]->()){0,}(b:PGIndexableNode)
        WHERE (b in fullTextResultNodes OR t in fullTextResultNodes)
    RETURN DISTINCT t
}
WITH FT[1].t as fullTextResultNodes, FT, collect(t) as currentResults
CALL (fullTextResultNodes, currentResults) {
    MATCH (t:ZoteroEntry)(()-[]->()){0,}(b:PGIndexableNode)
        WHERE t in currentResults AND (b in fullTextResultNodes OR t in fullTextResultNodes)
    RETURN DISTINCT t
    
    UNION
    
    MATCH (t:ZoteroEntry)(()<-[]-()){0,}(b:PGIndexableNode)
        WHERE t in currentResults AND (b in fullTextResultNodes OR t in fullTextResultNodes)
    RETURN DISTINCT t
    
    UNION
    
    MATCH (t:ZoteroEntry)(()<-[]-()){0,}(x:PGIndexableNode)
    MATCH (x)(()-[]->()){0,}(b:PGIndexableNode)
        WHERE t in currentResults AND (b in fullTextResultNodes OR t in fullTextResultNodes)
    RETURN DISTINCT t
}WITH FT[1].t as fullTextResultNodes, FT, collect(t) as currentResults
CALL (fullTextResultNodes, currentResults) {
    MATCH (t:ZoteroEntry)(()-[]->()){0,}(b:PGIndexableNode)
        WHERE t in currentResults AND (b in fullTextResultNodes OR t in fullTextResultNodes)
    RETURN DISTINCT t
    
    UNION
    
    MATCH (t:ZoteroEntry)(()<-[]-()){0,}(b:PGIndexableNode)
        WHERE t in currentResults AND (b in fullTextResultNodes OR t in fullTextResultNodes)
    RETURN DISTINCT t
    
    UNION
    
    MATCH (t:ZoteroEntry)(()<-[]-()){0,}(x:PGIndexableNode)
    MATCH (x)(()-[]->()){0,}(b:PGIndexableNode)
        WHERE t in currentResults AND (b in fullTextResultNodes OR t in fullTextResultNodes)
    RETURN DISTINCT t
}WITH apoc.agg.slice(t, 0, 49) as results, count(t) as count
RETURN {count: count, results: results}
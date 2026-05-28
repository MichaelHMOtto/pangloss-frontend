docker run --name dozer-pangloss-test \
    -p 7475:7474 -p 7688:7687 \
    -v $PWD/.dozer-test-pangloss/data:/data \
    -v $PWD/.dozer-test-pangloss/logs:/logs \
    -v $PWD/.dozer-test-pangloss/import:/var/lib/neo4j/import \
    -v $PWD/.dozer-test-pangloss/plugins:/plugins \
    --env NEO4J_AUTH=neo4j/password \
    --env NEO4J_PLUGINS='["apoc"]' \
    --env NEO4J_apoc_export_file_enabled=true \
    --env NEO4J_apoc_import_file_enabled=true \
    --env NEO4J_dbms_security_procedures_unrestricted='*' \
    graphstack/dozerdb:5.26.3.0
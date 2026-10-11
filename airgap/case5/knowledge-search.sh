#!/bin/bash

QUERY="$*"

curl -sG 'http://10.10.1.103:8080/search' \
  --data-urlencode "q=${QUERY}" |
jq -r '
  "=== RAG RETRIEVAL RANKING ===",
  (
    .ranking
    | to_entries[]
    | "\(.key + 1). \(.value.document)  SCORE=\(.value.score)"
  ),
  "",
  "=== SELECTED KNOWLEDGE ===",
  (
    if .result == null then
      "NO_RELEVANT_KNOWLEDGE"
    else
      "SOURCE: \(.result.document)\nSCORE: \(.result.score)\n\n\(.result.content)"
    end
  )
'

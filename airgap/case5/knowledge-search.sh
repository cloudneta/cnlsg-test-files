#!/bin/bash

QUERY="$*"

curl -sG 'http://10.10.1.103:8080/search' \
  --data-urlencode "q=${QUERY}" |
jq -r '
  if .result == null then
    "NO_RELEVANT_KNOWLEDGE"
  else
    "SOURCE: " + .result.document +
    "\nSCORE: " + (.result.score|tostring) +
    "\n\n" + .result.content
  end
'

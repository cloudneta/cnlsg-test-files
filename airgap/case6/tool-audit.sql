SELECT
  s."startTime" AS time,
  s.request_id,
  t.event->>'name' AS tool_name,
  LEFT(t.event->'input'->>'command', 150) AS tool_input,
  LEFT(r.event->>'content', 150) AS tool_result,
  COALESCE((r.event->>'is_error')::boolean, false) AS is_error
FROM "LiteLLM_SpendLogs" s
CROSS JOIN LATERAL jsonb_path_query(
  s.proxy_server_request,
  '$.messages[*].content[*] ? (@.type == "tool_use")'
) AS t(event)
LEFT JOIN LATERAL (
  SELECT x.event
  FROM jsonb_path_query(
    s.proxy_server_request,
    '$.messages[*].content[*] ? (@.type == "tool_result")'
  ) AS x(event)
  WHERE x.event->>'tool_use_id' = t.event->>'id'
  LIMIT 1
) AS r ON true
WHERE $__timeFilter(s."startTime")
ORDER BY s."startTime" DESC
LIMIT 100

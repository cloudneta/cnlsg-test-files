SELECT
  s."startTime" AS time,
  s.request_id,
  (
    SELECT LEFT(
      CASE
        WHEN jsonb_typeof(m.value->'content') = 'string'
          THEN m.value->>'content'
        WHEN jsonb_typeof(m.value->'content') = 'array'
          THEN (
            SELECT b.value->>'text'
            FROM jsonb_array_elements(m.value->'content') AS b(value)
            WHERE b.value->>'type' = 'text'
              AND b.value->>'text' NOT LIKE '<system-reminder>%'
            LIMIT 1
          )
      END, 150
    )
    FROM jsonb_array_elements(s.proxy_server_request->'messages')
         WITH ORDINALITY AS m(value, seq)
    WHERE m.value->>'role' = 'user'
    ORDER BY m.seq DESC
    LIMIT 1
  ) AS user_prompt,
  LEFT(s.response #>> '{choices,0,message,content}', 150) AS llm_response,
  s.prompt_tokens,
  s.completion_tokens,
  s.total_tokens
FROM "LiteLLM_SpendLogs" s
WHERE $__timeFilter(s."startTime")
  AND (
    EXISTS (
      SELECT 1
      FROM jsonb_array_elements(
        CASE
          WHEN jsonb_typeof(s.proxy_server_request->'messages') = 'array'
          THEN s.proxy_server_request->'messages'
          ELSE '[]'::jsonb
        END
      ) AS m(value)
      WHERE m.value->>'role' = 'user'
        AND (
          jsonb_typeof(m.value->'content') = 'string'
          OR jsonb_path_exists(
            m.value,
            '$.content[*] ? (@.type == "text")'
          )
        )
    )
    OR s.response #>> '{choices,0,message,content}' IS NOT NULL
  )
ORDER BY s."startTime" DESC
LIMIT 100

-- Normalize multi-word card_type separators in existing rows.
--
-- Bandai's site occasionally returns a fullwidth middle dot instead of a space
-- (e.g. "UNIT・TOKEN" vs "UNIT TOKEN"), which splits one conceptual type into
-- two distinct strings and makes token detection / deck legality miss the odd
-- row out. The scraper and export now fold these dots to a space; this cleans
-- the rows that were stored before that fix. Idempotent — safe to re-run.
--
-- Covers the three dot variants seen in Bandai data:
--   ・ U+30FB  (katakana middle dot)
--   ･ U+FF65  (halfwidth katakana middle dot)
--   · U+00B7  (middle dot)

UPDATE cards
SET card_type = btrim(regexp_replace(
        translate(card_type, '・･·', '   '),  -- each dot -> a space
        '\s+', ' ', 'g'                        -- collapse repeats
    ))
WHERE card_type ~ '[・･·]';

-- Verify afterward:
--   SELECT DISTINCT card_type FROM cards ORDER BY 1;

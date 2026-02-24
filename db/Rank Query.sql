WITH ranked AS (
    SELECT
        ROW_NUMBER() OVER (ORDER BY points DESC) AS rank,
        user_id,
        username,
        points
    FROM (
        SELECT
            u.user_id,
            u.username,
            SUM(c.points) AS points
        FROM assignments AS a
        JOIN users AS u ON a.completed_by = u.user_id
        JOIN chores AS c ON a.chore_id = c.chore_id
        WHERE a.status = 'Complete'
          AND date(a.date_completed) >= date('now', '-' || ((strftime('%w','now') + 2) % 7) || ' day')
        GROUP BY u.user_id, u.username
    )
)
SELECT
    me.rank,
    me.username,
    me.points,
    above.points AS points_above,
    CASE 
        WHEN above.points IS NULL THEN 0 
        ELSE above.points - me.points 
    END AS points_needed_to_overtake,
	below.points as points_below,
	    CASE 
        WHEN below.points IS NULL THEN 0 
        ELSE me.points - below.points
    END AS points_ahead_by
FROM ranked AS me
LEFT JOIN ranked AS above
    ON above.rank = me.rank - 1
LEFT JOIN ranked AS below
    ON below.rank = me.rank + 1
WHERE me.user_id = 4;

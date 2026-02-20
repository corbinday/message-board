update Board
filter .id = <uuid>$board_id
set { last_connected_at := datetime_of_statement() };

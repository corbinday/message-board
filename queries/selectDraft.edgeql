with
  user := assert_single(
    select User
    filter assert_single(.identity = global ext::auth::ClientTokenIdentity)
  )
select DraftGraphic {
  id,
  binary,
  frames,
  frame_delay_ms,
  size,
  updated_at
}
filter .creator = user
  and (
    (.active_board.id = <optional uuid>$board_id) if exists <optional uuid>$board_id
    else not exists .active_board
  )
limit 1

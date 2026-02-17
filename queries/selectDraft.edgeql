with
  user := assert_single(
    select User
    filter assert_single(.identity = global ext::auth::ClientTokenIdentity)
  )
select DraftGraphic {
  id,
  binary,
  frames,
  fps,
  size,
  updated_at
}
filter .creator = user
  and (
    (.id = <optional uuid>$draft_id) if exists <optional uuid>$draft_id else
    (
      (.active_board.id = <optional uuid>$board_id) if exists <optional uuid>$board_id
      else not exists .active_board
    )
  )
limit 1
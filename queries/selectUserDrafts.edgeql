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
  created_at,
  updated_at,
  active_board: { id, name }
}
filter .creator = user
order by .updated_at desc

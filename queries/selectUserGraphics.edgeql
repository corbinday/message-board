with
  user := assert_single(
    select User
    filter assert_single(.identity = global ext::auth::ClientTokenIdentity)
  )
select g := PixelGraphic {
  id,
  binary,
  size,
  created_at,
  updated_at,
  frames := [is PixelAnimation].frames ?? <int16>1,
  frame_delay_ms := [is PixelAnimation].frame_delay_ms ?? <int16>100
}
filter g.creator = user
  and not (g is DraftGraphic)
  and not (g is Avatar)
  and not exists (select Message filter .graphic = g)
order by g.updated_at desc

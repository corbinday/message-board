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
  fps := [is PixelAnimation].fps ?? <int16>10
}
filter g.creator = user
  and not (g is DraftGraphic)
  and not (g is Avatar)
  and not exists (select Message filter .graphic = g)
order by g.updated_at desc

with
  user := assert_single(
    select User
    filter assert_single(.identity = global ext::auth::ClientTokenIdentity)
  ),
  source := assert_single(
    select PixelGraphic
    filter .id = <uuid>$graphic_id
  )
insert DraftGraphic {
  creator := user,
  binary := source.binary,
  size := source.size,
  frames := source[is PixelAnimation].frames ?? 1,
  frame_delay_ms := source[is PixelAnimation].frame_delay_ms ?? 100
}

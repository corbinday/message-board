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
  fps := source[is PixelAnimation].fps ?? 10
}

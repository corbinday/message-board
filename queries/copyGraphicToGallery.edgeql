with
  user := assert_single(
    select User
    filter global ext::auth::ClientTokenIdentity in .identity
  ),
  source := assert_single(
    select PixelGraphic
    filter .id = <uuid>$graphic_id
  ),
  is_animation := source is PixelAnimation,
  new_graphic := (
    insert PixelAnimation {
      binary := source.binary,
      frames := source[is PixelAnimation].frames ?? <int16>1,
      fps := source[is PixelAnimation].fps ?? <int16>10,
      size := source.size,
      creator := user
    }
  ) if is_animation else (
    insert StaticImage {
      binary := source.binary,
      size := source.size,
      creator := user
    }
  )
select new_graphic { id }

with
  user := assert_single(
    select User
    filter assert_single(.identity = global ext::auth::ClientTokenIdentity)
  )
delete PixelGraphic
filter .id = <uuid>$graphic_id
  and .creator = user

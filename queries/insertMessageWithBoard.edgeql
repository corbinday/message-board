with
  user := assert_single(
    select User
    filter global ext::auth::ClientTokenIdentity in .identity
  ),
  graphic := assert_single(
    select PixelGraphic
    filter .id = <uuid>$graphic_id
  )
insert Message {
  graphic := graphic,
  sender := user,
  recipient := (select User filter .id = <optional uuid>$recipient_id)
}

with
  user := assert_single(
    select User
    filter assert_single(.identity = global ext::auth::ClientTokenIdentity)
  ),
  new_graphic := (
    insert StaticImage {
      binary := <bytes>$data,
      size := <BoardType>$size,
      creator := user
    }
  )
insert Message {
  graphic := new_graphic,
  sender := user,
  recipient := (select User filter .id = <optional uuid>$recipient_id)
}

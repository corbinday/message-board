with
  user := assert_single(
    select User
    filter assert_single(.identity = global ext::auth::ClientTokenIdentity)
  )
insert Avatar {
  binary := <bytes>$data,
  size := BoardType.Stellar,
  creator := user
}

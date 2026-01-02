insert Board {
  boardType := select <BoardType>$board_type,
  owner := select assert_single(
    select User {*}
    filter assert_single(.identity = global ext::auth::ClientTokenIdentity)
  )
}
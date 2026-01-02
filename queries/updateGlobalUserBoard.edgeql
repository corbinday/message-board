with
  board := select assert_single(
    select Board {*}
    filter .id = <uuid>$board_id and assert_single(
      .owner.identity = global ext::auth::ClientTokenIdentity
    )
  ),
  updated_board := (
    update board
    set {
      boardType := <optional BoardType>$board_type ?? .boardType,
      name := <optional str>$name ?? .name,
      secret_key_hash := <optional str>$secret_key_hash ?? .secret_key_hash
    }
  )
select updated_board{*};
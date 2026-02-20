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
      ota_updates_enabled := <bool>$ota_updates_enabled
    }
  )
select updated_board{*};

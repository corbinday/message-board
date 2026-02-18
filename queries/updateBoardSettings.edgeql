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
      display_mode := <optional DisplayMode>$display_mode ?? .display_mode,
      auto_rotate := <optional bool>$auto_rotate ?? .auto_rotate,
      brightness := <optional float32>$brightness ?? .brightness
    }
  )
select updated_board{*};

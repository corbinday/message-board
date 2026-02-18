with
  board := assert_single(
    select Board
    filter .id = <uuid>$board_id and assert_single(
      .owner.identity = global ext::auth::ClientTokenIdentity
    )
  ),
  new_profile := (
    insert BoardWifiProfile {
      ssid := <str>$ssid,
      password := <str>$password,
      priority := <optional int16>$priority ?? 0
    }
  ),
  updated_board := (
    update board
    set {
      wifi_profiles += new_profile
    }
  )
select new_profile { id, ssid, priority, created_at };

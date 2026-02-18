with
  board := assert_single(
    select Board
    filter .id = <uuid>$board_id and assert_single(
      .owner.identity = global ext::auth::ClientTokenIdentity
    )
  )
select board.wifi_profiles {
  id,
  ssid,
  priority,
  created_at
}
order by .priority desc then .created_at desc;

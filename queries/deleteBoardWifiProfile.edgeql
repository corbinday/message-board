with
  board := assert_single(
    select Board
    filter .id = <uuid>$board_id and assert_single(
      .owner.identity = global ext::auth::ClientTokenIdentity
    )
  ),
  profile := assert_single(
    select BoardWifiProfile
    filter .id = <uuid>$profile_id and board in .<wifi_profiles[is Board]
  )
delete profile;

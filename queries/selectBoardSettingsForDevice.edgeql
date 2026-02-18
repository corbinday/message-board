select Board {
  id,
  boardType,
  display_mode,
  auto_rotate,
  brightness,
  wifi_profiles: {
    ssid,
    password,
    priority
  } order by .priority desc,
  owner_id := .owner.id
}
filter .id = <uuid>$board_id
limit 1

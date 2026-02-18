select Board {
  id,
  boardType,
  display_mode,
  auto_rotate,
  brightness,
  owner_id := .owner.id
}
filter .id = <uuid>$board_id
limit 1

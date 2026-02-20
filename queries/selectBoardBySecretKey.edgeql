select Board {
  id,
  boardType,
  name,
  secret_key_hash,
  ota_updates_enabled,
  owner_id := .owner.id
}
filter .id = <uuid>$board_id
limit 1

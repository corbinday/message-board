select Board {
  id,
  boardType,
  name,
  secret_key_hash,
  owner_id := .owner.id
}
filter .id = <uuid>$board_id
limit 1

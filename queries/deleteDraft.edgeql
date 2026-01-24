with
  user := assert_single(
    select User
    filter assert_single(.identity = global ext::auth::ClientTokenIdentity)
  )
delete DraftGraphic
filter .id = <uuid>$draft_id
  and .creator = user

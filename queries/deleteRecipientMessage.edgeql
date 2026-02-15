with
  user := assert_single(
    select User
    filter global ext::auth::ClientTokenIdentity in .identity
  )
delete Message
filter .id = <uuid>$message_id
  and .recipient = user

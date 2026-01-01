select assert_exists(
  assert_single(
    select global ext::auth::ClientTokenIdentity { * }
  )
)